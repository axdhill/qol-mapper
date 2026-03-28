# QoL Mapper

Interactive map showing composite quality-of-life scores across the continental US. Layers are weighted and blended into a single colormap (red = poor, green = excellent). Click anywhere to see per-layer score breakdowns.

Built with Next.js, MapLibre GL, PMTiles, and Zustand.

## Current Layers

| Layer | Category | Source | Data Type | Status |
|-------|----------|--------|-----------|--------|
| PM2.5 Air Quality | Environmental | EPA AirData | Raster (interpolated) | Available |
| Estimated Noise | Environmental | Derived from OSM road network | Raster | Available |
| Tree Canopy Cover | Environmental | Hansen/UMD/Google GFC v1.11 | Raster | Available |
| School Quality (K-12) | Social | NCES EDGE ArcGIS Feature Service | Points | Available |
| University Quality | Social | NCES IPEDS | Points | Available |
| Power Plants | Environmental | EPA eGRID | Points | Available |
| Climate Vulnerability | Social | CDC Social Vulnerability Index | Polygons (tracts) | Available |
| Home Prices | Economic | Zillow ZHVI + Census ZCTA | Polygons (zip codes) | Available |
| Protected Areas | Environmental | USGS PAD-US 4.1 (via ArcGIS REST) | Polygons | Available |
| Grocery Store Access | Social | USDA SNAP Retailer Database | Points | Available |
| Violent Crime | Social | County Health Rankings (FBI UCR) | Polygons (counties) | Available |
| Transit / Walkability | Infrastructure | EPA Smart Location Database v3.0 | Polygons (block groups) | Available |
| Political Leaning (Dem) | Social | MIT Election Data + Science Lab | Polygons (counties) | Available |
| Political Leaning (GOP) | Social | MIT Election Data + Science Lab | Polygons (counties) | Available |
| Water / Drought | Environmental | US Drought Monitor | Polygons (counties) | Available |

## Architecture

### Data Pipeline (`data-pipeline/scripts/`)

Each layer has a processing script that:
1. Downloads raw data from public sources
2. Cleans, joins, and normalizes
3. Outputs GeoJSON + PMTiles (for annotation overlays)
4. Generates a 0-1 score grid at 0.05 deg resolution (`public/data/{name}-score.bin`)

Shared utilities:
- `score_grid.py` -- Common grid parameters, distance scoring, polygon rasterization
- `generate_score_grids.py` -- Master script to regenerate all score grids
- `utils.py` -- File paths, directory setup

### Client (`src/`)

- **Composite overlay:** Score grids are loaded on demand, weighted by user preferences, and composited into a single canvas rendered as a MapLibre image source
- **Annotation layers:** Vector data (points, polygons) shown as muted white dots/outlines for reference
- **Click querying:** Reads score grid values at clicked point for per-layer breakdown
- **State management:** Zustand store with enabled layers, weights, composite opacity

### Score Grid Format

Each score grid is a pair of files:
- `{name}-score.bin` -- Float32Array, row-major, north-to-south (~2.3MB)
- `{name}-score.json` -- Metadata: `{ width, height, originX, originY, pixelWidth, pixelHeight }`

Grid covers CONUS: 125 deg W to 66.5 deg W, 24.5 deg N to 49.5 deg N at 0.05 deg resolution (1170 x 500 cells).

## Development

```bash
npm install
npm run dev
```

Data files (`public/data/` and `public/tiles/`) are tracked via Git LFS and are fetched automatically on clone. You need `git-lfs` installed:

```bash
brew install git-lfs   # macOS
git lfs install
git clone <repo-url>   # LFS objects fetched automatically
```

### Running data pipelines

See [`data-pipeline/PIPELINE.md`](data-pipeline/PIPELINE.md) for full instructions. Quick start:

```bash
cd data-pipeline
uv sync
source .venv/bin/activate
cd scripts

# Process individual layers
python process_pm25.py
python process_schools.py
# etc.

# Regenerate all score grids
python generate_score_grids.py
```

## Deployment (Railway)

1. Push this repo to GitHub (LFS objects upload automatically)
2. Create a new [Railway](https://railway.app) project and connect the GitHub repo
3. Railway auto-detects Next.js via Nixpacks — no configuration needed
4. Click Deploy

Railway fetches Git LFS objects during the build, so all data files are available at runtime.

> **LFS bandwidth note:** Each Railway build downloads ~785 MB of LFS objects. GitHub's free tier includes 1 GB/month. Disable auto-deploys on Railway if you redeploy frequently to stay within the free tier.
