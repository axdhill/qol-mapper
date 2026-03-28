/** Continental US center coordinates */
export const CONUS_CENTER: [number, number] = [-98.5, 39.8];

/** Default zoom level showing full CONUS */
export const DEFAULT_ZOOM = 4;

/** Zoom level when flying to a searched location */
export const SEARCH_ZOOM = 11;

/** Debounce delay for search input (ms) */
export const SEARCH_DEBOUNCE_MS = 300;

/** Map animation duration for flyTo (ms) */
export const FLY_TO_DURATION_MS = 2000;

/** Category display names and order */
export const CATEGORY_LABELS: Record<string, string> = {
  environmental: "Environmental",
  infrastructure: "Infrastructure",
  social: "Social",
  economic: "Economic",
};

/** Category display order */
export const CATEGORY_ORDER = [
  "environmental",
  "social",
  "economic",
  "infrastructure",
];
