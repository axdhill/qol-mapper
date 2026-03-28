"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Search, X, MapPin } from "lucide-react";
import { geocode, type GeocodingResult } from "@/lib/geocoding";
import { SEARCH_DEBOUNCE_MS } from "@/lib/constants";

interface SearchBarProps {
  onSelect: (result: GeocodingResult) => void;
}

export default function SearchBar({ onSelect }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodingResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    setIsLoading(true);
    try {
      const res = await geocode(q);
      setResults(res);
      setIsOpen(res.length > 0);
      setSelectedIndex(-1);
    } catch {
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    clearTimeout(timerRef.current);
    if (query.trim()) {
      timerRef.current = setTimeout(() => search(query), SEARCH_DEBOUNCE_MS);
    } else {
      setResults([]);
      setIsOpen(false);
    }
    return () => clearTimeout(timerRef.current);
  }, [query, search]);

  const handleSelect = (result: GeocodingResult) => {
    setQuery(result.displayName);
    setIsOpen(false);
    onSelect(result);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (selectedIndex >= 0 && results[selectedIndex]) {
          handleSelect(results[selectedIndex]);
        }
        break;
      case "Escape":
        setIsOpen(false);
        inputRef.current?.blur();
        break;
    }
  };

  return (
    <div className="relative w-full max-w-md">
      {/* Search input */}
      <div className="relative">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search city, zip code, or address..."
          className="w-full h-10 pl-9 pr-9 rounded-lg bg-zinc-800/90 border border-zinc-700/50
            text-sm text-zinc-100 placeholder:text-zinc-500
            focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50
            backdrop-blur-sm"
        />
        {query && (
          <button
            onClick={() => {
              setQuery("");
              setResults([]);
              setIsOpen(false);
              inputRef.current?.focus();
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200"
          >
            <X size={14} />
          </button>
        )}
        {isLoading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-zinc-600 border-t-emerald-400 rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Results dropdown */}
      {isOpen && results.length > 0 && (
        <div className="absolute top-full mt-1 w-full bg-zinc-800/95 border border-zinc-700/50 rounded-lg shadow-xl backdrop-blur-sm overflow-hidden z-50">
          {results.map((result, i) => (
            <button
              key={`${result.lng}-${result.lat}-${i}`}
              onClick={() => handleSelect(result)}
              className={`flex items-center gap-3 w-full px-3 py-2.5 text-left transition-colors ${
                i === selectedIndex
                  ? "bg-zinc-700/60"
                  : "hover:bg-zinc-700/40"
              }`}
            >
              <MapPin size={14} className="text-zinc-500 flex-shrink-0" />
              <div className="min-w-0">
                <div className="text-sm text-zinc-200 truncate">
                  {result.name}
                </div>
                <div className="text-xs text-zinc-500 truncate">
                  {result.displayName}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
