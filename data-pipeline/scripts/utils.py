"""Shared utility functions for the QoL Mapper data pipeline."""

import os
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

# Project paths
PIPELINE_DIR = Path(__file__).parent.parent
RAW_DIR = PIPELINE_DIR / "raw"
OUTPUT_DIR = PIPELINE_DIR / "output"
PUBLIC_TILES_DIR = PIPELINE_DIR.parent / "public" / "tiles"

# CONUS bounding box (approximate)
CONUS_BOUNDS = {
    "west": -125.0,
    "south": 24.5,
    "east": -66.5,
    "north": 49.5,
}

# Default CRS
WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"


def ensure_dirs():
    """Create necessary directories if they don't exist."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_TILES_DIR.mkdir(parents=True, exist_ok=True)


def download_file(url: str, dest: Path, force: bool = False) -> Path:
    """Download a file if it doesn't already exist."""
    import requests

    if dest.exists() and not force:
        print(f"  Already downloaded: {dest.name}")
        return dest

    print(f"  Downloading: {url}")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"  Saved: {dest}")
    return dest


def write_geotiff(
    data: np.ndarray,
    bounds: dict,
    output_path: Path,
    nodata: float = -9999.0,
    crs: str = WGS84,
):
    """Write a 2D numpy array as a GeoTIFF."""
    height, width = data.shape
    transform = from_bounds(
        bounds["west"],
        bounds["south"],
        bounds["east"],
        bounds["north"],
        width,
        height,
    )

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=data.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)

    print(f"  Written GeoTIFF: {output_path}")


def copy_to_public(src: Path, name: str | None = None):
    """Copy a file to the public tiles directory."""
    import shutil

    dest = PUBLIC_TILES_DIR / (name or src.name)
    shutil.copy2(src, dest)
    print(f"  Copied to public: {dest}")


# CONUS state abbreviations (for filtering datasets)
CONUS_STATES = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}

# CONUS state FIPS codes (2-digit)
CONUS_STATE_FIPS = {
    "01", "04", "05", "06", "08", "09", "10", "11", "12", "13", "16", "17",
    "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "41",
    "42", "44", "45", "46", "47", "48", "49", "50", "51", "53", "54", "55", "56"
}

COUNTY_SHAPES_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip"


def download_county_shapes() -> "gpd.GeoDataFrame":
    """Download and cache Census county boundaries (500k cartographic)."""
    import geopandas as gpd
    import zipfile

    shp_dir = RAW_DIR / "cb_2020_county_500k"

    if not shp_dir.exists():
        zip_path = RAW_DIR / "cb_2020_us_county_500k.zip"
        if not zip_path.exists():
            print("  Downloading Census county boundaries (~30MB)...")
            download_file(COUNTY_SHAPES_URL, zip_path)

        print("  Extracting county shapefile...")
        shp_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(shp_dir)
    else:
        print("  Already have county shapefile")

    shp_files = list(shp_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found in county download")

    print("  Loading county geometries...")
    gdf = gpd.read_file(shp_files[0])
    # GEOID is 5-digit county FIPS, STATEFP is 2-digit state FIPS
    gdf = gdf[gdf["STATEFP"].isin(CONUS_STATE_FIPS)]
    gdf = gdf[["GEOID", "NAME", "STATEFP", "geometry"]]
    print(f"  Loaded {len(gdf)} county polygons in CONUS")
    return gdf
