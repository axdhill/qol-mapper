import type maplibregl from "maplibre-gl";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const schoolQualityLayer: LayerDefinition = {
  id: "school-quality",
  name: "School Quality (K-12)",
  description:
    "K-12 school locations scored by AP course offerings, STEM programs, and college readiness.",
  category: "social",
  icon: "GraduationCap",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/school-quality.pmtiles",
    attribution: "NCES Common Core of Data",
    sourceLayer: "schools",
  },

  minZoom: 6,
  maxZoom: 16,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "school-quality-circles",
        type: "circle",
        source: "school-quality-source",
        "source-layer": "schools",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6, 2,
            10, 4,
            14, 8,
          ],
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "quality_score"],
            0, "#d73027",
            0.25, "#fc8d59",
            0.5, "#fee08b",
            0.75, "#91cf60",
            1.0, "#1a9850",
          ],
          "circle-opacity": opacity * 0.8,
          "circle-stroke-width": 1,
          "circle-stroke-color": "rgba(255,255,255,0.3)",
        },
      },
    ];
  },

  normalizeValue(qualityScore: number): number {
    // Already on 0-1 scale from processing pipeline
    return Math.max(0, Math.min(1, qualityScore));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/schools-score",
  attributionUrl: "https://nces.ed.gov/ccd/",

  legend: {
    type: "continuous",
    stops: [
      { value: 0, color: "#d73027", label: "Low" },
      { value: 0.25, color: "#fc8d59", label: "" },
      { value: 0.5, color: "#fee08b", label: "Average" },
      { value: 0.75, color: "#91cf60", label: "" },
      { value: 1.0, color: "#1a9850", label: "Excellent" },
    ],
    unit: "score",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const bbox: [maplibregl.PointLike, maplibregl.PointLike] = [
      [point.x - 30, point.y - 30],
      [point.x + 30, point.y + 30],
    ];
    const features = map.queryRenderedFeatures(bbox, {
      layers: ["school-quality-circles"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.quality_score ?? null;
    }
    return null;
  },
};

registerLayer(schoolQualityLayer);
export default schoolQualityLayer;
