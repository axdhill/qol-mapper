/**
 * Accessible color ramps for data visualization.
 * All ramps go from low to high values.
 */

export const VIRIDIS = [
  "#440154", "#482777", "#3e4989", "#31688e", "#26828e",
  "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725",
];

export const MAGMA = [
  "#000004", "#180f3d", "#440f76", "#721f81", "#9e2f7f",
  "#cd4071", "#f1605d", "#fd9668", "#feca8d", "#fcfdbf",
];

export const CIVIDIS = [
  "#00224e", "#123570", "#1d4d84", "#2a6597", "#3d7da8",
  "#5694b7", "#72abc3", "#8fc2cd", "#b0d8d5", "#d4eddb",
];

export const INFERNO = [
  "#000004", "#1b0c41", "#4a0c6b", "#781c6d", "#a52c60",
  "#cf4446", "#ed6925", "#fb9b06", "#f7d13d", "#fcffa4",
];

/** Green ramp for vegetation/tree data */
export const GREENS = [
  "#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476",
  "#41ab5d", "#238b45", "#006d2c", "#00441b",
];

/** Red-to-blue diverging ramp (red = bad, blue = good) */
export const RD_BU = [
  "#b2182b", "#d6604d", "#f4a582", "#fddbc7", "#f7f7f7",
  "#d1e5f0", "#92c5de", "#4393c3", "#2166ac",
];

/**
 * Interpolate a color from a ramp given a normalized value (0-1).
 */
export function interpolateColor(value: number, ramp: string[]): string {
  const clamped = Math.max(0, Math.min(1, value));
  const idx = clamped * (ramp.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return ramp[lo];

  const t = idx - lo;
  const c1 = hexToRgb(ramp[lo]);
  const c2 = hexToRgb(ramp[hi]);

  const r = Math.round(c1.r + (c2.r - c1.r) * t);
  const g = Math.round(c1.g + (c2.g - c1.g) * t);
  const b = Math.round(c1.b + (c2.b - c1.b) * t);

  return `rgb(${r},${g},${b})`;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) return { r: 0, g: 0, b: 0 };
  return {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  };
}

/**
 * Generate a MapLibre interpolate expression for coloring raster data.
 * Maps numeric values [min, max] to colors in the given ramp.
 */
export function generateMaplibreColorExpr(
  ramp: string[],
  min: number,
  max: number
): unknown[] {
  const expr: unknown[] = ["interpolate", ["linear"], ["raster-value"]];
  for (let i = 0; i < ramp.length; i++) {
    const value = min + (i / (ramp.length - 1)) * (max - min);
    expr.push(value, ramp[i]);
  }
  return expr;
}

/**
 * Generate a CSS linear-gradient string for legend display.
 */
export function rampToGradient(ramp: string[]): string {
  return `linear-gradient(to right, ${ramp.join(", ")})`;
}
