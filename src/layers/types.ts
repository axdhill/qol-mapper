export type LayerCategory =
  | "environmental"
  | "infrastructure"
  | "social"
  | "economic";

export interface LegendStop {
  value: number;
  color: string;
  label: string;
}

export interface LayerLegend {
  type: "continuous" | "categorical";
  stops: LegendStop[];
  unit: string;
}

export interface LayerSource {
  type: "raster-pmtiles" | "vector-pmtiles" | "geojson";
  url: string;
  attribution?: string;
  /** For vector sources: the source layer name inside the PMTiles/MVT */
  sourceLayer?: string;
}

/**
 * Core interface that every data layer must implement.
 *
 * MapLibre types are kept as `unknown` / `any` here to avoid importing
 * maplibre-gl in modules that may be evaluated during SSR.
 * The actual types are enforced at usage sites (MapContainer).
 */
export interface LayerDefinition {
  /** Unique identifier, e.g. "pm25" */
  id: string;
  /** Display name shown in UI */
  name: string;
  /** Short description for tooltips */
  description: string;
  /** Category for grouping in sidebar */
  category: LayerCategory;
  /** Lucide icon name */
  icon: string;

  /** Data source configuration */
  source: LayerSource;

  /** Zoom range where this layer is visible/meaningful */
  minZoom: number;
  maxZoom: number;

  /**
   * Return MapLibre LayerSpecification(s) for rendering.
   * The source will be added automatically by the map container.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getMapLibreStyle(opacity: number): any[];

  /**
   * Given a raw data value from this layer, return a normalized 0-1 QoL score.
   * 0 = worst quality of life, 1 = best quality of life.
   */
  normalizeValue(rawValue: number): number;

  /** Whether higher raw values indicate better QoL (e.g., tree cover: true, PM2.5: false) */
  higherIsBetter: boolean;

  /** Default weight (0-1) for composite scoring */
  defaultWeight: number;

  /** Legend configuration for UI display */
  legend: LayerLegend;

  /**
   * Query the raw value at a specific geographic point.
   * Used for the detail panel when user clicks on the map.
   * The `map` parameter is a maplibregl.Map instance.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  queryPoint?(lng: number, lat: number, map: any): Promise<number | null>;

  /**
   * Whether tile data has been processed and is available.
   * Layers with dataAvailable=false are shown in the sidebar
   * but greyed out and non-toggleable.
   */
  dataAvailable?: boolean;

  /**
   * Path to pre-computed 0-1 score grid (e.g. "/data/pm25-score").
   * Layers with a scoreGridPath participate in the composite overlay.
   * The grid files are {scoreGridPath}.bin (Float32Array) + .json (metadata).
   */
  scoreGridPath?: string;

  /** Optional: Zillow integration hook for future correlation analysis */
  zillowHook?: {
    correlationField?: string;
  };
}
