import { queryRasterGrid } from "@/lib/rasterQuery";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const sunshineLayer: LayerDefinition = {
  id: "sunshine",
  name: "Annual Sunshine",
  description:
    "Annual mean solar radiation (kJ/m²/day) from WorldClim v2.1, a proxy for total sunny days per year. Higher is sunnier.",
  category: "environmental",
  icon: "Sun",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/sunshine.pmtiles",
    attribution: "WorldClim v2.1 (srad, 1970–2000 normals)",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "sunshine-raster",
        type: "raster",
        source: "sunshine-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  // Score grid already stores 0-1 normalized value.
  normalizeValue(score: number): number {
    return Math.max(0, Math.min(1, score));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/sunshine-score",
  scoreGridPathWinter: "/data/sunshine-winter-score",
  scoreGridPathSummer: "/data/sunshine-summer-score",
  attributionUrl: "https://worldclim.org/data/worldclim21.html",

  legend: {
    type: "continuous",
    stops: [
      { value: 9000,  color: "#9baabf", label: "Overcast (Pacific NW)" },
      { value: 13000, color: "#c8c888", label: "Partly cloudy" },
      { value: 17000, color: "#f5d040", label: "Mostly sunny" },
      { value: 20000, color: "#ff9900", label: "Very sunny" },
      { value: 23000, color: "#ff6600", label: "Desert SW" },
    ],
    unit: "kJ/m²/day",
  },

  async queryPoint(lng, lat) {
    return queryRasterGrid("/data/sunshine-score", lng, lat);
  },
};

registerLayer(sunshineLayer);
export default sunshineLayer;
