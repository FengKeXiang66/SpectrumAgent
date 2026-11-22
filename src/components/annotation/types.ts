// Wire contracts: Rust AnnotationRequest (R21), Python api/annotations.py.
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Pixel = [number, number]; // [line, sample], never canvas [x,y].
export type Seed = { point: Pixel } | { box: [number, number, number, number] } | { doodle: Pixel[] };
export type Geometry = { superpixels: number[] } | { polygon: Pixel[] };
export type EditAction = 'confirm' | 'erase' | 'uncertain';
export type SuperpixelOptions = { n_segments?: number; compactness?: number; pca_components?: number; force?: boolean };
export type DiffuseOptions = { threshold?: number; queue_min_similarity?: number };
export type SaveOptions = { note?: string | null };
export type FieldType = 'enum' | 'bool' | 'continuous' | 'ordinal';
export type SchemaInput = { name: string; tree_path: string; field_type: FieldType; unit?: string | null; config?: Json };
export type LabelBody =
  | { project_id: string; from_catalog: 'plastic'; codes: string[] }
  | { project_id: string; code: string; name: string; tree_path: string; color_hex: string; shortcut_key?: number | null; is_background?: boolean }
  | { project_id: string; schema: SchemaInput }
  | { project_id: string; name: string; color_hex: string };
export type AnnotationRequest =
  | { op: 'get_superpixels'; id: string }
  | ({ op: 'superpixels'; id: string } & SuperpixelOptions)
  | ({ op: 'diffuse'; id: string; seed: Seed } & DiffuseOptions)
  | { op: 'regions'; id: string; geometry: Geometry; action: EditAction; label_id?: string | null }
  | { op: 'undo' | 'working' | 'validate' | 'current'; id: string }
  | ({ op: 'save'; id: string } & SaveOptions)
  | { op: 'projects' | 'catalog' }
  | { op: 'labels'; project_id: string }
  | { op: 'add_label'; body: LabelBody }
  | { op: 'patch_label'; label_id: string; body: LabelPatch }
  | { op: 'delete_label'; label_id: string; confirm: boolean }
  | { op: 'merge_labels'; body: MergeLabels }
  | { op: 'import_tree_preview'; body: ImportTreeScope }
  | { op: 'import_tree_apply'; body: ImportTreeApply }
  | { op: 'assign_samples'; body: AssignSamples }
  | { op: 'sample_labels'; project_id?: string };

export type LabelPatch = { name?: string; color_hex?: string; shortcut_key?: number | null; tree_path?: string };
export type MergeLabels = { source_id: string; target_id: string };
export type ImportTreeScope = { project_id: string; root: string; depth?: number };
export type ImportTreeCandidate = { directory: string; code: string; name: string; color_hex: string;
  sample_count: number; reuse: boolean; needs_naming: boolean; confirmed: boolean };
export type ImportTreeApply = ImportTreeScope & { candidates: ImportTreeCandidate[] };
export type AssignSamples = { project_id: string; cube_ids: string[]; label_id: string; source: 'manual' | 'dialog' };
export type AppliedTree = { created_labels: number; created_samples: number; skipped: number };

export type Png = { width: number; height: number; mime?: 'image/png'; png_base64: string };
export type SegmentsMap = { png: string; shape: [number, number]; counts: number[] };
export type Blocks = { label: number[]; purity: number[]; label_count: number[] };
export type Parameters = { n_segments: number; compactness: number; pca_components: number; k: number; block_size: number; feature_version: string; pca_batch_size: number };
export type Candidate = { candidate_ref?: string; superpixels: number[]; pixel_count: number; seed_superpixels: number[]; min_similarity: number; avg_similarity: number; cos_s: number[]; overlay: Png };
export type Statistics = {
  n_pixels: number; labeled_pixels: number; uncertain_pixels: number; blank_pixels: number;
  labeled_percent: number; uncertain_percent: number; blank_percent: number;
  label_counts: Record<string, number>; pending_pixels: number; dominant_label_id: string | null;
};
export type Working = {
  project_id: string; queue: Candidate[]; superpixel_count: number; params: Parameters | null;
  statistics: Statistics | Record<string, never>; overlay: Png | null; blocks: Blocks;
};
export type SuperpixelReport = {
  action?: 'generated'|'reused'|'restored';
  segments_png: string; segments_shape: [number, number]; block_counts: number[];
  cube_id: string; shape: [number, number, number]; params: Parameters; superpixel_count: number;
  n_before: number; n_after: number; area_cv: number; R: number | null;
  boundary_sum: number; internal_sum: number; boundary_pairs: number; internal_pairs: number; sum_ratio_diagnostic: number | null;
  d_s: number[]; tau: number; subdivided_ids: number[]; parent_children: Record<string, number[]>;
  feature_bytes: number; resident_feature_bytes: number; feature_mean: number[]; feature_std: number[];
  normalized_mean: number[]; normalized_std: number[]; normalized_min: number; normalized_max: number;
  baseline_rss_bytes: number; baseline_peak_rss_bytes: number; peak_rss_bytes: number; peak_rss_delta_bytes: number;
  pca_seconds: number; slic_seconds: number; total_seconds: number; overlay: Png;
};
export type SuperpixelView =
  | { status: 'ready'; segmentation_ref: string; origin: 'memory' | 'disk'; durable: true; load_elapsed_ms: number; report: SuperpixelReport }
  | { status: 'missing'; segmentation_ref: null; origin: null; durable: false; load_elapsed_ms: number; report: null };

export function parseSuperpixelView(value: unknown, id: string): SuperpixelView {
  const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
  const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
  const positive = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0;
  const invalid = () => { throw new Error('分割读取响应不完整，未附接画布。'); };
  if (!object(value) || Object.keys(value).sort().join(',') !== 'durable,load_elapsed_ms,origin,report,segmentation_ref,status'
      || !integer(value.load_elapsed_ms)) return invalid();
  if (value.status === 'missing') {
    if (value.segmentation_ref !== null || value.origin !== null || value.durable !== false || value.report !== null) return invalid();
    return value as SuperpixelView;
  }
  if (value.status !== 'ready' || value.durable !== true || !['memory', 'disk'].includes(String(value.origin))
      || typeof value.segmentation_ref !== 'string' || !/^s-[0-9a-f]{64}$/.test(value.segmentation_ref)
      || !object(value.report)) return invalid();
  const r = value.report, p = r.params, shape = r.shape, map = r.segments_shape;
  if (typeof r.cube_id !== 'string' || r.cube_id.toLowerCase() !== id.toLowerCase()
      || !Array.isArray(shape) || shape.length !== 3 || !shape.every(n => integer(n) && n > 0)
      || !Array.isArray(map) || map.length !== 2 || map[0] !== shape[0] || map[1] !== shape[1]
      || !integer(r.superpixel_count) || r.superpixel_count === 0 || r.superpixel_count > 65536
      || !Array.isArray(r.block_counts) || r.block_counts.length !== r.superpixel_count
      || !r.block_counts.every(n => integer(n) && n > 0) || r.block_counts.reduce((a: number, b: number) => a + b, 0) !== shape[0] * shape[1]
      || typeof r.segments_png !== 'string' || !r.segments_png || !object(r.overlay)
      || !integer(r.overlay.width) || !integer(r.overlay.height) || !r.overlay.width || !r.overlay.height
      || r.overlay.width > 512 || r.overlay.height > 512 || typeof r.overlay.png_base64 !== 'string'
      || !object(p) || !integer(p.n_segments) || p.n_segments === 0 || !integer(p.pca_components) || p.pca_components === 0
      || !positive(p.compactness) || !positive(p.k) || !integer(p.block_size) || p.block_size === 0
      || p.pca_batch_size !== p.block_size * shape[1] || typeof p.feature_version !== 'string' || !p.feature_version) return invalid();
  return value as SuperpixelView;
}
export type DiffuseReport = {
  candidate: Candidate; candidates: Candidate[]; queue: Candidate[]; enqueued: boolean;
  not_queued_reasons: { below_queue_min_similarity: number }; params: Required<DiffuseOptions>;
  feature_bytes: number; mean_spectra_bytes: number; peak_rss_bytes: number; elapsed_seconds: number;
};
export type Comparison = { superpixel_id: number; label_index: number; pixel_count: number; cos: number | null; mean: (number | null)[] };
export type Quality = {
  threshold: number; threshold_level: string; reference: string; suspicious: Comparison[]; comparisons: Comparison[];
  references: { label_index: number; mean: (number | null)[] }[];
  high_variance: { d_s: (number | null)[]; tau: number | null; superpixel_ids: number[] }; completeness: Statistics;
  not_applicable: Record<string, string>;
};
export type SaveNote = { event: 'save' | 'overwrite'; at: string; text?: string };
export type SavedAnnotation = { id: string; cube_id: string; snapshot_ref: string; n_pixels: number;
  labeled_pixels: number; auto_ratio: number; params: Parameters; note: SaveNote | null; created_at: string };
// Disk truth for exports/<cube_id>/manifest.json; optional for older engines.
export type JsonProjectionStatus = {
  exists: boolean; path: string | null; filename: string | null;
  generated_at: string | null; reason: string | null;
};
export type CurrentAnnotation = { current: SavedAnnotation | null; working: Working; json_projection?: JsonProjectionStatus | null };
export type ExportResult = { ok: boolean; path: string | null; error: string | null };
export type Saved = { id: string; cube_id: string; snapshot_ref: string; created_at: string; note: string | null; export: ExportResult;
  quality: Quality; elapsed_seconds: number; transaction_seconds: number };
export type Project = { id: string; name: string; created_at: string; note: string | null };
export type CatalogItem = { code: string; name: string; color_hex: string };
export type Label = CatalogItem & { id: string; project_id: string; schema_id: string; tree_path: string;
  shortcut_key: number | null; sort_order: number; is_background: number; created_at: string };
export type LabelSchemaRow = { id: string; project_id: string; name: string; tree_path: string; field_type: FieldType;
  unit: string | null; config: Json; created_at: string };
export type LabelSchema = LabelSchemaRow & { labels: Label[] };
export type AnnotationApi = {
  getSuperpixels(id: string): Promise<SuperpixelView>;
  superpixels(id: string, options?: SuperpixelOptions): Promise<SuperpixelReport>;
  diffuse(id: string, seed: Seed, options?: DiffuseOptions): Promise<DiffuseReport>;
  regions(id: string, geometry: Geometry, action: EditAction, labelId?: string): Promise<Omit<Working, 'overlay'>>;
  undo(id: string): Promise<Working>; working(id: string): Promise<Working>; validate(id: string): Promise<Quality>;
  save(id: string, options?: SaveOptions): Promise<Saved>; current(id: string): Promise<CurrentAnnotation>;
  projects(): Promise<Project[]>;
  labels(projectId: string): Promise<LabelSchema[]>; addLabel(body: LabelBody): Promise<Label | Label[] | LabelSchemaRow>;
  catalog(): Promise<CatalogItem[]>;
  patchLabel(labelId: string, body: LabelPatch): Promise<Label>;
  deleteLabel(labelId: string): Promise<{ deleted: string }>;
  mergeLabels(body: MergeLabels): Promise<{ target: Label; references: Record<string, number> }>;
  importTreePreview(body: ImportTreeScope): Promise<ImportTreeCandidate[]>;
  importTreeApply(body: ImportTreeApply): Promise<AppliedTree>;
  assignSamples(body: AssignSamples): Promise<{ assigned: number; skipped: number }>;
  sampleLabels(projectId?: string): Promise<Record<string, Label[]>>;
};

export function describeAnnotationError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'error' in error && 'detail' in error) {
    const code = typeof error.error === 'string' ? error.error : 'REQUEST_FAILED';
    const cacheErrors: Record<string, string> = {
      SEGMENTATION_INCOMPATIBLE: '分割格式或算法不兼容，请显式重新准备。',
      SEGMENTATION_CORRUPT: '分割产物损坏，未自动重新计算。',
      SEGMENTATION_STALE: '分割或源内容已变化，请核查后显式重新准备。',
      CACHE_UNAVAILABLE: '分割存储暂不可用，原标注保持不变。',
      CACHE_MEMORY_BUDGET: '分割或编辑内存预算不足，原标注与历史保持不变。',
      CACHE_DISK_BUDGET: '分割缓存磁盘预算不足，未提交新结果。',
    };
    if (cacheErrors[code]) return `${code}：${cacheErrors[code]}`;
    const detail = typeof error.detail === 'string' ? error.detail : '标注请求失败';
    const context = 'context' in error ? `\n${JSON.stringify(error.context, null, 2)}` : '';
    return `${code}：${detail}${context}`;
  }
  return error instanceof Error ? error.message : typeof error === 'string' ? error : '标注请求失败，请检查引擎状态。';
}
