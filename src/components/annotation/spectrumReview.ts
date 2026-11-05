import { curveRuns } from '../preprocess/pipeline.ts';
import type { Comparison, Label, Quality } from './types.ts';

export type ReviewRange = readonly [number, number];
export const reviewKey = (item: Pick<Comparison, 'superpixel_id' | 'label_index'>): string =>
  `${item.superpixel_id}:${item.label_index}`;

export function sortReviewComparisons(items: readonly Comparison[]): Comparison[] {
  const score = (value: number | null) => value === null || !Number.isFinite(value) ? Infinity : value;
  return [...items].sort((left, right) => {
    const a = score(left.cos), b = score(right.cos);
    return a === b ? 0 : a < b ? -1 : 1;
  });
}

export function formatReviewNumber(value: number | null, digits?: number): string {
  return value === null || !Number.isFinite(value) ? '—' : digits === undefined ? String(value) : value.toFixed(digits);
}

// Defensive branch: null cos is currently unreachable under row_blocks' guard.
export function formatReviewCos(value: number | null): string {
  return value === null || !Number.isFinite(value) ? '余弦无法定义' : formatReviewNumber(value, 6);
}

export function reviewLegend(index: number, labels: readonly Label[]) {
  return { code: labels[index]?.code ?? `label_index ${index}`, color: labels[index]?.color_hex ?? '#61717e' };
}

export function sharedReviewRange(curves: readonly (readonly (number | null)[])[]): ReviewRange | null {
  let low = Infinity, high = -Infinity;
  for (const curve of curves) for (const value of curve) {
    if (value !== null && Number.isFinite(value)) { low = Math.min(low, value); high = Math.max(high, value); }
  }
  return Number.isFinite(low) ? [low, high] : null;
}

export const reviewX = (index: number, bands: number): number => bands <= 1 ? .5 : index / (bands - 1);
export function reviewBandTitle(index: number, wavelengths: readonly number[]): string {
  const wavelength = wavelengths[index];
  return `band ${index}${Number.isFinite(wavelength) ? ` · 波长 ${wavelength}` : ''}`;
}

export function reviewRuns(values: (number | null)[], range: ReviewRange, bands: number): [number, number][][] {
  const [low, high] = range;
  return curveRuns(values).map(run => run.map(([index, value]): [number, number] => [
    reviewX(index, bands), high === low ? .5 : (high - value) / (high - low),
  ]));
}

export function reviewModel(quality: Quality, labels: readonly Label[], bands: number, selected?: ReadonlySet<string>) {
  const ordered = sortReviewComparisons(quality.comparisons);
  const visible = selected ? ordered.filter(item => selected.has(reviewKey(item))) : ordered;
  const indexes = new Set(visible.map(item => item.label_index));
  const references = quality.references.filter(item => indexes.has(item.label_index));
  const range = sharedReviewRange([...visible.map(item => item.mean), ...references.map(item => item.mean)]);
  const curves = [
    ...visible.map(item => ({ key: reviewKey(item), label_index: item.label_index, mean: item.mean, reference: false })),
    ...references.map(item => ({ key: `reference:${item.label_index}`, label_index: item.label_index, mean: item.mean, reference: true })),
  ].map(item => ({ ...item, ...reviewLegend(item.label_index, labels),
    runs: range ? reviewRuns(item.mean, range, bands) : [] }));
  const groups = [...indexes].sort((a, b) => a - b).map(index => ({
    index, ...reviewLegend(index, labels), count: visible.filter(item => item.label_index === index).length,
  }));
  return { ordered, visible, references, range, curves, groups };
}

export async function eraseAndRefresh(
  block: number, erase: (block: number) => Promise<boolean>, refresh: () => Promise<unknown>,
): Promise<boolean> {
  if (!await erase(block)) return false;
  await refresh();
  return true;
}
