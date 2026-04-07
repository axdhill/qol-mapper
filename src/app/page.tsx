"use client";

import dynamic from "next/dynamic";
import { useCallback, useRef, useState } from "react";

import Sidebar from "@/components/Sidebar/Sidebar";
import SearchBar from "@/components/Search/SearchBar";
import CompositeLegend from "@/components/Legend/CompositeLegend";
import DetailPanel from "@/components/DetailPanel/DetailPanel";
import { useLayerStore } from "@/stores/layerStore";
import { useSeasonStore } from "@/stores/seasonStore";
import { getAllLayers } from "@/layers/registry";
import { getScoreGrid } from "@/lib/compositeRenderer";
import type { CompositeResult, ScoreBreakdownItem } from "@/lib/scoring";
import { SEARCH_ZOOM, FLY_TO_DURATION_MS } from "@/lib/constants";
import type { GeocodingResult } from "@/lib/geocoding";

// Dynamic import to avoid SSR for WebGL map
const MapContainer = dynamic(
  () => import("@/components/Map/MapContainer"),
  { ssr: false }
);

export default function Home() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapRef = useRef<any>(null);
  const [clickedPoint, setClickedPoint] = useState<{
    lng: number;
    lat: number;
  } | null>(null);
  const [compositeResult, setCompositeResult] =
    useState<CompositeResult | null>(null);

  const weights = useLayerStore((s) => s.weights);
  const enabledLayers = useLayerStore((s) => s.enabledLayers);
  const season = useSeasonStore((s) => s.season);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleMapReady = useCallback((map: any) => {
    mapRef.current = map;
  }, []);

  const handleMapClick = useCallback(
    async (lng: number, lat: number) => {
      setClickedPoint({ lng, lat });
      setCompositeResult(null);

      const allLayers = getAllLayers();
      const activeLayers = allLayers.filter(
        (l) => enabledLayers.has(l.id) && l.dataAvailable !== false
      );

      if (activeLayers.length === 0) return;

      const breakdown: ScoreBreakdownItem[] = [];
      let weightedSum = 0;
      let totalWeight = 0;

      for (const layer of activeLayers) {
        const w = weights[layer.id] ?? layer.defaultWeight;
        let score: number | null = null;
        let rawGridValue: number | null = null;

        try {
          // Resolve which grid path to use for the active season
          const gridPath =
            (season === "winter" && layer.scoreGridPathWinter) ? layer.scoreGridPathWinter :
            (season === "summer" && layer.scoreGridPathSummer) ? layer.scoreGridPathSummer :
            layer.scoreGridPath;

          if (gridPath) {
            // Load full grid (cached after first map render) to apply the same
            // per-layer min-max normalization the composite renderer uses.
            const grid = await getScoreGrid(gridPath);
            const { data, meta } = grid;

            // Compute per-layer min/max (mirrors compositeRenderer)
            let mn = Infinity;
            let mx = -Infinity;
            for (let i = 0; i < data.length; i++) {
              const v = data[i];
              if (!isNaN(v)) {
                if (v < mn) mn = v;
                if (v > mx) mx = v;
              }
            }
            const layerRange = mx > mn ? mx - mn : 1;
            const layerMin = mn === Infinity ? 0 : mn;

            const col = Math.floor((lng - meta.originX) / meta.pixelWidth);
            const row = Math.floor((lat - meta.originY) / meta.pixelHeight);
            if (col >= 0 && col < meta.width && row >= 0 && row < meta.height) {
              const raw = data[row * meta.width + col];
              if (!isNaN(raw)) {
                rawGridValue = raw;
                score = Math.max(0, Math.min(1, (raw - layerMin) / layerRange));
              }
            }
          } else if (layer.queryPoint) {
            const raw = await layer.queryPoint(lng, lat, mapRef.current);
            if (raw != null) {
              rawGridValue = raw;
              score = layer.normalizeValue(raw);
            }
          }
        } catch {
          score = null;
        }

        if (score != null && w > 0) {
          weightedSum += score * w;
          totalWeight += w;
        }

        breakdown.push({
          layerId: layer.id,
          layerName: layer.name,
          rawValue: rawGridValue,
          normalizedScore: score,
          weight: w,
          contribution: score != null ? score * w : 0,
        });
      }

      setCompositeResult({
        score: totalWeight > 0 ? weightedSum / totalWeight : 0,
        breakdown,
        totalWeight,
      });
    },
    [weights, enabledLayers, season]
  );

  const handleSearchSelect = useCallback((result: GeocodingResult) => {
    const map = mapRef.current;
    if (!map) return;

    map.flyTo({
      center: [result.lng, result.lat],
      zoom: SEARCH_ZOOM,
      duration: FLY_TO_DURATION_MS,
    });
  }, []);

  const handleCloseDetail = useCallback(() => {
    setClickedPoint(null);
    setCompositeResult(null);
  }, []);

  return (
    <div className="relative w-full h-full overflow-hidden">
      {/* Map (full screen background) */}
      <MapContainer onMapClick={handleMapClick} onMapReady={handleMapReady} />

      {/* Sidebar (left) */}
      <Sidebar />

      {/* Search bar (top center) */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 w-full max-w-md px-4">
        <SearchBar onSelect={handleSearchSelect} />
      </div>

      {/* Legend (bottom center) */}
      <CompositeLegend />

      {/* Detail panel (right, shown on click) */}
      {clickedPoint && (
        <DetailPanel
          lng={clickedPoint.lng}
          lat={clickedPoint.lat}
          compositeResult={compositeResult}
          onClose={handleCloseDetail}
        />
      )}
    </div>
  );
}
