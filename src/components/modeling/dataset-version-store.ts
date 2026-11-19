// Session-scoped selected training-set version. TASK-51: this is a transient
// UI binding, not a persisted business fact; the frozen version itself lives
// in the session database and is always re-read from the backend.
let selectedId = '';
const listeners = new Set<() => void>();

export const datasetVersionSelection = {
  get: () => selectedId,
  set: (id: string) => {
    if (selectedId === id) return;
    selectedId = id;
    listeners.forEach(listener => listener());
  },
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};
