import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const homePricesLayer: LayerDefinition = {
  id: "home-prices",
  name: "Home Prices",
  description:
    "Median home values by zip code from Zillow Home Value Index. Informational layer.",
  category: "economic",
  icon: "Home",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/home-prices.pmtiles",
    attribution: "Zillow Research (ZHVI)",
    sourceLayer: "home_prices",
  },

  minZoom: 4,
  maxZoom: 14,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "home-prices-fill",
        type: "fill",
        source: "home-prices-source",
        "source-layer": "home_prices",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "median_price"],
            100000, "#ffffcc",
            250000, "#a1dab4",
            400000, "#41b6c4",
            600000, "#2c7fb8",
            1000000, "#253494",
          ],
          "fill-opacity": opacity * 0.55,
        },
      },
      {
        id: "home-prices-outline",
        type: "line",
        source: "home-prices-source",
        "source-layer": "home_prices",
        paint: {
          "line-color": "rgba(255,255,255,0.1)",
          "line-width": 0.5,
        },
        minzoom: 9,
      },
    ];
  },

  normalizeValue(price: number): number {
    // Lower prices = higher affordability score.
    // $100k = 1.0, $1M+ = 0.0 (log scale for better distribution)
    const logMin = Math.log(100000);
    const logMax = Math.log(1000000);
    const logPrice = Math.log(Math.max(100000, Math.min(1000000, price)));
    return 1 - (logPrice - logMin) / (logMax - logMin);
  },

  higherIsBetter: false,
  defaultWeight: 0.05, // Low default weight - informational
  dataAvailable: true,
  scoreGridPath: "/data/home-prices-score",

  legend: {
    type: "continuous",
    stops: [
      { value: 100000, color: "#ffffcc", label: "$100k" },
      { value: 250000, color: "#a1dab4", label: "$250k" },
      { value: 400000, color: "#41b6c4", label: "$400k" },
      { value: 600000, color: "#2c7fb8", label: "$600k" },
      { value: 1000000, color: "#253494", label: "$1M+" },
    ],
    unit: "USD",
  },

  zillowHook: {
    correlationField: "zestimate",
  },

  async queryPoint(lng, lat, map) {
    const point = map.project([lng, lat]);
    const features = map.queryRenderedFeatures(point, {
      layers: ["home-prices-fill"],
    });
    if (features.length > 0 && features[0].properties) {
      return features[0].properties.median_price ?? null;
    }
    return null;
  },
};

registerLayer(homePricesLayer);
export default homePricesLayer;
