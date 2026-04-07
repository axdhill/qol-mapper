#!/usr/bin/env python3
"""
Thunderstorm incidence layer.

Uses GHCN-Daily weather-type WT03 ("thunder observed") station records to
compute mean annual thunderstorm days per station (1991-2020), then
interpolates to the CONUS 0.05° score grid.

This is unbiased by population density: every CONUS weather station
contributes equally, regardless of how many people live nearby.

Scoring: more thunderstorm days = higher score (per user preference).
  0   days/yr → score 0.0  (Pacific coast / desert SW)
  100 days/yr → score 1.0  (central Florida, highest in CONUS)

Usage:
    python process_thunderstorms.py
"""

import gzip
import re
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from score_grid import (
    GRID_EAST,
    GRID_HEIGHT,
    GRID_NORTH,
    GRID_SOUTH,
    GRID_WEST,
    GRID_WIDTH,
    get_grid_coords,
    write_score_grid,
    score_to_raster_pmtiles,
)
from utils import OUTPUT_DIR, RAW_DIR, ensure_dirs

GHCN_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
STATIONS_URL  = f"{GHCN_BASE}/ghcnd-stations.txt"
INVENTORY_URL = f"{GHCN_BASE}/ghcnd-inventory.txt"
STATION_DLY   = f"{GHCN_BASE}/all/{{station_id}}.dly"

ANALYSIS_START = 1991
ANALYSIS_END   = 2020
MIN_YEARS      = 10   # require ≥10 years of WT03 records to use a station

MAX_DAYS_PER_YEAR = 100.0

COLOR_RAMP = """\
0   240 248 255 200
30  160 200 230 200
60   80 150 210 200
100  30  90 185 200
140  10  50 160 200
175   5  20 120 200
200   2   5  80 200
nv    0   0   0   0
"""


# ---------------------------------------------------------------------------
# Station metadata
# ---------------------------------------------------------------------------

def load_station_metadata() -> pd.DataFrame:
    """Parse GHCN-Daily ghcnd-stations.txt (fixed-width)."""
    path = RAW_DIR / "ghcnd-stations.txt"
    if not path.exists():
        print("  Downloading station inventory...")
        resp = requests.get(STATIONS_URL, timeout=120)
        resp.raise_for_status()
        path.write_bytes(resp.content)

    rows = []
    for line in path.read_text(encoding="latin-1").splitlines():
        if len(line) < 38:
            continue
        rows.append({
            "station": line[0:11].strip(),
            "lat":     float(line[12:20]),
            "lon":     float(line[21:30]),
            "state":   line[38:40].strip(),
        })
    return pd.DataFrame(rows)


def load_inventory() -> pd.DataFrame:
    """Parse GHCN-Daily ghcnd-inventory.txt (space-delimited)."""
    path = RAW_DIR / "ghcnd-inventory.txt"
    if not path.exists():
        print("  Downloading element inventory...")
        resp = requests.get(INVENTORY_URL, timeout=120)
        resp.raise_for_status()
        path.write_bytes(resp.content)

    rows = []
    for line in path.read_text(encoding="latin-1").splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        rows.append({
            "station":   parts[0],
            "element":   parts[3],
            "firstyear": int(parts[4]),
            "lastyear":  int(parts[5]),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Identify usable stations
# ---------------------------------------------------------------------------

def find_thunder_stations(stations: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Return CONUS station metadata where WT03 covers at least MIN_YEARS of 1991-2020."""
    # WT03 inventory rows that overlap with our analysis window
    wt03 = inventory[
        (inventory["element"] == "WT03") &
        (inventory["firstyear"] <= ANALYSIS_END) &
        (inventory["lastyear"]  >= ANALYSIS_START)
    ].copy()

    # Clip to analysis window and require minimum coverage
    wt03["overlap"] = (
        wt03["lastyear"].clip(upper=ANALYSIS_END) -
        wt03["firstyear"].clip(lower=ANALYSIS_START) + 1
    )
    wt03 = wt03[wt03["overlap"] >= MIN_YEARS]

    # Join with station coordinates; keep only CONUS bounding box
    merged = wt03.merge(stations, on="station")
    conus = merged[
        (merged["lon"] >= GRID_WEST) & (merged["lon"] <= GRID_EAST) &
        (merged["lat"] >= GRID_SOUTH) & (merged["lat"] <= GRID_NORTH)
    ].copy()

    print(f"  {len(conus)} CONUS stations with WT03 coverage ≥ {MIN_YEARS} years")
    return conus[["station", "lat", "lon"]].drop_duplicates("station")


# ---------------------------------------------------------------------------
# Per-station thunder-day computation
# ---------------------------------------------------------------------------

def parse_dly_wt03(content: str) -> float | None:
    """
    Parse a GHCN DLY file and return mean annual WT03 days (1991-2020).

    DLY format: each line = 21-char header + 31 × 8-char day values.
    Header: ID(11) YEAR(4) MONTH(2) ELEMENT(4)
    Day:    VALUE(5) M_FLAG(1) Q_FLAG(1) S_FLAG(1)
    WT03 VALUE = 1 means thunder observed that day; -9999 = missing.
    """
    year_counts: dict[int, int] = {}

    for line in content.splitlines():
        if len(line) < 21 or line[17:21] != "WT03":
            continue
        year = int(line[11:15])
        if year < ANALYSIS_START or year > ANALYSIS_END:
            continue
        count = 0
        for d in range(31):
            offset = 21 + d * 8
            if offset + 5 > len(line):
                break
            val_str = line[offset:offset + 5].strip()
            if val_str and val_str != "-9999":
                try:
                    if int(val_str) == 1:
                        count += 1
                except ValueError:
                    pass
        year_counts[year] = year_counts.get(year, 0) + count

    if len(year_counts) < MIN_YEARS:
        return None
    return sum(year_counts.values()) / len(year_counts)


def fetch_station_thunder_days(station_id: str) -> float | None:
    """Download (cached) DLY file and return mean annual WT03 days."""
    cache = RAW_DIR / "ghcn_dly" / f"{station_id}.dly"
    cache.parent.mkdir(exist_ok=True)

    if not cache.exists():
        url = STATION_DLY.format(station_id=station_id)
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            return None
        cache.write_bytes(resp.content)

    return parse_dly_wt03(cache.read_text(encoding="latin-1"))


# ---------------------------------------------------------------------------
# Spatial interpolation
# ---------------------------------------------------------------------------

def interpolate_to_grid(lons: np.ndarray, lats: np.ndarray, values: np.ndarray) -> np.ndarray:
    """
    Interpolate scattered station values to the CONUS score grid.

    Uses linear triangulation (scipy griddata) — robust and fast for
    meteorological data with ~500–1500 well-distributed stations.
    """
    from scipy.interpolate import griddata

    grid_lons, grid_lats = get_grid_coords()
    lon_grid, lat_grid = np.meshgrid(grid_lons, grid_lats)

    points = np.column_stack([lons, lats])
    grid_points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])

    interp = griddata(points, values, grid_points, method="linear")

    # Fill small gaps outside the convex hull with nearest-neighbour
    mask_nan = np.isnan(interp)
    if mask_nan.any():
        nearest = griddata(points, values, grid_points[mask_nan], method="nearest")
        interp[mask_nan] = nearest

    return interp.reshape(GRID_HEIGHT, GRID_WIDTH).astype(np.float32)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_dirs()
    print("=== Processing Thunderstorm Incidence (GHCN-Daily WT03) ===")
    print(f"  Analysis window: {ANALYSIS_START}–{ANALYSIS_END}, min {MIN_YEARS} years")

    stations  = load_station_metadata()
    inventory = load_inventory()
    target    = find_thunder_stations(stations, inventory)

    print(f"  Downloading/reading DLY files for {len(target)} stations...")
    records = []
    for i, row in enumerate(target.itertuples(), 1):
        if i % 100 == 0:
            print(f"    {i}/{len(target)}...")
        days = fetch_station_thunder_days(row.station)
        if days is not None:
            records.append({"lon": row.lon, "lat": row.lat, "thunder_days": days})

    if not records:
        raise RuntimeError("No station data loaded — check URLs and network access")

    df = pd.DataFrame(records)
    print(
        f"  {len(df)} stations with valid data; "
        f"range {df['thunder_days'].min():.1f}–{df['thunder_days'].max():.1f} days/yr, "
        f"median {df['thunder_days'].median():.1f}"
    )

    print("  Interpolating to CONUS grid...")
    thunder_grid = interpolate_to_grid(
        df["lon"].values, df["lat"].values, df["thunder_days"].values
    )
    thunder_grid = np.clip(thunder_grid, 0.0, None)

    # Score: more days = higher score
    score = np.clip(thunder_grid / MAX_DAYS_PER_YEAR, 0.0, 1.0).astype(np.float32)

    write_score_grid(score, "thunderstorms")

    print("  Generating PMTiles...")
    score_to_raster_pmtiles(score, "thunderstorms", COLOR_RAMP, OUTPUT_DIR)

    print("Done!")


if __name__ == "__main__":
    main()
