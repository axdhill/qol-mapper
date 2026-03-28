import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const votingGopLayer: LayerDefinition = {
  id: "voting-gop",
  name: "Republican Vote Share",
  description:
    "Republican presidential vote share by county. Informational layer.",
  category: "social",
  icon: "Vote",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/voting-gop.pmtiles",
    attribution: "MIT Election Data + Science Lab (MEDSL)",
    sourceLayer: "voting_gop",
  },

  minZoom: 3,
  maxZoom: 12,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "voting-gop-fill",
        type: "fill",
        source: "voting-gop-source",
        "source-layer": "voting_gop",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "gop_share"],
            0.1, "#fff5f0",
            0.3, "#fcbba1",
            0.5, "#fb6a4a",
            0.7, "#cb181d",
            0.9, "#67000d",
          ],
          "fill-opacity": opacity * 0.55,
        },
      },
      {
        id: "voting-gop-outline",
        type: "line",
        source: "voting-gop-source",
        "source-layer": "voting_gop",
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
  scoreGridPath: "/data/voting-gop-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 0.1, color: "#fff5f0", label: "10%" },
      { value: 0.3, color: "#fcbba1", label: "30%" },
      { value: 0.5, color: "#fb6a4a", label: "50%" },
      { value: 0.7, color: "#cb181d", label: "70%" },
      { value: 0.9, color: "#67000d", label: "90%" },
    ],
    unit: "%",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["voting-gop-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.gop_share ?? null;
    }
    return null;
  },
};

registerLayer(votingGopLayer);
export default votingGopLayer;
