import { create } from "zustand";

export type Season = "all" | "winter" | "summer";

interface SeasonStore {
  season: Season;
  setSeason: (s: Season) => void;
}

export const useSeasonStore = create<SeasonStore>((set) => ({
  season: "all",
  setSeason: (season) => set({ season }),
}));
