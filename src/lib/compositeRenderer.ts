/**
 * Client-side composite score grid computation and canvas rendering.
 *
 * Loads pre-computed 0-1 score grids for each layer, computes a weighted
 * composite, and renders it to an HTML canvas for MapLibre overlay.
 *
 * The score grids are stored in geographic coordinates (uniform lat/lon),
 * but MapLibre's image source linearly interpolates in Web Mercator space.
 * We resample from geographic → Mercator when building the canvas so that
 * the overlay aligns correctly on the map.
 */

interface ScoreGridMeta {
  width: number;
  height: number;
  originX: number;
  originY: number;
  pixelWidth: number;
  pixelHeight: number;
}

interface ScoreGrid {
  data: Float32Array;
  meta: ScoreGridMeta;
}

// Cache loaded grids
const gridCache = new Map<string, Promise<ScoreGrid>>();

async function loadScoreGrid(basePath: string): Promise<ScoreGrid> {
  const [metaRes, binRes] = await Promise.all([
    fetch(`${basePath}.json`),
    fetch(`${basePath}.bin`),
  ]);

  if (!metaRes.ok || !binRes.ok) {
    throw new Error(`Failed to load score grid: ${basePath}`);
  }

  const meta: ScoreGridMeta = await metaRes.json();
  const buffer = await binRes.arrayBuffer();
  const data = new Float32Array(buffer);

  return { data, meta };
}

export function getScoreGrid(basePath: string): Promise<ScoreGrid> {
  let cached = gridCache.get(basePath);
  if (!cached) {
    cached = loadScoreGrid(basePath);
    gridCache.set(basePath, cached);
  }
  return cached;
}

/**
 * Query a score grid value at a geographic point.
 */
export async function queryScoreGrid(
  basePath: string,
  lng: number,
  lat: number
): Promise<number | null> {
  const grid = await getScoreGrid(basePath);
  const { data, meta } = grid;

  const col = Math.floor((lng - meta.originX) / meta.pixelWidth);
  const row = Math.floor((lat - meta.originY) / meta.pixelHeight);

  if (col < 0 || col >= meta.width || row < 0 || row >= meta.height) {
    return null;
  }

  const value = data[row * meta.width + col];
  if (isNaN(value)) return null;
  return value;
}

// --- Mercator projection helpers ---

function latToMercatorY(lat: number): number {
  const latRad = (lat * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + latRad / 2));
}

function mercatorYToLat(y: number): number {
  return (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * (180 / Math.PI);
}

/**
 * Composite color ramp: red (bad) → yellow → green (good)
 */
const COMPOSITE_RAMP = [
  [215, 48, 39],    // 0.0 - red (very poor)
  [252, 141, 89],   // 0.2 - orange
  [254, 224, 139],  // 0.4 - yellow
  [145, 207, 96],   // 0.6 - light green
  [26, 152, 80],    // 0.8 - green
  [0, 104, 55],     // 1.0 - dark green (excellent)
];

export function scoreToRGBA(score: number): [number, number, number, number] {
  const clamped = Math.max(0, Math.min(1, score));
  const idx = clamped * (COMPOSITE_RAMP.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, COMPOSITE_RAMP.length - 1);
  const t = idx - lo;

  const r = Math.round(COMPOSITE_RAMP[lo][0] + (COMPOSITE_RAMP[hi][0] - COMPOSITE_RAMP[lo][0]) * t);
  const g = Math.round(COMPOSITE_RAMP[lo][1] + (COMPOSITE_RAMP[hi][1] - COMPOSITE_RAMP[lo][1]) * t);
  const b = Math.round(COMPOSITE_RAMP[lo][2] + (COMPOSITE_RAMP[hi][2] - COMPOSITE_RAMP[lo][2]) * t);

  return [r, g, b, 200]; // Semi-transparent
}

export const COMPOSITE_RAMP_CSS = `linear-gradient(to right, rgb(215,48,39), rgb(252,141,89), rgb(254,224,139), rgb(145,207,96), rgb(26,152,80), rgb(0,104,55))`;

export interface CompositeInput {
  gridPath: string;
  weight: number;
}

/**
 * Build a lookup table mapping each canvas row (in Mercator space) to
 * the corresponding row in the geographic score grid.
 *
 * MapLibre's image source linearly interpolates pixels between the
 * corner coordinates in Web Mercator. Our grids use uniform lat/lon
 * steps, so we need to resample: for each canvas row we compute the
 * geographic latitude it represents in Mercator and find the matching
 * grid row.
 */
function buildMercatorRowLUT(
  canvasHeight: number,
  meta: ScoreGridMeta,
): Int32Array {
  const northLat = meta.originY; // 49.5
  const southLat = meta.originY + meta.height * meta.pixelHeight; // 24.5

  const mercNorth = latToMercatorY(northLat);
  const mercSouth = latToMercatorY(southLat);

  const lut = new Int32Array(canvasHeight);
  for (let canvasRow = 0; canvasRow < canvasHeight; canvasRow++) {
    // Fraction from top (north) to bottom (south)
    const f = canvasRow / (canvasHeight - 1);
    const mercY = mercNorth + f * (mercSouth - mercNorth);
    const lat = mercatorYToLat(mercY);

    // Map latitude to grid row
    const gridRow = Math.floor((lat - meta.originY) / meta.pixelHeight);
    lut[canvasRow] = Math.max(0, Math.min(meta.height - 1, gridRow));
  }
  return lut;
}

/**
 * Compute the weighted composite of multiple score grids and render to canvas.
 *
 * Each layer is independently normalized to [0, 1] using its own observed
 * min/max before weighting, so every dataset spans the full poor→excellent
 * range regardless of its absolute score values. The composite output is then
 * re-normalized to [0, 1] so the full color ramp is always used.
 *
 * The canvas is rendered in Web Mercator row-space so that MapLibre's
 * image source (which linearly interpolates in Mercator) displays the
 * overlay at the correct geographic positions.
 *
 * @returns Canvas element or null if no grids available
 */
export async function renderCompositeCanvas(
  inputs: CompositeInput[],
): Promise<HTMLCanvasElement | null> {
  if (inputs.length === 0) return null;

  // Load all grids
  const grids: { grid: ScoreGrid; weight: number }[] = [];
  for (const input of inputs) {
    try {
      const grid = await getScoreGrid(input.gridPath);
      grids.push({ grid, weight: input.weight });
    } catch {
      // Skip grids that fail to load
      console.warn(`Failed to load score grid: ${input.gridPath}`);
    }
  }

  if (grids.length === 0) return null;

  const { width, height, ...rest } = grids[0].grid.meta;

  // Canvas matches grid dimensions; we resample rows from geographic → Mercator
  const canvasWidth = width;
  const canvasHeight = height;

  const rowLUT = buildMercatorRowLUT(canvasHeight, grids[0].grid.meta);

  const canvas = document.createElement("canvas");
  canvas.width = canvasWidth;
  canvas.height = canvasHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  // Pass 1: per-layer normalization — compute each layer's observed min/max over
  // all valid CONUS pixels so each dataset spans the full [0, 1] range before weighting.
  const layerMin = new Float32Array(grids.length);
  const layerRange = new Float32Array(grids.length).fill(1);
  for (let k = 0; k < grids.length; k++) {
    const data = grids[k].grid.data;
    let mn = Infinity;
    let mx = -Infinity;
    for (let i = 0; i < data.length; i++) {
      const v = data[i];
      if (!isNaN(v)) {
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
    }
    layerMin[k] = mn === Infinity ? 0 : mn;
    layerRange[k] = mx > mn ? mx - mn : 1;
  }

  // Pass 2: compute composite scores for all pixels.
  // Use -1 as sentinel for "no data" (transparent).
  const compositeScores = new Float32Array(canvasWidth * canvasHeight).fill(-1);

  for (let canvasRow = 0; canvasRow < canvasHeight; canvasRow++) {
    const gridRow = rowLUT[canvasRow];

    for (let col = 0; col < canvasWidth; col++) {
      const gridIdx = gridRow * width + col;

      let weightedSum = 0;
      let totalWeight = 0;

      for (let k = 0; k < grids.length; k++) {
        const { grid, weight } = grids[k];
        const raw = grid.data[gridIdx];
        if (!isNaN(raw) && weight > 0) {
          const v = Math.max(0, Math.min(1, (raw - layerMin[k]) / layerRange[k]));
          weightedSum += v * weight;
          totalWeight += weight;
        }
      }

      if (totalWeight > 0) {
        compositeScores[canvasRow * canvasWidth + col] = weightedSum / totalWeight;
      }
    }
  }

  // Pass 3: re-normalize composite to [0, 1] so the full color ramp is always used,
  // then map to colors.
  let compMin = Infinity;
  let compMax = -Infinity;
  for (let i = 0; i < compositeScores.length; i++) {
    const s = compositeScores[i];
    if (s >= 0) {
      if (s < compMin) compMin = s;
      if (s > compMax) compMax = s;
    }
  }
  const compRange = compMax > compMin ? compMax - compMin : 1;

  const imageData = ctx.createImageData(canvasWidth, canvasHeight);
  const pixels = imageData.data;

  for (let i = 0; i < compositeScores.length; i++) {
    const score = compositeScores[i];
    if (score >= 0) {
      const display = (score - compMin) / compRange;
      const [r, g, b, a] = scoreToRGBA(display);
      const offset = i * 4;
      pixels[offset] = r;
      pixels[offset + 1] = g;
      pixels[offset + 2] = b;
      pixels[offset + 3] = a;
    }
    // else: stays 0,0,0,0 (transparent)
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}
