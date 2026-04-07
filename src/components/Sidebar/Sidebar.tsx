"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, Layers } from "lucide-react";
import LayerPanel from "./LayerPanel";
import SeasonToggle from "./SeasonToggle";

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {/* Collapse toggle button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute top-4 z-20 flex items-center justify-center w-8 h-8
          bg-zinc-900/90 border border-zinc-700 rounded-r-md text-zinc-300
          hover:bg-zinc-800 hover:text-white transition-all"
        style={{ left: collapsed ? 0 : 320 }}
        aria-label={collapsed ? "Open sidebar" : "Close sidebar"}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>

      {/* Sidebar panel */}
      <div
        className={`absolute top-0 left-0 z-10 h-full bg-zinc-900/95 backdrop-blur-sm
          border-r border-zinc-700/50 transition-transform duration-300 ease-in-out
          flex flex-col overflow-hidden`}
        style={{
          width: 320,
          transform: collapsed ? "translateX(-320px)" : "translateX(0)",
        }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-zinc-700/50">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-600/20">
            <Layers size={18} className="text-emerald-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-zinc-100">
              QoL Mapper
            </h1>
            <p className="text-xs text-zinc-400">
              Quality of Life Explorer
            </p>
          </div>
        </div>

        {/* Season filter */}
        <SeasonToggle />

        {/* Layer panel */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <LayerPanel />
        </div>

      </div>
    </>
  );
}
