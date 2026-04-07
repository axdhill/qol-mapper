"use client";

import { ExternalLink } from "lucide-react";
import { scoreToColor } from "@/lib/scoring";
import type { ScoreBreakdownItem } from "@/lib/scoring";

interface ScoreBreakdownProps {
  breakdown: ScoreBreakdownItem[];
}

export default function ScoreBreakdown({ breakdown }: ScoreBreakdownProps) {
  // Sort by weight descending so most important factors appear first
  const sorted = [...breakdown].sort((a, b) => b.weight - a.weight);

  return (
    <div className="px-4 py-3 space-y-3">
      <div className="text-xs text-zinc-500 font-medium uppercase tracking-wider">
        Factor Breakdown
      </div>

      {sorted.map((item) => {
        const hasData = item.normalizedScore != null;
        const score = item.normalizedScore ?? 0;
        const color = hasData ? scoreToColor(score) : "#4a4a4a";

        return (
          <div key={item.layerId} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-300">{item.layerName}</span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-500">
                  wt: {(item.weight * 100).toFixed(0)}%
                </span>
                {hasData ? (
                  <span
                    className="text-xs font-medium tabular-nums"
                    style={{ color }}
                  >
                    {(score * 100).toFixed(0)}
                  </span>
                ) : (
                  <span className="text-xs text-zinc-600 italic">
                    N/A
                  </span>
                )}
              </div>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              {hasData ? (
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${score * 100}%`,
                    backgroundColor: color,
                  }}
                />
              ) : (
                <div className="h-full w-full bg-zinc-800 rounded-full" />
              )}
            </div>
            {hasData && item.rawValue != null && (
              <div className="text-[10px] text-zinc-500">
                Raw: {item.rawValue.toFixed(2)}
              </div>
            )}
            {item.attributionUrl ? (
              <a
                href={item.attributionUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                <ExternalLink size={9} />
                {item.attribution ?? "Source"}
              </a>
            ) : item.attribution ? (
              <div className="text-[10px] text-zinc-600">{item.attribution}</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
