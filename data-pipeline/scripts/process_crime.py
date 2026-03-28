#!/usr/bin/env python3
"""
Download and process violent crime data into vector PMTiles and a score grid.

Source: County Health Rankings (derived from FBI UCR)
- Annual analytic data with violent crime rate per 100,000 population by county.

Steps:
1. Download County Health Rankings analytic data CSV
2. Extract violent crime rate by county FIPS
3. Join with Census county boundaries
4. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, download_file, ensure_dirs, download_county_shapes

# County Health Rankings analytic data
# The CSV has a header row, then a row per county with many health metrics.
# Column "Violent Crime Rate raw value" contains the rate per 100k.
CHR_URL = "https://www.countyhealthrankings.org/sites/default/files/media/document/analytic_data2024.csv"


def download_crime_data() -> pd.DataFrame:
    """Download County Health Rankings and extract violent crime rates."""
    csv_path = RAW_DIR / "chr_analytic_2024.csv"
    download_file(CHR_URL, csv_path)

    print("  Loading County Health Rankings data...")
    # Row 0 = human-readable header, row 1 = machine variable names, row 2+ = data
    # Use header=0, skip row 1 (machine names)
    df = pd.read_csv(csv_path, header=0, skiprows=[1], low_memory=False)

    # Find FIPS column
    fips_col = None
    for col in df.columns:
        if "5-digit" in col.lower() and "fips" in col.lower():
            fips_col = col
            break
    if fips_col is None:
        for col in df.columns:
            if "fips" in col.lower():
                fips_col = col
                break
    if fips_col is None:
        raise ValueError(f"No FIPS column found. Columns: {list(df.columns)[:20]}")

    # Find homicide/violent crime rate column
    crime_col = None
    for col in df.columns:
        cl = col.lower()
        if "violent crime" in cl and "raw value" in cl:
            crime_col = col
            break
    if crime_col is None:
        for col in df.columns:
            cl = col.lower()
            if "homicide" in cl and "raw value" in cl:
                crime_col = col
                break
    if crime_col is None:
        print("  Available columns containing 'homicide' or 'crime':")
        for c in df.columns:
            if "homicide" in c.lower() or "crime" in c.lower():
                print(f"    {c}")
        raise ValueError("Could not find crime/homicide rate column")

    print(f"  Using FIPS column: {fips_col}")
    print(f"  Using crime column: {crime_col}")

    result = df[[fips_col, crime_col]].copy()
    result.columns = ["FIPS", "crime_rate"]
    result["FIPS"] = result["FIPS"].astype(str).str.zfill(5)

    # Drop rows without crime data and non-county rows (state summaries have 3-digit FIPS)
    result = result.dropna(subset=["crime_rate"])
    result = result[result["FIPS"].str.len() == 5]
    result["crime_rate"] = pd.to_numeric(result["crime_rate"], errors="coerce")
    result = result.dropna(subset=["crime_rate"])

    print(f"  Found {len(result)} counties with violent crime data")
    print(f"  Crime rate range: {result['crime_rate'].min():.0f} - {result['crime_rate'].max():.0f} per 100k")
    return result


def main():
    ensure_dirs()
    print("=== Processing Violent Crime Data ===")

    crime = download_crime_data()
    counties = download_county_shapes()

    # Join crime data to county geometries
    print("  Joining crime data to county geometries...")
    merged = counties.merge(crime, left_on="GEOID", right_on="FIPS", how="inner")
    print(f"  Matched {len(merged)} counties")

    # Simplify geometries
    print("  Simplifying geometries...")
    merged["geometry"] = merged["geometry"].simplify(0.005, preserve_topology=True)

    # Write GeoJSON
    geojson_path = OUTPUT_DIR / "crime.geojson"
    print("  Writing GeoJSON...")
    merged[["GEOID", "NAME", "crime_rate", "geometry"]].to_file(geojson_path, driver="GeoJSON")

    # Convert to PMTiles
    pmtiles_path = OUTPUT_DIR / "crime.pmtiles"
    print("  Running tippecanoe...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12",
                "-Z", "3",
                "-l", "crime",
                "--coalesce-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--force",
                str(geojson_path),
            ],
            check=True,
        )
        print(f"  PMTiles written: {pmtiles_path}")
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found.")

    print("Done!")


if __name__ == "__main__":
    main()
