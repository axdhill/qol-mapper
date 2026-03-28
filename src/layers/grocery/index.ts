import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const groceryLayer: LayerDefinition = {
  id: "grocery",
  name: "Grocery Store Access",
  description:
    "Distance to nearest grocery store. Closer is better — identifies food deserts.",
  category: "social",
  icon: "ShoppingCart",

  source: {
    type: "raster-pmtiles",
    url: "pmtiles:///tiles/grocery.pmtiles",
    attribution: "OpenStreetMap / USDA SNAP",
  },

  minZoom: 3,
  maxZoom: 10,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "grocery-raster",
        type: "raster",
        source: "grocery-source",
        paint: {
          "raster-opacity": opacity,
          "raster-resampling": "nearest",
        },
      },
    ];
  },

  normalizeValue(distanceScore: number): number {
    return Math.max(0, Math.min(1, distanceScore));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/grocery-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 0, color: "#e34a33", label: "Far" },
      { value: 0.5, color: "#fdd49e", label: "Moderate" },
      { value: 1, color: "#238b45", label: "Close" },
    ],
    unit: "access",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["grocery-raster"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.value ?? null;
    }
    return null;
  },
};

registerLayer(groceryLayer);
export default groceryLayer;
