#!/usr/bin/env python3
"""
Download and process Zillow ZHVI and Census ZCTA boundaries into vector PMTiles.

Source:
- Zillow Home Value Index (ZHVI) by zip code:
  https://www.zillow.com/research/data/
- Census ZCTA boundaries (for polygon geometries):
  https://www.census.gov/cgi-bin/geo/shapefiles/

Steps:
1. Download Zillow ZHVI CSV (median home values by zip)
2. Download Census ZCTA shapefile (zip code polygons)
3. Join ZHVI to ZCTA geometries
4. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import json
import subprocess
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs

# Zillow ZHVI All Homes (SFR & Condo) - Smoothed, Seasonally Adjusted, by Zip Code
ZHVI_URL = "https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"

# Census 2020 ZCTA boundaries (shapefile)
ZCTA_URL = "https://www2.census.gov/geo/tiger/TIGER2020/ZCTA520/tl_2020_us_zcta520.zip"


def download_zhvi(raw_dir: Path) -> pd.DataFrame:
    """Download and load Zillow ZHVI data."""
    csv_path = raw_dir / "zillow_zhvi.csv"
    if not csv_path.exists():
        print("  Downloading Zillow ZHVI...")
        resp = requests.get(ZHVI_URL, timeout=300)
        resp.raise_for_status()
        with open(csv_path, "wb") as f:
            f.write(resp.content)
    else:
        print("  Already have zillow_zhvi.csv")

    print("  Loading ZHVI data...")
    df = pd.read_csv(csv_path, dtype={"RegionName": str})

    # Get the most recent month's value
    date_cols = [c for c in df.columns if c.startswith("20")]
    if not date_cols:
        raise ValueError("No date columns found in ZHVI data")

    latest_col = sorted(date_cols)[-1]
    print(f"  Using latest data: {latest_col}")

    result = df[["RegionName", "RegionType", "StateName", latest_col]].copy()
    result.columns = ["zip", "region_type", "state", "median_price"]
    result = result.dropna(subset=["median_price"])
    result["zip"] = result["zip"].str.zfill(5)
    result["median_price"] = result["median_price"].astype(float).round(0)

    print(f"  Found {len(result)} zip codes with home prices")
    return result


def download_zcta_shapes(raw_dir: Path) -> gpd.GeoDataFrame:
    """Download Census ZCTA shapefile."""
    zip_path = raw_dir / "zcta520.zip"
    shp_dir = raw_dir / "zcta520"

    if not shp_dir.exists():
        if not zip_path.exists():
            print("  Downloading Census ZCTA boundaries (~800MB)...")
            resp = requests.get(ZCTA_URL, timeout=600, stream=True)
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
        else:
            print("  Already have zcta520.zip")

        print("  Extracting ZCTA shapefile...")
        shp_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(shp_dir)
    else:
        print("  Already have ZCTA shapefile")

    # Find the .shp file
    shp_files = list(shp_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found in ZCTA download")

    print("  Loading ZCTA geometries...")
    gdf = gpd.read_file(shp_files[0])
    # ZCTA5CE20 is the zip code column
    gdf = gdf.rename(columns={"ZCTA5CE20": "zip"})
    gdf = gdf[["zip", "geometry"]]

    # Filter to approximate CONUS bounds
    gdf = gdf.cx[-126:-66, 24:50]
    print(f"  Loaded {len(gdf)} ZCTA polygons in CONUS")
    return gdf


def main():
    ensure_dirs()
    print("=== Processing Home Price Data ===")

    zhvi = download_zhvi(RAW_DIR)
    zcta = download_zcta_shapes(RAW_DIR)

    # Join prices to geometries
    print("  Joining prices to ZCTA polygons...")
    merged = zcta.merge(zhvi[["zip", "median_price", "state"]], on="zip", how="inner")
    print(f"  Matched {len(merged)} zip codes with both geometry and price data")

    # Simplify geometries for smaller tile output
    print("  Simplifying geometries...")
    merged["geometry"] = merged["geometry"].simplify(0.001, preserve_topology=True)

    # Write GeoJSON
    geojson_path = OUTPUT_DIR / "home-prices.geojson"
    print("  Writing GeoJSON...")
    merged.to_file(geojson_path, driver="GeoJSON")
    print(f"  Written: {geojson_path}")

    # Convert to PMTiles
    pmtiles_path = OUTPUT_DIR / "home-prices.pmtiles"
    print("  Running tippecanoe...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12",
                "-Z", "4",
                "-l", "home_prices",
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
