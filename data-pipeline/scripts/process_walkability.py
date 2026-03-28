#!/usr/bin/env python3
"""
Process EPA Smart Location Database (SLD) v3.0 into a composite
Walkability / Transit score grid.

Source: EPA Smart Location Database v3.0
  https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip

Key fields used:
  NatWalkInd  -- National Walkability Index (1-20 scale)
  D4A         -- Aggregate transit frequency (vehicles/hour within walking distance)
                 Note: -99999 sentinel value used for block groups with no transit data.
  GEOID20     -- Census block group GEOID (joins to TIGER boundaries)

Normalization:
  walk_score    = (NatWalkInd - 1) / 19          maps 1-20 to 0-1
  transit_score = min(D4A / 100, 1.0)            cap at 100 vehicles/hour
  composite     = 0.6 * walk_score + 0.4 * transit_score
                  (if D4A is missing/sentinel, falls back to walk_score alone)

Output:
  public/data/walkability-score.bin  -- Float32Array, row-major, north-to-south
  public/data/walkability-score.json -- Grid metadata

Usage:
    python process_walkability.py
"""

import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

# Allow running from any directory by adding the scripts dir to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from score_grid import rasterize_polygons_to_grid, write_score_grid
from utils import (
    CONUS_STATE_FIPS,
    OUTPUT_DIR,
    RAW_DIR,
    download_file,
    ensure_dirs,
)

# ---------------------------------------------------------------------------
# Data source URLs
# ---------------------------------------------------------------------------

# EPA Smart Location Database v3.0
SLD_URL = "https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip"

# Census 2020 block group boundaries (cartographic, 500k)
BG_SHAPES_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_bg_500k.zip"

# Sentinel value used in D4A when no transit data exists for a block group
D4A_NODATA_SENTINEL = -99999.0

# Composite weights (walkability is primary; transit data has geographic gaps)
WALK_WEIGHT = 0.6
TRANSIT_WEIGHT = 0.4


def download_sld_data() -> pd.DataFrame:
    """Download EPA Smart Location Database and return a filtered DataFrame.

    Returns only CONUS block groups with NatWalkInd, D4A, and GEOID20.
    D4A sentinel values (-99999) are replaced with NaN so downstream code
    can treat them as missing without special-casing.
    """
    zip_path = RAW_DIR / "SmartLocationDatabaseV3.zip"
    csv_path = RAW_DIR / "SmartLocationDatabaseV3.csv"

    if not csv_path.exists():
        download_file(SLD_URL, zip_path)
        print("  Extracting SLD data...")
        with zipfile.ZipFile(zip_path) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if csv_names:
                target = csv_names[0]
                print(f"    Found CSV: {target}")
                zf.extract(target, RAW_DIR)
                extracted = RAW_DIR / target
                if extracted != csv_path:
                    extracted.rename(csv_path)
            else:
                # May contain a geodatabase; extract everything and convert
                print("    No CSV in zip, trying geodatabase...")
                zf.extractall(RAW_DIR)
                gdb_dirs = list(RAW_DIR.glob("*.gdb"))
                if gdb_dirs:
                    print(f"    Reading geodatabase: {gdb_dirs[0]}")
                    gdf = gpd.read_file(gdb_dirs[0])
                    gdf.drop(columns=["geometry"], errors="ignore").to_csv(csv_path, index=False)
                else:
                    raise FileNotFoundError("No CSV or geodatabase found in SLD zip")
    else:
        print("  Already have SLD CSV")

    print("  Loading SLD data...")

    # Load only the columns we need to limit memory usage (~500 MB unzipped)
    usecols = ["GEOID20", "STATEFP", "NatWalkInd", "D4A"]
    try:
        df = pd.read_csv(
            csv_path,
            usecols=usecols,
            dtype={"GEOID20": str, "STATEFP": str},
        )
    except (ValueError, KeyError):
        # Column names may differ between SLD versions -- fall back to full load
        df = pd.read_csv(csv_path, dtype=str, low_memory=False)
        print(f"    Columns found: {list(df.columns)[:25]}...")

        # Locate the key columns by fuzzy name matching
        geoid_col = next((c for c in df.columns if "geoid" in c.lower()), None)
        state_col = next((c for c in df.columns if c.upper() == "STATEFP"), None)
        walk_col  = next((c for c in df.columns if "natwalkind" in c.lower()), None)
        d4a_col   = next((c for c in df.columns if c.upper() == "D4A"), None)

        if walk_col is None or geoid_col is None:
            raise ValueError("Cannot find NatWalkInd or GEOID columns in SLD CSV")

        rename = {geoid_col: "GEOID20", walk_col: "NatWalkInd"}
        if state_col:
            rename[state_col] = "STATEFP"
        if d4a_col:
            rename[d4a_col] = "D4A"

        df = df[list(rename)].rename(columns=rename)
        if "STATEFP" not in df.columns:
            df["STATEFP"] = df["GEOID20"].str[:2]
        if "D4A" not in df.columns:
            df["D4A"] = np.nan

    # Filter to CONUS states
    df = df[df["STATEFP"].isin(CONUS_STATE_FIPS)].copy()

    # Convert to numeric, coercing any non-numeric strings to NaN
    df["NatWalkInd"] = pd.to_numeric(df["NatWalkInd"], errors="coerce")
    df["D4A"]        = pd.to_numeric(df["D4A"],        errors="coerce")

    # Replace the -99999 sentinel with NaN (block groups with no transit service)
    df.loc[df["D4A"] <= D4A_NODATA_SENTINEL + 1, "D4A"] = np.nan

    df = df.dropna(subset=["NatWalkInd"])

    print(f"  Found {len(df)} CONUS block groups with walkability data")
    print(f"  NatWalkInd range: {df['NatWalkInd'].min():.1f} - {df['NatWalkInd'].max():.1f}")
    d4a_valid = df["D4A"].notna().sum()
    print(f"  D4A transit data: {d4a_valid}/{len(df)} block groups have non-zero transit frequency")

    return df


def download_bg_shapes() -> gpd.GeoDataFrame:
    """Download and cache Census 2020 block group boundaries.

    Returns a GeoDataFrame with GEOID and geometry columns, in EPSG:4326,
    filtered to CONUS.
    """
    shp_dir = RAW_DIR / "cb_2020_bg_500k"

    if not shp_dir.exists():
        zip_path = RAW_DIR / "cb_2020_us_bg_500k.zip"
        download_file(BG_SHAPES_URL, zip_path)

        print("  Extracting block group shapefile...")
        shp_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(shp_dir)
    else:
        print("  Already have block group shapefile")

    shp_files = list(shp_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in {shp_dir}")

    print("  Loading block group geometries (this may take a moment)...")
    gdf = gpd.read_file(shp_files[0])
    gdf = gdf[gdf["STATEFP"].isin(CONUS_STATE_FIPS)]
    gdf = gdf[["GEOID", "geometry"]]

    # Ensure WGS84 for rasterize_polygons_to_grid (which uses EPSG:4326 internally)
    if gdf.crs is not None and not gdf.crs.equals("EPSG:4326"):
        gdf = gdf.to_crs("EPSG:4326")

    print(f"  Loaded {len(gdf)} block group polygons in CONUS")
    return gdf


def compute_composite_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute normalized walk, transit, and composite scores.

    Walkability score:    (NatWalkInd - 1) / 19       -> [0, 1]
    Transit score:        min(D4A / 100, 1.0)          -> [0, 1], NaN if no data
    Composite:            0.6 * walk + 0.4 * transit
                          Falls back to walk_score alone when transit is missing.
    """
    out = df.copy()

    # Walk score: linear mapping of 1-20 scale to 0-1
    out["walk_score"] = ((out["NatWalkInd"] - 1) / 19).clip(0, 1)

    # Transit score: cap at 100 vehicles/hour; NaN preserved where D4A was missing
    out["transit_score"] = (out["D4A"] / 100.0).clip(0, 1)

    # Composite: full formula where transit is available, otherwise walkability only
    has_transit = out["transit_score"].notna()
    out["composite_score"] = np.where(
        has_transit,
        WALK_WEIGHT * out["walk_score"] + TRANSIT_WEIGHT * out["transit_score"],
        out["walk_score"],
    ).astype(np.float32)

    n_transit = int(has_transit.sum())
    n_total   = len(out)
    print(f"  {n_transit}/{n_total} block groups use full walk+transit formula")
    print(f"  {n_total - n_transit}/{n_total} block groups fall back to walkability only")
    print(f"  composite_score range: {out['composite_score'].min():.3f} - {out['composite_score'].max():.3f}")

    return out


def build_scored_geodataframe(
    bg_shapes: gpd.GeoDataFrame,
    sld: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Join SLD composite scores to Census block group polygons.

    The SLD GEOID20 field matches the GEOID in the 2020 TIGER/GENZ file.
    Block groups without a match (e.g. water-only features) are dropped.
    """
    print("  Joining scores to block group geometries...")
    merged = bg_shapes.merge(
        sld[["GEOID20", "composite_score"]],
        left_on="GEOID",
        right_on="GEOID20",
        how="inner",
    )
    print(f"  Matched {len(merged)}/{len(bg_shapes)} block groups")

    merged = merged.dropna(subset=["composite_score"])
    return merged


def main():
    ensure_dirs()
    print("=== Processing Walkability / Transit Score Grid ===")

    # Step 1: Load source data (downloads only if not already cached)
    sld       = download_sld_data()
    bg_shapes = download_bg_shapes()

    # Step 2: Compute composite scores
    sld = compute_composite_scores(sld)

    # Step 3: Join scores to polygon geometries
    gdf = build_scored_geodataframe(bg_shapes, sld)

    # Step 4: Rasterize to the standard 1170x500 CONUS grid
    # fill_value=nan marks ocean/unmapped cells as no-data (consistent with
    # other polygon-based layers like climate-vulnerability and crime)
    print("  Rasterizing to score grid...")
    score_grid = rasterize_polygons_to_grid(gdf, "composite_score", fill_value=np.nan)
    print(f"  Grid shape: {score_grid.shape}, dtype: {score_grid.dtype}")

    # Step 5: Write .bin + .json to public/data/
    write_score_grid(score_grid, "walkability")

    # Step 6: Print summary statistics
    valid_mask = ~np.isnan(score_grid)
    valid_vals = score_grid[valid_mask]
    print()
    print("=== Score Grid Summary ===")
    print(f"  Valid cells : {valid_mask.sum():,} / {score_grid.size:,}")
    print(f"  Min         : {valid_vals.min():.4f}")
    print(f"  Max         : {valid_vals.max():.4f}")
    print(f"  Mean        : {valid_vals.mean():.4f}")
    print(f"  Median      : {float(np.median(valid_vals)):.4f}")
    print()
    print("Done!")


if __name__ == "__main__":
    main()
