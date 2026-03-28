#!/usr/bin/env python3
"""
Download and process transit/walkability data into vector PMTiles and a score grid.

Source: EPA Smart Location Database (SLD) v3.0
- Census block group-level walkability and transit metrics
- NatWalkInd (National Walkability Index, 1-20 scale)

Steps:
1. Download EPA SLD CSV
2. Extract walkability index by block group GEOID
3. Join with Census block group boundaries
4. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import subprocess
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, download_file, ensure_dirs, CONUS_STATE_FIPS

# EPA Smart Location Database v3.0
SLD_URL = "https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip"

# Census 2020 block group boundaries (cartographic, 500k)
BG_SHAPES_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_bg_500k.zip"


def download_sld_data() -> pd.DataFrame:
    """Download EPA Smart Location Database."""
    zip_path = RAW_DIR / "SmartLocationDatabaseV3.zip"
    csv_path = RAW_DIR / "SmartLocationDatabaseV3.csv"

    if not csv_path.exists():
        download_file(SLD_URL, zip_path)
        print("  Extracting SLD data...")
        with zipfile.ZipFile(zip_path) as zf:
            # Find CSV inside zip (may be nested in a subdirectory)
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if csv_names:
                # Extract the CSV
                target = csv_names[0]
                print(f"    Found CSV: {target}")
                zf.extract(target, RAW_DIR)
                extracted = RAW_DIR / target
                if extracted != csv_path:
                    extracted.rename(csv_path)
            else:
                # No CSV - may contain geodatabase; extract all and convert
                print(f"    No CSV found in zip. Contents: {zf.namelist()[:10]}")
                zf.extractall(RAW_DIR)
                # Try to find the extracted geodatabase
                gdb_dirs = list(RAW_DIR.glob("*.gdb"))
                if gdb_dirs:
                    import geopandas as gpd_
                    print(f"    Reading geodatabase: {gdb_dirs[0]}")
                    gdf = gpd_.read_file(gdb_dirs[0])
                    gdf.to_csv(csv_path, index=False)
                else:
                    raise FileNotFoundError("No CSV or geodatabase found in SLD zip")
    else:
        print("  Already have SLD CSV")

    print("  Loading SLD data (this may take a moment)...")
    # Only load columns we need to save memory
    usecols = ["GEOID20", "STATEFP", "NatWalkInd", "D4A", "D3BPO4", "Ac_Total"]
    try:
        df = pd.read_csv(csv_path, usecols=usecols, dtype={"GEOID20": str, "STATEFP": str})
    except (ValueError, KeyError):
        # Column names may differ; load all and find
        df = pd.read_csv(csv_path, dtype=str, low_memory=False)
        print(f"  Available columns: {list(df.columns)[:20]}...")
        # Try to find walkability column
        walk_col = None
        geoid_col = None
        state_col = None
        for col in df.columns:
            if "natwalkind" in col.lower():
                walk_col = col
            elif "geoid" in col.lower():
                geoid_col = col
            elif col.upper() == "STATEFP":
                state_col = col

        if walk_col is None or geoid_col is None:
            raise ValueError(f"Could not find walkability/GEOID columns in SLD data")

        df = df[[geoid_col, state_col or geoid_col, walk_col]].copy()
        df.columns = ["GEOID20", "STATEFP", "NatWalkInd"] if state_col else ["GEOID20", "GEOID20_dup", "NatWalkInd"]
        if state_col is None:
            df["STATEFP"] = df["GEOID20"].str[:2]
        df = df[["GEOID20", "STATEFP", "NatWalkInd"]]

    # Filter to CONUS
    df = df[df["STATEFP"].isin(CONUS_STATE_FIPS)]
    df["NatWalkInd"] = pd.to_numeric(df["NatWalkInd"], errors="coerce")
    df = df.dropna(subset=["NatWalkInd"])

    print(f"  Found {len(df)} block groups with walkability data")
    print(f"  NatWalkInd range: {df['NatWalkInd'].min():.1f} - {df['NatWalkInd'].max():.1f}")
    return df


def download_bg_shapes() -> gpd.GeoDataFrame:
    """Download Census block group boundaries."""
    shp_dir = RAW_DIR / "cb_2020_bg_500k"

    if not shp_dir.exists():
        zip_path = RAW_DIR / "cb_2020_us_bg_500k.zip"
        download_file(BG_SHAPES_URL, zip_path)

        print("  Extracting block group shapefile...")
        shp_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(shp_dir)
    else:
        print("  Already have block group shapefile")

    shp_files = list(shp_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found in block group download")

    print("  Loading block group geometries (this may take a minute)...")
    gdf = gpd.read_file(shp_files[0])
    gdf = gdf[gdf["STATEFP"].isin(CONUS_STATE_FIPS)]
    gdf = gdf[["GEOID", "geometry"]]
    print(f"  Loaded {len(gdf)} block group polygons in CONUS")
    return gdf


def main():
    ensure_dirs()
    print("=== Processing Transit / Walkability Data ===")

    sld = download_sld_data()
    bg_shapes = download_bg_shapes()

    # Join SLD to block group geometries
    print("  Joining walkability data to block group geometries...")
    merged = bg_shapes.merge(sld[["GEOID20", "NatWalkInd"]], left_on="GEOID", right_on="GEOID20", how="inner")
    print(f"  Matched {len(merged)} block groups")

    # Normalize walkability: 1-20 scale -> 0-1
    merged["walkability"] = ((merged["NatWalkInd"] - 1) / 19).clip(0, 1).round(3)

    # Simplify geometries (block groups are small, need less simplification)
    print("  Simplifying geometries...")
    merged["geometry"] = merged["geometry"].simplify(0.001, preserve_topology=True)

    # Write GeoJSON
    geojson_path = OUTPUT_DIR / "transit.geojson"
    print("  Writing GeoJSON...")
    merged[["GEOID", "NatWalkInd", "walkability", "geometry"]].to_file(geojson_path, driver="GeoJSON")

    # Convert to PMTiles
    pmtiles_path = OUTPUT_DIR / "transit.pmtiles"
    print("  Running tippecanoe...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12", "-Z", "3",
                "-l", "transit",
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
