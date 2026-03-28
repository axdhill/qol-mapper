"use client";

interface WeightSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}

export default function WeightSlider({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
}: WeightSliderProps) {
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500">{label}</span>
        <span className="text-xs text-zinc-400 tabular-nums">
          {Math.round(pct)}%
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={Math.round(pct)}
        onChange={(e) => {
          const newPct = parseInt(e.target.value, 10) / 100;
          onChange(min + newPct * (max - min));
        }}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer
          bg-zinc-700
          [&::-webkit-slider-thumb]:appearance-none
          [&::-webkit-slider-thumb]:w-3
          [&::-webkit-slider-thumb]:h-3
          [&::-webkit-slider-thumb]:rounded-full
          [&::-webkit-slider-thumb]:bg-emerald-400
          [&::-webkit-slider-thumb]:shadow-md
          [&::-webkit-slider-thumb]:cursor-pointer
          [&::-moz-range-thumb]:w-3
          [&::-moz-range-thumb]:h-3
          [&::-moz-range-thumb]:rounded-full
          [&::-moz-range-thumb]:bg-emerald-400
          [&::-moz-range-thumb]:border-0
          [&::-moz-range-thumb]:cursor-pointer"
      />
    </div>
  );
}
