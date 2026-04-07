#!/usr/bin/env python3
"""
Generate normalized 0-1 score grids for all available data layers.

Each grid covers CONUS at 0.05° resolution (1170×500) and is written as
a Float32Array binary file + JSON metadata to public/data/.

For continuous data (PM2.5, noise): resample and normalize.
For point data (schools, universities, power plants): compute distance-weighted scores.
For polygon data (climate vuln, home prices): rasterize and normalize.
"""

import json
from pathlib import Path

import numpy as np

from score_grid import (
    GRID_HEIGHT,
    GRID_WIDTH,
    GRID_WEST,
    GRID_SOUTH,
    GRID_EAST,
    GRID_NORTH,
    get_grid_coords,
    distance_score_grid,
    rasterize_polygons_to_grid,
    resample_raster_to_grid,
    write_score_grid,
)
from utils import OUTPUT_DIR, RAW_DIR, ensure_dirs

PIPELINE_DIR = Path(__file__).parent.parent


def generate_pm25_score():
    """PM2.5: lower is better. Score = 1 - (pm25 - 2) / 18."""
    tif = OUTPUT_DIR / "pm25.tif"
    if not tif.exists():
        print("  Skipping PM2.5 (no GeoTIFF found)")
        return

    print("  Generating PM2.5 score grid...")
    raw = resample_raster_to_grid(tif)
    # Normalize: 2 ug/m3 = score 1.0, 20 ug/m3 = score 0.0
    score = 1.0 - (raw - 2.0) / 18.0
    score = np.clip(score, 0, 1)
    score[np.isnan(raw)] = np.nan
    write_score_grid(score.astype(np.float32), "pm25")


def generate_noise_score():
    """Noise: lower is better. Score = 1 - (dB - 30) / 45."""
    tif = OUTPUT_DIR / "noise.tif"
    if not tif.exists():
        print("  Skipping noise (no GeoTIFF found)")
        return

    print("  Generating noise score grid...")
    raw = resample_raster_to_grid(tif)
    # Normalize: 30 dB = score 1.0, 75 dB = score 0.0
    score = 1.0 - (raw - 30.0) / 45.0
    score = np.clip(score, 0, 1)
    score[np.isnan(raw)] = np.nan
    write_score_grid(score.astype(np.float32), "noise")


def generate_schools_score():
    """Schools: close to quality schools = high score."""
    geojson_path = OUTPUT_DIR / "school-quality.geojson"
    if not geojson_path.exists():
        print("  Skipping schools (no GeoJSON found)")
        return

    print("  Generating schools score grid...")
    with open(geojson_path) as f:
        data = json.load(f)

    points = []
    weights = []
    for feat in data["features"]:
        coords = feat["geometry"]["coordinates"]
        qs = feat["properties"].get("quality_score", 0.5)
        points.append(coords)
        weights.append(qs)

    points = np.array(points)
    weights = np.array(weights)
    print(f"    {len(points)} school points")

    score = distance_score_grid(points, weights, decay_km=10.0, higher_is_better=True)
    write_score_grid(score, "schools")


def generate_universities_score():
    """R1 + R2 research universities: linear distance decay, combined via max().

    R1: Excellent (1.0) within 2 miles, Poor (0.0) beyond 120 miles.
    R2: Excellent (0.9) within 2 miles, Poor (0.0) beyond 60 miles.
    Score = max(r1_score, r2_score) per cell.
    """
    from scipy.spatial import cKDTree

    geojson_path = OUTPUT_DIR / "university-quality.geojson"
    if not geojson_path.exists():
        print("  Skipping universities (run process_universities.py first)")
        return

    print("  Generating R1+R2 university distance score grid...")
    with open(geojson_path) as f:
        data = json.load(f)

    r1_pts = np.array([
        feat["geometry"]["coordinates"]
        for feat in data["features"]
        if feat["properties"].get("tier") == "R1"
    ])
    r2_pts = np.array([
        feat["geometry"]["coordinates"]
        for feat in data["features"]
        if feat["properties"].get("tier") == "R2"
    ])
    print(f"    {len(r1_pts)} R1 universities, {len(r2_pts)} R2 universities")

    lons, lats = get_grid_coords()
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    # Approximate km/degree at mid-CONUS latitude
    km_per_deg_lon = 111.32 * np.cos(np.radians(37.0))
    km_per_deg_lat = 110.57

    grid_km = np.column_stack([lon_grid.ravel() * km_per_deg_lon, lat_grid.ravel() * km_per_deg_lat])

    near_km = 3.219   # 2 miles

    # R1: 0 → 1.0, 193.1 km (120 mi) → 0.0
    r1_far_km = 193.121
    r1_pts_km = np.column_stack([r1_pts[:, 0] * km_per_deg_lon, r1_pts[:, 1] * km_per_deg_lat])
    dist_r1, _ = cKDTree(r1_pts_km).query(grid_km, k=1)
    dist_r1 = dist_r1.reshape(GRID_HEIGHT, GRID_WIDTH)
    score_r1 = np.clip(1.0 - (dist_r1 - near_km) / (r1_far_km - near_km), 0.0, 1.0)

    # R2: 0 → 0.9, 96.6 km (60 mi) → 0.0
    r2_far_km = 96.561
    r2_pts_km = np.column_stack([r2_pts[:, 0] * km_per_deg_lon, r2_pts[:, 1] * km_per_deg_lat])
    dist_r2, _ = cKDTree(r2_pts_km).query(grid_km, k=1)
    dist_r2 = dist_r2.reshape(GRID_HEIGHT, GRID_WIDTH)
    score_r2 = np.clip(0.9 * (1.0 - (dist_r2 - near_km) / (r2_far_km - near_km)), 0.0, 0.9)

    score = np.maximum(score_r1, score_r2)
    write_score_grid(score.astype(np.float32), "universities")


def generate_power_plants_score():
    """Industrial hazards: far from polluting plants and industrial emitters = high score.

    Facilities are weighted by combined air emission intensity.
    Large emitters have a wider danger radius (up to 80 km).
    """
    geojson_path = OUTPUT_DIR / "power-plants.geojson"
    if not geojson_path.exists():
        print("  Skipping industrial hazards (no GeoJSON found)")
        return

    print("  Generating industrial hazards score grid...")
    with open(geojson_path) as f:
        data = json.load(f)

    points = []
    weights = []
    for feat in data["features"]:
        coords = feat["geometry"]["coordinates"]
        ew = feat["properties"].get("emission_weight", 0) or 0
        if ew <= 0:
            ew = 0.1  # minimum presence penalty for any listed facility
        # Log-scale weight: a 10M-ton emitter isn't 10k× worse than a 1k-ton emitter
        w = max(0.05, min(1.0, (np.log1p(ew) / np.log1p(1_000_000))))
        points.append(coords)
        weights.append(w)

    if not points:
        print("    No industrial hazard points found")
        return

    points = np.array(points)
    weights = np.array(weights)
    print(f"    {len(points)} industrial hazard facilities")

    # Decay radius ~30 km: most air pollution health impacts within 30 km
    score = distance_score_grid(points, weights, decay_km=30.0, higher_is_better=False)
    write_score_grid(score, "power-plants")


def generate_climate_vulnerability_score():
    """Climate vulnerability: low hazard risk = high QoL score."""
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "climate-vulnerability.geojson"
    if not geojson_path.exists():
        print("  Skipping climate vulnerability (no GeoJSON found)")
        return

    print("  Generating climate vulnerability score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} county polygons")

    # risk_score is 0-1 where 1 = highest hazard risk.
    # Invert: low risk = high QoL score.
    gdf["score"] = 1.0 - gdf["risk_score"].fillna(0.5)
    gdf["score"] = gdf["score"].clip(0, 1)

    score = rasterize_polygons_to_grid(gdf, "score", fill_value=0.5)
    write_score_grid(score, "climate-vulnerability")


def generate_home_prices_score():
    """Home prices: lower prices = higher affordability score."""
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "home-prices.geojson"
    if not geojson_path.exists():
        print("  Skipping home prices (no GeoJSON found)")
        return

    print("  Generating home prices score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} zip code polygons")

    # Log-scale normalization: $100k = 1.0, $1M = 0.0
    log_min = np.log(100_000)
    log_max = np.log(1_000_000)
    prices = gdf["median_price"].fillna(300_000).clip(100_000, 1_000_000)
    gdf["score"] = 1.0 - (np.log(prices) - log_min) / (log_max - log_min)
    gdf["score"] = gdf["score"].clip(0, 1).astype(np.float32)

    score = rasterize_polygons_to_grid(gdf, "score", fill_value=0.5)
    write_score_grid(score, "home-prices")


def generate_protected_areas_score():
    """Protected areas: distance from park boundaries.

    Inside a park = 1.0. Score decays linearly to 0 at 100 km (~62 miles)
    from the nearest park boundary.
    """
    geojson_path = OUTPUT_DIR / "protected-areas.geojson"
    if not geojson_path.exists():
        print("  Skipping protected areas (no GeoJSON found)")
        return

    print("  Generating protected areas score grid...")
    import geopandas as gpd
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    from scipy.ndimage import distance_transform_edt

    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} protected area polygons")

    # Rasterize park boundaries to a binary mask (1 = inside park)
    transform = from_bounds(
        GRID_WEST, GRID_SOUTH, GRID_EAST, GRID_NORTH, GRID_WIDTH, GRID_HEIGHT
    )
    shapes = [
        (geom, 1)
        for geom in gdf.geometry
        if geom is not None and not geom.is_empty
    ]
    park_mask = rasterize(
        shapes,
        out_shape=(GRID_HEIGHT, GRID_WIDTH),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )

    # For each outside pixel, compute distance (in pixels) to nearest park pixel
    outside = (park_mask == 0).astype(np.uint8)
    dist_pixels = distance_transform_edt(outside)

    # 0.05° ≈ 5.5 km at CONUS mid-latitudes
    km_per_pixel = 5.5
    dist_km = dist_pixels * km_per_pixel

    # Linear decay: 0 km → 1.0, 100 km (~62 mi) → 0.0
    max_km = 100.0
    score = np.maximum(0.0, 1.0 - dist_km / max_km)

    # Pixels inside parks are always 1.0
    score[park_mask == 1] = 1.0

    write_score_grid(score.astype(np.float32), "protected-areas")


def generate_crime_score():
    """Homicide rate: low rate = high score.

    Data is homicides per 100k from County Health Rankings.
    0/100k = score 1.0 (safest), 20+/100k = score 0.0.
    Counties without data get the median score.
    """
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "crime.geojson"
    if not geojson_path.exists():
        print("  Skipping crime (no GeoJSON found)")
        return

    print("  Generating crime score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} county polygons")

    median_rate = float(gdf["crime_rate"].median())
    rates = gdf["crime_rate"].fillna(median_rate).clip(0, 20)
    gdf["score"] = (1.0 - rates / 20.0).clip(0, 1).astype(np.float32)

    median_score = float(1.0 - min(median_rate, 20) / 20.0)
    score = rasterize_polygons_to_grid(gdf, "score", fill_value=median_score)
    write_score_grid(score, "crime")


def generate_voting_dem_score():
    """Democratic vote share by county."""
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "voting-dem.geojson"
    if not geojson_path.exists():
        print("  Skipping voting-dem (no GeoJSON found)")
        return

    print("  Generating Democratic vote share score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} county polygons")

    gdf["score"] = gdf["dem_share"].fillna(0.5).clip(0, 1).astype(np.float32)
    score = rasterize_polygons_to_grid(gdf, "score", fill_value=0.5)
    write_score_grid(score, "voting-dem")


def generate_voting_gop_score():
    """Republican vote share by county."""
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "voting-gop.geojson"
    if not geojson_path.exists():
        print("  Skipping voting-gop (no GeoJSON found)")
        return

    print("  Generating Republican vote share score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} county polygons")

    gdf["score"] = gdf["gop_share"].fillna(0.5).clip(0, 1).astype(np.float32)
    score = rasterize_polygons_to_grid(gdf, "score", fill_value=0.5)
    write_score_grid(score, "voting-gop")


def generate_grocery_score():
    """Grocery stores: close to grocery = high score."""
    geojson_path = OUTPUT_DIR / "grocery.geojson"
    if not geojson_path.exists():
        print("  Skipping grocery (no GeoJSON found)")
        return

    print("  Generating grocery score grid...")
    with open(geojson_path) as f:
        data = json.load(f)

    points = []
    weights = []
    for feat in data["features"]:
        coords = feat["geometry"]["coordinates"]
        w = feat["properties"].get("weight", 0.7)
        points.append(coords)
        weights.append(w)

    if not points:
        print("    No grocery points found")
        return

    points = np.array(points)
    weights = np.array(weights)
    print(f"    {len(points)} grocery store points")

    score = distance_score_grid(points, weights, decay_km=5.0, higher_is_better=True)
    write_score_grid(score, "grocery")


def generate_transit_score():
    """Transit/walkability: high walkability = high score."""
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "transit.geojson"
    if not geojson_path.exists():
        print("  Skipping transit (no GeoJSON found)")
        return

    print("  Generating transit/walkability score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} block group polygons")

    gdf["score"] = gdf["walkability"].fillna(0.5).clip(0, 1).astype(np.float32)
    score = rasterize_polygons_to_grid(gdf, "score", fill_value=0.5)
    write_score_grid(score, "transit")


def generate_rainfall_score():
    """Annual rainfall: log-normalized total precipitation.

    Source: output/rainfall.tif (produced by process_rainfall.py).
    100 mm/yr → 0.0, 2500 mm/yr → 1.0 (log scale).
    """
    tif = OUTPUT_DIR / "rainfall.tif"
    if not tif.exists():
        print("  Skipping rainfall (run process_rainfall.py first)")
        return

    print("  Generating rainfall score grid...")
    raw = resample_raster_to_grid(tif)

    prec_min, prec_max = 100.0, 2500.0
    log_min = np.log1p(prec_min)
    log_max = np.log1p(prec_max)
    score = np.clip(
        (np.log1p(np.maximum(raw, 0.0)) - log_min) / (log_max - log_min),
        0.0, 1.0,
    ).astype(np.float32)
    score[np.isnan(raw)] = np.nan
    write_score_grid(score, "rainfall")


def generate_ticks_score():
    """Tick-borne illness: low Lyme rate = high score.

    Rate (avg annual Lyme cases per 100k, 2018-2022):
      0/100k  → score 1.0
      50+/100k → score 0.0
    """
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "ticks.geojson"
    if not geojson_path.exists():
        print("  Skipping ticks (run process_ticks.py first)")
        return

    print("  Generating tick-borne illness score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} county polygons")

    # Score: lower rate is better; 50 cases/100k/yr = 0.0
    rates = gdf["lyme_rate"].fillna(0).clip(0, 50)
    gdf["score"] = (1.0 - rates / 50.0).clip(0, 1).astype(np.float32)

    score = rasterize_polygons_to_grid(gdf, "score", fill_value=1.0)
    write_score_grid(score, "ticks")


def generate_topography_score():
    """Terrain ruggedness: log-scaled local elevation std dev.

    Source: output/topography_stddev.tif (produced by process_topography.py).
    std_dev ≈ 0 m → score 0.0 (flat), std_dev ≈ 1500 m → score 1.0 (very rugged).
    """
    tif = OUTPUT_DIR / "topography_stddev.tif"
    if not tif.exists():
        print("  Skipping topography (run process_topography.py first)")
        return

    print("  Generating topography score grid...")
    raw = resample_raster_to_grid(tif)

    # Mask nodata sentinel written by process_topography.py
    raw = np.where(raw < -9000, np.nan, raw)

    max_std_dev = 1500.0
    score = np.log1p(np.maximum(raw, 0.0)) / np.log1p(max_std_dev)
    score = np.clip(score, 0.0, 1.0).astype(np.float32)
    score[np.isnan(raw)] = np.nan
    write_score_grid(score, "topography")


def generate_temperateness_score():
    """Temperateness: penalty for hot summers, cold winters, and high seasonality.

    Three equal components (°C):
      heat_score:  1.0 if tmax ≤ 21.1°C (70°F),  0.0 if tmax ≥ 37.8°C (100°F)
      cold_score:  1.0 if tmin ≥ 21.1°C (70°F),  0.0 if tmin ≤ -28.9°C (-20°F)
      range_score: 1.0 at 0°C annual swing,        0.0 at 50°C swing

    The range_score penalises continental and high-elevation climates (large
    swings between summer highs and winter lows) that the heat/cold components
    alone under-penalise.
    """
    tmax_tif = OUTPUT_DIR / "tmax_hottest.tif"
    tmin_tif = OUTPUT_DIR / "tmin_coldest.tif"
    if not tmax_tif.exists() or not tmin_tif.exists():
        print("  Skipping temperateness (run process_temperateness.py first)")
        return

    print("  Generating temperateness score grid...")
    bio5 = resample_raster_to_grid(tmax_tif)  # hottest month mean daily max (°C)
    bio6 = resample_raster_to_grid(tmin_tif)  # coldest month mean daily min (°C)

    # Thresholds in °C (70°F = 21.1°C, 100°F = 37.8°C, -20°F = -28.9°C)
    ideal_c   = 21.1
    max_hot_c = 37.8
    min_cold_c = -28.9

    heat_score  = np.clip((max_hot_c - bio5)  / (max_hot_c  - ideal_c),   0.0, 1.0)
    cold_score  = np.clip((bio6 - min_cold_c) / (ideal_c    - min_cold_c), 0.0, 1.0)
    range_score = np.clip(1.0 - (bio5 - bio6) / 50.0,                     0.0, 1.0)

    score = (heat_score + cold_score + range_score) / 3.0
    score[np.isnan(bio5) | np.isnan(bio6)] = np.nan
    write_score_grid(score.astype(np.float32), "temperateness")


def generate_sunshine_score():
    """Annual solar radiation: proxy for total sunny days per year.

    Source: output/sunshine.tif (produced by process_sunshine.py).
    Linear mapping: 9 000 kJ/m²/day → 0.0, 23 000 kJ/m²/day → 1.0.
    """
    tif = OUTPUT_DIR / "sunshine.tif"
    if not tif.exists():
        print("  Skipping sunshine (run process_sunshine.py first)")
        return

    print("  Generating sunshine score grid...")
    raw = resample_raster_to_grid(tif)

    srad_min, srad_max = 9_000.0, 23_000.0
    score = np.clip((raw - srad_min) / (srad_max - srad_min), 0.0, 1.0).astype(np.float32)
    score[np.isnan(raw)] = np.nan
    write_score_grid(score, "sunshine")


def generate_thunderstorms_score():
    """Thunderstorm incidence: fewer storm days per year = higher score.

    Source: output/thunderstorms.geojson (produced by process_thunderstorms.py).
    0 days/yr → 1.0, 100+ days/yr → 0.0.
    """
    import geopandas as gpd

    geojson_path = OUTPUT_DIR / "thunderstorms.geojson"
    if not geojson_path.exists():
        print("  Skipping thunderstorms (run process_thunderstorms.py first)")
        return

    print("  Generating thunderstorm score grid...")
    gdf = gpd.read_file(geojson_path)
    print(f"    {len(gdf)} county polygons")

    max_days = 100.0
    median_days = float(gdf["thunder_days"].median())
    days = gdf["thunder_days"].fillna(median_days).clip(0, max_days)
    gdf["score"] = (days / max_days).clip(0, 1).astype(np.float32)

    median_score = float(min(median_days, max_days) / max_days)
    score = rasterize_polygons_to_grid(gdf, "score", fill_value=median_score)
    write_score_grid(score, "thunderstorms")


# ---------------------------------------------------------------------------
# Seasonal helpers
# ---------------------------------------------------------------------------

WINTER_MONTHS = [12, 1, 2]   # Dec, Jan, Feb
SUMMER_MONTHS = [6, 7, 8]    # Jun, Jul, Aug


def _load_monthly_prec(months: list[int]) -> np.ndarray | None:
    """Sum WorldClim prec over the given months. Returns None if data missing."""
    prec_dir = RAW_DIR / "wc2.1_2.5m_prec"
    if not prec_dir.exists():
        return None
    stack = []
    for m in months:
        tif = next(iter(sorted(prec_dir.glob(f"*_{m:02d}.tif"))), None)
        if tif is None:
            return None
        stack.append(resample_raster_to_grid(tif))
    arr = np.stack(stack, axis=0)
    total = np.nansum(arr, axis=0).astype(np.float32)
    all_nan = np.all(np.isnan(arr), axis=0)
    total[all_nan] = np.nan
    return total


def _load_monthly_srad(months: list[int]) -> np.ndarray | None:
    """Mean WorldClim srad over the given months. Returns None if data missing."""
    srad_dir = RAW_DIR / "wc2.1_2.5m_srad"
    if not srad_dir.exists():
        return None
    stack = []
    for m in months:
        tif = next(iter(sorted(srad_dir.glob(f"*_{m:02d}.tif"))), None)
        if tif is None:
            return None
        stack.append(resample_raster_to_grid(tif))
    arr = np.stack(stack, axis=0)
    return np.nanmean(arr, axis=0).astype(np.float32)


def _load_monthly_mean_temp(months: list[int]) -> np.ndarray | None:
    """Mean daily temperature (tmax+tmin)/2 averaged over the given months."""
    tmax_dir = RAW_DIR / "wc2.1_2.5m_tmax"
    tmin_dir = RAW_DIR / "wc2.1_2.5m_tmin"
    if not tmax_dir.exists() or not tmin_dir.exists():
        return None
    temps = []
    for m in months:
        tx = next(iter(sorted(tmax_dir.glob(f"*_{m:02d}.tif"))), None)
        tn = next(iter(sorted(tmin_dir.glob(f"*_{m:02d}.tif"))), None)
        if tx is None or tn is None:
            return None
        temps.append((resample_raster_to_grid(tx) + resample_raster_to_grid(tn)) / 2.0)
    arr = np.stack(temps, axis=0)
    return np.nanmean(arr, axis=0).astype(np.float32)


# ---------------------------------------------------------------------------
# Seasonal score generators
# ---------------------------------------------------------------------------

def generate_rainfall_score_winter():
    """Winter (Dec–Feb) precipitation score.

    Uses same log-scale but with seasonal bounds (3-month totals ~25% of annual):
    ~25 mm → 0.0 (arid desert winter),  ~625 mm → 1.0 (very wet, Pacific NW).
    """
    label = "rainfall (winter)"
    print(f"  Generating {label} score grid...")
    prec = _load_monthly_prec(WINTER_MONTHS)
    if prec is None:
        print(f"  Skipping {label} (run process_rainfall.py first to download WorldClim prec)")
        return
    prec_min, prec_max = 25.0, 625.0
    log_min, log_max = np.log1p(prec_min), np.log1p(prec_max)
    score = np.clip(
        (np.log1p(np.maximum(prec, 0.0)) - log_min) / (log_max - log_min),
        0.0, 1.0,
    ).astype(np.float32)
    score[np.isnan(prec)] = np.nan
    write_score_grid(score, "rainfall-winter")


def generate_rainfall_score_summer():
    """Summer (Jun–Aug) precipitation score.

    ~20 mm → 0.0 (California desert summer),  ~600 mm → 1.0 (Gulf coast).
    """
    label = "rainfall (summer)"
    print(f"  Generating {label} score grid...")
    prec = _load_monthly_prec(SUMMER_MONTHS)
    if prec is None:
        print(f"  Skipping {label} (run process_rainfall.py first to download WorldClim prec)")
        return
    prec_min, prec_max = 20.0, 600.0
    log_min, log_max = np.log1p(prec_min), np.log1p(prec_max)
    score = np.clip(
        (np.log1p(np.maximum(prec, 0.0)) - log_min) / (log_max - log_min),
        0.0, 1.0,
    ).astype(np.float32)
    score[np.isnan(prec)] = np.nan
    write_score_grid(score, "rainfall-summer")


def generate_sunshine_score_winter():
    """Winter (Dec–Feb) solar radiation.

    Range: 2 000 kJ/m²/day (dark Pacific NW winter) → 20 000 (Arizona winter).
    """
    label = "sunshine (winter)"
    print(f"  Generating {label} score grid...")
    srad = _load_monthly_srad(WINTER_MONTHS)
    if srad is None:
        print(f"  Skipping {label} (run process_sunshine.py first to download WorldClim srad)")
        return
    srad_min, srad_max = 2_000.0, 20_000.0
    score = np.clip((srad - srad_min) / (srad_max - srad_min), 0.0, 1.0).astype(np.float32)
    score[np.isnan(srad)] = np.nan
    write_score_grid(score, "sunshine-winter")


def generate_sunshine_score_summer():
    """Summer (Jun–Aug) solar radiation.

    Range: 12 000 kJ/m²/day (cloudy NE summer) → 28 000 (desert SW summer).
    """
    label = "sunshine (summer)"
    print(f"  Generating {label} score grid...")
    srad = _load_monthly_srad(SUMMER_MONTHS)
    if srad is None:
        print(f"  Skipping {label} (run process_sunshine.py first to download WorldClim srad)")
        return
    srad_min, srad_max = 12_000.0, 28_000.0
    score = np.clip((srad - srad_min) / (srad_max - srad_min), 0.0, 1.0).astype(np.float32)
    score[np.isnan(srad)] = np.nan
    write_score_grid(score, "sunshine-summer")


def generate_temperateness_score_winter():
    """Winter (Dec–Feb) temperature comfort: milder winters score higher.

    Mean daily temp in DJF (°C):
      −15°C → 0.0  (Minneapolis/Fairbanks level)
      +20°C → 1.0  (Miami / Southern California level)
    Linear, no seasonality penalty — this is purely "how warm is winter."
    """
    label = "temperateness (winter)"
    print(f"  Generating {label} score grid...")
    t = _load_monthly_mean_temp(WINTER_MONTHS)
    if t is None:
        print(f"  Skipping {label} (run process_temperateness.py first)")
        return
    # clip((t - (-15)) / (20 - (-15)), 0, 1) = clip((t + 15) / 35, 0, 1)
    score = np.clip((t + 15.0) / 35.0, 0.0, 1.0).astype(np.float32)
    score[np.isnan(t)] = np.nan
    write_score_grid(score, "temperateness-winter")


def generate_temperateness_score_summer():
    """Summer (Jun–Aug) temperature comfort: peaks near 22°C (72°F).

    Mean daily temp in JJA (°C):
      ≤  7°C → 0.0  (too cold — no real summer)
      22°C   → 1.0  (ideal — Denver, Chicago, Boston, Pacific Northwest highs)
      ≥ 37°C → 0.0  (too hot — Phoenix, Death Valley level)
    Triangular scoring symmetric around 22°C with ±15°C half-width.
    """
    label = "temperateness (summer)"
    print(f"  Generating {label} score grid...")
    t = _load_monthly_mean_temp(SUMMER_MONTHS)
    if t is None:
        print(f"  Skipping {label} (run process_temperateness.py first)")
        return
    IDEAL = 22.0
    HALF_WIDTH = 15.0  # score = 0 at IDEAL ± HALF_WIDTH
    score = np.clip(1.0 - np.abs(t - IDEAL) / HALF_WIDTH, 0.0, 1.0).astype(np.float32)
    score[np.isnan(t)] = np.nan
    write_score_grid(score, "temperateness-summer")


def main():
    ensure_dirs()
    print("=== Generating Score Grids ===")
    print(f"  Grid: {GRID_WIDTH}x{GRID_HEIGHT} at 0.05° resolution")
    print()

    generate_pm25_score()
    generate_noise_score()
    generate_schools_score()
    generate_universities_score()
    generate_power_plants_score()
    generate_climate_vulnerability_score()
    generate_home_prices_score()
    generate_protected_areas_score()
    generate_crime_score()
    generate_voting_dem_score()
    generate_grocery_score()
    generate_transit_score()
    generate_rainfall_score()
    generate_ticks_score()
    generate_temperateness_score()
    generate_topography_score()
    generate_sunshine_score()
    generate_thunderstorms_score()

    # Seasonal variants (require the same raw WorldClim monthly downloads)
    print()
    print("=== Generating Seasonal Score Grids ===")
    generate_rainfall_score_winter()
    generate_rainfall_score_summer()
    generate_sunshine_score_winter()
    generate_sunshine_score_summer()
    generate_temperateness_score_winter()
    generate_temperateness_score_summer()

    print()
    print("Done! Score grids written to public/data/")


if __name__ == "__main__":
    main()
