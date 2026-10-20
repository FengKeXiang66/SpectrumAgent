// Wire contracts: Rust AnnotationRequest (R21), Python api/annotations.py.
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Pixel = [number, number]; // [line, sample], never canvas [x,y].
export type Seed = { point: Pixel } | { box: [number, number, number, number] } | { doodle: Pixel[] };
export type Geometry = { superpixels: number[] } | { polygon: Pixel[] };
export type EditAction = 'confirm' | 'erase' | 'uncertain';
export type SuperpixelOptions = { n_segments?: number; compactness?: number; pca_components?: number; force?: boolean };
export type DiffuseOptions = { threshold?: number; queue_min_similarity?: number };
export type SaveOptions = { note?: string | null; overwrite?: boolean; confirm?: boolean };
export type FieldType = 'enum' | 'bool' | 'continuous' | 'ordinal';
export type SchemaInput = { name: string; tree_path: string; field_type: FieldType; unit?: string | null; config?: Json };
export type LabelBody =
  | { project_id: string; from_catalog: 'plastic'; codes: string[] }
  | { project_id: string; code: string; name: string; tree_path: string; color_hex: string; shortcut_key?: number | null; is_background?: boolean }
  | { project_id: string; schema: SchemaInput };
export type AnnotationRequest =
  | ({ op: 'superpixels'; id: string } & SuperpixelOptions)
  | ({ op: 'diffuse'; id: string; seed: Seed } & DiffuseOptions)
  | { op: 'regions'; id: string; geometry: Geometry; action: EditAction; label_id?: string | null }
  | { op: 'undo' | 'working' | 'validate' | 'versions'; id: string }
  | ({ op: 'save'; id: string } & SaveOptions)
  | { op: 'version_overlay'; id: string; version: string }
  | { op: 'projects' | 'catalog' }
  | { op: 'labels'; project_id: string }
  | { op: 'add_label'; body: LabelBody };

export type Png = { width: number; height: number; mime?: 'image/png'; png_base64: string };
export type Parameters = { n_segments: number; compactness: number; pca_components: number; k: number; block_size: number; feature_version: string; pca_batch_size: number };
export type Candidate = { superpixels: number[]; pixel_count: number; seed_superpixels: number[]; min_similarity: number; avg_similarity: number; cos_s: number[]; overlay: Png };
export type Statistics = {
  n_pixels: number; labeled_pixels: number; uncertain_pixels: number; blank_pixels: number;
  labeled_percent: number; uncertain_percent: number; blank_percent: number;
  label_counts: Record<string, number>; pending_pixels: number; dominant_label_id: string | null;
};
export type Working = {
  project_id: string; queue: Candidate[]; superpixel_count: number; params: Parameters | null;
  statistics: Statistics | Record<string, never>; overlay: Png | null;
};
export type SuperpixelReport = {
  cube_id: string; shape: [number, number, number]; params: Parameters; superpixel_count: number;
  n_before: number; n_after: number; area_cv: number; R: number | null;
  boundary_sum: number; internal_sum: number; boundary_pairs: number; internal_pairs: number; sum_ratio_diagnostic: number | null;
  d_s: number[]; tau: number; subdivided_ids: number[]; parent_children: Record<string, number[]>;
  feature_bytes: number; resident_feature_bytes: number; feature_mean: number[]; feature_std: number[];
  normalized_mean: number[]; normalized_std: number[]; normalized_min: number; normalized_max: number;
  baseline_rss_bytes: number; baseline_peak_rss_bytes: number; peak_rss_bytes: number; peak_rss_delta_bytes: number;
  pca_seconds: number; slic_seconds: number; total_seconds: number; overlay: Png;
};
export type DiffuseReport = {
  candidate: Candidate; candidates: Candidate[]; queue: Candidate[]; enqueued: boolean;
  not_queued_reasons: { below_queue_min_similarity: number }; params: Required<DiffuseOptions>;
  feature_bytes: number; mean_spectra_bytes: number; peak_rss_bytes: number; elapsed_seconds: number;
};
export type Comparison = { superpixel_id: number; label_index: number; pixel_count: number; cos: number };
export type Quality = {
  threshold: number; threshold_level: string; reference: string; suspicious: Comparison[]; comparisons: Comparison[];
  high_variance: { d_s: number[]; tau: number; superpixel_ids: number[] }; completeness: Statistics;
  not_applicable: Record<string, string>;
};
export type VersionNote = { event: 'save' | 'overwrite'; at: string; text?: string };
export type Version = { id: string; cube_id: string; version_no: number; snapshot_ref: string; n_pixels: number;
  labeled_pixels: number; auto_ratio: number; params: Parameters; note: VersionNote | null; created_at: string };
export type Versions = { versions: Version[]; working: Working };
export type Saved = { id: string; cube_id: string; snapshot_ref: string; created_at: string; note: string | null;
  quality: Quality; elapsed_seconds: number; transaction_seconds: number };
export type Project = { id: string; name: string; created_at: string; note: string | null };
export type CatalogItem = { code: string; name: string; color_hex: string };
export type Label = CatalogItem & { id: string; project_id: string; schema_id: string; tree_path: string;
  shortcut_key: number | null; sort_order: number; is_background: number; created_at: string };
export type LabelSchemaRow = { id: string; project_id: string; name: string; tree_path: string; field_type: FieldType;
  unit: string | null; config: Json; created_at: string };
export type LabelSchema = LabelSchemaRow & { labels: Label[] };
export type AnnotationApi = {
  superpixels(id: string, options?: SuperpixelOptions): Promise<SuperpixelReport>;
  diffuse(id: string, seed: Seed, options?: DiffuseOptions): Promise<DiffuseReport>;
  regions(id: string, geometry: Geometry, action: EditAction, labelId?: string): Promise<Working>;
  undo(id: string): Promise<Working>; working(id: string): Promise<Working>; validate(id: string): Promise<Quality>;
  save(id: string, options?: SaveOptions): Promise<Saved>; versions(id: string): Promise<Versions>;
  versionOverlay(id: string, version: string): Promise<Png>; projects(): Promise<Project[]>;
  labels(projectId: string): Promise<LabelSchema[]>; addLabel(body: LabelBody): Promise<Label | Label[] | LabelSchemaRow>;
  catalog(): Promise<CatalogItem[]>;
};

export function describeAnnotationError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'error' in error && 'detail' in error) {
    const code = typeof error.error === 'string' ? error.error : 'REQUEST_FAILED';
    const detail = typeof error.detail === 'string' ? error.detail : '标注请求失败';
    const context = 'context' in error ? `\n${JSON.stringify(error.context, null, 2)}` : '';
    return `${code}：${detail}${context}`;
  }
  return error instanceof Error ? error.message : typeof error === 'string' ? error : '标注请求失败，请检查引擎状态。';
}
