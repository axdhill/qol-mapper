#!/usr/bin/env python3
"""
Download and process drought/water availability data into vector PMTiles.

Source: US Drought Monitor - county-level comprehensive statistics.
- Weekly drought severity data by county
- Categories: None, D0 (Abnormally Dry), D1 (Moderate), D2 (Severe),
  D3 (Extreme), D4 (Exceptional)

Steps:
1. Download current Drought Monitor county-level statistics
2. Compute composite drought score per county
3. Join with Census county boundaries
4. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from utils import (
    OUTPUT_DIR, RAW_DIR, copy_to_public, download_file, ensure_dirs,
    download_county_shapes, CONUS_STATES,
)

# US Drought Monitor API
# Requires specific state/FIPS + date range. We query state-by-state for the most recent week.
DM_API_BASE = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"


def download_drought_data() -> pd.DataFrame:
    """Download US Drought Monitor county statistics via state-by-state API queries."""
    import requests
    from datetime import datetime, timedelta

    csv_path = RAW_DIR / "drought_county.csv"

    if not csv_path.exists():
        print("  Downloading US Drought Monitor county data (state by state)...")

        # Use a recent date range (last 2 weeks to capture the latest report)
        end = datetime.now()
        start = end - timedelta(days=14)
        start_str = start.strftime("%-m/%-d/%Y")
        end_str = end.strftime("%-m/%-d/%Y")

        all_dfs = []
        state_abbrevs = sorted(CONUS_STATES - {"DC"})  # DC doesn't have counties in DM

        for i, state in enumerate(state_abbrevs):
            url = f"{DM_API_BASE}?aoi={state}&startdate={start_str}&enddate={end_str}&statisticsType=1"
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                # API returns CSV, not JSON
                from io import StringIO
                state_df = pd.read_csv(StringIO(resp.text))
                if len(state_df) > 0:
                    all_dfs.append(state_df)
                if (i + 1) % 10 == 0:
                    total = sum(len(d) for d in all_dfs)
                    print(f"    Queried {i + 1}/{len(state_abbrevs)} states ({total} records)...")
            except Exception as e:
                print(f"    Warning: Failed for {state}: {e}")
                continue

        if not all_dfs:
            print("  No drought data retrieved from API")
            return pd.DataFrame({"FIPS": [], "drought_score": []})

        df = pd.concat(all_dfs, ignore_index=True)
        df.to_csv(csv_path, index=False)
        print(f"  Downloaded {len(df)} county drought records")
    else:
        print("  Already have drought_county.csv")

    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  Loaded {len(df)} drought records")
    print(f"  Columns: {list(df.columns)}")

    # Find FIPS column
    fips_col = None
    for col in df.columns:
        if col.upper() in ("FIPS", "COUNTYFIPS", "COUNTY_FIPS"):
            fips_col = col
            break
    if fips_col is None:
        for col in df.columns:
            if "fips" in col.lower():
                fips_col = col
                break

    if fips_col is None:
        print("  Could not find FIPS column")
        return pd.DataFrame({"FIPS": [], "drought_score": []})

    df["FIPS"] = df[fips_col].astype(str).str.zfill(5)

    # Get most recent date's data
    date_col = None
    for col in df.columns:
        if "date" in col.lower() or "mapdate" in col.lower():
            date_col = col
            break

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        latest = df[date_col].max()
        df = df[df[date_col] == latest]
        print(f"  Using data from: {latest}")

    # Find drought severity columns (D0-D4 and None)
    d_cols = {}
    for d in ["None", "D0", "D1", "D2", "D3", "D4"]:
        for col in df.columns:
            if col.strip() == d:
                d_cols[d] = col
                break

    if len(d_cols) < 3:
        print(f"  Found drought columns: {d_cols}")
        print("  Not enough drought severity columns")
        return pd.DataFrame({"FIPS": [], "drought_score": []})

    # Compute drought score: weighted by severity
    # None=1.0, D0=0.8, D1=0.6, D2=0.4, D3=0.2, D4=0.0
    weights = {"None": 1.0, "D0": 0.8, "D1": 0.6, "D2": 0.4, "D3": 0.2, "D4": 0.0}
    score = pd.Series(0.0, index=df.index)
    total_pct = pd.Series(0.0, index=df.index)

    for severity, w in weights.items():
        if severity in d_cols:
            pct = pd.to_numeric(df[d_cols[severity]], errors="coerce").fillna(0)
            score += pct * w
            total_pct += pct

    # Normalize to 0-1
    df["drought_score"] = (score / total_pct.clip(lower=1)).clip(0, 1)

    result = df[["FIPS", "drought_score"]].drop_duplicates(subset="FIPS")
    result = result[result["FIPS"].str.len() == 5]
    print(f"  Computed drought scores for {len(result)} counties")
    print(f"  Score range: {result['drought_score'].min():.2f} - {result['drought_score'].max():.2f}")
    return result


def main():
    ensure_dirs()
    print("=== Processing Water Quality / Drought Data ===")

    drought = download_drought_data()

    if len(drought) == 0:
        print("  No drought data available. Skipping.")
        return

    counties = download_county_shapes()

    # Join drought data to county geometries
    print("  Joining drought data to county geometries...")
    merged = counties.merge(drought, left_on="GEOID", right_on="FIPS", how="left")
    # Counties without drought data get a neutral score
    merged["drought_score"] = merged["drought_score"].fillna(0.7)
    print(f"  {len(merged)} counties total, {merged['drought_score'].notna().sum()} with data")

    # Simplify geometries
    print("  Simplifying geometries...")
    merged["geometry"] = merged["geometry"].simplify(0.005, preserve_topology=True)

    merged["drought_score"] = merged["drought_score"].round(3)

    # Write GeoJSON
    geojson_path = OUTPUT_DIR / "water-quality.geojson"
    print("  Writing GeoJSON...")
    merged[["GEOID", "NAME", "drought_score", "geometry"]].to_file(geojson_path, driver="GeoJSON")

    # Convert to PMTiles
    pmtiles_path = OUTPUT_DIR / "water-quality.pmtiles"
    print("  Running tippecanoe...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12", "-Z", "3",
                "-l", "water_quality",
                "--coalesce-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--force",
                str(geojson_path),
            ],
            check=True,
        )
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found.")

    print("Done!")


if __name__ == "__main__":
    main()
