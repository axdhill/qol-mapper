# Runtime Data Files

All files in `public/data/` and `public/tiles/` are tracked via Git LFS. They are required for the app to function and are fetched automatically when cloning the repo.

## Score Grids (`public/data/`)

Each layer has a binary score grid (Float32Array, 1170×500, CONUS at 0.05° resolution) plus a JSON metadata file. Values are normalized to [0, 1].

| File | Size | Description |
|------|------|-------------|
| `pm25-score.bin` + `.json` | 2.3 MB | PM2.5 air quality score |
| `noise-score.bin` + `.json` | 2.3 MB | Estimated noise level score |
| `tree-canopy-score.bin` + `.json` | 2.3 MB | Tree canopy coverage score |
| `schools-score.bin` + `.json` | 2.3 MB | K-12 school quality score |
| `universities-score.bin` + `.json` | 2.3 MB | Research university proximity score |
| `power-plants-score.bin` + `.json` | 2.3 MB | Industrial hazard score |
| `climate-vulnerability-score.bin` + `.json` | 2.3 MB | CDC social vulnerability score |
| `home-prices-score.bin` + `.json` | 2.3 MB | Housing affordability score |
| `protected-areas-score.bin` + `.json` | 2.3 MB | Protected land proximity score |
| `crime-score.bin` + `.json` | 2.3 MB | Violent crime rate score |
| `voting-dem-score.bin` + `.json` | 2.3 MB | Democratic vote share score |
| `voting-gop-score.bin` + `.json` | 2.3 MB | Republican vote share score |
| `grocery-score.bin` + `.json` | 2.3 MB | Grocery store access score |
| `transit-score.bin` + `.json` | 2.3 MB | Transit/walkability score |
| `walkability-score.bin` + `.json` | 2.3 MB | Walkability score |
| `water-quality-score.bin` + `.json` | 2.3 MB | Water/drought score |
| `ticks-score.bin` + `.json` | 2.3 MB | Tick/Lyme disease risk score |
| `temperateness-score.bin` + `.json` | 2.3 MB | Climate comfort score |
| `pm25-grid.bin` + `.json` | 2.3 MB | Raw PM2.5 values (µg/m³) for point query |
| `noise-grid.bin` + `.json` | 58.5 MB | Raw noise raster for point query |

**Total: ~115 MB**

### Score Grid Format

```json
{ "width": 1170, "height": 500, "originX": -125.0, "originY": 49.5, "pixelWidth": 0.05, "pixelHeight": 0.05 }
```

Binary: row-major Float32, north-to-south, west-to-east.

## PMTiles Annotation Overlays (`public/tiles/`)

Vector/raster tiles shown as muted white overlays for reference when a layer is active.

| File | Size | Description |
|------|------|-------------|
| `tree-canopy.pmtiles` | 222 MB | Hansen GFC raster canopy coverage |
| `climate-vulnerability.pmtiles` | 121 MB | CDC SVI census tract polygons |
| `transit.pmtiles` | 101 MB | EPA SLD block group polygons |
| `home-prices.pmtiles` | 77 MB | Zillow ZHVI zip code polygons |
| `school-quality.pmtiles` | 25 MB | NCES school point features |
| `voting-dem.pmtiles` | 25 MB | Election results county polygons |
| `voting-gop.pmtiles` | 25 MB | Election results county polygons |
| `ticks.pmtiles` | 19 MB | CDC Lyme disease county polygons |
| `water-quality.pmtiles` | 20 MB | Drought monitor county polygons |
| `crime.pmtiles` | 10 MB | County Health Rankings county polygons |
| `noise.pmtiles` | 5.5 MB | Road noise raster tiles |
| `power-plants.pmtiles` | 6.5 MB | EPA eGRID plant point features |
| `pm25.pmtiles` | 3.6 MB | PM2.5 interpolated raster tiles |
| `grocery.pmtiles` | 3.6 MB | USDA SNAP retailer point features |
| `protected-areas.pmtiles` | 4.1 MB | USGS PAD-US polygon features |
| `university-quality.pmtiles` | 0.3 MB | NCES IPEDS university point features |

**Total: ~670 MB**

## Regenerating

See `data-pipeline/PIPELINE.md` for instructions on regenerating these files from source data.
