import { registerLayer } from "../registry";
import type { LayerDefinition } from "../types";

const FACILITY_COLORS: Record<string, string> = {
  COAL:       "#e74c3c",
  GAS:        "#f39c12",
  OIL:        "#8b4513",
  BIOMASS:    "#a0522d",
  OTHG:       "#c0392b",
  INDUSTRIAL: "#9b59b6",
  OTHER:      "#95a5a6",
};

const powerPlantsLayer: LayerDefinition = {
  id: "power-plants",
  name: "Industrial Hazards",
  description:
    "Polluting power plants (coal, oil, gas, biomass) and industrial emitters (chemical plants, refineries) from EPA eGRID and Toxics Release Inventory. Proximity reduces QoL score.",
  category: "environmental",
  icon: "Factory",

  source: {
    type: "vector-pmtiles",
    url: "pmtiles:///tiles/power-plants.pmtiles",
    attribution: "EPA eGRID",
    sourceLayer: "power_plants",
  },

  minZoom: 3,
  maxZoom: 14,

  getMapLibreStyle(opacity: number): any[] {
    return [
      {
        id: "power-plants-circles",
        type: "circle",
        source: "power-plants-source",
        "source-layer": "power_plants",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3, ["interpolate", ["linear"], ["get", "capacity_mw"], 0, 2, 1000, 6, 5000, 12],
            10, ["interpolate", ["linear"], ["get", "capacity_mw"], 0, 4, 1000, 10, 5000, 20],
          ],
          "circle-color": [
            "match",
            ["get", "fuel_type"],
            "COAL",       FACILITY_COLORS.COAL,
            "GAS",        FACILITY_COLORS.GAS,
            "OIL",        FACILITY_COLORS.OIL,
            "BIOMASS",    FACILITY_COLORS.BIOMASS,
            "OTHG",       FACILITY_COLORS.OTHG,
            "INDUSTRIAL", FACILITY_COLORS.INDUSTRIAL,
            FACILITY_COLORS.OTHER,
          ],
          "circle-opacity": opacity * 0.85,
          "circle-stroke-width": 1,
          "circle-stroke-color": "rgba(255,255,255,0.4)",
        },
      },
    ];
  },

  normalizeValue(distanceKm: number): number {
    // Distance from nearest fossil fuel plant.
    // 0 km = score 0, 50+ km = score 1.0
    return Math.max(0, Math.min(1, distanceKm / 50));
  },

  higherIsBetter: false,
  defaultWeight: 0.05,
  dataAvailable: true,
  scoreGridPath: "/data/power-plants-score",
  attributionUrl: "https://www.epa.gov/egrid",

  legend: {
    type: "categorical",
    stops: [
      { value: 0, color: FACILITY_COLORS.COAL,       label: "Coal" },
      { value: 1, color: FACILITY_COLORS.OIL,        label: "Oil" },
      { value: 2, color: FACILITY_COLORS.GAS,        label: "Natural Gas" },
      { value: 3, color: FACILITY_COLORS.BIOMASS,    label: "Biomass" },
      { value: 4, color: FACILITY_COLORS.INDUSTRIAL, label: "Chemical / Refinery" },
    ],
    unit: "",
  },

  async queryPoint(lng, lat, map) {
    // Query within a bounding box around the click point (30px radius)
    const point = map.project([lng, lat]);
    const bbox: [maplibregl.PointLike, maplibregl.PointLike] = [
      [point.x - 30, point.y - 30],
      [point.x + 30, point.y + 30],
    ];
    const features = map.queryRenderedFeatures(bbox, {
      layers: ["power-plants-circles"],
    });
    if (features.length > 0 && features[0].properties) {
      // Return distance proxy: 0 means a plant is very close
      return 0;
    }
    // No plant nearby - return a high distance (good for QoL)
    return 50;
  },
};

registerLayer(powerPlantsLayer);
export default powerPlantsLayer;
