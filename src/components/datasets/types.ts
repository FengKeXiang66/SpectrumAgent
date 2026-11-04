export type Dataset = {
  name: string;
  shape: [number, number, number];
  dtype: string;
  interleave: 'bsq' | 'bil' | 'bip';
  wavelengths: number[];
  fwhm: number[] | null;
  data_path: string;
  header_path: string;
  metadata: Record<string, unknown>;
};
export type DatasetRecord = { id: string; dataset: Dataset; existing: boolean; display_name?: string };
export type ImportResponse = {
  datasets: DatasetRecord[];
  all_datasets: DatasetRecord[];
  summary: { total: number; imported: number; existing: number };
};

export type DatasetReference = DatasetRecord | { id: string; display_name: string };
export function displayName(record: DatasetReference): string {
  return record.display_name ?? ('dataset' in record ? record.dataset.name : '数据集');
}
export type Preview = { id: string; band: number; width: number; height: number; mime: 'image/png'; png_base64: string;
  bands?: [number, number, number]; wavelengths?: number[]; fallback?: boolean };
export type PreviewOptions = { band?: number; bands?: string; stretch?: 'auto' | 'none'; size?: 'preview' | 'full' };
export type SpectrumRegion = { l0: number; l1: number; s0: number; s1: number; raw?: boolean };
export type MeanSpectrum = { id: string; shape: [number, number]; count: number; mean: (number | null)[]; nan_bands: number[] };
export type CatalogRecord = { id: string; display_name: string; shape: [number, number, number];
  wavelength_range: [number, number] | null; raw: boolean; source_path: string; available: boolean };
export type CatalogPage = { datasets: CatalogRecord[]; total: number; limit: number; offset: number };
export type DeletePreview = { cube_id: string; annotation_versions: number; preprocess_runs: number;
  training_runs: number; inference_runs: number; directories: { path: string; bytes: number }[];
  total_bytes: number; preview_token: string; expires_at: string };
export type DeleteResult = Omit<DeletePreview, 'preview_token'> & { deletion_id: string };
export type RecycleRecord = { deletion_id: string; cube_id: string; display_name: string; source_path: string;
  created_at: string; expires_at: string; total_bytes: number; status: 'READY' | 'INCOMPLETE' };
export type RecycleList = { items: RecycleRecord[]; count: number; total_bytes: number };
export type DatasetTransport = {
  get: (id: string) => Promise<DatasetRecord>;
  chooseDirectories: () => Promise<string[] | null>;
  importDirectory: (path: string, raw: boolean, confirmNew?: boolean) => Promise<ImportResponse>;
  catalog: (limit?: number, offset?: number) => Promise<CatalogPage>;
  deletePreview: (id: string) => Promise<DeletePreview>;
  delete: (id: string, previewToken: string, confirm: boolean) => Promise<DeleteResult>;
  recycleList: () => Promise<RecycleList>;
  restore: (deletionId: string, confirm: boolean) => Promise<{ deletion_id: string; cube_id: string; restored: boolean }>;
  preview: (id: string, selection: number | PreviewOptions) => Promise<Preview>;
  spectraMean: (id: string, region: SpectrumRegion) => Promise<MeanSpectrum>;
};

export function mergeRecords(previous: DatasetRecord[], incoming: DatasetRecord[]): DatasetRecord[] {
  const merged = new Map(previous.map(record => [record.id, record]));
  for (const record of incoming) merged.set(record.id, record);
  return [...merged.values()];
}

export function describeError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = typeof error.detail === 'string' ? error.detail : '数据请求失败';
    const context = 'context' in error ? `\n${JSON.stringify(error.context, null, 2)}` : '';
    return detail + context;
  }
  return error instanceof Error ? error.message : typeof error === 'string' ? error : '数据请求失败，请查看引擎状态。';
}
