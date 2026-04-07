import type maplibregl from "maplibre-gl";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const universityQualityLayer: LayerDefinition = {
  id: "university-quality",
  name: "University Quality",
  description:
    "Postsecondary institutions scored by graduation rate, research output, and program breadth.",
  category: "social",
  icon: "BookOpen",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/university-quality.pmtiles",
    attribution: "NCES IPEDS",
    sourceLayer: "universities",
  },

  minZoom: 4,
  maxZoom: 16,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "university-quality-circles",
        type: "circle",
        source: "university-quality-source",
        "source-layer": "universities",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            4, ["interpolate", ["linear"], ["get", "enrollment"], 0, 2, 10000, 5, 50000, 10],
            12, ["interpolate", ["linear"], ["get", "enrollment"], 0, 5, 10000, 12, 50000, 22],
          ],
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "quality_score"],
            0, "#fee5d9",
            0.25, "#fcae91",
            0.5, "#fb6a4a",
            0.75, "#de2d26",
            1.0, "#a50f15",
          ],
          "circle-opacity": opacity * 0.75,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "rgba(255,255,255,0.5)",
        },
      },
    ];
  },

  normalizeValue(qualityScore: number): number {
    return Math.max(0, Math.min(1, qualityScore));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/universities-score",
  attributionUrl: "https://nces.ed.gov/ipeds/",

  legend: {
    type: "continuous",
    stops: [
      { value: 0, color: "#fee5d9", label: "Low" },
      { value: 0.5, color: "#fb6a4a", label: "Average" },
      { value: 1.0, color: "#a50f15", label: "Top Tier" },
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
      layers: ["university-quality-circles"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.quality_score ?? null;
    }
    return null;
  },
};

registerLayer(universityQualityLayer);
export default universityQualityLayer;
