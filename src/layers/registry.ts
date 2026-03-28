import type { LayerDefinition } from "./types";

const layers: Map<string, LayerDefinition> = new Map();

export function registerLayer(layer: LayerDefinition): void {
  layers.set(layer.id, layer);
}

export function getLayer(id: string): LayerDefinition | undefined {
  return layers.get(id);
}

export function getAllLayers(): LayerDefinition[] {
  return Array.from(layers.values());
}

export function getLayersByCategory(): Record<string, LayerDefinition[]> {
  const result: Record<string, LayerDefinition[]> = {};
  for (const layer of layers.values()) {
    if (!result[layer.category]) {
      result[layer.category] = [];
    }
    result[layer.category].push(layer);
  }
  return result;
}
