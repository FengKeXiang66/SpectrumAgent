import type { Json } from '../annotation/types.ts';

export type Params = Record<string, Json>;
export type Step = { op: string; version: number; params: Params };
export type Pipeline = { steps: Step[] };
export type RecipeVersion = { id: string; recipe_id: string; version_no: number; pipeline: Pipeline; note: string | null; created_at: string };
export type Recipe = { id: string; code: string; name: string; description: string | null; builtin: number; created_at: string; versions: RecipeVersion[] };
export type RecipeBody = { code: string; name: string; description?: string | null; pipeline: Pipeline; note?: string | null };
export type VersionBody = { pipeline: Pipeline; note?: string | null };
export type RunBody = { annotation_version_id: string; recipe_version_id: string };
export type CompareBody = { annotation_version_id: string; recipe_version_ids: string[] };
export type RunStatus = 'pending' | 'running' | 'succeeded' | 'failed';
export type ForwardError = { error: string; detail: string; context?: Params };
export type Metrics = { snr: { mean: number | null; median: number | null; p10: number | null; p90: number | null; n_pixels: number };
  snr_nan_count: number; nan_spectra_skipped: number; interclass_distance?: number | null; intraclass_variance?: number | null;
  fisher?: number | null; excluded_classes: { label_index: number; pixel_count: number; reason: string }[];
  boundaries: string[]; limitations: string[]; source: string; variance_definition: string };
export type Artifact = { id: string; run_id: string; kind: 'sample_spectra' | 'report'; relative_path: string; sha256: string; created_at: string };
export type PreprocessRun = { id: string; cube_id: string; annotation_version_id: string; recipe_version_id: string;
  b01_branch: string; input_fingerprint: string; status: RunStatus; scaler_params: Json; metrics: Metrics | null;
  error: ForwardError | null; created_at: string; finished_at: string | null; note: string | null; artifacts: Artifact[] };
export type RunSummary = Pick<PreprocessRun, 'id' | 'status' | 'b01_branch' | 'input_fingerprint' | 'created_at' | 'finished_at'> & { error_code: string | null };
export type Ranking = { rank: number; run_id: string; recipe_version_id: string; fisher: number };
export type CompareResult = { runs: PreprocessRun[]; ranking: Ranking[]; boundaries: string[]; selection: string };
export type Curves = { labeled: boolean; wavelengths_in: number[] | null; wavelengths_out: number[] | null;
  classes: { label_index: number; count: number; before: (number | null)[]; after: (number | null)[] | null }[]; sampling: string };
export type Report = { run_id: string; cube_id: string; annotation_version_id: string; recipe_version_id: string;
  input_fingerprint: string; source_hashes: Record<string, string>; label_index: Record<string, string>; metrics: Metrics;
  steps: { op: string; version: number; params: Params; meta: Params }[]; b01: Json; wavelengths: number[] | null;
  curves: Curves; temporary_bytes: number; temporary_peak_bytes: number; temporary_data: string; peak_rss_bytes: number;
  input_fingerprint_matches_previous: boolean | null; fitting_source: Params; not_applicable: string[]; ranking: Ranking[] };
export type BinaryArtifact = { content_type: 'application/octet-stream'; body_base64: string; filename: string };
export type ProjectRecipe = { project_id: string; recipe_id: string; selected_at: string };
export type PreprocessRequest =
  | { op: 'list_recipes' }
  | { op: 'create_recipe'; body: RecipeBody }
  | { op: 'get_recipe'; id: string }
  | { op: 'add_version'; id: string; body: VersionBody }
  | { op: 'select_recipe' | 'deselect_recipe'; project_id: string; recipe_id: string }
  | { op: 'list_project_recipes'; project_id: string }
  | { op: 'create_run'; dataset_id: string; body: RunBody }
  | { op: 'list_runs'; dataset_id: string }
  | { op: 'get_run'; id: string }
  | { op: 'compare'; dataset_id: string; body: CompareBody }
  | { op: 'get_artifact'; run_id: string; kind: 'sample_spectra' | 'report' };
export type PreprocessApi = {
  listRecipes(): Promise<Recipe[]>; createRecipe(body: RecipeBody): Promise<Recipe>; getRecipe(id: string): Promise<Recipe>;
  addVersion(id: string, body: VersionBody): Promise<RecipeVersion>; selectRecipe(project: string, recipe: string): Promise<ProjectRecipe>;
  deselectRecipe(project: string, recipe: string): Promise<null>; listProjectRecipes(project: string): Promise<Recipe[]>;
  createRun(dataset: string, body: RunBody): Promise<PreprocessRun>; listRuns(dataset: string): Promise<RunSummary[]>;
  getRun(id: string): Promise<PreprocessRun>; compare(dataset: string, body: CompareBody): Promise<CompareResult>;
  getArtifact(run: string, kind: 'report'): Promise<Report>;
  getArtifact(run: string, kind: 'sample_spectra'): Promise<BinaryArtifact>;
};

export function describePreprocessError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'error' in error && 'detail' in error) {
    return `${String(error.error)}：${String(error.detail)}${'context' in error ? `\n${JSON.stringify(error.context, null, 2)}` : ''}`;
  }
  return error instanceof Error ? error.message : String(error);
}

export function classLegend(index: number, mapping: Record<string, string>, labels: { id: string; code: string; color_hex: string }[]) {
  const id = mapping[String(index)];
  const label = labels.find(label => label.id === id);
  return { code: index === -1 ? '整体均值' : label?.code ?? id?.slice(0, 8) ?? String(index), color: label?.color_hex ?? '#606a78' };
}

export const PHASE_TWO = ['坏波段剔除：阶段二/不适用', '去背景/仅 ROI：阶段二/不适用', '历史 Kappa 表：阶段二/不适用', '每步单独预览：阶段二/不适用', 'MSC/EMSC：参考谱来源待定，阶段二'];
