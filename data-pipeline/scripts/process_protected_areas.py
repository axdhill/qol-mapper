#!/usr/bin/env python3
"""
Download and process USGS PAD-US protected areas into vector PMTiles.

Source: USGS PAD-US 4.1 via ArcGIS REST Feature Service (no auth required)
  Federal_Fee_Managers_Authoritative_PADUS — ~1,800 major federal protected areas
  https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/
        Federal_Fee_Managers_Authoritative_PADUS/FeatureServer/0

Covers National Parks, National Forests, National Wildlife Refuges, Wilderness
Areas, National Monuments, and National Grasslands within CONUS.

Steps:
1. Paginate through the ArcGIS feature service (50 features/page to avoid timeout)
2. Convert to GeoDataFrame, normalize designation labels
3. Simplify geometries
4. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import json
import subprocess
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Polygon

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs

# ArcGIS REST endpoint for PAD-US Federal Fee Managers layer (public, no auth)
PADUS_FEATURE_SERVICE = (
    "https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services"
    "/Federal_Fee_Managers_Authoritative_PADUS/FeatureServer/0"
)

# Major federal designation types to include
MAJOR_DESIGNATIONS = ("NP", "NF", "NWR", "WA", "NM", "NG")

# Map PAD-US designation codes to display labels
DESIGNATION_MAP = {
    "NP": "National Park",
    "NM": "National Monument",
    "NF": "National Forest",
    "NG": "National Grassland",
    "NWR": "National Wildlife Refuge",
    "WA": "Wilderness Area",
}


def download_padus_via_rest(cache_path: Path) -> gpd.GeoDataFrame:
    """Download PAD-US federal features via ArcGIS REST API with pagination."""
    if cache_path.exists():
        print(f"  Loading cached GeoJSON: {cache_path}")
        return gpd.read_file(cache_path)

    des_list = ",".join(f"'{d}'" for d in MAJOR_DESIGNATIONS)
    where_clause = f"Des_Tp IN ({des_list})"
    out_fields = "Des_Tp,Unit_Nm,Loc_Nm,GIS_Acres,State_Nm"

    print("  Querying total feature count...")
    count_resp = requests.get(
        f"{PADUS_FEATURE_SERVICE}/query",
        params={"where": where_clause, "returnCountOnly": "true", "f": "json"},
        timeout=30,
    )
    count_resp.raise_for_status()
    total = count_resp.json().get("count", 0)
    print(f"  Total features to download: {total}")

    print("  Downloading PAD-US via ArcGIS REST API (paginated)...")

    all_features = []
    offset = 0
    page_size = 50  # small pages to avoid gateway timeout on large polygon responses

    while offset < total:
        params = {
            "where": where_clause,
            "outFields": out_fields,
            "outSR": "4326",
            "returnGeometry": "true",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        resp = requests.get(
            f"{PADUS_FEATURE_SERVICE}/query",
            params=params,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        pct = len(all_features) / total * 100
        print(f"    {len(all_features)}/{total} ({pct:.0f}%)...", end="\r", flush=True)

        offset += len(features)
        time.sleep(0.05)

    print(f"\n  Downloaded {len(all_features)} features")

    if not all_features:
        raise ValueError("No features returned from ArcGIS REST service")

    # Convert to GeoDataFrame
    records = []
    for feat in all_features:
        attrs = feat.get("attributes", {})
        geom_data = feat.get("geometry")
        if not geom_data:
            continue

        geom = _arcgis_polygon_to_shapely(geom_data)
        if geom is None or geom.is_empty:
            continue

        des_tp = attrs.get("Des_Tp", "")
        designation = DESIGNATION_MAP.get(des_tp, "Other Protected Area")
        name = attrs.get("Unit_Nm") or attrs.get("Loc_Nm") or "Unknown"
        acres = float(attrs.get("GIS_Acres") or 0)

        records.append({
            "area_name": name,
            "designation": designation,
            "acres": round(acres),
            "geometry": geom,
        })

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    print(f"  Converted to GeoDataFrame: {len(gdf)} valid features")

    gdf.to_file(cache_path, driver="GeoJSON")
    print(f"  Cached: {cache_path}")
    return gdf


def _arcgis_polygon_to_shapely(geom_data: dict):
    """Convert ArcGIS REST polygon (rings) to Shapely geometry."""
    from shapely.geometry import MultiPolygon
    from shapely.ops import unary_union

    rings = geom_data.get("rings", [])
    if not rings:
        return None

    try:
        exterior = rings[0]
        holes = rings[1:] if len(rings) > 1 else []
        poly = Polygon(exterior, holes)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly
    except Exception:
        return None


def main():
    ensure_dirs()
    print("=== Processing Protected Areas (PAD-US) Data ===")

    cache_path = RAW_DIR / "protected_areas_federal_raw.geojson"
    gdf = download_padus_via_rest(cache_path)

    # Filter to CONUS
    print("  Filtering to CONUS...")
    gdf = gdf.cx[-126:-66, 24:50]
    print(f"  After CONUS filter: {len(gdf)} features")

    # Simplify geometries
    print("  Simplifying geometries...")
    gdf["geometry"] = gdf["geometry"].simplify(0.002, preserve_topology=True)
    gdf = gdf[~gdf["geometry"].is_empty]

    print(f"  Final dataset: {len(gdf)} protected areas")

    # Write GeoJSON
    geojson_path = OUTPUT_DIR / "protected-areas.geojson"
    print("  Writing GeoJSON...")
    gdf.to_file(geojson_path, driver="GeoJSON")
    print(f"  Written: {geojson_path}")

    # Convert to PMTiles
    pmtiles_path = OUTPUT_DIR / "protected-areas.pmtiles"
    print("  Running tippecanoe...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12",
                "-Z", "3",
                "-l", "protected_areas",
                "--coalesce-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--force",
                str(geojson_path),
            ],
            check=True,
        )
        print(f"  PMTiles written: {pmtiles_path}")
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found.")

    print("Done!")


if __name__ == "__main__":
    main()
