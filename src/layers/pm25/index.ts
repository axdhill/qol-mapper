import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";
import { queryRasterGrid } from "@/lib/rasterQuery";

const pm25Layer: LayerDefinition = {
  id: "pm25",
  name: "PM2.5 Air Quality",
  description: "Annual average fine particulate matter (ug/m\u00B3). Lower is better.",
  category: "environmental",
  icon: "Wind",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/pm25.pmtiles",
    attribution: "EPA AirData",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "pm25-raster",
        type: "raster",
        source: "pm25-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  normalizeValue(pm25: number): number {
    // WHO guideline: 5 ug/m3 annual mean.
    // Score: 1.0 at 2 ug/m3 (pristine), 0.0 at 20+ ug/m3 (very unhealthy)
    return Math.max(0, Math.min(1, 1 - (pm25 - 2) / 18));
  },

  higherIsBetter: false,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/pm25-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 2, color: "#440154", label: "2 (Excellent)" },
      { value: 5, color: "#31688e", label: "5 (WHO limit)" },
      { value: 9, color: "#35b779", label: "9 (Moderate)" },
      { value: 12, color: "#fde725", label: "12 (Sensitive)" },
      { value: 20, color: "#ff4444", label: "20+ (Unhealthy)" },
    ],
    unit: "\u03BCg/m\u00B3",
  },

  async queryPoint(lng, lat) {
    return queryRasterGrid("/data/pm25-grid", lng, lat);
  },
};

registerLayer(pm25Layer);
export default pm25Layer;
