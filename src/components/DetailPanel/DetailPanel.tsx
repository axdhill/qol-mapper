"use client";

import { useEffect, useState } from "react";
import { X, MapPin, ExternalLink } from "lucide-react";
import { reverseGeocode } from "@/lib/geocoding";
import { scoreToColor, scoreToGrade } from "@/lib/scoring";
import type { CompositeResult } from "@/lib/scoring";
import ScoreBreakdown from "./ScoreBreakdown";

interface DetailPanelProps {
  lng: number;
  lat: number;
  compositeResult: CompositeResult | null;
  onClose: () => void;
}

export default function DetailPanel({
  lng,
  lat,
  compositeResult,
  onClose,
}: DetailPanelProps) {
  const [placeName, setPlaceName] = useState<string>("");

  useEffect(() => {
    setPlaceName("");
    reverseGeocode(lng, lat).then(setPlaceName);
  }, [lng, lat]);

  const score = compositeResult?.score ?? 0;
  const grade = scoreToGrade(score);
  const color = scoreToColor(score);  // used only when compositeResult is non-null

  return (
    <div className="absolute top-0 right-0 z-20 h-full w-80
      bg-zinc-900/95 backdrop-blur-sm border-l border-zinc-700/50
      flex flex-col overflow-hidden
      animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="flex items-start justify-between px-4 py-4 border-b border-zinc-700/50">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
            <MapPin size={12} />
            <span>
              {lat.toFixed(4)}, {lng.toFixed(4)}
            </span>
          </div>
          <div className="text-sm text-zinc-200 truncate">
            {placeName || "Loading..."}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() =>
              window.open(
                `https://www.zillow.com/homes/for_sale/?searchQueryState=%7B%22mapBounds%22%3A%7B%22north%22%3A${lat + 0.05}%2C%22south%22%3A${lat - 0.05}%2C%22east%22%3A${lng + 0.08}%2C%22west%22%3A${lng - 0.08}%7D%7D`,
                "_blank"
              )
            }
            className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded"
            title="View on Zillow"
          >
            <ExternalLink size={16} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Composite score */}
      <div className="px-4 py-4 border-b border-zinc-700/50">
        <div className="text-xs text-zinc-500 mb-2">Composite QoL Score</div>
        {compositeResult && compositeResult.totalWeight > 0 ? (
          <>
            <div className="flex items-end gap-3">
              <div className="text-4xl font-bold tabular-nums" style={{ color }}>
                {(score * 100).toFixed(0)}
              </div>
              <div className="flex flex-col mb-1">
                <div className="text-xl font-semibold" style={{ color }}>
                  {grade}
                </div>
                <div className="text-[10px] text-zinc-500">/ 100</div>
              </div>
            </div>
            <div className="mt-3 h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${score * 100}%`, backgroundColor: color }}
              />
            </div>
          </>
        ) : (
          <div className="text-sm text-zinc-500 italic">
            {compositeResult ? "No data at this location." : "Enable layers in the sidebar to see a score."}
          </div>
        )}
      </div>

      {/* Score breakdown */}
      <div className="flex-1 overflow-y-auto">
        {compositeResult && (
          <ScoreBreakdown breakdown={compositeResult.breakdown} />
        )}
      </div>
    </div>
  );
}
