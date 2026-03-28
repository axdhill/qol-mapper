#!/usr/bin/env python3
"""
Download and process grocery store data into vector PMTiles and a score grid.

Source: USDA SNAP Retailer Locator
- ~250,000 authorized SNAP retailers with lat/lon and store type
- Filtered to Supermarket, Large Grocery, Medium Grocery

Fallback: OpenStreetMap Overpass API for shop=supermarket tags.

Steps:
1. Download SNAP retailer data (or query Overpass)
2. Filter to grocery-relevant store types
3. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs, CONUS_BOUNDS

# USDA SNAP retailer data
SNAP_URL = "https://usda-fns.hub.arcgis.com/api/download/v1/items/4cff23faea9a4a3f8aa0c393e3e99a05/csv"


def download_snap_data() -> pd.DataFrame:
    """Download SNAP retailer data."""
    import requests

    csv_path = RAW_DIR / "snap_retailers.csv"

    if not csv_path.exists():
        print("  Downloading USDA SNAP retailer data...")
        try:
            resp = requests.get(SNAP_URL, timeout=300, stream=True)
            resp.raise_for_status()
            with open(csv_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            print(f"  Downloaded SNAP data")
        except Exception as e:
            print(f"  SNAP download failed: {e}")
            print("  Falling back to Overpass API...")
            return _download_overpass_groceries()
    else:
        print("  Already have snap_retailers.csv")

    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  Loaded {len(df)} SNAP retailers")
    print(f"  Columns: {list(df.columns)}")

    # Find relevant columns (lat, lon, store type)
    lat_col = lon_col = type_col = name_col = None
    for col in df.columns:
        cl = col.lower()
        if cl in ("latitude", "lat", "y"):
            lat_col = col
        elif cl in ("longitude", "lon", "long", "x"):
            lon_col = col
        elif "store" in cl and "type" in cl:
            type_col = col
        elif cl in ("store_name", "storename", "name"):
            name_col = col

    if lat_col is None or lon_col is None:
        print(f"  Could not find lat/lon columns. Available: {list(df.columns)}")
        print("  Falling back to Overpass API...")
        return _download_overpass_groceries()

    df["lat"] = pd.to_numeric(df[lat_col], errors="coerce")
    df["lon"] = pd.to_numeric(df[lon_col], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    # Filter to CONUS
    df = df[
        (df["lon"] >= CONUS_BOUNDS["west"]) & (df["lon"] <= CONUS_BOUNDS["east"]) &
        (df["lat"] >= CONUS_BOUNDS["south"]) & (df["lat"] <= CONUS_BOUNDS["north"])
    ]

    # Filter to grocery-relevant store types and assign weights
    if type_col:
        print(f"  Store types: {df[type_col].value_counts().head(10).to_dict()}")
        grocery_types = {
            "Supermarket": 1.0,
            "Super Store": 1.0,
            "Large Grocery Store": 0.7,
            "Medium Grocery Store": 0.4,
            "Grocery/Supermarket": 1.0,
        }
        # Case-insensitive matching
        df["store_type_lower"] = df[type_col].str.strip()
        mask = df["store_type_lower"].isin(grocery_types.keys())
        if mask.sum() == 0:
            # Try partial matching
            for gt in grocery_types:
                mask |= df["store_type_lower"].str.contains(gt, case=False, na=False)

        df = df[mask].copy()
        df["weight"] = df["store_type_lower"].map(grocery_types).fillna(0.5)
    else:
        # No type column - use all with default weight
        df["weight"] = 0.7

    if name_col:
        df["name"] = df[name_col]
    else:
        df["name"] = "Grocery Store"

    print(f"  {len(df)} grocery stores in CONUS after filtering")
    return df[["lat", "lon", "weight", "name"]].reset_index(drop=True)


def _download_overpass_groceries() -> pd.DataFrame:
    """Fallback: query OpenStreetMap for supermarkets via Overpass API."""
    import requests

    cache_path = RAW_DIR / "osm_supermarkets.json"

    if not cache_path.exists():
        print("  Querying Overpass API for supermarkets in CONUS...")
        query = """
        [out:json][timeout:300];
        (
          node["shop"="supermarket"](24.5,-125.0,49.5,-66.5);
        );
        out center;
        """
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()
        with open(cache_path, "w") as f:
            json.dump(data, f)
        print(f"  Got {len(data.get('elements', []))} supermarkets")
    else:
        print("  Already have OSM supermarket data")
        with open(cache_path) as f:
            data = json.load(f)

    elements = data.get("elements", [])
    rows = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat and lon:
            name = el.get("tags", {}).get("name", "Supermarket")
            rows.append({"lat": lat, "lon": lon, "weight": 1.0, "name": name})

    print(f"  {len(rows)} supermarkets from OSM")
    return pd.DataFrame(rows)


def main():
    ensure_dirs()
    print("=== Processing Grocery Store Data ===")

    stores = download_snap_data()

    if len(stores) == 0:
        print("  No grocery store data available. Skipping.")
        return

    # Write GeoJSON
    print("  Writing GeoJSON...")
    features = []
    for _, row in stores.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {"name": row["name"], "weight": round(row["weight"], 2)},
        })

    geojson = {"type": "FeatureCollection", "features": features}
    geojson_path = OUTPUT_DIR / "grocery.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)
    print(f"  Written {len(features)} features")

    # Generate distance-based score grid and raster heatmap PMTiles
    from score_grid import distance_score_grid, score_to_raster_pmtiles, write_score_grid

    points = np.column_stack([stores["lon"].values, stores["lat"].values])
    weights = stores["weight"].values

    print("  Computing distance score grid...")
    score = distance_score_grid(points, weights, decay_km=5.0, higher_is_better=True)
    write_score_grid(score, "grocery")

    # Color ramp: 0-200 uint8 scale (0=far/bad, 200=close/good)
    # Red (far) -> Yellow (moderate) -> Green (close)
    color_ramp = """\
0 227 74 51 200
40 244 165 96 200
80 253 212 158 200
120 199 233 192 200
160 116 196 118 200
200 35 139 69 200
255 0 0 0 0
"""

    score_to_raster_pmtiles(score, "grocery", color_ramp, OUTPUT_DIR)

    print("Done!")


if __name__ == "__main__":
    main()
