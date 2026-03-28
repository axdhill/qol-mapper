import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const walkabilityLayer: LayerDefinition = {
  id: "walkability",
  name: "Walkability / Transit",
  description:
    "Composite walkability and transit access score from EPA Smart Location Database v3.0. " +
    "Combines National Walkability Index (60%) with aggregate transit frequency (40%). " +
    "Higher scores indicate more walkable neighborhoods with better transit access.",
  category: "infrastructure",
  icon: "Footprints",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/transit.pmtiles",
    attribution: "EPA Smart Location Database v3.0 — Public Domain",
    sourceLayer: "transit",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "walkability-fill",
        type: "fill",
        source: "walkability-source",
        "source-layer": "transit",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "walkability"],
            0.0, "#f7fbff",
            0.2, "#c6dbef",
            0.4, "#6baed6",
            0.6, "#2171b5",
            0.8, "#084594",
            1.0, "#08306b",
          ],
          "fill-opacity": opacity * 0.6,
        },
      },
    ];
  },

  normalizeValue(rawValue: number): number {
    // Values are already normalized 0-1 composite scores
    return Math.max(0, Math.min(1, rawValue));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/walkability-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 0.0, color: "#f7fbff", label: "0.0 (Car-dependent)" },
      { value: 0.25, color: "#c6dbef", label: "0.25" },
      { value: 0.5, color: "#6baed6", label: "0.5 (Somewhat walkable)" },
      { value: 0.75, color: "#2171b5", label: "0.75" },
      { value: 1.0, color: "#08306b", label: "1.0 (Walker's paradise)" },
    ],
    unit: "score (0–1)",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["walkability-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.walkability ?? null;
    }
    return null;
  },
};

registerLayer(walkabilityLayer);
export default walkabilityLayer;
