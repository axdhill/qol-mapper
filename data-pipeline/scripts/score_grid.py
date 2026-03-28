"""
Shared utilities for computing normalized score grids.

All score grids share the same CONUS extent and 0.05° resolution (1170×500).
Each cell contains a 0-1 QoL score (1 = excellent, 0 = poor), stored as Float32Array.
"""

import json
import sqlite3
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

# Module-level cache for the CONUS land mask
_conus_mask_cache: np.ndarray | None = None

# Non-CONUS state/territory FIPS codes to exclude
_NON_CONUS_FIPS = {"02", "15", "60", "66", "69", "72", "78"}

TIGER_STATES_URL = "https://www2.census.gov/geo/tiger/TIGER2023/STATE/tl_2023_us_state.zip"


def get_conus_land_mask(raw_dir: Path | None = None) -> np.ndarray:
    """Return a boolean mask (True = land within CONUS) at the common grid resolution.

    Downloads Census TIGER 2023 state boundaries on first call and caches the
    rasterized result in memory for subsequent calls.
    """
    global _conus_mask_cache
    if _conus_mask_cache is not None:
        return _conus_mask_cache

    import geopandas as gpd
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    import requests

    if raw_dir is None:
        raw_dir = Path(__file__).parent.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    zip_path = raw_dir / "tl_2023_us_state.zip"
    shp_dir  = raw_dir / "tl_2023_us_state"

    if not shp_dir.exists():
        if not zip_path.exists():
            print("  Downloading Census TIGER state boundaries for CONUS mask...")
            resp = requests.get(TIGER_STATES_URL, timeout=120)
            resp.raise_for_status()
            zip_path.write_bytes(resp.content)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(shp_dir)

    shp_file = next(shp_dir.glob("*.shp"))
    states = gpd.read_file(shp_file)

    # Filter to CONUS only
    conus = states[~states["STATEFP"].isin(_NON_CONUS_FIPS)].copy()
    conus = conus.to_crs("EPSG:4326")
    dissolved = conus.dissolve()

    transform = from_bounds(GRID_WEST, GRID_SOUTH, GRID_EAST, GRID_NORTH, GRID_WIDTH, GRID_HEIGHT)
    shapes = [(geom, 1) for geom in dissolved.geometry if geom is not None]
    mask = rasterize(
        shapes,
        out_shape=(GRID_HEIGHT, GRID_WIDTH),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    ).astype(bool)

    _conus_mask_cache = mask
    print(f"  CONUS land mask: {mask.sum()} of {mask.size} cells are land")
    return mask

# Common grid parameters
GRID_WEST = -125.0
GRID_SOUTH = 24.5
GRID_EAST = -66.5
GRID_NORTH = 49.5
GRID_RES = 0.05  # degrees (~5km)

GRID_WIDTH = int((GRID_EAST - GRID_WEST) / GRID_RES)   # 1170
GRID_HEIGHT = int((GRID_NORTH - GRID_SOUTH) / GRID_RES)  # 500

NODATA = np.float32("nan")

# Output directory
PUBLIC_DATA_DIR = Path(__file__).parent.parent.parent / "public" / "data"


def get_grid_coords() -> tuple[np.ndarray, np.ndarray]:
    """Return (lons, lats) arrays for the center of each grid cell."""
    lons = np.linspace(GRID_WEST + GRID_RES / 2, GRID_EAST - GRID_RES / 2, GRID_WIDTH)
    lats = np.linspace(GRID_NORTH - GRID_RES / 2, GRID_SOUTH + GRID_RES / 2, GRID_HEIGHT)
    return lons, lats


def write_score_grid(data: np.ndarray, name: str, raw_dir: Path | None = None):
    """Write a score grid as Float32Array binary + JSON metadata.

    Automatically applies the CONUS land mask — cells outside the continental
    US boundary are set to NaN so they render as transparent.
    """
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

    assert data.shape == (GRID_HEIGHT, GRID_WIDTH), f"Expected ({GRID_HEIGHT}, {GRID_WIDTH}), got {data.shape}"

    # Apply CONUS land mask: set ocean / outside-US cells to NaN
    mask = get_conus_land_mask(raw_dir)
    data = data.copy()
    data[~mask] = np.nan

    bin_path = PUBLIC_DATA_DIR / f"{name}-score.bin"
    json_path = PUBLIC_DATA_DIR / f"{name}-score.json"

    data.astype(np.float32).tofile(bin_path)

    meta = {
        "width": GRID_WIDTH,
        "height": GRID_HEIGHT,
        "originX": GRID_WEST,
        "originY": GRID_NORTH,
        "pixelWidth": GRID_RES,
        "pixelHeight": -GRID_RES,
        "nodata": None,  # NaN used for nodata
    }
    with open(json_path, "w") as f:
        json.dump(meta, f)

    valid = np.count_nonzero(~np.isnan(data))
    print(f"  Score grid '{name}': {bin_path.stat().st_size / 1e6:.1f} MB, {valid}/{data.size} valid cells")


def distance_score_grid(
    points: np.ndarray,
    weights: np.ndarray | None = None,
    decay_km: float = 20.0,
    higher_is_better: bool = True,
    max_km: float | None = None,
) -> np.ndarray:
    """
    Compute distance-based score grid from point locations.

    Args:
        points: (N, 2) array of (lon, lat)
        weights: (N,) array of quality weights (0-1), or None for uniform
        decay_km: Distance decay in km (half-life-ish)
        higher_is_better: If True, close = high score. If False, close = low score (e.g. power plants).
        max_km: Maximum distance to nearest point before marking cell as NaN.
                Defaults to decay_km * 10. Prevents artificial scores in ocean/border areas.

    Returns:
        (GRID_HEIGHT, GRID_WIDTH) float32 array of 0-1 scores
    """
    lons, lats = get_grid_coords()
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    # Approximate km conversion at mid-CONUS latitude (~37°)
    km_per_deg_lon = 111.32 * np.cos(np.radians(37.0))
    km_per_deg_lat = 110.57

    # Build KDTree in km space
    pts_km = np.column_stack([
        points[:, 0] * km_per_deg_lon,
        points[:, 1] * km_per_deg_lat,
    ])
    tree = cKDTree(pts_km)

    # Query grid points
    grid_km = np.column_stack([
        lon_grid.ravel() * km_per_deg_lon,
        lat_grid.ravel() * km_per_deg_lat,
    ])

    # Find nearest K points and compute weighted score
    k = min(5, len(points))
    distances, indices = tree.query(grid_km, k=k)

    if k == 1:
        distances = distances[:, np.newaxis]
        indices = indices[:, np.newaxis]

    if weights is None:
        weights = np.ones(len(points))

    # Exponential decay
    decay_factor = np.exp(-distances / decay_km)  # (N_grid, k)
    point_weights = weights[indices]  # (N_grid, k)

    # Weighted score: sum of (decay * point_weight) / sum of decay
    numerator = np.sum(decay_factor * point_weights, axis=1)
    denominator = np.sum(decay_factor, axis=1)
    score = numerator / np.maximum(denominator, 1e-10)

    if not higher_is_better:
        # Invert: far from bad things = good
        score = 1.0 - score

    score = np.clip(score, 0, 1)

    # Mark cells too far from any data point as NaN (ocean/border areas)
    if max_km is None:
        max_km = decay_km * 10
    nearest_dist = distances[:, 0]
    score[nearest_dist > max_km] = np.nan

    return score.reshape(GRID_HEIGHT, GRID_WIDTH).astype(np.float32)


def rasterize_polygons_to_grid(
    gdf,
    value_col: str,
    fill_value: float = 0.5,
) -> np.ndarray:
    """
    Rasterize a polygon GeoDataFrame to the common grid.

    Args:
        gdf: GeoDataFrame with geometry and value column
        value_col: Column name containing the score value (0-1)
        fill_value: Value for cells not covered by any polygon

    Returns:
        (GRID_HEIGHT, GRID_WIDTH) float32 array
    """
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds

    transform = from_bounds(GRID_WEST, GRID_SOUTH, GRID_EAST, GRID_NORTH, GRID_WIDTH, GRID_HEIGHT)

    # Create shapes iterator
    shapes = [(geom, val) for geom, val in zip(gdf.geometry, gdf[value_col]) if geom is not None]

    grid = rasterize(
        shapes,
        out_shape=(GRID_HEIGHT, GRID_WIDTH),
        transform=transform,
        fill=fill_value,
        dtype=np.float32,
    )

    return grid.astype(np.float32)


def resample_raster_to_grid(raster_path: str | Path) -> np.ndarray:
    """
    Resample an existing raster to the common grid using GDAL.

    Returns the raw values (not yet normalized).
    """
    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_bounds

    dst_transform = from_bounds(GRID_WEST, GRID_SOUTH, GRID_EAST, GRID_NORTH, GRID_WIDTH, GRID_HEIGHT)

    with rasterio.open(raster_path) as src:
        dst = np.empty((GRID_HEIGHT, GRID_WIDTH), dtype=np.float32)
        reproject(
            source=src.read(1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )

    return dst


def write_score_geotiff(data: np.ndarray, output_path: Path):
    """Write a score grid (0-1 float32) as a single-band GeoTIFF.

    Values are scaled to 0-200 as uint8 (0=worst, 200=best, 255=nodata).
    """
    import rasterio
    from rasterio.transform import from_bounds

    assert data.shape == (GRID_HEIGHT, GRID_WIDTH)

    transform = from_bounds(GRID_WEST, GRID_SOUTH, GRID_EAST, GRID_NORTH, GRID_WIDTH, GRID_HEIGHT)

    # Scale 0-1 float to 0-200 uint8 (reserve 255 for nodata)
    scaled = np.round(data * 200).astype(np.float32)
    scaled[np.isnan(data)] = 255
    scaled = scaled.astype(np.uint8)

    with rasterio.open(
        output_path, "w",
        driver="GTiff",
        width=GRID_WIDTH,
        height=GRID_HEIGHT,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        nodata=255,
        compress="deflate",
    ) as dst:
        dst.write(scaled, 1)

    print(f"  Score GeoTIFF: {output_path}")


def score_to_raster_pmtiles(
    score_data: np.ndarray,
    name: str,
    color_ramp: str,
    output_dir: Path,
    zoom_range: str = "3-10",
):
    """Convert a score grid to colorized raster PMTiles.

    Args:
        score_data: (GRID_HEIGHT, GRID_WIDTH) float32 array of 0-1 scores
        name: Layer name (used for file naming)
        color_ramp: GDAL color-relief text (values mapped to 0-200 uint8 scale)
        output_dir: Directory for intermediate and output files
        zoom_range: Zoom range for gdal2tiles (e.g. "3-10")
    """
    from utils import copy_to_public

    tif_path = output_dir / f"{name}-score.tif"
    write_score_geotiff(score_data, tif_path)

    # Colorize
    color_file = output_dir / f"{name}_colors.txt"
    color_file.write_text(color_ramp)

    colored_vrt = output_dir / f"{name}_colored.vrt"
    print(f"  Colorizing {name}...")
    subprocess.run(
        [
            "gdaldem", "color-relief",
            str(tif_path), str(color_file), str(colored_vrt),
            "-alpha", "-of", "VRT", "-nearest_color_entry",
        ],
        check=True,
    )

    # Tile
    tiles_dir = output_dir / f"{name}_tiles"
    print(f"  Tiling {name}...")
    subprocess.run(
        [
            "gdal2tiles.py",
            "-z", zoom_range,
            "--processes=4",
            "-r", "near",
            str(colored_vrt),
            str(tiles_dir),
        ],
        check=True,
    )

    # XYZ tiles -> MBTiles -> PMTiles
    mbtiles_path = output_dir / f"{name}.mbtiles"
    _xyz_to_mbtiles(tiles_dir, mbtiles_path, name)

    pmtiles_path = output_dir / f"{name}.pmtiles"
    print(f"  Converting to PMTiles...")
    subprocess.run(
        ["pmtiles", "convert", str(mbtiles_path), str(pmtiles_path)],
        check=True,
    )
    copy_to_public(pmtiles_path)
    print(f"  Raster PMTiles: {pmtiles_path}")


def _xyz_to_mbtiles(tiles_dir: Path, mbtiles_path: Path, name: str):
    """Convert XYZ tile directory to MBTiles."""
    if mbtiles_path.exists():
        mbtiles_path.unlink()

    conn = sqlite3.connect(str(mbtiles_path))
    conn.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    conn.execute(
        "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, "
        "tile_row INTEGER, tile_data BLOB)"
    )
    conn.execute("INSERT INTO metadata VALUES ('name', ?)", (name,))
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
                if tile_file.suffix != ".png":
                    continue
                y = int(tile_file.stem)
                tms_y = (1 << z) - 1 - y
                conn.execute(
                    "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                    (z, x, tms_y, tile_file.read_bytes()),
                )
                count += 1

    conn.execute(
        "CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)"
    )
    conn.commit()
    conn.close()
    print(f"  MBTiles: {count} tiles")
