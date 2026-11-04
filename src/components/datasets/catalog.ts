import { describeError, type CatalogRecord, type DatasetRecord, type DatasetTransport } from './types.ts';

export type CatalogState = { records: CatalogRecord[]; phase: 'idle' | 'loading' | 'ready' | 'error'; error: string };
export const emptyCatalog = (): CatalogState => ({ records: [], phase: 'idle', error: '' });

export function catalogRecord(record: DatasetRecord): CatalogRecord {
  const data = record.dataset;
  return { id: record.id, display_name: record.display_name ?? data.name, shape: data.shape,
    wavelength_range: data.wavelengths.length ? [Math.min(...data.wavelengths), Math.max(...data.wavelengths)] : null,
    raw: data.metadata.value_mode === 'raw_dn', source_path: data.header_path, available: true };
}

export async function readCatalog(api: Pick<DatasetTransport, 'catalog'>): Promise<CatalogRecord[]> {
  const rows = new Map<string, CatalogRecord>();
  let offset = 0;
  for (;;) {
    const page = await api.catalog(100, offset);
    if (page.offset !== offset || page.limit < 1 || page.total < 0
        || (!page.datasets.length && offset < page.total)) throw new Error('数据目录分页不完整，请重新加载。');
    for (const row of page.datasets) rows.set(row.id, row);
    offset += page.datasets.length;
    if (offset >= page.total) return [...rows.values()];
  }
}

// Own the async boundary independently of React renders. Every engine generation
// and newer refresh invalidates earlier success AND failure callbacks.
export function createCatalogController(api: Pick<DatasetTransport, 'catalog'>, changed: (state: CatalogState) => void) {
  let state = emptyCatalog(), generation: number | null = null, ticket = 0;
  const publish = (next: CatalogState) => { state = next; changed(next); };
  const refresh = async (mode: 'replace' | 'names', additions: string[] = []) => {
    const request = ++ticket, engine = generation;
    if (engine === null) return;
    publish({ ...state, phase: 'loading', error: '' });
    try {
      const all = await readCatalog(api);
      if (engine !== generation || request !== ticket) return;
      const visible = new Set([...state.records.map(row => row.id), ...additions]);
      publish({ records: mode === 'replace' ? all : all.filter(row => visible.has(row.id)), phase: 'ready', error: '' });
    } catch (failure) {
      if (engine === generation && request === ticket) publish({ ...state, phase: 'error', error: describeError(failure) });
    }
  };
  return {
    reset(engine: number) { ticket++; generation = engine; publish(emptyCatalog()); },
    cancel() { ticket++; generation = null; },
    load: (engine?: number) => { if (engine !== undefined) generation = engine; return refresh('replace'); },
    snapshot: () => state,
    refreshNames: (additions: string[] = []) => refresh('names', additions),
    async imported(batch: DatasetRecord[]) {
      ticket++;
      const merged = new Map(state.records.map(row => [row.id, row]));
      for (const row of batch) merged.set(row.id, catalogRecord(row));
      publish({ records: [...merged.values()], phase: 'loading', error: '' });
      await refresh('names');
    },
    remove(id: string) {
      ticket++;
      publish({ ...state, records: state.records.filter(row => row.id !== id) });
    },
  };
}
