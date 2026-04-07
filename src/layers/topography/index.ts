import { queryRasterGrid } from "@/lib/rasterQuery";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const topographyLayer: LayerDefinition = {
  id: "topography",
  name: "Topographic Interest",
  description:
    "Local terrain ruggedness based on elevation variability within a ~25 km radius. Scored logarithmically — rolling hills score meaningfully, not just mountain ranges.",
  category: "environmental",
  icon: "Mountain",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/topography.pmtiles",
    attribution: "WorldClim v2.1 SRTM 30-arcsec elevation",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "topography-raster",
        type: "raster",
        source: "topography-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  // The score grid already stores the 0-1 log-normalized value.
  normalizeValue(score: number): number {
    return Math.max(0, Math.min(1, score));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/topography-score",
  attributionUrl: "https://worldclim.org/data/worldclim21.html",

  legend: {
    type: "continuous",
    stops: [
      { value: 0.0,  color: "#f0ead2", label: "Flat" },
      { value: 0.33, color: "#d4b382", label: "Gentle hills" },
      { value: 0.63, color: "#a06028", label: "Rolling hills" },
      { value: 0.85, color: "#6e3a10", label: "Mountains" },
      { value: 1.0,  color: "#2a0e02", label: "Very rugged" },
    ],
    unit: "terrain score",
  },

  async queryPoint(lng, lat) {
    return queryRasterGrid("/data/topography-score", lng, lat);
  },
};

registerLayer(topographyLayer);
export default topographyLayer;
