import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const treeCanopyLayer: LayerDefinition = {
  id: "tree-canopy",
  name: "Tree Canopy Cover",
  description: "Percentage of area covered by tree canopy. Higher is better for QoL.",
  category: "environmental",
  icon: "Trees",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/tree-canopy.pmtiles",
    attribution: "Hansen/UMD/Google/USGS/NASA (GFC v1.11)",
  },

  minZoom: 3,
  maxZoom: 13,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "tree-canopy-raster",
        type: "raster",
        source: "tree-canopy-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  normalizeValue(pct: number): number {
    // 0% canopy = 0 score, 80%+ = 1.0
    return Math.min(1, Math.max(0, pct / 80));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/tree-canopy-score",
  attributionUrl: "https://glad.umd.edu/dataset/global-forest-change",

  legend: {
    type: "continuous",
    stops: [
      { value: 0, color: "#f7fcf5", label: "0%" },
      { value: 20, color: "#c7e9c0", label: "20%" },
      { value: 40, color: "#74c476", label: "40%" },
      { value: 60, color: "#238b45", label: "60%" },
      { value: 80, color: "#00441b", label: "80%+" },
    ],
    unit: "%",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["tree-canopy-raster"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.value ?? null;
    }
    return null;
  },
};

registerLayer(treeCanopyLayer);
export default treeCanopyLayer;
