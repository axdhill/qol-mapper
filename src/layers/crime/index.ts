import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const crimeLayer: LayerDefinition = {
  id: "crime",
  name: "Homicide Rate",
  description:
    "Homicide rate per 100,000 population by county (County Health Rankings). Lower is better.",
  category: "social",
  icon: "ShieldAlert",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/crime.pmtiles",
    attribution: "County Health Rankings (FBI UCR)",
    sourceLayer: "crime",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "crime-fill",
        type: "fill",
        source: "crime-source",
        "source-layer": "crime",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "crime_rate"],
            0, "#ffffb2",
            5, "#fecc5c",
            10, "#fd8d3c",
            15, "#f03b20",
            20, "#bd0026",
          ],
          "fill-opacity": opacity * 0.55,
        },
      },
      {
        id: "crime-outline",
        type: "line",
        source: "crime-source",
        "source-layer": "crime",
        paint: {
          "line-color": "rgba(255,255,255,0.1)",
          "line-width": 0.5,
        },
        minzoom: 6,
      },
    ];
  },

  normalizeValue(rate: number): number {
    // 0 per 100k = 1.0 (safest), 20+ per 100k = 0.0
    return Math.max(0, Math.min(1, 1 - rate / 20));
  },

  higherIsBetter: false,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/crime-score",
  attributionUrl: "https://www.countyhealthrankings.org/health-data/methodology-and-sources/data-documentation",

  legend: {
    type: "continuous",
    stops: [
      { value: 0, color: "#ffffb2", label: "0" },
      { value: 5, color: "#fecc5c", label: "5" },
      { value: 10, color: "#fd8d3c", label: "10" },
      { value: 15, color: "#f03b20", label: "15" },
      { value: 20, color: "#bd0026", label: "20+" },
    ],
    unit: "per 100k",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["crime-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.crime_rate ?? null;
    }
    return null;
  },
};

registerLayer(crimeLayer);
export default crimeLayer;
