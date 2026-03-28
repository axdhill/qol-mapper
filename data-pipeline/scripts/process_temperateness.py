#!/usr/bin/env python3
"""
Process WorldClim 2.1 monthly temperature data into BIO5/BIO6 GeoTIFFs.

BIO5 = Max Temperature of Warmest Month (°C)
BIO6 = Min Temperature of Coldest Month (°C)

These are then used by generate_score_grids.py to produce the temperateness
score grid.

Usage:
    python process_temperateness.py
"""

import zipfile
from pathlib import Path

import numpy as np

from score_grid import (
    GRID_HEIGHT,
    GRID_WIDTH,
    resample_raster_to_grid,
)
from utils import CONUS_BOUNDS, OUTPUT_DIR, RAW_DIR, download_file, ensure_dirs, write_geotiff

WORLDCLIM_BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"


def download_worldclim_monthly(var: str) -> Path:
    """Download and extract WorldClim 2.1 monthly variable (tmin or tmax)."""
    extract_dir = RAW_DIR / f"wc2.1_2.5m_{var}"

    if extract_dir.exists() and len(list(extract_dir.glob("*.tif"))) == 12:
        print(f"  Already have WorldClim {var} monthly data")
        return extract_dir

    zip_name = f"wc2.1_2.5m_{var}.zip"
    zip_path = RAW_DIR / zip_name
    url = f"{WORLDCLIM_BASE}/{zip_name}"
    download_file(url, zip_path)

    print(f"  Extracting {zip_name}...")
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    return extract_dir


def compute_bio5_bio6() -> tuple[np.ndarray, np.ndarray]:
    """
    Compute BIO5 (max of monthly tmax) and BIO6 (min of monthly tmin)
    resampled to the common CONUS grid (1170×500 at 0.05°).

    Returns arrays in °C.
    """
    tmax_dir = download_worldclim_monthly("tmax")
    tmin_dir = download_worldclim_monthly("tmin")

    print("  Resampling 12 monthly tmax rasters...")
    tmax_grids = []
    for month in range(1, 13):
        tif = next(iter(sorted(tmax_dir.glob(f"*_{month:02d}.tif"))), None)
        if tif is None:
            raise FileNotFoundError(f"Missing tmax month {month:02d} in {tmax_dir}")
        tmax_grids.append(resample_raster_to_grid(tif))

    print("  Resampling 12 monthly tmin rasters...")
    tmin_grids = []
    for month in range(1, 13):
        tif = next(iter(sorted(tmin_dir.glob(f"*_{month:02d}.tif"))), None)
        if tif is None:
            raise FileNotFoundError(f"Missing tmin month {month:02d} in {tmin_dir}")
        tmin_grids.append(resample_raster_to_grid(tif))

    tmax_stack = np.stack(tmax_grids, axis=0)  # (12, H, W)
    tmin_stack = np.stack(tmin_grids, axis=0)  # (12, H, W)

    bio5 = np.nanmax(tmax_stack, axis=0).astype(np.float32)
    bio6 = np.nanmin(tmin_stack, axis=0).astype(np.float32)

    return bio5, bio6


def main():
    ensure_dirs()
    print("=== Processing Temperateness (WorldClim 2.1) ===")
    print(f"  CONUS grid: {GRID_WIDTH}×{GRID_HEIGHT}")

    bio5, bio6 = compute_bio5_bio6()

    tmax_path = OUTPUT_DIR / "tmax_hottest.tif"
    tmin_path = OUTPUT_DIR / "tmin_coldest.tif"

    write_geotiff(bio5, CONUS_BOUNDS, tmax_path)
    write_geotiff(bio6, CONUS_BOUNDS, tmin_path)

    print(f"  tmax_hottest range: {np.nanmin(bio5):.1f} – {np.nanmax(bio5):.1f} °C")
    print(f"  tmin_coldest range: {np.nanmin(bio6):.1f} – {np.nanmax(bio6):.1f} °C")
    print("Done!")


if __name__ == "__main__":
    main()
