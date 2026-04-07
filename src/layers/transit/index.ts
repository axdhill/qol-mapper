import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const transitLayer: LayerDefinition = {
  id: "transit",
  name: "Walkability / Transit",
  description:
    "National Walkability Index from EPA Smart Location Database. Higher is more walkable.",
  category: "infrastructure",
  icon: "Footprints",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/transit.pmtiles",
    attribution: "EPA Smart Location Database v3.0",
    sourceLayer: "transit",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "transit-fill",
        type: "fill",
        source: "transit-source",
        "source-layer": "transit",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "walkability"],
            0.0, "#fff5eb",
            0.25, "#fdbe85",
            0.5, "#fd8d3c",
            0.75, "#e6550d",
            1.0, "#a63603",
          ],
          "fill-opacity": opacity * 0.55,
        },
      },
    ];
  },

  normalizeValue(walkability: number): number {
    return Math.max(0, Math.min(1, walkability));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/transit-score",
  attributionUrl: "https://www.epa.gov/smartgrowth/smart-location-mapping",

  legend: {
    type: "continuous",
    stops: [
      { value: 1, color: "#fff5eb", label: "1" },
      { value: 5, color: "#fdbe85", label: "5" },
      { value: 10, color: "#fd8d3c", label: "10" },
      { value: 15, color: "#e6550d", label: "15" },
      { value: 20, color: "#a63603", label: "20" },
    ],
    unit: "NWI",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["transit-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.walkability ?? null;
    }
    return null;
  },
};

registerLayer(transitLayer);
export default transitLayer;
