import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const votingDemLayer: LayerDefinition = {
  id: "voting-dem",
  name: "Harris 2024 Vote Share",
  description:
    "Kamala Harris 2024 presidential vote share by county (MEDSL). Informational layer.",
  category: "social",
  icon: "Vote",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/voting-dem.pmtiles",
    attribution: "MIT Election Data + Science Lab (MEDSL)",
    sourceLayer: "voting_dem",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "voting-dem-fill",
        type: "fill",
        source: "voting-dem-source",
        "source-layer": "voting_dem",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "dem_share"],
            0.1, "#f7fbff",
            0.3, "#c6dbef",
            0.5, "#6baed6",
            0.7, "#2171b5",
            0.9, "#08306b",
          ],
          "fill-opacity": opacity * 0.55,
        },
      },
      {
        id: "voting-dem-outline",
        type: "line",
        source: "voting-dem-source",
        "source-layer": "voting_dem",
        paint: {
          "line-color": "rgba(255,255,255,0.1)",
          "line-width": 0.5,
        },
        minzoom: 6,
      },
    ];
  },

  normalizeValue(share: number): number {
    return Math.max(0, Math.min(1, share));
  },

  higherIsBetter: true,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/voting-dem-score",
  attributionUrl: "https://electionlab.mit.edu/data",

  legend: {
    type: "continuous",
    stops: [
      { value: 0.1, color: "#f7fbff", label: "10%" },
      { value: 0.3, color: "#c6dbef", label: "30%" },
      { value: 0.5, color: "#6baed6", label: "50%" },
      { value: 0.7, color: "#2171b5", label: "70%" },
      { value: 0.9, color: "#08306b", label: "90%" },
    ],
    unit: "%",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["voting-dem-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.dem_share ?? null;
    }
    return null;
  },
};

registerLayer(votingDemLayer);
export default votingDemLayer;
