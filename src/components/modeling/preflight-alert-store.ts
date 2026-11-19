// Session-scoped near-duplicate warning passed from S07 preflight to S12.
// TASK-51: transient UI hint only; never persisted, never a business fact.
export type NearDuplicatePair = { a: string; b: string; similarity: number };

// A near-duplicate report can arrive in two shapes: the preflight result puts
// leak_report at the top level, while a failed create_run nests it under
// context (see LEAK_PREFLIGHT_FAILED). Both are read so S12 sees the warning
// whichever action surfaced it.
export function extractNearDuplicates(payload: unknown): NearDuplicatePair[] {
  const object = (value: unknown): Record<string, unknown> =>
    value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const root = object(payload);
  const outer = object(root.leak_report ?? object(root.context).leak_report);
  const raw = outer.near_duplicate_spectra;
  const pairs = Array.isArray(object(raw).pairs) ? (object(raw).pairs as unknown[]) : [];
  return pairs.flatMap(item => {
    const row = object(item), ids = row.cube_ids;
    return Array.isArray(ids) && ids.length >= 2 && typeof ids[0] === 'string' && typeof ids[1] === 'string'
      ? [{ a: ids[0], b: ids[1], similarity: typeof row.similarity === 'number' ? row.similarity : 0 }] : [];
  });
}

let pairs: NearDuplicatePair[] = [];
const listeners = new Set<() => void>();

export const preflightAlerts = {
  get: () => pairs,
  set: (next: NearDuplicatePair[]) => {
    pairs = next;
    listeners.forEach(listener => listener());
  },
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};
