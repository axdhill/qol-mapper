#!/usr/bin/env python3
"""
Process industrial hazard facility data into GeoJSON and vector PMTiles.

Two data sources are merged:
  1. EPA eGRID (2023) — polluting power plants only (coal, oil, gas, biomass).
     Weighted by annual CO2+SO2+NOx air emissions.
  2. EPA Toxics Release Inventory (TRI, 2022) — chemical plants, refineries,
     metal smelters, paper mills, and other high-emitting industrial sites.
     Weighted by total on-site air releases (lbs/yr).

Clean energy (wind, solar, hydro, nuclear, geothermal) is excluded entirely.
"""

import json
import subprocess
from pathlib import Path

import pandas as pd
import requests

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, ensure_dirs

EGRID_URL = "https://www.epa.gov/system/files/documents/2024-01/egrid2023_data.xlsx"
TRI_URL = "https://data.epa.gov/api-cache/downloads/tri/mv_tri_basic_download/2022_us.csv"

# eGRID primary fuel codes for zero-emission sources — everything else is polluting
CLEAN_FUELS = {"NUC", "WAT", "SUN", "WND", "GEO", "MWH", "WH", "PUR"}


def load_egrid_plants(raw_dir: Path) -> pd.DataFrame:
    """Load polluting power plants from eGRID."""
    xlsx_path = raw_dir / "egrid2023_data.xlsx"
    if not xlsx_path.exists():
        print("  Downloading eGRID 2023...")
        resp = requests.get(EGRID_URL, timeout=300)
        resp.raise_for_status()
        xlsx_path.write_bytes(resp.content)

    print("  Loading eGRID (PLNT sheet)...")
    xl = pd.ExcelFile(xlsx_path)
    plant_sheet = next(s for s in xl.sheet_names if s.upper().startswith("PLNT"))
    df = pd.read_excel(xlsx_path, sheet_name=plant_sheet, skiprows=1)

    cols = {
        "PNAME":    "name",
        "LAT":      "lat",
        "LON":      "lon",
        "PLPRMFL":  "primary_fuel",
        "NAMEPCAP": "capacity_mw",
        "PLCO2AN":  "co2_tons",
        "PLSO2AN":  "so2_tons",
        "PLNOXAN":  "nox_tons",
    }
    available = {k: v for k, v in cols.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)
    df = df.dropna(subset=["lat", "lon"])

    df["fuel_type"] = df["primary_fuel"].str.upper().fillna("OTHER")
    # Exclude clean zero-emission sources; keep anything that produces CO2
    df = df[~df["fuel_type"].isin(CLEAN_FUELS)].copy()
    # Additional guard: drop plants with zero CO2 and zero capacity (phantom entries)
    if "co2_tons" in df.columns and "capacity_mw" in df.columns:
        df = df[(df["co2_tons"] > 0) | (df["capacity_mw"] > 0)].copy()

    for col in ["capacity_mw", "co2_tons", "so2_tons", "nox_tons"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Combined air toxics weight: CO2 drives climate, SO2/NOx drive local health
    # Scale SO2/NOx up so they matter even when CO2 is modest (gas peakers)
    df["emission_weight"] = (
        df.get("co2_tons", 0) + df.get("so2_tons", 0) * 100 + df.get("nox_tons", 0) * 50
    )

    # CONUS only
    df = df[(df["lat"] >= 24) & (df["lat"] <= 50) & (df["lon"] >= -126) & (df["lon"] <= -66)]
    print(f"  Found {len(df)} polluting power plants in CONUS")
    df["facility_type"] = "POWER"
    return df[["name", "lat", "lon", "fuel_type", "emission_weight", "facility_type"]]


def load_tri_facilities(raw_dir: Path) -> pd.DataFrame:
    """Load industrial emitters from EPA Toxics Release Inventory (2022).

    Source: https://data.epa.gov/api-cache/downloads/tri/mv_tri_basic_download/2022_us.csv
    One row per chemical per facility; we aggregate air releases by facility.
    """
    csv_path = raw_dir / "tri_2022_us.csv"

    if not csv_path.exists():
        print("  Downloading EPA TRI 2022 (~63 MB)...")
        resp = requests.get(TRI_URL, timeout=600, stream=True)
        resp.raise_for_status()
        with open(csv_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)

    print("  Loading TRI data...")
    df = pd.read_csv(csv_path, encoding="latin-1", low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]

    # Identify facility columns
    name_col   = next((c for c in df.columns if "FACILITY NAME" in c), None)
    lat_col    = next((c for c in df.columns if "LATITUDE" in c), None)
    lon_col    = next((c for c in df.columns if "LONGITUDE" in c), None)
    # On-site air releases: fugitive + stack
    fug_col    = next((c for c in df.columns if "FUGITIVE" in c and "AIR" in c), None)
    stack_col  = next((c for c in df.columns if "STACK" in c and "AIR" in c), None)
    total_col  = next((c for c in df.columns if "ON-SITE RELEASE TOTAL" in c), None)

    missing = [n for n, c in [("name", name_col), ("lat", lat_col), ("lon", lon_col)] if c is None]
    if missing:
        raise ValueError(f"Missing TRI columns: {missing}. Available: {list(df.columns[:30])}")

    keep = {name_col: "name", lat_col: "lat", lon_col: "lon"}
    air_cols = [c for c in [fug_col, stack_col, total_col] if c is not None]
    df = df[[*keep.keys(), *air_cols]].rename(columns=keep)

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    # Sum all available air release columns per row, then aggregate by facility
    for c in air_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["air_lbs"] = df[air_cols].sum(axis=1)

    agg = (
        df.groupby(["name", "lat", "lon"], as_index=False)
        .agg(air_lbs=("air_lbs", "sum"))
    )

    # Only keep facilities with meaningful releases (top emitters)
    # 1000 lbs/yr threshold filters out trivial reporters
    agg = agg[agg["air_lbs"] >= 1000].copy()

    # CONUS only
    agg = agg[(agg["lat"] >= 24) & (agg["lat"] <= 50) & (agg["lon"] >= -126) & (agg["lon"] <= -66)]

    # Convert lbs to tons for consistent scale, then use as emission weight
    agg["emission_weight"] = agg["air_lbs"] / 2000.0
    agg["fuel_type"] = "INDUSTRIAL"
    agg["facility_type"] = "INDUSTRIAL"

    print(f"  Found {len(agg)} TRI industrial facilities in CONUS (≥1000 lbs air releases/yr)")
    return agg[["name", "lat", "lon", "fuel_type", "emission_weight", "facility_type"]]


def main():
    ensure_dirs()
    print("=== Processing Industrial Hazard Facilities ===")

    power_df = load_egrid_plants(RAW_DIR)
    tri_df   = load_tri_facilities(RAW_DIR)

    combined = pd.concat([power_df, tri_df], ignore_index=True)
    print(f"  Total: {len(combined)} facilities")

    features = []
    for _, row in combined.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
            "properties": {
                "name":          str(row["name"]),
                "fuel_type":     str(row["fuel_type"]),
                "facility_type": str(row["facility_type"]),
                "emission_weight": float(row["emission_weight"]),
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    geojson_path = OUTPUT_DIR / "power-plants.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)
    print(f"  Written: {geojson_path} ({len(features)} features)")

    pmtiles_path = OUTPUT_DIR / "power-plants.pmtiles"
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "14", "-Z", "3",
                "-l", "power_plants",
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
