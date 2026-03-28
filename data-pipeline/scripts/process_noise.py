#!/usr/bin/env python3
"""
Estimate ambient noise levels from road network density.

Source: US DOT Bureau of Transportation Statistics - road network
https://geodata.bts.gov/datasets/usdot::highway-performance-monitoring-system-hpms/about

Alternative: OpenStreetMap road data from Geofabrik.

Approach:
- Download BTS highway data (or OSM roads)
- Rasterize road density weighted by road class
  (interstates contribute more noise than local roads)
- Apply distance decay function to estimate noise propagation
- Output as raster PMTiles

Steps:
1. Download road network data
2. Rasterize with road-class weights
3. Apply Gaussian blur for noise propagation
4. Colorize and tile
5. Convert to PMTiles
"""

import json
import subprocess
import sqlite3
from pathlib import Path

import numpy as np
import requests
from scipy.ndimage import gaussian_filter

from utils import OUTPUT_DIR, RAW_DIR, CONUS_BOUNDS, copy_to_public, ensure_dirs, write_geotiff

# BTS HPMS (Highway Performance Monitoring System) - major roads
# This is a GeoJSON API endpoint
HPMS_URL = "https://geo.dot.gov/server/rest/services/Hosted/HPMS_Full_National_2021/FeatureServer/0/query"

# Alternative: use Natural Earth roads (much simpler, lower resolution)
NE_ROADS_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_roads_north_america.zip"

# OSM road data from Geofabrik (US extract is ~10GB, too large)
# Instead use a WFS/API approach or the BTS data

# For a practical approach, we'll use Census TIGER roads
TIGER_PRIMARY_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PRIMARYROADS/tl_2023_us_primaryroads.zip"
TIGER_PRISEC_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PRISECROADS/"

# Road class noise weights (dB contribution per road type)
ROAD_WEIGHTS = {
    "I": 75,   # Interstate
    "U": 65,   # US Highway
    "S": 60,   # State Highway
    "C": 50,   # County road
    "O": 45,   # Other
}


def download_tiger_roads(raw_dir: Path) -> Path:
    """Download Census TIGER primary roads (interstates and US highways)."""
    import zipfile

    zip_path = raw_dir / "tiger_primaryroads.zip"
    shp_dir = raw_dir / "tiger_primaryroads"

    if shp_dir.exists():
        print("  Already have TIGER primary roads")
        return shp_dir

    if not zip_path.exists():
        print("  Downloading Census TIGER primary roads...")
        resp = requests.get(TIGER_PRIMARY_URL, timeout=300, stream=True)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)

    print("  Extracting...")
    shp_dir.mkdir(exist_ok=True)
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(shp_dir)

    return shp_dir


def rasterize_roads(shp_dir: Path, output_path: Path, resolution: float = 0.01):
    """Rasterize road network with distance-based noise weights."""
    import geopandas as gpd

    shp_files = list(shp_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found")

    print("  Loading road geometries...")
    gdf = gpd.read_file(shp_files[0])

    # Filter to CONUS
    gdf = gdf.cx[-126:-66, 24:50]
    print(f"  Loaded {len(gdf)} road segments")

    # RTTYP = Route Type: I=Interstate, U=US, S=State, C=County, O=Other
    if "RTTYP" in gdf.columns:
        gdf["weight"] = gdf["RTTYP"].map(ROAD_WEIGHTS).fillna(45)
    else:
        gdf["weight"] = 60  # Default for primary roads

    # Create raster grid
    west, south, east, north = -125, 24.5, -66.5, 49.5
    width = int((east - west) / resolution)
    height = int((north - south) / resolution)
    print(f"  Grid: {width} x {height} ({resolution}° resolution)")

    # Use GDAL to rasterize
    # First write a temporary GeoJSON with weight attribute
    temp_geojson = OUTPUT_DIR / "roads_weighted.geojson"
    gdf_out = gdf[["weight", "geometry"]].copy()
    gdf_out.to_file(temp_geojson, driver="GeoJSON")

    temp_tif = OUTPUT_DIR / "road_density_raw.tif"
    print("  Rasterizing roads with gdal_rasterize...")
    subprocess.run(
        [
            "gdal_rasterize",
            "-a", "weight",
            "-te", str(west), str(south), str(east), str(north),
            "-tr", str(resolution), str(resolution),
            "-ot", "Float32",
            "-init", "30",  # Background noise level (quiet rural)
            "-a_nodata", "-9999",
            str(temp_geojson),
            str(temp_tif),
        ],
        check=True,
    )

    # Apply Gaussian blur to simulate noise propagation
    print("  Applying noise propagation (Gaussian blur)...")
    import rasterio
    with rasterio.open(temp_tif) as src:
        data = src.read(1)
        transform = src.transform
        crs = src.crs

    # Sigma of ~5 pixels ≈ 5km propagation at 0.01° resolution
    blurred = gaussian_filter(data.astype(float), sigma=5)
    # Take the max of original and blurred (roads are louder at source)
    noise = np.maximum(data, blurred)
    # Clip to reasonable range
    noise = np.clip(noise, 30, 80)

    write_geotiff(noise.astype(np.float32), CONUS_BOUNDS, output_path, nodata=-9999.0)
    print(f"  Written noise raster: {output_path}")

    return output_path


COLOR_RAMP = """30 26 152 80 200
35 26 152 80 200
40 145 207 96 200
45 145 207 96 200
50 254 224 139 200
55 254 224 139 200
60 252 141 89 200
65 252 141 89 200
70 215 48 39 200
75 215 48 39 200
80 165 0 38 200
nv 0 0 0 0
"""


def tile_and_convert(geotiff_path: Path, pmtiles_path: Path):
    """Colorize, tile, and convert to PMTiles."""
    color_file = OUTPUT_DIR / "noise_colors.txt"
    color_file.write_text(COLOR_RAMP)

    colored = OUTPUT_DIR / "noise_colored.vrt"
    print("  Colorizing...")
    subprocess.run(
        [
            "gdaldem", "color-relief",
            str(geotiff_path),
            str(color_file),
            str(colored),
            "-alpha",
            "-of", "VRT",
            "-nearest_color_entry",
        ],
        check=True,
    )

    tiles_dir = OUTPUT_DIR / "noise_tiles"
    print("  Running gdal2tiles.py...")
    subprocess.run(
        [
            "gdal2tiles.py",
            "-z", "3-10",
            "--processes=4",
            "-r", "near",
            str(colored),
            str(tiles_dir),
        ],
        check=True,
    )

    # XYZ -> MBTiles -> PMTiles
    mbtiles_path = OUTPUT_DIR / "noise.mbtiles"
    xyz_to_mbtiles(tiles_dir, mbtiles_path)

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
    conn.execute("INSERT INTO metadata VALUES ('name', 'noise')")
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
    print("=== Processing Noise Estimation Data ===")

    shp_dir = download_tiger_roads(RAW_DIR)

    geotiff_path = OUTPUT_DIR / "noise.tif"
    if not geotiff_path.exists():
        rasterize_roads(shp_dir, geotiff_path)
    else:
        print(f"  Already have noise raster: {geotiff_path}")

    pmtiles_path = OUTPUT_DIR / "noise.pmtiles"
    tile_and_convert(geotiff_path, pmtiles_path)
    copy_to_public(pmtiles_path)

    print("Done!")


if __name__ == "__main__":
    main()
