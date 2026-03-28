#!/usr/bin/env python3
"""
Process EPA PM2.5 data into a raster GeoTIFF and then PMTiles.

Steps:
1. Load the annual monitor CSV
2. Filter to PM2.5 FRM/FEM (parameter code 88101)
3. Extract lat/lon and annual mean concentration
4. Interpolate to a regular grid covering CONUS using IDW
5. Write as GeoTIFF
6. Colorize to RGBA, tile with gdal2tiles, convert to PMTiles

Usage:
    python process_pm25.py
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import RBFInterpolator

from utils import (
    CONUS_BOUNDS,
    OUTPUT_DIR,
    RAW_DIR,
    copy_to_public,
    ensure_dirs,
    write_geotiff,
)

YEARS = [2019, 2020, 2021, 2022, 2023]  # 5-year average
# Grid resolution in degrees (~5km at mid-latitudes for faster processing)
RESOLUTION = 0.05
PARAMETER_CODE = "88101"

# Viridis-like color ramp for PM2.5 values (reversed: low=good/purple, high=bad/yellow-red)
# Format: value R G B A
COLOR_RAMP = """
0 68 1 84 200
2 68 1 84 200
5 49 104 142 200
8 33 145 140 200
10 53 183 121 200
12 143 215 68 200
15 253 231 37 200
20 255 68 68 200
35 180 0 0 200
50 128 0 0 200
nv 0 0 0 0
"""


def _download_year(year: int) -> None:
    """Download EPA annual monitor CSV for a given year if not cached."""
    import requests

    csv_path = RAW_DIR / f"annual_conc_by_monitor_{year}.csv"
    if csv_path.exists():
        return
    zip_path = RAW_DIR / f"annual_conc_by_monitor_{year}.zip"
    if not zip_path.exists():
        url = f"https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_{year}.zip"
        print(f"  Downloading {year} data from EPA AQS...")
        resp = requests.get(url, timeout=300, stream=True)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(RAW_DIR)


def load_pm25_monitors() -> pd.DataFrame:
    """Load and average PM2.5 monitor data across YEARS for a stable multi-year mean."""
    dfs = []
    for year in YEARS:
        csv_path = RAW_DIR / f"annual_conc_by_monitor_{year}.csv"
        if not csv_path.exists():
            _download_year(year)
        if not csv_path.exists():
            print(f"  Warning: {year} data not found, skipping")
            continue
        df = pd.read_csv(csv_path)
        df = df[df["Parameter Code"] == int(PARAMETER_CODE)]
        df = df[df["Sample Duration"].str.contains("24", na=False)]
        df = df[["Latitude", "Longitude", "Arithmetic Mean"]].dropna()
        dfs.append(df)

    if not dfs:
        raise FileNotFoundError("No PM2.5 data found. Check EPA AQS downloads.")

    combined = pd.concat(dfs, ignore_index=True)
    # Average across all years per monitor location
    result = combined.groupby(["Latitude", "Longitude"], as_index=False)["Arithmetic Mean"].mean()
    print(f"  Found {len(result)} PM2.5 monitoring sites ({YEARS[0]}–{YEARS[-1]} average)")
    return result


def interpolate_to_grid(df: pd.DataFrame) -> np.ndarray:
    """Interpolate point measurements to a regular grid using RBF."""
    bounds = CONUS_BOUNDS
    lons = np.arange(bounds["west"], bounds["east"], RESOLUTION)
    lats = np.arange(bounds["south"], bounds["north"], RESOLUTION)

    print(f"  Grid size: {len(lons)} x {len(lats)} = {len(lons) * len(lats)} cells")

    # Create meshgrid for interpolation points
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    grid_points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])

    # Monitor locations and values
    points = df[["Longitude", "Latitude"]].values
    values = df["Arithmetic Mean"].values

    print("  Interpolating (RBF, this may take a minute)...")
    rbf = RBFInterpolator(points, values, kernel="thin_plate_spline", smoothing=0.5)
    grid_values = rbf(grid_points).reshape(lat_grid.shape)

    # Clip to reasonable PM2.5 range
    grid_values = np.clip(grid_values, 0, 50)

    # Flip vertically (GeoTIFF convention: top-left origin)
    grid_values = np.flipud(grid_values)

    return grid_values.astype(np.float32)


def geotiff_to_pmtiles(geotiff_path: Path, pmtiles_path: Path):
    """Convert float32 GeoTIFF to colorized RGBA tiles then PMTiles."""
    color_file = OUTPUT_DIR / "pm25_colors.txt"
    colored_vrt = OUTPUT_DIR / "pm25_colored.vrt"
    tiles_dir = OUTPUT_DIR / "pm25_tiles"

    # Write color ramp file
    color_file.write_text(COLOR_RAMP.strip())

    # Step 1: Colorize to RGBA using gdaldem
    print("  Colorizing raster...")
    subprocess.run(
        [
            "gdaldem", "color-relief",
            str(geotiff_path),
            str(color_file),
            str(colored_vrt),
            "-of", "VRT",
            "-alpha",
            "-nearest_color_entry",
        ],
        check=True,
    )

    # Step 2: Generate tiles
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir)

    print("  Generating tiles with gdal2tiles...")
    subprocess.run(
        [
            "gdal2tiles.py",
            "-z", "3-10",
            "--processes=4",
            "-r", "near",
            str(colored_vrt),
            str(tiles_dir),
        ],
        check=True,
    )

    # Step 3: Convert tile directory to PMTiles
    print("  Converting to PMTiles...")
    subprocess.run(
        ["pmtiles", "convert", str(tiles_dir), str(pmtiles_path)],
        check=True,
    )

    print(f"  PMTiles written: {pmtiles_path}")


def main():
    ensure_dirs()
    print("=== Processing PM2.5 Data ===")

    geotiff_path = OUTPUT_DIR / "pm25.tif"

    df = load_pm25_monitors()
    grid = interpolate_to_grid(df)
    write_geotiff(grid, CONUS_BOUNDS, geotiff_path, nodata=-9999.0)

    pmtiles_path = OUTPUT_DIR / "pm25.pmtiles"
    try:
        geotiff_to_pmtiles(geotiff_path, pmtiles_path)
        copy_to_public(pmtiles_path)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"  Error during tiling: {e}")
        print("  Falling back: copying raw GeoTIFF for manual conversion.")

    print("Done!")


if __name__ == "__main__":
    main()
