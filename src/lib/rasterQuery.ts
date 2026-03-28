/**
 * Client-side raster grid querying.
 *
 * Loads a raw Float32Array binary grid + JSON metadata,
 * then provides point queries by geographic coordinate.
 */

interface GridMeta {
  width: number;
  height: number;
  originX: number;
  originY: number;
  pixelWidth: number;
  pixelHeight: number;
  nodata: number;
}

interface RasterGrid {
  data: Float32Array;
  meta: GridMeta;
}

const gridCache = new Map<string, Promise<RasterGrid>>();

async function loadGrid(basePath: string): Promise<RasterGrid> {
  const [metaRes, binRes] = await Promise.all([
    fetch(`${basePath}.json`),
    fetch(`${basePath}.bin`),
  ]);

  const meta: GridMeta = await metaRes.json();
  const buffer = await binRes.arrayBuffer();
  const data = new Float32Array(buffer);

  return { data, meta };
}

function getGrid(basePath: string): Promise<RasterGrid> {
  let cached = gridCache.get(basePath);
  if (!cached) {
    cached = loadGrid(basePath);
    gridCache.set(basePath, cached);
  }
  return cached;
}

/**
 * Query a raster grid value at a geographic point.
 *
 * @param basePath - Path prefix for the grid files (e.g. "/data/pm25-grid")
 *                   Expects {basePath}.json and {basePath}.bin
 * @param lng - Longitude
 * @param lat - Latitude
 * @returns The grid value at that point, or null if outside bounds / nodata
 */
export async function queryRasterGrid(
  basePath: string,
  lng: number,
  lat: number
): Promise<number | null> {
  const grid = await getGrid(basePath);
  const { data, meta } = grid;

  // Convert geographic coords to pixel coords
  const col = Math.floor((lng - meta.originX) / meta.pixelWidth);
  const row = Math.floor((lat - meta.originY) / meta.pixelHeight);

  if (col < 0 || col >= meta.width || row < 0 || row >= meta.height) {
    return null;
  }

  const value = data[row * meta.width + col];

  if (value === meta.nodata || isNaN(value)) {
    return null;
  }

  return value;
}
