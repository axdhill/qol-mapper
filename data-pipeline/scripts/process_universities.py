#!/usr/bin/env python3
"""
Extract R1 (Very High Research Activity) research universities from IPEDS
and write as GeoJSON + vector PMTiles.

Source: NCES IPEDS HD2023 (C21BASIC == 15 → Carnegie R1)
Reference: https://en.wikipedia.org/wiki/List_of_research_universities_in_the_United_States

Score grid is computed separately in generate_score_grids.py using linear
distance decay: excellent within 2 miles, poor beyond 120 miles.
"""

import csv
import json
import subprocess
import zipfile
from pathlib import Path

import requests

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs

IPEDS_HD_URL = "https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip"

# Carnegie 2021 Basic Classification codes
# 15 = "Doctoral Universities: Very High Research Activity" (R1)
# 16 = "Doctoral Universities: High Research Activity" (R2)
R1_CODE = "15"
R2_CODE = "16"


def download_and_extract_csv(url: str, dest_dir: Path, name: str) -> Path:
    zip_path = dest_dir / f"{name}.zip"
    csv_path = dest_dir / f"{name}.csv"
    if csv_path.exists():
        print(f"  Already have {name}.csv")
        return csv_path
    print(f"  Downloading {name}...")
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    zip_path.write_bytes(resp.content)
    with zipfile.ZipFile(zip_path) as zf:
        csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        csv_file = sorted(csv_files, key=lambda x: zf.getinfo(x).file_size, reverse=True)[0]
        with zf.open(csv_file) as src, open(csv_path, "wb") as dst:
            dst.write(src.read())
    return csv_path


def load_research_universities(raw_dir: Path) -> list[dict]:
    hd_path = download_and_extract_csv(IPEDS_HD_URL, raw_dir, "ipeds_hd2023")

    institutions = []
    r1_count = 0
    r2_count = 0
    with open(hd_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row.get("C21BASIC", "").strip()
            if code == R1_CODE:
                tier = "R1"
                r1_count += 1
            elif code == R2_CODE:
                tier = "R2"
                r2_count += 1
            else:
                continue
            try:
                lat = float(row["LATITUDE"])
                lon = float(row["LONGITUD"])
            except (ValueError, TypeError):
                continue
            # CONUS only
            if not (24 <= lat <= 50 and -126 <= lon <= -66):
                continue
            institutions.append({
                "name": row.get("INSTNM", "Unknown").strip(),
                "lat": lat,
                "lon": lon,
                "city": row.get("CITY", "").strip(),
                "state": row.get("STABBR", "").strip(),
                "tier": tier,
                "control": {"1": "Public", "2": "Private nonprofit", "3": "Private for-profit"}.get(
                    row.get("CONTROL", ""), "Unknown"
                ),
            })

    print(f"  Found {r1_count} R1 and {r2_count} R2 universities in CONUS")
    return institutions


def main():
    ensure_dirs()
    print("=== Processing R1 Research Universities (Carnegie Classification) ===")

    institutions = load_research_universities(RAW_DIR)

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [inst["lon"], inst["lat"]]},
            "properties": {
                "name": inst["name"],
                "city": inst["city"],
                "state": inst["state"],
                "tier": inst["tier"],
                "control": inst["control"],
            },
        }
        for inst in institutions
    ]
    geojson = {"type": "FeatureCollection", "features": features}

    geojson_path = OUTPUT_DIR / "university-quality.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)
    print(f"  Written: {geojson_path} ({len(features)} features)")

    pmtiles_path = OUTPUT_DIR / "university-quality.pmtiles"
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "14", "-Z", "4",
                "-l", "universities",
                "--drop-densest-as-needed",
                "--force",
                str(geojson_path),
            ],
            check=True,
        )
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found")

    print("Done!")


if __name__ == "__main__":
    main()
