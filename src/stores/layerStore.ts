import { create } from "zustand";

export interface LayerState {
  /** Set of layer IDs that are currently enabled/visible */
  enabledLayers: Set<string>;
  /** Per-layer weight for composite scoring (0-1) */
  weights: Record<string, number>;
  /** Global composite overlay opacity (0-1) */
  compositeOpacity: number;

  toggleLayer: (id: string) => void;
  setLayerEnabled: (id: string, enabled: boolean) => void;
  setWeight: (id: string, weight: number) => void;
  setCompositeOpacity: (opacity: number) => void;
  resetWeights: () => void;
  initializeLayer: (id: string, defaultWeight: number) => void;
}

export const useLayerStore = create<LayerState>((set) => ({
  enabledLayers: new Set<string>(),
  weights: {},
  compositeOpacity: 0.7,

  toggleLayer: (id) =>
    set((state) => {
      const next = new Set(state.enabledLayers);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return { enabledLayers: next };
    }),

  setLayerEnabled: (id, enabled) =>
    set((state) => {
      const next = new Set(state.enabledLayers);
      if (enabled) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return { enabledLayers: next };
    }),

  setWeight: (id, weight) =>
    set((state) => ({
      weights: { ...state.weights, [id]: Math.max(0, Math.min(1, weight)) },
    })),

  setCompositeOpacity: (opacity) =>
    set({ compositeOpacity: Math.max(0, Math.min(1, opacity)) }),

  resetWeights: () => set({ weights: {} }),

  initializeLayer: (id, defaultWeight) =>
    set((state) => {
      if (state.weights[id] !== undefined) return state;
      return {
        weights: { ...state.weights, [id]: defaultWeight },
      };
    }),
}));
