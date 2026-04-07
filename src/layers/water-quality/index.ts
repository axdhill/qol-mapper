import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const waterQualityLayer: LayerDefinition = {
  id: "water-quality",
  name: "Water / Drought",
  description:
    "Drought severity from US Drought Monitor. No drought = best score.",
  category: "environmental",
  icon: "Droplets",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/water-quality.pmtiles",
    attribution: "US Drought Monitor",
    sourceLayer: "water_quality",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "water-quality-fill",
        type: "fill",
        source: "water-quality-source",
        "source-layer": "water_quality",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "drought_score"],
            0.0, "#8b0000",
            0.2, "#d7301f",
            0.4, "#fc8d59",
            0.6, "#fdcc8a",
            0.8, "#b3d9f2",
            1.0, "#2166ac",
          ],
          "fill-opacity": opacity * 0.55,
        },
      },
      {
        id: "water-quality-outline",
        type: "line",
        source: "water-quality-source",
        "source-layer": "water_quality",
        paint: {
          "line-color": "rgba(255,255,255,0.1)",
          "line-width": 0.5,
        },
        minzoom: 6,
      },
    ];
  },

  normalizeValue(droughtScore: number): number {
    return Math.max(0, Math.min(1, droughtScore));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/water-quality-score",
  attributionUrl: "https://droughtmonitor.unl.edu/",

  legend: {
    type: "continuous",
    stops: [
      { value: 0, color: "#8b0000", label: "D4" },
      { value: 0.2, color: "#d7301f", label: "D3" },
      { value: 0.4, color: "#fc8d59", label: "D2" },
      { value: 0.6, color: "#fdcc8a", label: "D1" },
      { value: 0.8, color: "#b3d9f2", label: "D0" },
      { value: 1, color: "#2166ac", label: "None" },
    ],
    unit: "drought",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["water-quality-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.drought_score ?? null;
    }
    return null;
  },
};

registerLayer(waterQualityLayer);
export default waterQualityLayer;
