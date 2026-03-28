#!/usr/bin/env python3
"""
Process CDC tick-borne illness data (Lyme disease) into a county-level score grid.

Sources:
  - CDC Lyme Disease Case Counts by County, 2001-2022
    https://www.cdc.gov/lyme/resources/datasurveillance/LD_Case_Counts_by_County_2022.csv
  - Census Bureau County Population Estimates 2020-2023
    https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv

Score:
  - Average annual Lyme cases per 100k population (2018-2022)
  - 0 cases/100k  → score 1.0 (best)
  - 50+ cases/100k → score 0.0 (worst)
  - Counties not in CDC data (low-incidence states) get a near-zero rate
"""

import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, download_file, ensure_dirs, download_county_shapes

CDC_LYME_URL = (
    "https://www.cdc.gov/lyme/resources/datasurveillance/LD_Case_Counts_by_County_2022.csv"
)
CENSUS_POP_URL = (
    "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/"
    "co-est2023-alldata.csv"
)
# Pre-restructuring estimates (2010-2020) cover old CT county FIPS codes
CENSUS_POP_2020_URL = (
    "https://www2.census.gov/programs-surveys/popest/datasets/2010-2020/counties/totals/"
    "co-est2020-alldata.csv"
)

# 5-year average window to smooth year-to-year noise
YEARS = [2018, 2019, 2020, 2021, 2022]


def load_lyme_cases() -> pd.DataFrame:
    """Load CDC Lyme disease case counts and compute 5-year average rate."""
    csv_path = RAW_DIR / "LD_Case_Counts_by_County_2022.csv"
    download_file(CDC_LYME_URL, csv_path)

    df = pd.read_csv(csv_path, encoding="latin-1")
    # Normalize column names to lowercase for consistent access
    df.columns = [c.lower().strip() for c in df.columns]
    print(f"  Loaded {len(df)} county rows from CDC Lyme data")

    # Build 5-digit FIPS: stcode (state numeric, 1-2 digits) + ctycode (county, 1-3 digits)
    df["stcode"] = df["stcode"].astype(str).str.strip().str.zfill(2)
    df["ctycode"] = df["ctycode"].astype(str).str.strip().str.zfill(3)
    df["FIPS"] = df["stcode"] + df["ctycode"]

    # Find available year columns (normalized to lowercase like "cases2018")
    year_cols = [f"cases{y}" for y in YEARS if f"cases{y}" in df.columns]
    if not year_cols:
        raise ValueError(f"No case columns found for years {YEARS}. Available: {list(df.columns)}")
    print(f"  Using case columns: {year_cols}")

    for col in year_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["avg_cases_annual"] = df[year_cols].sum(axis=1) / len(year_cols)
    return df[["FIPS", "avg_cases_annual"]].copy()


def load_county_population() -> pd.DataFrame:
    """Load Census Bureau county population estimates.

    Uses 2023 file as primary source; falls back to 2020 file for counties
    missing from 2023 (e.g. Connecticut, which restructured its county system).
    """
    def _load(url: str, path: Path, pop_col: str) -> pd.DataFrame:
        download_file(url, path)
        df = pd.read_csv(path, dtype={"STATE": str, "COUNTY": str}, encoding="latin-1")
        df = df[df["COUNTY"] != "000"].copy()
        df["FIPS"] = df["STATE"].str.zfill(2) + df["COUNTY"].str.zfill(3)
        return df[["FIPS", pop_col]].rename(columns={pop_col: "population"})

    pop = _load(CENSUS_POP_URL, RAW_DIR / "co-est2023-alldata.csv", "POPESTIMATE2022")
    fallback = _load(CENSUS_POP_2020_URL, RAW_DIR / "co-est2020-alldata.csv", "POPESTIMATE2019")

    # Fill in counties missing from 2023 file (mainly CT old counties)
    missing_fips = set(fallback["FIPS"]) - set(pop["FIPS"])
    if missing_fips:
        extra = fallback[fallback["FIPS"].isin(missing_fips)]
        pop = pd.concat([pop, extra], ignore_index=True)
        print(f"  Added {len(extra)} counties from 2020 fallback (e.g. old CT counties)")

    print(f"  Loaded {len(pop)} county population estimates")
    return pop


def main():
    ensure_dirs()
    print("=== Processing Tick-Borne Illness (CDC Lyme Disease) ===")

    lyme = load_lyme_cases()
    pop = load_county_population()
    counties = download_county_shapes()

    # Merge cases + population — inner join drops counties lacking population data
    # (avoids absurd rates for the handful of counties missing from Census file)
    merged = lyme.merge(pop, on="FIPS", how="inner")
    merged["avg_cases_annual"] = merged["avg_cases_annual"].fillna(0)

    # Rate per 100k per year (5-year average)
    merged["lyme_rate"] = (merged["avg_cases_annual"] / merged["population"]) * 100_000
    merged["lyme_rate"] = merged["lyme_rate"].clip(0, 500)  # cap at 500/100k (safeguard)
    merged["FIPS"] = merged["FIPS"].str.zfill(5)

    print(f"  Lyme rate range: {merged['lyme_rate'].min():.1f} – {merged['lyme_rate'].max():.1f} per 100k/yr")
    print(f"  Median rate: {merged['lyme_rate'].median():.2f}")

    # Join with county geometries (counties has GEOID, merged has FIPS — same 5-digit value)
    gdf = counties.merge(merged[["FIPS", "lyme_rate"]], left_on="GEOID", right_on="FIPS", how="left")
    gdf["lyme_rate"] = gdf["lyme_rate"].fillna(0).astype(np.float32)
    gdf["geometry"] = gdf["geometry"].simplify(0.005, preserve_topology=True)
    print(f"  Matched {gdf['lyme_rate'].notna().sum()} / {len(gdf)} counties")

    # Write GeoJSON
    geojson_path = OUTPUT_DIR / "ticks.geojson"
    gdf[["GEOID", "NAME", "lyme_rate", "geometry"]].to_file(geojson_path, driver="GeoJSON")
    print(f"  Written: {geojson_path}")

    # PMTiles
    pmtiles_path = OUTPUT_DIR / "ticks.pmtiles"
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12", "-Z", "3",
                "-l", "ticks",
                "--coalesce-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--force",
                str(geojson_path),
            ],
            check=True,
        )
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found, skipping PMTiles")

    print("Done!")


if __name__ == "__main__":
    main()
