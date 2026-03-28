#!/usr/bin/env python3
"""
Download and process NCES school data into vector PMTiles.

Source: NCES EDGE ArcGIS Feature Service (School Characteristics)
https://data-nces.opendata.arcgis.com/

Steps:
1. Query NCES EDGE ArcGIS API for school characteristics (paginated)
2. Extract school locations, levels, enrollment
3. Compute quality score (0-1) based on available metrics
4. Write GeoJSON -> vector PMTiles via tippecanoe
"""

import json
import subprocess
from pathlib import Path

import requests

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs

# NCES EDGE ArcGIS Feature Service - School Characteristics (current year)
EDGE_BASE = (
    "https://services1.arcgis.com/Ua5sjt3LWTPigjyD/arcgis/rest/services"
    "/School_Characteristics_Current/FeatureServer/0/query"
)
# Fields we need
FIELDS = "NCESSCH,SCH_NAME,SCHOOL_LEVEL,SCHOOL_TYPE_TEXT,SY_STATUS_TEXT,GSLO,GSHI,TOTAL,TOTFRL"
PAGE_SIZE = 2000


def query_schools() -> list[dict]:
    """Query all schools from NCES EDGE ArcGIS API with pagination."""
    cache_path = RAW_DIR / "nces_edge_schools.json"
    if cache_path.exists():
        print("  Already have cached school data")
        with open(cache_path) as f:
            return json.load(f)

    all_features = []
    offset = 0

    print("  Querying NCES EDGE ArcGIS API...")
    while True:
        params = {
            "where": "1=1",
            "outFields": FIELDS,
            "returnGeometry": "true",
            "f": "json",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": offset,
        }
        resp = requests.get(EDGE_BASE, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        offset += len(features)
        print(f"\r  Fetched {len(all_features)} schools...", end="", flush=True)

        # ArcGIS returns exceededTransferLimit when there's more data
        if not data.get("exceededTransferLimit", False):
            break

    print(f"\n  Total: {len(all_features)} schools from API")

    # Cache to disk
    with open(cache_path, "w") as f:
        json.dump(all_features, f)

    return all_features


def process_schools(features: list[dict]) -> list[dict]:
    """Process raw ArcGIS features into school records."""
    schools = []

    for feat in features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})

        lon = geom.get("x")
        lat = geom.get("y")
        if lon is None or lat is None:
            continue

        # Filter to CONUS
        if not (24 <= lat <= 50 and -126 <= lon <= -66):
            continue

        # Filter to open regular schools
        status = (attrs.get("SY_STATUS_TEXT") or "").strip().lower()
        if not any(kw in status for kw in ("operational", "new", "reopen")):
            continue

        school_type = (attrs.get("SCHOOL_TYPE_TEXT") or "").strip()
        is_regular = "Regular" in school_type

        # School level
        level = (attrs.get("SCHOOL_LEVEL") or "").strip()
        if level in ("High", "Secondary"):
            level_name = "High"
        elif level == "Middle":
            level_name = "Middle"
        elif level in ("Elementary", "Prekindergarten"):
            level_name = "Elementary"
        else:
            # Try to infer from grade range
            gshi = attrs.get("GSHI", "")
            if gshi in ("12", "11", "10", "13"):
                level_name = "High"
            elif gshi in ("08", "07", "06"):
                level_name = "Middle"
            else:
                level_name = "Elementary"

        enrollment = attrs.get("TOTAL") or 0
        try:
            enrollment = int(float(enrollment))
        except (ValueError, TypeError):
            enrollment = 0

        if not is_regular:
            continue

        # Compute quality score proxy
        base = 0.3
        level_bonus = 0.15 if level_name == "High" else (0.1 if level_name == "Middle" else 0.05)
        size_factor = min(0.35, enrollment / 3000 * 0.35) if enrollment > 0 else 0
        regular_bonus = 0.2
        score = round(min(1.0, max(0, base + level_bonus + size_factor + regular_bonus)), 3)

        schools.append({
            "name": attrs.get("SCH_NAME", "Unknown"),
            "lat": lat,
            "lon": lon,
            "level": level_name,
            "enrollment": enrollment,
            "quality_score": score,
        })

    print(f"  Processed {len(schools)} regular schools in CONUS")
    return schools


def to_geojson(schools: list[dict], output_path: Path):
    """Write schools to GeoJSON."""
    features = []
    for sch in schools:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [sch["lon"], sch["lat"]],
            },
            "properties": {
                "name": sch["name"],
                "quality_score": sch["quality_score"],
                "enrollment": sch["enrollment"],
                "level": sch["level"],
            },
        }
        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}
    with open(output_path, "w") as f:
        json.dump(geojson, f)
    print(f"  Written GeoJSON: {output_path} ({len(features)} features)")


def geojson_to_pmtiles(geojson_path: Path, pmtiles_path: Path):
    print("  Running tippecanoe...")
    subprocess.run(
        [
            "tippecanoe",
            "-o", str(pmtiles_path),
            "-z", "14",
            "-Z", "6",
            "-l", "schools",
            "--drop-densest-as-needed",
            "--force",
            str(geojson_path),
        ],
        check=True,
    )
    print(f"  PMTiles written: {pmtiles_path}")


def main():
    ensure_dirs()
    print("=== Processing School Quality Data ===")

    features = query_schools()
    schools = process_schools(features)

    geojson_path = OUTPUT_DIR / "school-quality.geojson"
    to_geojson(schools, geojson_path)

    pmtiles_path = OUTPUT_DIR / "school-quality.pmtiles"
    try:
        geojson_to_pmtiles(geojson_path, pmtiles_path)
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found.")

    print("Done!")


if __name__ == "__main__":
    main()
