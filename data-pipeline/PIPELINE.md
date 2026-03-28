# Data Pipeline

The pipeline downloads raw public datasets, processes them into normalized score grids and PMTiles annotation overlays, and writes the final outputs to `public/data/` and `public/tiles/`.

## Directory Layout

```
data-pipeline/
  scripts/     Processing scripts (committed)
  raw/         Raw downloaded source data (~8 GB, gitignored)
  output/      Intermediate processed files (~2 GB, gitignored)
```

`raw/` and `output/` are gitignored. The final deliverables — the contents of `public/data/` and `public/tiles/` — are committed to the repo via Git LFS (see `public/DATA.md`).

## Setup

```bash
cd data-pipeline
pip install uv
uv sync
source .venv/bin/activate
```

## Scripts

### Download scripts (fetch raw data)

Run these first for the relevant layers:

| Script | Fetches |
|--------|---------|
| `download_epa_pm25.py` | EPA annual PM2.5 monitor data (2019–2023) |
| `download_nlcd_tree.py` | Hansen GFC tree canopy raster |
| `download_egrid.py` | EPA eGRID power plant emissions data |

Most layer scripts download their own data on first run (NCES, USDA SNAP, etc.).

### Processing scripts (produce outputs)

Run per-layer scripts independently. Each reads from `raw/`, writes intermediate files to `output/`, and writes the final score grid to `public/data/` and PMTiles to `public/tiles/`:

```bash
cd scripts

python process_pm25.py
python process_noise.py
python process_tree_canopy.py
python process_schools.py
python process_universities.py
python process_power_plants.py
python process_climate_vulnerability.py
python process_home_prices.py
python process_protected_areas.py
python process_grocery.py
python process_crime.py
python process_transit.py
python process_walkability.py
python process_voting.py
python process_water_quality.py
python process_ticks.py
python process_temperateness.py
```

### Score grid regeneration

After all layers are processed, regenerate all score grids at once:

```bash
python generate_score_grids.py
```

This reads the processed layer data in `output/` and (re)writes all `public/data/*-score.bin` files.

### Shared utilities

- `score_grid.py` — Grid constants (1170×500, CONUS bounds), `distance_score_grid()`, `rasterize_polygons_to_grid()`, `write_score_grid()`
- `utils.py` — File paths, state FIPS codes, census downloader helpers

## After Regenerating Data

If you regenerate data files, re-stage and push the updated LFS objects:

```bash
cd ..  # repo root
git add public/data/ public/tiles/
git commit -m "Update data: <layer name>"
git push
```

## Raw Data Sources

| File(s) in `raw/` | Source | Script |
|--------------------|--------|--------|
| `annual_conc_by_monitor_*.csv` | EPA AirData | `download_epa_pm25.py` |
| `SmartLocationDatabaseV3.*` | EPA Smart Location Database v3 | manual download |
| `wc2.1_2.5m_tmax.zip`, `tmin.zip` | WorldClim 2.1 | `process_temperateness.py` |
| `zillow_zhvi.csv` | Zillow ZHVI | `process_home_prices.py` |
| `cdc_svi_2022.csv` | CDC Social Vulnerability Index 2022 | `process_climate_vulnerability.py` |
| `chr_analytic_2024.csv` | County Health Rankings 2024 | `process_crime.py` |
| `countypres_2000-2020.csv` | MIT Election Data + Science Lab | `process_voting.py` |
| `egrid2023_data.xlsx` | EPA eGRID 2023 | `download_egrid.py` |
| `cb_2020_us_*.zip` | Census TIGER/Line shapefiles | various |
| `nces_edge_schools.json` | NCES EDGE ArcGIS REST API | `process_schools.py` |
| `ipeds_*.csv` | NCES IPEDS | `process_universities.py` |
| `osm_supermarkets.json` | OpenStreetMap (Overpass) | `process_grocery.py` |
| `LD_Case_Counts_by_County_2022.csv` | CDC Lyme Disease Surveillance | `process_ticks.py` |
| `drought_county.csv` | US Drought Monitor | `process_water_quality.py` |
| `PADUS4_1Geodatabase/` | USGS PAD-US 4.1 (ArcGIS REST) | `process_protected_areas.py` |
