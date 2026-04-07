#!/usr/bin/env python3
"""
Topographic ruggedness layer.

Downloads SRTM 30-arc-second elevation from WorldClim v2.1 and computes
local elevation standard deviation within a sliding window (~25 km radius)
as a proxy for terrain interest.

Scoring is logarithmic so that rolling hills score meaningfully and the
Rockies don't score 10× better than the Appalachians:

  std_dev ≈ 0 m      (flat plains)    → score ≈ 0.00
  std_dev ≈ 10 m     (gentle)         → score ≈ 0.33
  std_dev ≈ 100 m    (rolling hills)  → score ≈ 0.63
  std_dev ≈ 500 m    (mountains)      → score ≈ 0.85
  std_dev ≈ 1500 m+  (extreme)        → score ≈ 1.00

Usage:
    python process_topography.py
"""

import zipfile
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter

from score_grid import (
    GRID_EAST,
    GRID_NORTH,
    GRID_SOUTH,
    GRID_WEST,
    resample_raster_to_grid,
    score_to_raster_pmtiles,
    write_score_grid,
)
from utils import OUTPUT_DIR, RAW_DIR, download_file, ensure_dirs

WORLDCLIM_ELEV_URL = (
    "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_elev.zip"
)

# std_dev at this value → score 1.0 (representative maximum for CONUS)
MAX_STD_DEV = 1500.0

# Sliding window diameter in 30-arcsec cells.
# 30 arcsec ≈ 0.9 km/cell → 57 cells ≈ 51 km diameter (~25 km radius).
WINDOW_SIZE = 57

# gdaldem color-relief ramp (uint8 0-200 = score 0.0-1.0, 255 = nodata)
COLOR_RAMP = """\
0   240 234 210 200
30  225 195 148 200
60  198 155  98 200
100 158 108  52 200
140 112  68  26 200
175  72  40  12 200
200  42  18   4 200
nv    0   0   0   0
"""


def download_elevation() -> Path:
    """Download WorldClim 30-arcsec elevation; return path to extracted .tif."""
    tif_path = RAW_DIR / "wc2.1_30s_elev.tif"
    if tif_path.exists():
        print(f"  Already have elevation raster: {tif_path.name}")
        return tif_path

    zip_path = RAW_DIR / "wc2.1_30s_elev.zip"
    download_file(WORLDCLIM_ELEV_URL, zip_path)

    print("  Extracting elevation raster...")
    with zipfile.ZipFile(zip_path) as zf:
        tif_names = [n for n in zf.namelist() if n.lower().endswith(".tif")]
        if not tif_names:
            raise FileNotFoundError("No .tif found in WorldClim elevation zip")
        zf.extract(tif_names[0], RAW_DIR)
        extracted = RAW_DIR / tif_names[0]
        if extracted != tif_path:
            extracted.rename(tif_path)

    return tif_path


def compute_stddev_tif(elev_tif: Path, output_path: Path):
    """
    Compute sliding-window elevation std dev and write to a GeoTIFF.

    Steps:
      1. Load the WorldClim raster cropped to CONUS bounds.
      2. Compute Var = E[x²] - E[x]² using uniform_filter (O(n), fast).
      3. Write the resulting std_dev as float32 GeoTIFF (nodata = -9999).
    """
    import rasterio
    from rasterio.windows import from_bounds

    print("  Loading CONUS elevation slice...")
    with rasterio.open(elev_tif) as src:
        window = from_bounds(GRID_WEST, GRID_SOUTH, GRID_EAST, GRID_NORTH, src.transform)
        elev = src.read(1, window=window, boundless=True, fill_value=-9999).astype(np.float64)
        win_transform = src.window_transform(window)
        nodata = src.nodata if src.nodata is not None else -32768

    print(f"  Elevation array shape: {elev.shape}")

    # Build a valid-data mask (ocean / nodata → False)
    valid = (elev > -9000) & (np.abs(elev - nodata) > 1)

    # Replace invalid cells with 0 for the convolution (neutral elevation).
    # Their contribution will be corrected by the valid-count normalization below.
    elev_fill = np.where(valid, elev, 0.0)
    valid_f = valid.astype(np.float64)

    print(
        f"  Computing sliding std dev  "
        f"(window={WINDOW_SIZE} cells ≈ {WINDOW_SIZE * 30 / 3600 * 111:.0f} km)..."
    )
    # Count of valid cells in each window (for correct mean computation)
    valid_count = uniform_filter(valid_f, size=WINDOW_SIZE) * (WINDOW_SIZE ** 2)

    # Weighted sums: only valid cells contribute
    sum1 = uniform_filter(elev_fill * valid_f, size=WINDOW_SIZE) * (WINDOW_SIZE ** 2)
    sum2 = uniform_filter(elev_fill ** 2 * valid_f, size=WINDOW_SIZE) * (WINDOW_SIZE ** 2)

    # Avoid division by zero in empty windows
    safe_n = np.maximum(valid_count, 1.0)
    mean = sum1 / safe_n
    mean_sq = sum2 / safe_n
    std_dev = np.sqrt(np.maximum(0.0, mean_sq - mean ** 2)).astype(np.float32)

    # Mark originally-invalid cells as nodata
    std_dev[~valid] = -9999.0
    # Also mask windows with fewer than 10% valid cells
    std_dev[valid_count < 0.1 * WINDOW_SIZE ** 2] = -9999.0

    # Write output GeoTIFF at native resolution
    height, width = std_dev.shape
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=win_transform,
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        dst.write(std_dev, 1)

    print(f"  Std-dev raster written: {output_path}")


def generate_topography_score(stddev_tif: Path):
    """Resample std-dev tif to score grid and apply log normalization."""
    print("  Resampling to score grid resolution...")
    raw = resample_raster_to_grid(stddev_tif)  # values in metres, nodata → NaN

    # Mask nodata sentinel
    raw = np.where(raw < -9000, np.nan, raw)

    # Logarithmic normalization: log1p(x) / log1p(MAX)
    score = np.log1p(np.maximum(raw, 0.0)) / np.log1p(MAX_STD_DEV)
    score = np.clip(score, 0.0, 1.0).astype(np.float32)
    score[np.isnan(raw)] = np.nan

    write_score_grid(score, "topography")
    return score


def main():
    ensure_dirs()
    print("=== Processing Topography (Terrain Ruggedness) ===")

    elev_tif = download_elevation()

    stddev_tif = OUTPUT_DIR / "topography_stddev.tif"
    if not stddev_tif.exists():
        compute_stddev_tif(elev_tif, stddev_tif)
    else:
        print(f"  Already have std-dev raster: {stddev_tif.name}")

    score = generate_topography_score(stddev_tif)

    print("  Generating PMTiles visualization...")
    score_to_raster_pmtiles(
        score,
        "topography",
        COLOR_RAMP,
        OUTPUT_DIR,
        zoom_range="3-10",
    )

    print("Done!")


if __name__ == "__main__":
    main()
