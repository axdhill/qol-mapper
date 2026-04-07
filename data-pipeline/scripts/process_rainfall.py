#!/usr/bin/env python3
"""
Average annual rainfall layer.

Downloads WorldClim v2.1 2.5-arcmin monthly precipitation (prec, mm/month)
and sums the 12 monthly values to produce an annual total (mm/year).

Scoring is logarithmic so that the difference between 200 mm and 400 mm
registers as meaningfully as the difference between 1000 mm and 2000 mm:

  prec ≤   100 mm/yr → score 0.0  (desert: Death Valley, Mojave)
  prec ≥  2500 mm/yr → score 1.0  (temperate rainforest: Olympic Peninsula)

Usage:
    python process_rainfall.py
"""

import zipfile
from pathlib import Path

import numpy as np

from score_grid import (
    resample_raster_to_grid,
    score_to_raster_pmtiles,
    write_score_grid,
)
from utils import CONUS_BOUNDS, OUTPUT_DIR, RAW_DIR, download_file, ensure_dirs, write_geotiff

WORLDCLIM_BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"

# Log-scale normalization bounds (mm/year)
PREC_MIN = 100.0
PREC_MAX = 2500.0

LOG_MIN = np.log1p(PREC_MIN)
LOG_MAX = np.log1p(PREC_MAX)

# Color ramp: tan/brown (dry) → green → deep blue (wet)
# Values are 0-200 uint8 (score × 200)
COLOR_RAMP = """\
0   195 155  95 200
25  210 180 115 200
50  175 195 125 200
80  100 170  95 200
120  45 135  75 200
155  25  95 150 200
200  10  45 140 200
nv    0   0   0   0
"""


def download_worldclim_prec() -> Path:
    """Download and extract WorldClim 2.1 monthly prec; return extract dir."""
    extract_dir = RAW_DIR / "wc2.1_2.5m_prec"
    if extract_dir.exists() and len(list(extract_dir.glob("*.tif"))) == 12:
        print("  Already have WorldClim prec monthly data")
        return extract_dir

    zip_name = "wc2.1_2.5m_prec.zip"
    zip_path = RAW_DIR / zip_name
    download_file(f"{WORLDCLIM_BASE}/{zip_name}", zip_path)

    print(f"  Extracting {zip_name}...")
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    return extract_dir


def compute_annual_precip() -> np.ndarray:
    """Return total annual precipitation resampled to CONUS score grid (mm/year)."""
    prec_dir = download_worldclim_prec()

    print("  Resampling 12 monthly prec rasters...")
    monthly = []
    for month in range(1, 13):
        tif = next(iter(sorted(prec_dir.glob(f"*_{month:02d}.tif"))), None)
        if tif is None:
            raise FileNotFoundError(f"Missing prec month {month:02d} in {prec_dir}")
        monthly.append(resample_raster_to_grid(tif))

    stack = np.stack(monthly, axis=0)          # (12, H, W)
    annual = np.nansum(stack, axis=0).astype(np.float32)
    # nansum returns 0 where all months are NaN — restore NaN for ocean cells
    all_nan = np.all(np.isnan(stack), axis=0)
    annual[all_nan] = np.nan

    print(
        f"  Annual precip range: "
        f"{np.nanmin(annual):.0f} – {np.nanmax(annual):.0f} mm/yr"
    )
    return annual


def score_from_precip(annual: np.ndarray) -> np.ndarray:
    """Log-normalize annual precipitation to 0-1 score."""
    score = np.clip(
        (np.log1p(np.maximum(annual, 0.0)) - LOG_MIN) / (LOG_MAX - LOG_MIN),
        0.0, 1.0,
    ).astype(np.float32)
    score[np.isnan(annual)] = np.nan
    return score


def main():
    ensure_dirs()
    print("=== Processing Annual Rainfall (WorldClim v2.1 prec) ===")

    annual = compute_annual_precip()

    # Intermediate GeoTIFF for generate_score_grids.py
    write_geotiff(annual, CONUS_BOUNDS, OUTPUT_DIR / "rainfall.tif")

    score = score_from_precip(annual)
    write_score_grid(score, "rainfall")

    print("  Generating PMTiles...")
    score_to_raster_pmtiles(score, "rainfall", COLOR_RAMP, OUTPUT_DIR)

    print("Done!")


if __name__ == "__main__":
    main()
