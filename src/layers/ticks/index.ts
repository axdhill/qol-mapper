import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const ticksLayer: LayerDefinition = {
  id: "ticks",
  name: "Tick-Borne Illness",
  description:
    "Average annual Lyme disease incidence per 100k population by county (CDC, 2018–2022). Lower is better.",
  category: "environmental",
  icon: "Bug",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/ticks.pmtiles",
    attribution: "CDC Lyme Disease Surveillance Data (2018–2022)",
    sourceLayer: "ticks",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "ticks-fill",
        type: "fill",
        source: "ticks-source",
        "source-layer": "ticks",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "lyme_rate"],
            0,   "#1a9850",
            5,   "#91cf60",
            15,  "#fee08b",
            50,  "#fc8d59",
            100, "#d73027",
          ],
          "fill-opacity": opacity * 0.6,
        },
      },
      {
        id: "ticks-outline",
        type: "line",
        source: "ticks-source",
        "source-layer": "ticks",
        paint: {
          "line-color": "rgba(255,255,255,0.1)",
          "line-width": 0.5,
        },
        minzoom: 6,
      },
    ];
  },

  normalizeValue(rate: number): number {
    // 0/100k = 1.0, 50+/100k = 0.0
    return Math.max(0, Math.min(1, 1 - rate / 50));
  },

  higherIsBetter: false,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/ticks-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 0,   color: "#1a9850", label: "0 (none)" },
      { value: 5,   color: "#91cf60", label: "5" },
      { value: 15,  color: "#fee08b", label: "15" },
      { value: 50,  color: "#fc8d59", label: "50" },
      { value: 100, color: "#d73027", label: "100+" },
    ],
    unit: "per 100k/yr",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["ticks-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.lyme_rate ?? null;
    }
    return null;
  },
};

registerLayer(ticksLayer);
export default ticksLayer;
