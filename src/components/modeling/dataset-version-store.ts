// Remember the selection; the version and its members are re-read from the backend.
const key = 'spectrumagent.selected-training-set';
let selectedId = '';
try { selectedId = localStorage.getItem(key) ?? ''; } catch { /* Optional UI preference. */ }
const listeners = new Set<() => void>();

export const datasetVersionSelection = {
  get: () => selectedId,
  set: (id: string) => {
    if (selectedId === id) return;
    selectedId = id;
    try { localStorage.setItem(key, id); } catch { /* The backend keeps the version. */ }
    listeners.forEach(listener => listener());
  },
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};
