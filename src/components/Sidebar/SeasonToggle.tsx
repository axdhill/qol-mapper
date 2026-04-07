"use client";

import { useSeasonStore, type Season } from "@/stores/seasonStore";

const OPTIONS: { value: Season; label: string; sub: string }[] = [
  { value: "all",    label: "All Year", sub: "annual"  },
  { value: "winter", label: "Winter",   sub: "Dec–Feb" },
  { value: "summer", label: "Summer",   sub: "Jun–Aug" },
];

export default function SeasonToggle() {
  const { season, setSeason } = useSeasonStore();

  return (
    <div className="px-4 py-3 border-b border-zinc-700/50">
      <div className="text-xs text-zinc-500 mb-2">Season filter</div>
      <div className="flex rounded-md border border-zinc-700 overflow-hidden">
        {OPTIONS.map(({ value, label, sub }) => (
          <button
            key={value}
            onClick={() => setSeason(value)}
            className={`flex-1 py-1.5 text-center transition-colors ${
              season === value
                ? "bg-emerald-700/80 text-white"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
            }`}
          >
            <div className="text-xs font-medium leading-none">{label}</div>
            <div className="text-[10px] opacity-60 mt-0.5">{sub}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
