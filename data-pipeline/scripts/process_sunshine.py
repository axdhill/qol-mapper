#!/usr/bin/env python3
"""
Annual solar radiation layer (proxy for sunny days).

Downloads WorldClim v2.1 2.5-arcmin monthly solar radiation (srad, kJ/m²/day)
and computes the annual mean as a proxy for year-round sunshine.

Scoring:
  srad ≤  9,000 kJ/m²/day  → score 0.0  (Pacific NW, very overcast)
  srad ≥ 23,000 kJ/m²/day  → score 1.0  (Desert SW, nearly cloudless)

Usage:
    python process_sunshine.py
"""

import zipfile
from pathlib import Path

import numpy as np

from score_grid import (
    GRID_EAST,
    GRID_NORTH,
    GRID_SOUTH,
    GRID_WEST,
    resample_raster_to_grid,
    score_to_raster_pmtiles,
    write_score_grid,
)
from utils import CONUS_BOUNDS, OUTPUT_DIR, RAW_DIR, download_file, ensure_dirs, write_geotiff

WORLDCLIM_BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"

# Linear normalization bounds (kJ/m²/day annual mean)
SRAD_MIN = 9_000.0
SRAD_MAX = 23_000.0

# Color ramp: gray-blue (overcast) → yellow → bright orange (sunny)
# Values are 0-200 uint8 (score 0.0-1.0 × 200)
COLOR_RAMP = """\
0   155 170 195 200
30  185 185 165 200
60  220 205 120 200
100 250 210  60 200
140 255 185  20 200
175 255 155   0 200
200 255 120   0 200
nv    0   0   0   0
"""


def download_worldclim_srad() -> Path:
    """Download and extract WorldClim 2.1 monthly srad; return extract dir."""
    extract_dir = RAW_DIR / "wc2.1_2.5m_srad"
    if extract_dir.exists() and len(list(extract_dir.glob("*.tif"))) == 12:
        print("  Already have WorldClim srad monthly data")
        return extract_dir

    zip_name = "wc2.1_2.5m_srad.zip"
    zip_path = RAW_DIR / zip_name
    download_file(f"{WORLDCLIM_BASE}/{zip_name}", zip_path)

    print(f"  Extracting {zip_name}...")
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    return extract_dir


def compute_annual_mean_srad() -> np.ndarray:
    """Return mean annual solar radiation resampled to CONUS score grid (kJ/m²/day)."""
    srad_dir = download_worldclim_srad()

    print("  Resampling 12 monthly srad rasters...")
    monthly = []
    for month in range(1, 13):
        tif = next(iter(sorted(srad_dir.glob(f"*_{month:02d}.tif"))), None)
        if tif is None:
            raise FileNotFoundError(f"Missing srad month {month:02d} in {srad_dir}")
        monthly.append(resample_raster_to_grid(tif))

    stack = np.stack(monthly, axis=0)  # (12, H, W)
    annual_mean = np.nanmean(stack, axis=0).astype(np.float32)
    print(
        f"  Annual mean srad range: "
        f"{np.nanmin(annual_mean):.0f} – {np.nanmax(annual_mean):.0f} kJ/m²/day"
    )
    return annual_mean


def main():
    ensure_dirs()
    print("=== Processing Sunshine (WorldClim v2.1 srad) ===")

    annual_srad = compute_annual_mean_srad()

    # Write intermediate GeoTIFF for generate_score_grids.py
    tif_path = OUTPUT_DIR / "sunshine.tif"
    write_geotiff(annual_srad, CONUS_BOUNDS, tif_path)

    # Score grid
    score = np.clip(
        (annual_srad - SRAD_MIN) / (SRAD_MAX - SRAD_MIN), 0.0, 1.0
    ).astype(np.float32)
    score[np.isnan(annual_srad)] = np.nan
    write_score_grid(score, "sunshine")

    # PMTiles visualization
    print("  Generating PMTiles...")
    score_to_raster_pmtiles(score, "sunshine", COLOR_RAMP, OUTPUT_DIR)

    print("Done!")


if __name__ == "__main__":
    main()
