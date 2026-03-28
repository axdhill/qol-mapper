"use client";

import { useLayerStore } from "@/stores/layerStore";
import { COMPOSITE_RAMP_CSS } from "@/lib/compositeRenderer";
import WeightSlider from "@/components/Sidebar/WeightSlider";

export default function CompositeLegend() {
  const enabledLayers = useLayerStore((s) => s.enabledLayers);
  const compositeOpacity = useLayerStore((s) => s.compositeOpacity);
  const setCompositeOpacity = useLayerStore((s) => s.setCompositeOpacity);

  if (enabledLayers.size === 0) return null;

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10
      bg-zinc-900/90 backdrop-blur-sm border border-zinc-700/50 rounded-lg
      px-4 py-3 w-72 shadow-xl">
      <div className="space-y-2">
        <div className="text-xs text-zinc-300 font-medium">
          Composite QoL Score
        </div>
        <div
          className="h-3 rounded-sm"
          style={{ background: COMPOSITE_RAMP_CSS }}
        />
        <div className="flex justify-between text-[10px] text-zinc-400">
          <span>Poor</span>
          <span>Excellent</span>
        </div>
        <WeightSlider
          label="Overlay Opacity"
          value={compositeOpacity}
          onChange={setCompositeOpacity}
        />
      </div>
    </div>
  );
}
