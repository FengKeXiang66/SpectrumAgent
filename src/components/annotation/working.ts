import type { AnnotationApi, Candidate, Label, LabelSchema, Statistics, Working } from './types.ts';

// This is a display projection, not a label map, edit log or undo stack.
// Drop unknown runtime fields too, so a future response cannot introduce a map.
export function workingView(value: Working): Working {
  return { project_id: value.project_id, superpixel_count: value.superpixel_count, params: value.params,
    statistics: value.statistics, overlay: value.overlay, queue: value.queue };
}
export async function readWorking(api: Pick<AnnotationApi, 'working'>, id: string): Promise<Working> {
  return workingView(await api.working(id));
}
export async function editThenRead(api: Pick<AnnotationApi, 'working'>, id: string, edit: () => Promise<unknown>): Promise<Working> {
  await edit();
  // Never reconstruct pixels, percentages, history or the queue from an edit.
  return readWorking(api, id);
}
export function statistics(working: Working | null): Statistics | null {
  return working && typeof working.statistics.n_pixels === 'number' ? working.statistics as Statistics : null;
}
export function candidateKey(candidate: Candidate): string { return candidate.superpixels.join(','); }
export function selectedCandidate(working: Working | null, key: string | null): Candidate | null {
  return working?.queue.find(candidate => candidateKey(candidate) === key) ?? null;
}
export function recoverSelection(working: Working, key: string | null): string | null {
  return selectedCandidate(working, key) ? key : working.queue.length ? candidateKey(working.queue[0]) : null;
}
// SQLite BINARY (UTF-8) order equals Unicode code point order, not localeCompare
// or UTF-16 '<' for supplementary characters. R17 requires the same total order.
function compareCode(a: string, b: string): number {
  const left = Array.from(a), right = Array.from(b);
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    const delta = left[i].codePointAt(0)! - right[i].codePointAt(0)!;
    if (delta) return delta;
  }
  return left.length - right.length;
}
export function orderedLabels(schemas: LabelSchema[]): Label[] {
  return schemas.flatMap(schema => schema.labels).sort((a, b) => a.sort_order - b.sort_order || compareCode(a.code, b.code));
}
// Purely local estimate; not a request/response field or an acceptance metric.
export function estimateRemaining(startedMs: number, initialLabeled: number, current: Statistics | null, nowMs: number): number | null {
  if (!current || nowMs <= startedMs || current.labeled_pixels <= initialLabeled) return null;
  return (current.blank_pixels + current.uncertain_pixels) * (nowMs - startedMs) / (current.labeled_pixels - initialLabeled) / 1000;
}
export function similarColors(color: string, labels: Label[]): Label[] {
  const rgb = (hex: string) => [1, 3, 5].map(at => Number.parseInt(hex.slice(at, at + 2), 16));
  const source = rgb(color);
  // TASK-04 §4.4: RGB Euclidean distance <30 triggers the override hint.
  return labels.filter(label => Math.hypot(...rgb(label.color_hex).map((c, i) => c - source[i])) < 30);
}
