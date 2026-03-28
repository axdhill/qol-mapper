import { queryRasterGrid } from "@/lib/rasterQuery";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const temperatenessLayer: LayerDefinition = {
  id: "temperateness",
  name: "Temperateness",
  description:
    "Year-round temperature comfort. Penalizes hot summers and cold winters — a place at 70°F year-round scores perfectly.",
  category: "environmental",
  icon: "Thermometer",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/temperateness.pmtiles",
    attribution: "WorldClim 2.1 (30-year normals, 1970–2000)",
  },

  minZoom: 3,
  maxZoom: 14,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "temperateness-raster",
        type: "raster",
        source: "temperateness-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  normalizeValue(score: number): number {
    return Math.max(0, Math.min(1, score));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/temperateness-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 0.0, color: "#d73027", label: "Harsh (−20°F / 100°F)" },
      { value: 0.3, color: "#fc8d59", label: "Tough extremes" },
      { value: 0.5, color: "#fee08b", label: "Moderate seasons" },
      { value: 0.75, color: "#91cf60", label: "Mild" },
      { value: 1.0, color: "#1a9850", label: "Ideal (~70°F year-round)" },
    ],
    unit: "score",
  },

  async queryPoint(lng, lat) {
    return queryRasterGrid("/data/temperateness-score", lng, lat);
  },
};

registerLayer(temperatenessLayer);
export default temperatenessLayer;
