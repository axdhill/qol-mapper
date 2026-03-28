#!/usr/bin/env python3
"""
Process tree canopy cover into raster PMTiles and a score grid.

Uses Hansen Global Forest Change v1.11 (treecover2000) tiles from Google
Cloud Storage.  These are publicly accessible GeoTIFFs at ~30 m resolution.
We resample to ~0.003° (~330 m) for PMTiles and to 0.05° (~5 km) for the
composite score grid.

Steps:
1. Build a GDAL VRT of all Hansen tiles covering CONUS via /vsicurl/
2. gdalwarp to WGS84 at target resolution
3. Colorize and tile for PMTiles (raster overlay)
4. Generate score grid for composite overlay

Usage:
    python process_tree_canopy.py
"""

import subprocess
import sqlite3
from pathlib import Path

import numpy as np

from score_grid import (
    GRID_EAST,
    GRID_HEIGHT,
    GRID_NORTH,
    GRID_SOUTH,
    GRID_WEST,
    GRID_WIDTH,
    resample_raster_to_grid,
    write_score_grid,
)
from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs

# Hansen GFC 2023-v1.11 tree cover (year 2000 baseline) on Google Cloud Storage
HANSEN_BASE = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11"
HANSEN_PRODUCT = "treecover2000"

# CONUS coverage: lat 20N-50N, lon 130W-60W (with some margin)
HANSEN_LATS = ["20N", "30N", "40N", "50N"]
HANSEN_LONS = ["060W", "070W", "080W", "090W", "100W", "110W", "120W", "130W"]

COLOR_RAMP = """0 247 252 245 0
1 237 248 233 200
10 199 233 192 200
20 161 217 155 200
30 116 196 118 200
40 65 171 93 200
50 35 139 69 200
60 0 109 44 200
70 0 68 27 200
80 0 50 20 200
90 0 40 15 200
100 0 30 10 200
nv 0 0 0 0
"""


def build_hansen_vrt(vrt_path: Path) -> Path:
    """Build a GDAL VRT that mosaics all Hansen tiles covering CONUS."""
    tile_urls = []
    for lat in HANSEN_LATS:
        for lon in HANSEN_LONS:
            filename = f"Hansen_GFC-2023-v1.11_{HANSEN_PRODUCT}_{lat}_{lon}.tif"
            url = f"/vsicurl/{HANSEN_BASE}/{filename}"
            tile_urls.append(url)

    print(f"  Building VRT from {len(tile_urls)} Hansen tiles...")

    cmd = [
        "gdalbuildvrt",
        str(vrt_path),
    ] + tile_urls

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"  VRT: {vrt_path}")
    return vrt_path


def downsample_to_conus(vrt_path: Path, output_path: Path, resolution_deg: float = 0.003):
    """Downsample the Hansen VRT to a manageable CONUS GeoTIFF."""
    print(f"  Downsampling to ~{resolution_deg}\u00b0 ({resolution_deg * 111:.0f}m)...")
    print("  (Reading tiles remotely \u2014 this may take 15-30 minutes)")

    cmd = [
        "gdalwarp",
        "-t_srs", "EPSG:4326",
        "-te", str(GRID_WEST), str(GRID_SOUTH), str(GRID_EAST), str(GRID_NORTH),
        "-tr", str(resolution_deg), str(resolution_deg),
        "-r", "average",
        "-co", "COMPRESS=DEFLATE",
        "-co", "TILED=YES",
        "-ot", "Byte",
        "-overwrite",
        str(vrt_path),
        str(output_path),
    ]

    subprocess.run(cmd, check=True)
    print(f"  Downsampled: {output_path}")


def downsample_for_score_grid(vrt_path: Path, output_path: Path):
    """Downsample directly to score grid resolution (0.05\u00b0)."""
    print("  Downsampling to score grid resolution (0.05\u00b0)...")
    print("  (Reading tiles remotely \u2014 ~15-20 minutes)")

    cmd = [
        "gdalwarp",
        "-t_srs", "EPSG:4326",
        "-te", str(GRID_WEST), str(GRID_SOUTH), str(GRID_EAST), str(GRID_NORTH),
        "-tr", "0.05", "0.05",
        "-r", "average",
        "-co", "COMPRESS=DEFLATE",
        "-ot", "Byte",
        "-overwrite",
        str(vrt_path),
        str(output_path),
    ]

    subprocess.run(cmd, check=True)
    print(f"  Score grid resolution raster: {output_path}")


def generate_tree_canopy_score(tif_path: Path):
    """Generate 0-1 score grid from tree canopy percentage."""
    print("  Generating tree canopy score grid...")

    raw = resample_raster_to_grid(tif_path)

    # Tree canopy 0-100%. Higher = better.
    # 0% = score 0.0, 80%+ = score 1.0
    score = np.clip(raw / 80.0, 0, 1)
    score[np.isnan(raw)] = np.nan
    score = score.astype(np.float32)

    write_score_grid(score, "tree-canopy")


def colorize_geotiff(input_path: Path, output_path: Path, color_file: Path):
    """Apply color ramp to single-band GeoTIFF."""
    print("  Colorizing with gdaldem...")
    subprocess.run(
        [
            "gdaldem", "color-relief",
            str(input_path),
            str(color_file),
            str(output_path),
            "-alpha",
            "-of", "VRT",
            "-nearest_color_entry",
        ],
        check=True,
    )
    print(f"  Colorized: {output_path}")


def tile_and_convert(colored_path: Path, pmtiles_path: Path):
    """Tile the colorized raster and convert to PMTiles."""
    tiles_dir = OUTPUT_DIR / "tree_canopy_tiles"

    print("  Running gdal2tiles.py...")
    subprocess.run(
        [
            "gdal2tiles.py",
            "-z", "3-10",
            "--processes=4",
            "-r", "near",
            str(colored_path),
            str(tiles_dir),
        ],
        check=True,
    )

    # Convert XYZ tiles to MBTiles
    mbtiles_path = OUTPUT_DIR / "tree-canopy.mbtiles"
    print("  Converting XYZ tiles to MBTiles...")
    xyz_to_mbtiles(tiles_dir, mbtiles_path)

    # Convert MBTiles to PMTiles
    print("  Converting MBTiles to PMTiles...")
    subprocess.run(
        ["pmtiles", "convert", str(mbtiles_path), str(pmtiles_path)],
        check=True,
    )
    print(f"  PMTiles written: {pmtiles_path}")


def xyz_to_mbtiles(tiles_dir: Path, mbtiles_path: Path):
    """Convert XYZ tile directory to MBTiles."""
    if mbtiles_path.exists():
        mbtiles_path.unlink()

    conn = sqlite3.connect(str(mbtiles_path))
    conn.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    conn.execute(
        "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, "
        "tile_row INTEGER, tile_data BLOB)"
    )

    conn.execute("INSERT INTO metadata VALUES ('name', 'tree-canopy')")
    conn.execute("INSERT INTO metadata VALUES ('format', 'png')")
    conn.execute("INSERT INTO metadata VALUES ('type', 'overlay')")

    count = 0
    for z_dir in sorted(tiles_dir.iterdir()):
        if not z_dir.is_dir() or not z_dir.name.isdigit():
            continue
        z = int(z_dir.name)
        for x_dir in z_dir.iterdir():
            if not x_dir.is_dir():
                continue
            x = int(x_dir.name)
            for tile_file in x_dir.iterdir():
                if not tile_file.suffix == ".png":
                    continue
                y = int(tile_file.stem)
                tms_y = (1 << z) - 1 - y
                tile_data = tile_file.read_bytes()
                conn.execute(
                    "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                    (z, x, tms_y, tile_data),
                )
                count += 1

    conn.execute(
        "CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)"
    )
    conn.commit()
    conn.close()
    print(f"  MBTiles written: {count} tiles")


def main():
    ensure_dirs()
    print("=== Processing Tree Canopy Cover Data ===")

    vrt_path = OUTPUT_DIR / "hansen_treecover_conus.vrt"
    if not vrt_path.exists():
        build_hansen_vrt(vrt_path)
    else:
        print(f"  Already have VRT: {vrt_path}")

    # Step 1: Generate score grid (fast — only 0.05° resolution)
    score_tif = OUTPUT_DIR / "tree_canopy_score_res.tif"
    if not score_tif.exists():
        downsample_for_score_grid(vrt_path, score_tif)
    else:
        print(f"  Already have score grid raster: {score_tif}")

    generate_tree_canopy_score(score_tif)

    # Step 2: Generate PMTiles (slower — 0.003° resolution)
    downsampled = OUTPUT_DIR / "tree_canopy_downsampled.tif"
    if not downsampled.exists():
        downsample_to_conus(vrt_path, downsampled)
    else:
        print(f"  Already have downsampled GeoTIFF: {downsampled}")

    color_file = OUTPUT_DIR / "tree_canopy_colors.txt"
    color_file.write_text(COLOR_RAMP)

    colored = OUTPUT_DIR / "tree_canopy_colored.vrt"
    colorize_geotiff(downsampled, colored, color_file)

    pmtiles_path = OUTPUT_DIR / "tree-canopy.pmtiles"
    tile_and_convert(colored, pmtiles_path)
    copy_to_public(pmtiles_path)

    print("Done!")


if __name__ == "__main__":
    main()
