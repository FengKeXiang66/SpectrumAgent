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
export type DeleteResult = { deletion_id: string; deleted_at: string; permanent: true;
  pending_directories: string[]; cube_id: string; annotation_versions: number; preprocess_runs: number;
  training_runs: number; inference_runs: number; directories: { path: string; bytes: number }[];
  total_bytes: number };
export type BatchDirectory = { path: string; bytes: number; cube_id: string };
export type BatchDeletePreview = { cube_ids: string[]; linked_runs: { id: string; cube_ids: string[]; status: string }[];
  per_cube: { cube_id: string; annotation_versions: number; preprocess_runs: number; inference_runs: number;
    directories: BatchDirectory[]; total_bytes: number }[];
  directories: BatchDirectory[]; shared_directories: { path: string; bytes: number; representative_cube_id: string; run_id: string }[];
  total_bytes: number; training_runs: number; preview_token: string; expires_at: string };
export type BatchDeleteResult = Omit<BatchDeletePreview, 'preview_token' | 'expires_at'> & {
  deletion_id: string; deleted_at: string; permanent: true; pending_directories: string[] };
export type DatasetVersionItem = { id: string; content_hash: string; cube_count: number; created_at: string;
  confirmed_at: string; cube_ids: string[]; is_frozen: 1 };
export type TrainingSetMemberInput = { cube_id: string; annotation_version_id: string; recipe_version_id: string };
export type TrainingSetOptionsInput = { content_hash_dedup: boolean };
export type TrainingSetPreviewInput = { members: TrainingSetMemberInput[]; options?: TrainingSetOptionsInput };
export type TrainingSetVersion = { id: string; content_hash: string; created_at: string; actor: 'local'; is_frozen: 0 | 1;
  member_count: number; label_summary: Record<string, number>; source_note: string | null; confirmed_at: string | null };
export type TrainingSetGap = TrainingSetMemberInput & { input_fingerprint: string };
export type TrainingSetMember = TrainingSetGap & { label_id: string | null; n_pixels: number; preprocess_run_id: string | null };
export type TrainingSetMembersResponse = { version_id: string; members: TrainingSetMember[]; need_preprocess: TrainingSetGap[] };
export type TrainingSetPreviewResponse = TrainingSetVersion & TrainingSetMembersResponse & { reused: boolean; duplicate_of: string | null };
export type TrainingSetTransport = {
  trainingSets(): Promise<TrainingSetVersion[]>;
  trainingSetPreview(body: TrainingSetPreviewInput): Promise<TrainingSetPreviewResponse>;
  trainingSetConfirm(versionId: string): Promise<TrainingSetVersion>;
  trainingSetMembers(versionId: string): Promise<TrainingSetMembersResponse>;
};
export type DatasetTransport = {
  get: (id: string) => Promise<DatasetRecord>;
  chooseDirectories: () => Promise<string[] | null>;
  importDirectory: (path: string, raw: boolean, confirmNew?: boolean) => Promise<ImportResponse>;
  catalog: (limit?: number, offset?: number) => Promise<CatalogPage>;
  deletePreview: (id: string) => Promise<DeletePreview>;
  delete: (id: string, previewToken: string, confirm: boolean) => Promise<DeleteResult>;
  batchDeletePreview: (ids: string[]) => Promise<BatchDeletePreview>;
  batchDelete: (ids: string[], previewToken: string, confirm: boolean) => Promise<BatchDeleteResult>;
  preview: (id: string, selection: number | PreviewOptions) => Promise<Preview>;
  spectraMean: (id: string, region: SpectrumRegion) => Promise<MeanSpectrum>;
  listDatasetVersions: () => Promise<DatasetVersionItem[]>;
};

export function mergeRecords(previous: DatasetRecord[], incoming: DatasetRecord[]): DatasetRecord[] {
  const merged = new Map(previous.map(record => [record.id, record]));
  for (const record of incoming) merged.set(record.id, record);
  return [...merged.values()];
}

export function describeError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'context' in error && typeof error.context === 'object'
      && error.context !== null && 'run_id' in error.context && typeof error.context.run_id === 'string'
      && 'cube_ids' in error.context && Array.isArray(error.context.cube_ids)) {
    const detail = 'detail' in error && typeof error.detail === 'string' ? error.detail : '数据请求失败';
    const hint = 'hint' in error.context && typeof error.context.hint === 'string' ? error.context.hint : '';
    return `${detail}\n实验 ${error.context.run_id}\n关联数据集：${error.context.cube_ids.join('、')}\n${hint}`;
  }
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = typeof error.detail === 'string' ? error.detail : '数据请求失败';
    const context = 'context' in error ? `\n${JSON.stringify(error.context, null, 2)}` : '';
    return detail + context;
  }
  return error instanceof Error ? error.message : typeof error === 'string' ? error : '数据请求失败，请查看引擎状态。';
}
