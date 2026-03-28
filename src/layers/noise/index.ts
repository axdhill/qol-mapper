import { queryRasterGrid } from "@/lib/rasterQuery";
import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const noiseLayer: LayerDefinition = {
  id: "noise",
  name: "Estimated Noise",
  description:
    "Estimated ambient noise levels derived from road network density and classification. Lower is better.",
  category: "environmental",
  icon: "Volume2",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/noise.pmtiles",
    attribution: "Derived from OpenStreetMap",
  },

  minZoom: 4,
  maxZoom: 13,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "noise-raster",
        type: "raster",
        source: "noise-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  normalizeValue(decibels: number): number {
    // Noise levels: <40 dB = quiet rural, 70+ dB = loud urban
    // Score: 1.0 at 30 dB, 0.0 at 75+ dB
    return Math.max(0, Math.min(1, 1 - (decibels - 30) / 45));
  },

  higherIsBetter: false,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/noise-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 30, color: "#1a9850", label: "<30 dB (Quiet)" },
      { value: 45, color: "#91cf60", label: "45 dB" },
      { value: 55, color: "#fee08b", label: "55 dB (Moderate)" },
      { value: 65, color: "#fc8d59", label: "65 dB (Loud)" },
      { value: 75, color: "#d73027", label: "75+ dB (Very Loud)" },
    ],
    unit: "dB",
  },

  async queryPoint(lng, lat) {
    return queryRasterGrid("/data/noise-grid", lng, lat);
  },
};

registerLayer(noiseLayer);
export default noiseLayer;
