"use client";

import { useEffect, useState } from "react";
import { getAllLayers, getLayersByCategory } from "@/layers/registry";
import { useLayerStore } from "@/stores/layerStore";
import { CATEGORY_LABELS, CATEGORY_ORDER } from "@/lib/constants";
import LayerToggle from "./LayerToggle";

export default function LayerPanel() {
  const initializeLayer = useLayerStore((s) => s.initializeLayer);
  const [layersReady, setLayersReady] = useState(false);

  // Register all layers, then initialize weights and trigger a re-render.
  useEffect(() => {
    import("@/layers/init").then(() => {
      for (const layer of getAllLayers()) {
        initializeLayer(layer.id, layer.defaultWeight);
      }
      setLayersReady(true);
    });
  }, [initializeLayer]);

  const layersByCategory = layersReady ? getLayersByCategory() : {};

  return (
    <div className="py-2">
      {CATEGORY_ORDER.map((category) => {
        const layers = layersByCategory[category];
        if (!layers || layers.length === 0) return null;

        return (
          <div key={category} className="mb-1">
            <div className="px-4 py-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {CATEGORY_LABELS[category] || category}
            </div>
            {layers.map((layer) => (
              <LayerToggle key={layer.id} layer={layer} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
