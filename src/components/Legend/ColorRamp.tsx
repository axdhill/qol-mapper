"use client";

import type { LayerLegend } from "@/layers/types";

interface ColorRampProps {
  legend: LayerLegend;
  layerName: string;
}

export default function ColorRamp({ legend, layerName }: ColorRampProps) {
  if (legend.type === "continuous") {
    return (
      <div className="flex flex-col gap-1">
        <div className="text-xs text-zinc-300 font-medium">{layerName}</div>
        <div
          className="h-3 rounded-sm"
          style={{
            background: `linear-gradient(to right, ${legend.stops
              .map((s) => s.color)
              .join(", ")})`,
          }}
        />
        <div className="flex justify-between text-[10px] text-zinc-400">
          {legend.stops
            .filter((_, i) => i === 0 || i === legend.stops.length - 1)
            .map((stop) => (
              <span key={stop.label}>{stop.label}</span>
            ))}
        </div>
      </div>
    );
  }

  // Categorical legend
  return (
    <div className="flex flex-col gap-1">
      <div className="text-xs text-zinc-300 font-medium">{layerName}</div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {legend.stops.map((stop) => (
          <div
            key={stop.label}
            className="flex items-center gap-1 text-[10px] text-zinc-400"
          >
            <div
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: stop.color }}
            />
            {stop.label}
          </div>
        ))}
      </div>
    </div>
  );
}
