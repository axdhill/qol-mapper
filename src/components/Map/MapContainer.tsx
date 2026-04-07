"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { addPMTilesProtocol } from "@/lib/pmtiles";
import { CONUS_CENTER, DEFAULT_ZOOM } from "@/lib/constants";
import { useLayerStore } from "@/stores/layerStore";
import { useSeasonStore } from "@/stores/seasonStore";
import { getAllLayers } from "@/layers/registry";
import type { LayerDefinition } from "@/layers/types";
import {
  renderCompositeCanvas,
  type CompositeInput,
} from "@/lib/compositeRenderer";

const DARK_BASEMAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  name: "Dark Basemap",
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: "carto-dark",
      type: "raster",
      source: "carto",
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

// Grid extent for the composite overlay (must match pipeline's score_grid.py)
const GRID_BOUNDS: [number, number, number, number] = [-125.0, 24.5, -66.5, 49.5];

interface MapContainerProps {
  onMapClick?: (lng: number, lat: number) => void;
  onMapReady?: (map: maplibregl.Map) => void;
}

export default function MapContainer({
  onMapClick,
  onMapReady,
}: MapContainerProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const onMapClickRef = useRef(onMapClick);
  useEffect(() => { onMapClickRef.current = onMapClick; }, [onMapClick]);
  const { enabledLayers, weights, compositeOpacity } = useLayerStore();
  const season = useSeasonStore((s) => s.season);
  const compositeUpdateTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    addPMTilesProtocol();

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: DARK_BASEMAP_STYLE,
      center: CONUS_CENTER,
      zoom: DEFAULT_ZOOM,
      minZoom: 3,
      maxZoom: 18,
      attributionControl: {},
      hash: true,
    });

    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.addControl(
      new maplibregl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: false,
      }),
      "bottom-right"
    );

    map.on("load", () => {
      mapRef.current = map;
      setMapLoaded(true);
      onMapReady?.(map);
    });

    map.on("click", (e) => {
      onMapClickRef.current?.(e.lngLat.lng, e.lngLat.lat);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update composite overlay when enabled layers or weights change
  const updateComposite = useCallback(async () => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const allLayers = getAllLayers();

    // Build composite inputs from enabled layers with score grids,
    // using seasonal grid paths when a non-"all" season is active.
    const inputs: CompositeInput[] = [];
    for (const layer of allLayers) {
      if (!enabledLayers.has(layer.id) || layer.dataAvailable === false) continue;
      const gridPath =
        (season === "winter" && layer.scoreGridPathWinter) ? layer.scoreGridPathWinter :
        (season === "summer" && layer.scoreGridPathSummer) ? layer.scoreGridPathSummer :
        layer.scoreGridPath;
      if (!gridPath) continue;
      inputs.push({
        gridPath,
        // If using a seasonal path, fall back to the annual grid if the
        // seasonal file hasn't been generated yet.
        fallbackGridPath: gridPath !== layer.scoreGridPath ? layer.scoreGridPath : undefined,
        weight: weights[layer.id] ?? layer.defaultWeight,
      });
    }

    // Remove old composite layer and source
    if (map.getLayer("composite-raster")) {
      map.removeLayer("composite-raster");
    }
    if (map.getSource("composite-canvas")) {
      map.removeSource("composite-canvas");
    }

    if (inputs.length === 0) return;

    // Render composite to canvas
    const canvas = await renderCompositeCanvas(inputs);
    if (!canvas) return;

    // Add canvas as image source
    map.addSource("composite-canvas", {
      type: "image",
      url: canvas.toDataURL(),
      coordinates: [
        [GRID_BOUNDS[0], GRID_BOUNDS[3]], // top-left
        [GRID_BOUNDS[2], GRID_BOUNDS[3]], // top-right
        [GRID_BOUNDS[2], GRID_BOUNDS[1]], // bottom-right
        [GRID_BOUNDS[0], GRID_BOUNDS[1]], // bottom-left
      ],
    });

    // Add raster layer for the composite
    map.addLayer(
      {
        id: "composite-raster",
        type: "raster",
        source: "composite-canvas",
        paint: {
          "raster-opacity": compositeOpacity,
          "raster-resampling": "nearest",
        },
      },
      // Insert before annotation layers
      getFirstAnnotationLayerId(map)
    );
  }, [enabledLayers, weights, compositeOpacity, mapLoaded, season]);

  // Debounce composite updates
  useEffect(() => {
    if (compositeUpdateTimer.current) {
      clearTimeout(compositeUpdateTimer.current);
    }
    compositeUpdateTimer.current = setTimeout(() => {
      updateComposite();
    }, 150);
    return () => {
      if (compositeUpdateTimer.current) {
        clearTimeout(compositeUpdateTimer.current);
      }
    };
  }, [updateComposite]);

  // Sync annotation layers (dots/outlines for reference, not colored)
  const syncAnnotations = useCallback(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const allLayers = getAllLayers();

    for (const layer of allLayers) {
      if (layer.dataAvailable === false) continue;

      const sourceId = `${layer.id}-source`;
      const annotationId = `${layer.id}-annotation`;

      if (!enabledLayers.has(layer.id)) {
        // Remove annotation
        if (map.getLayer(annotationId)) {
          map.removeLayer(annotationId);
        }
        if (map.getSource(sourceId)) {
          map.removeSource(sourceId);
        }
        continue;
      }

      // Only add annotations for vector/point layers (not raster)
      if (layer.source.type === "raster-pmtiles") continue;

      // Add source if needed
      if (!map.getSource(sourceId)) {
        try {
          addLayerSource(map, layer, sourceId);
        } catch (err) {
          console.warn(`Failed to add source for ${layer.id}:`, err);
          continue;
        }
      }

      // Add annotation layer if needed
      if (!map.getLayer(annotationId)) {
        try {
          const annotationStyle = getAnnotationStyle(layer, annotationId);
          if (annotationStyle) {
            map.addLayer(annotationStyle);
          }
        } catch (err) {
          console.warn(`Failed to add annotation for ${layer.id}:`, err);
        }
      }
    }
  }, [enabledLayers, mapLoaded]);

  useEffect(() => {
    syncAnnotations();
  }, [syncAnnotations]);

  return (
    <div ref={mapContainer} className="absolute inset-0 w-full h-full" />
  );
}

function addLayerSource(
  map: maplibregl.Map,
  layer: LayerDefinition,
  sourceId: string
) {
  switch (layer.source.type) {
    case "raster-pmtiles":
      map.addSource(sourceId, {
        type: "raster",
        url: layer.source.url,
        tileSize: 256,
        attribution: layer.source.attribution,
      });
      break;
    case "vector-pmtiles":
      map.addSource(sourceId, {
        type: "vector",
        url: layer.source.url,
        attribution: layer.source.attribution,
      });
      break;
    case "geojson":
      map.addSource(sourceId, {
        type: "geojson",
        data: layer.source.url,
        attribution: layer.source.attribution,
      });
      break;
  }
}

/**
 * Create a muted reference annotation layer.
 * Points → small white dots (reference locations).
 * Polygons → no annotation; the composite canvas is the sole colored visualization.
 */
function getAnnotationStyle(
  layer: LayerDefinition,
  layerId: string
): maplibregl.LayerSpecification | null {
  if (layer.source.type === "vector-pmtiles" && layer.source.sourceLayer) {
    const origStyles = layer.getMapLibreStyle(1);
    const hasCircle = origStyles.some(
      (s: { type: string }) => s.type === "circle"
    );

    if (hasCircle) {
      return {
        id: layerId,
        type: "circle",
        source: `${layer.id}-source`,
        "source-layer": layer.source.sourceLayer,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            4, 1.5,
            10, 3,
            14, 5,
          ],
          "circle-color": "rgba(255, 255, 255, 0.6)",
          "circle-stroke-width": 0.5,
          "circle-stroke-color": "rgba(255, 255, 255, 0.3)",
        },
      };
    }

    // Polygon layers: no annotation overlay; composite canvas shows the data.
    return null;
  }
  return null;
}

/**
 * Get the ID of the first annotation layer, so we can insert
 * the composite overlay before annotations.
 */
function getFirstAnnotationLayerId(
  map: maplibregl.Map
): string | undefined {
  const style = map.getStyle();
  if (!style?.layers) return undefined;
  const annotation = style.layers.find((l) =>
    l.id.endsWith("-annotation")
  );
  return annotation?.id;
}

export function useMapRef() {
  return useRef<maplibregl.Map | null>(null);
}
