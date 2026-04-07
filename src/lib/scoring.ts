import type { LayerDefinition } from "@/layers/types";

export interface ScoreBreakdownItem {
  layerId: string;
  layerName: string;
  attribution: string | undefined;
  attributionUrl: string | undefined;
  rawValue: number | null;
  normalizedScore: number | null;
  weight: number;
  contribution: number;
}

export interface CompositeResult {
  score: number;
  breakdown: ScoreBreakdownItem[];
  totalWeight: number;
}

/**
 * Compute a weighted composite QoL score from multiple layer values.
 *
 * Each layer's raw value is normalized to 0-1 (via its normalizeValue function),
 * then weighted. Layers with null values (data unavailable at that point) are
 * excluded and their weights are redistributed proportionally.
 */
export function computeComposite(
  layerValues: Record<string, number | null>,
  weights: Record<string, number>,
  layers: LayerDefinition[]
): CompositeResult {
  const breakdown: ScoreBreakdownItem[] = [];
  let weightedSum = 0;
  let totalWeight = 0;

  for (const layer of layers) {
    const raw = layerValues[layer.id] ?? null;
    const w = weights[layer.id] ?? layer.defaultWeight;

    if (raw == null || w === 0) {
      breakdown.push({
        layerId: layer.id,
        layerName: layer.name,
        attribution: layer.source.attribution,
        attributionUrl: layer.attributionUrl,
        rawValue: raw,
        normalizedScore: null,
        weight: w,
        contribution: 0,
      });
      continue;
    }

    const normalized = layer.normalizeValue(raw);
    const contribution = normalized * w;
    weightedSum += contribution;
    totalWeight += w;

    breakdown.push({
      layerId: layer.id,
      layerName: layer.name,
      attribution: layer.source.attribution,
      attributionUrl: layer.attributionUrl,
      rawValue: raw,
      normalizedScore: normalized,
      weight: w,
      contribution,
    });
  }

  const score = totalWeight > 0 ? weightedSum / totalWeight : 0;

  return { score, breakdown, totalWeight };
}

/**
 * Format a composite score as a letter grade.
 */
export function scoreToGrade(score: number): string {
  if (score >= 0.9) return "A+";
  if (score >= 0.8) return "A";
  if (score >= 0.7) return "B+";
  if (score >= 0.6) return "B";
  if (score >= 0.5) return "C+";
  if (score >= 0.4) return "C";
  if (score >= 0.3) return "D";
  return "F";
}

/**
 * Get a color for a composite score (green = good, red = bad).
 */
export function scoreToColor(score: number): string {
  if (score >= 0.8) return "#1a9850";
  if (score >= 0.6) return "#91cf60";
  if (score >= 0.4) return "#fee08b";
  if (score >= 0.2) return "#fc8d59";
  return "#d73027";
}
