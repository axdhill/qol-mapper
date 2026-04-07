import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const protectedAreasLayer: LayerDefinition = {
  id: "protected-areas",
  name: "Parks & Protected Areas",
  description:
    "National parks, state parks, national forests, and other protected areas. Proximity improves QoL.",
  category: "environmental",
  icon: "TreePine",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/protected-areas.pmtiles",
    attribution: "USGS PAD-US",
    sourceLayer: "protected_areas",
  },

  minZoom: 3,
  maxZoom: 14,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "protected-areas-fill",
        type: "fill",
        source: "protected-areas-source",
        "source-layer": "protected_areas",
        paint: {
          "fill-color": [
            "match",
            ["get", "designation"],
            "National Park", "#2d6a4f",
            "State Park", "#40916c",
            "National Forest", "#52b788",
            "Wilderness Area", "#1b4332",
            "National Wildlife Refuge", "#74c69d",
            "#95d5b2", // default
          ],
          "fill-opacity": opacity * 0.4,
        },
      },
      {
        id: "protected-areas-outline",
        type: "line",
        source: "protected-areas-source",
        "source-layer": "protected_areas",
        paint: {
          "line-color": "#2d6a4f",
          "line-width": 1,
          "line-opacity": opacity * 0.6,
        },
      },
    ];
  },

  normalizeValue(distanceKm: number): number {
    // Distance to nearest protected area: 0 km (or inside) = 1.0, 100+ km = 0
    return Math.max(0, Math.min(1, 1 - distanceKm / 100));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/protected-areas-score",
  attributionUrl: "https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-download",

  legend: {
    type: "categorical",
    stops: [
      { value: 0, color: "#2d6a4f", label: "National Park" },
      { value: 1, color: "#40916c", label: "State Park" },
      { value: 2, color: "#52b788", label: "National Forest" },
      { value: 3, color: "#1b4332", label: "Wilderness" },
      { value: 4, color: "#74c69d", label: "Wildlife Refuge" },
    ],
    unit: "",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["protected-areas-fill"],
    });
    if (features.length > 0) {
      return 0; // Inside a protected area
    }
    return null;
  },
};

registerLayer(protectedAreasLayer);
export default protectedAreasLayer;
