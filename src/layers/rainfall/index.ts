import { queryRasterGrid } from "@/lib/rasterQuery";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const rainfallLayer: LayerDefinition = {
  id: "rainfall",
  name: "Annual Rainfall",
  description:
    "Total annual precipitation (mm/year) from WorldClim v2.1 30-year normals (1970–2000). Scored on a log scale — the gap between 200 mm and 400 mm counts as much as 1000 mm to 2000 mm.",
  category: "environmental",
  icon: "CloudRain",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/rainfall.pmtiles",
    attribution: "WorldClim v2.1 (prec, 1970–2000 normals)",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "rainfall-raster",
        type: "raster",
        source: "rainfall-source",
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
  scoreGridPath: "/data/rainfall-score",
  attributionUrl: "https://worldclim.org/data/worldclim21.html",

  legend: {
    type: "continuous",
    stops: [
      { value: 0.0,  color: "#c39b5f", label: "<100 mm (desert)" },
      { value: 0.28, color: "#afc87d", label: "~250 mm (semi-arid)" },
      { value: 0.50, color: "#64aa5f", label: "~500 mm" },
      { value: 0.71, color: "#195f96", label: "~1000 mm" },
      { value: 1.0,  color: "#0a2d8c", label: "2500+ mm (rainforest)" },
    ],
    unit: "score (log-scaled)",
  },

  async queryPoint(lng, lat) {
    return queryRasterGrid("/data/rainfall-score", lng, lat);
  },
};

registerLayer(rainfallLayer);
export default rainfallLayer;
