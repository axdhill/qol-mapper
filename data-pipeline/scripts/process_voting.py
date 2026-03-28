#!/usr/bin/env python3
"""
Download and process presidential election results into vector PMTiles.

Source: MIT Election Data + Science Lab (MEDSL) county presidential returns.
- Harvard Dataverse: doi:10.7910/DVN/VOQCHQ
- CC0 public domain license

Uses 2024 results (Harris vs Trump) where available, falls back to 2020.

Steps:
1. Download MEDSL county presidential returns CSV via Dataverse API
2. Filter to most recent election year
3. Compute Democratic and Republican vote shares by county
4. Join with Census county boundaries
5. Write two GeoJSON files -> two PMTiles (one per party)
"""

import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from utils import OUTPUT_DIR, RAW_DIR, copy_to_public, download_file, ensure_dirs, download_county_shapes

MEDSL_DATASET_DOI = "doi:10.7910/DVN/VOQCHQ"
MEDSL_FALLBACK_URL = "https://dataverse.harvard.edu/api/access/datafile/13573089?format=original"
MEDSL_FALLBACK_FILE = "countypres_2000-2020.csv"


def _find_latest_medsl_file() -> tuple[str, str]:
    """Query Harvard Dataverse API to find the latest county presidential returns file.

    Returns (url, filename) for the most recent countypres CSV in the dataset.
    Raises on failure so the caller can fall back.
    """
    api_url = "https://dataverse.harvard.edu/api/datasets/:persistentId/versions/:latest/files"
    resp = requests.get(api_url, params={"persistentId": MEDSL_DATASET_DOI}, timeout=30)
    resp.raise_for_status()

    files = resp.json()["data"]
    candidates = [
        f["dataFile"]
        for f in files
        if "countypres" in f["dataFile"]["filename"].lower()
        and f["dataFile"]["filename"].lower().endswith(".csv")
    ]
    if not candidates:
        raise ValueError("No countypres CSV found in MEDSL dataset")

    # Pick file covering the most years (largest year in name, or largest file)
    best = max(candidates, key=lambda f: f["filename"])
    file_id = best["id"]
    url = f"https://dataverse.harvard.edu/api/access/datafile/{file_id}?format=original"
    return url, best["filename"]


def download_election_data() -> pd.DataFrame:
    """Download MEDSL county presidential returns (latest available year)."""
    # Try API first to get the most up-to-date file
    csv_path = None
    try:
        print("  Querying Harvard Dataverse for latest MEDSL file...")
        url, filename = _find_latest_medsl_file()
        csv_path = RAW_DIR / filename
        download_file(url, csv_path)
    except Exception as e:
        print(f"  API lookup failed ({e}), using cached file")
        csv_path = RAW_DIR / MEDSL_FALLBACK_FILE
        if not csv_path.exists():
            download_file(MEDSL_FALLBACK_URL, csv_path)

    print("  Loading election data...")
    df = pd.read_csv(csv_path, dtype={"county_fips": str})

    # Use most recent year
    latest_year = df["year"].max()
    print(f"  Using election year: {latest_year}")
    df = df[df["year"] == latest_year]

    # Compute vote shares by county
    county_totals = df.groupby("county_fips")["totalvotes"].first().reset_index()
    county_totals.columns = ["FIPS", "total_votes"]

    dem_votes = df[df["party"] == "DEMOCRAT"].groupby("county_fips")["candidatevotes"].sum().reset_index()
    dem_votes.columns = ["FIPS", "dem_votes"]

    gop_votes = df[df["party"] == "REPUBLICAN"].groupby("county_fips")["candidatevotes"].sum().reset_index()
    gop_votes.columns = ["FIPS", "gop_votes"]

    result = county_totals.merge(dem_votes, on="FIPS", how="left").merge(gop_votes, on="FIPS", how="left")
    result["dem_votes"] = result["dem_votes"].fillna(0)
    result["gop_votes"] = result["gop_votes"].fillna(0)
    result["dem_share"] = (result["dem_votes"] / result["total_votes"]).clip(0, 1)
    result["gop_share"] = (result["gop_votes"] / result["total_votes"]).clip(0, 1)
    result["FIPS"] = result["FIPS"].str.zfill(5)
    result["election_year"] = latest_year

    # Drop invalid FIPS
    result = result[result["FIPS"].str.len() == 5]
    result = result.dropna(subset=["total_votes"])

    print(f"  Found {len(result)} counties with election data")
    print(f"  Dem share range: {result['dem_share'].min():.2f} – {result['dem_share'].max():.2f}")
    print(f"  GOP share range: {result['gop_share'].min():.2f} – {result['gop_share'].max():.2f}")
    return result


def main():
    ensure_dirs()
    print("=== Processing Voting / Election Data ===")

    election = download_election_data()
    counties = download_county_shapes()

    # Join election data to county geometries
    print("  Joining election data to county geometries...")
    merged = counties.merge(election, left_on="GEOID", right_on="FIPS", how="inner")
    print(f"  Matched {len(merged)} counties")

    # Simplify geometries
    print("  Simplifying geometries...")
    merged["geometry"] = merged["geometry"].simplify(0.005, preserve_topology=True)

    # Round values
    for col in ["dem_share", "gop_share"]:
        merged[col] = merged[col].round(3)

    keep_cols = ["GEOID", "NAME", "dem_share", "gop_share", "total_votes", "geometry"]
    merged = merged[keep_cols]

    # Write Democratic GeoJSON + PMTiles
    geojson_path = OUTPUT_DIR / "voting-dem.geojson"
    print("  Writing Democratic vote share GeoJSON...")
    merged.to_file(geojson_path, driver="GeoJSON")

    pmtiles_path = OUTPUT_DIR / "voting-dem.pmtiles"
    print("  Running tippecanoe for Democratic layer...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path),
                "-z", "12", "-Z", "3",
                "-l", "voting_dem",
                "--coalesce-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--force",
                str(geojson_path),
            ],
            check=True,
        )
        copy_to_public(pmtiles_path)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found.")

    # Write Republican GeoJSON + PMTiles (same geometry, different styling)
    geojson_path_gop = OUTPUT_DIR / "voting-gop.geojson"
    print("  Writing Republican vote share GeoJSON...")
    merged.to_file(geojson_path_gop, driver="GeoJSON")

    pmtiles_path_gop = OUTPUT_DIR / "voting-gop.pmtiles"
    print("  Running tippecanoe for Republican layer...")
    try:
        subprocess.run(
            [
                "tippecanoe",
                "-o", str(pmtiles_path_gop),
                "-z", "12", "-Z", "3",
                "-l", "voting_gop",
                "--coalesce-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--force",
                str(geojson_path_gop),
            ],
            check=True,
        )
        copy_to_public(pmtiles_path_gop)
    except FileNotFoundError:
        print("  Warning: tippecanoe not found.")

    print("Done!")


if __name__ == "__main__":
    main()
