"use client";

import { useState } from "react";
import {
  Wind,
  Factory,
  Trees,
  TreePine,
  GraduationCap,
  Thermometer,
  Home,
  BookOpen,
  Volume2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { LayerDefinition } from "@/layers/types";
import { useLayerStore } from "@/stores/layerStore";
import WeightSlider from "./WeightSlider";

const ICON_MAP: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  Wind,
  Factory,
  Trees,
  TreePine,
  GraduationCap,
  Thermometer,
  Home,
  BookOpen,
  Volume2,
};

interface LayerToggleProps {
  layer: LayerDefinition;
}

export default function LayerToggle({ layer }: LayerToggleProps) {
  const [expanded, setExpanded] = useState(false);
  const enabledLayers = useLayerStore((s) => s.enabledLayers);
  const toggleLayer = useLayerStore((s) => s.toggleLayer);
  const weights = useLayerStore((s) => s.weights);
  const setWeight = useLayerStore((s) => s.setWeight);

  const available = layer.dataAvailable !== false;
  const isEnabled = enabledLayers.has(layer.id);
  const Icon = ICON_MAP[layer.icon] || Wind;
  const weight = weights[layer.id] ?? layer.defaultWeight;

  return (
    <div
      className={`mx-2 mb-1 rounded-lg border transition-colors ${
        !available
          ? "border-transparent bg-transparent opacity-50"
          : isEnabled
            ? "border-zinc-600 bg-zinc-800/60"
            : "border-transparent bg-transparent hover:bg-zinc-800/30"
      }`}
    >
      {/* Main toggle row */}
      <div className="flex items-center gap-3 px-3 py-2.5">
        {/* Toggle switch */}
        <button
          onClick={() => available && toggleLayer(layer.id)}
          disabled={!available}
          className={`relative w-9 h-5 rounded-full transition-colors flex-shrink-0 ${
            !available
              ? "bg-zinc-700 cursor-not-allowed"
              : isEnabled
                ? "bg-emerald-600"
                : "bg-zinc-600"
          }`}
          aria-label={`Toggle ${layer.name}`}
        >
          <div
            className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
              isEnabled ? "translate-x-4.5" : "translate-x-0.5"
            }`}
          />
        </button>

        {/* Icon + label */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Icon
            size={16}
            className={
              !available
                ? "text-zinc-600"
                : isEnabled
                  ? "text-emerald-400"
                  : "text-zinc-500"
            }
          />
          <div className="flex-1 min-w-0">
            <div
              className={`text-sm font-medium truncate ${
                !available
                  ? "text-zinc-600"
                  : isEnabled
                    ? "text-zinc-100"
                    : "text-zinc-400"
              }`}
            >
              {layer.name}
            </div>
            {!available && (
              <div className="text-[10px] text-zinc-600 italic">Coming soon</div>
            )}
          </div>
        </div>

        {/* Expand button for settings */}
        {isEnabled && available && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 text-zinc-400 hover:text-zinc-200"
            aria-label="Layer settings"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        )}
      </div>

      {/* Expanded settings */}
      {isEnabled && expanded && (
        <div className="px-3 pb-3 space-y-3">
          <p className="text-xs text-zinc-400 leading-relaxed">
            {layer.description}
          </p>

          <WeightSlider
            label="Weight"
            value={weight}
            onChange={(v) => setWeight(layer.id, v)}
          />
        </div>
      )}
    </div>
  );
}
