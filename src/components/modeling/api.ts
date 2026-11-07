import { invoke } from '@tauri-apps/api/core';

export type Target = { cube_id: string; schema_id: string; tree_path: string; value: number; source: 'annotation' | 'import' };
export type ImportResult = { imported: number; unmatched: unknown[]; pending_confirmation: unknown[]; invalid: unknown[]; unknown_fields: unknown[]; out_of_range: unknown[] };
export type RegressionBody = { task: 'regression'; preprocess_run_ids: string[]; target_schema_id: string; split_strategy: 'ks';
  cv_strategy: 'kfold' | 'loo'; cv_folds: number; test_ratio: number; seed: number; n_components?: number };
export type ClassificationBody = { task: 'classification'; cube_ids: string[]; annotation_version_ids: string[];
  preprocess_run_ids: string[]; target: 'label'; cv_strategy: 'group_kfold'; cv_folds: number; seed: number;
  split_strategy: 'none'; confidence_threshold: number; n_components?: number; max_components?: number };
export type TrainBody = RegressionBody | ClassificationBody;
export type Prediction = { cube_id: string; y_true: number; y_pred: number; residual: number; set: 'calibration' | 'prediction' };
export type RegressionResult = { task?: 'regression'; run_id: string; status: string; n_samples: number; n_pixels_used: number; selected_lv: number | null;
  best_lv: number | null; metrics: Record<string, number | null>; quality_label: string | null; leak_report: unknown; error: unknown;
  predictions?: Prediction[]; semi_quantitative?: boolean };
export type Sweep = { best_lv: number; elbow_lv: number; selected_lv: number; by_cv_min: number; by_elbow: number;
  manual_override: boolean; definition: string; curve: { n_components: number; rmsecv: number; sd: number }[] };
export type ClassScore = { oa: number | null; kappa: number | null; aa: number | null; macro_f1: number | null;
  labels: number[]; confusion: number[][]; per_class: { label: number; precision: number | null; recall: number | null; f1: number | null }[] };
export type ClassScopes = Record<'pixel' | 'sample', ClassScore>;
export type FoldStatistic = { mean: number | null; std: number | null };
export type ClassConfusion = { scores: ClassScopes; folds: ({ fold_index: number } & ClassScopes)[];
  fold_summary: Record<'pixel' | 'sample', Record<'oa' | 'kappa' | 'aa' | 'macro_f1', FoldStatistic> & {
    per_class: { label: number; precision: FoldStatistic; recall: FoldStatistic; f1: FoldStatistic }[] }>;
  threshold: { confidence_threshold: number; uncertain_pixels: number; accepted_pixels: number; total_pixels: number };
  lv: Sweep; manifest: { operator: string; operator_version: number; code_version: string | null; seed: number } };
export type ClassificationResult = Omit<RegressionResult, 'task' | 'metrics' | 'predictions' | 'quality_label'> & {
  task: 'classification'; metrics: Record<'pixel' | 'sample', { oa: number | null; kappa: number | null }>;
  confusion?: ClassConfusion; by_cv_min: number | null; by_elbow: number | null; predictions?: never; quality_label?: null };
export type Result = RegressionResult | ClassificationResult;
export type RunRow = { id: string; task: string; status: string; oa?: number | null; kappa?: number | null; lv?: number | null };
export type PreflightBody = { cube_ids: string[]; annotation_version_ids: string[]; preprocess_run_ids: string[];
  task: 'classification'; target: 'label'; cv_strategy: 'group_kfold' | 'random'; cv_folds: number; seed: number };
export type ModelStage = 'experiment' | 'candidate' | 'production';
export type RegisteredModel = { id: string; run_id: string; name: string; version: number; stage: ModelStage;
  target_schema_id: string; data_fingerprint: string; metrics: Record<string, number | null>; quality_label: string | null;
  applicability: { y_min: number; y_max: number; n_features: number; wavelength_axis_sha256: string;
    recipe_version_id: string; target_schema_id: string; task: 'regression' } };
export type InferenceBody = { model_id: string; cube_id: string; preprocess_run_id: string; annotation_version_id: string };
export type InferenceStats = { n_pixels: number; n_foreground: number; mean: number; std: number; min: number; max: number;
  pixel_mean: number; sample_prediction: number; out_of_domain_count: number; out_of_domain_fraction: number;
  out_of_range_count: number; below_range_count: number; above_range_count: number; low: number; high: number;
  warning: string; quality_label: string | null; calibration_limitation: string; quantiles: Record<string, number>;
  calibration_origin: string; fit_scope: string | null; calibration_provenance_present: boolean;
  residual_interval: { mean: number; sd: number | null; low: number | null; high: number | null } };
export type InferenceResult = InferenceBody & { id: string; status: string; stats: InferenceStats | null; error: unknown };
export type ConcentrationMap = { width: number; height: number; mime: 'image/png'; png_base64: string;
  applicability_png_base64: string; low: number; high: number; palette: number[][]; stats: InferenceStats };
export type Coefficients = { model_id: string; name: string; version: number; stage: ModelStage; selected_lv: number;
  quality_label: string | null; n_features: number; n_wavelengths: number; comparable: boolean;
  coefficients: number[]; wavelengths: number[]; limitation: string };
export type Request = { op: 'list_targets'; project_id: string } | { op: 'put_target'; cube_id: string; schema_id: string; value: number }
  | { op: 'import_targets'; project_id: string; csv_text: string; overwrite: boolean } | { op: 'create_run'; body: TrainBody }
  | { op: 'preflight_run'; body: PreflightBody } | { op: 'list_runs' } | { op: 'get_run' | 'lv_sweep'; id: string }
  | { op: 'register_model'; run_id: string; name?: string } | { op: 'list_models' }
  | { op: 'set_model_stage'; id: string; stage: ModelStage }
  | ({ op: 'create_inference' } & InferenceBody) | { op: 'get_inference' | 'get_inference_map'; id: string }
  | { op: 'get_coefficients'; model_id: string };
type Send = <T>(command: string, args: { request: Request }) => Promise<T>;
export function modelingClient(send: Send = invoke) {
  const forward = <T>(request: Request) => send<T>('models_forward', { request });
  return {
    targets: (project: string) => forward<Target[]>({ op: 'list_targets', project_id: project }),
    put: (cube: string, schema: string, value: number) => {
      if (!Number.isFinite(value)) return Promise.reject(new Error('连续量须为有限数值'));
      return forward<Target>({ op: 'put_target', cube_id: cube, schema_id: schema, value });
    },
    importCSV: (project: string, text: string, overwrite = false) => forward<ImportResult>({ op: 'import_targets', project_id: project, csv_text: text, overwrite }),
    train: (body: TrainBody) => forward<Result>({ op: 'create_run', body }),
    preflight: (body: PreflightBody) => forward<unknown>({ op: 'preflight_run', body }),
    runs: () => forward<RunRow[]>({ op: 'list_runs' }),
    run: (id: string) => forward<Result>({ op: 'get_run', id }),
    sweep: (id: string) => forward<Sweep>({ op: 'lv_sweep', id }),
    register: (run_id: string, name?: string) => forward<RegisteredModel>({ op: 'register_model', run_id, ...(name === undefined ? {} : { name }) }),
    models: () => forward<RegisteredModel[]>({ op: 'list_models' }),
    stage: (id: string, stage: ModelStage) => forward<RegisteredModel>({ op: 'set_model_stage', id, stage }),
    infer: (body: InferenceBody) => forward<InferenceResult>({ op: 'create_inference',
      model_id: body.model_id, cube_id: body.cube_id, preprocess_run_id: body.preprocess_run_id, annotation_version_id: body.annotation_version_id }),
    inference: (id: string) => forward<InferenceResult>({ op: 'get_inference', id }),
    inferenceMap: (id: string) => forward<ConcentrationMap>({ op: 'get_inference_map', id }),
    coefficients: (model_id: string) => forward<Coefficients>({ op: 'get_coefficients', model_id }),
  };
}
export const modeling = modelingClient();
export const metricLabels: Record<string, string> = { rmse: 'RMSEC', r2: 'R²C', rmsep: 'RMSEP', r2p: 'R²P', rpd: 'RPD', rer: 'RER', bias: '偏差' };

export const stageLabels: Record<ModelStage, string> = { experiment: '实验', candidate: '候选', production: '生产' };
export const inferenceWarning = '模型训练粒度＝样品均值谱；像素级预测为域外外推，仅表示含量空间分布趋势';
export function mapSource(map: ConcentrationMap, domain = false): string {
  const data = domain ? map.applicability_png_base64 : map.png_base64;
  if (map.mime !== 'image/png' || !Number.isInteger(map.width) || map.width < 1
      || !Number.isInteger(map.height) || map.height < 1 || !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(data)) return '';
  return 'data:image/png;base64,' + data;
}
export function clippingMessage(stats: InferenceStats): string {
  return '越界像素已按量程上限/下限显示，共 ' + stats.out_of_range_count + ' 个越界（前景；低于下限 '
    + stats.below_range_count + '，高于上限 ' + stats.above_range_count + '）';
}
export function paletteGradient(palette: number[][]): string {
  if (palette.length < 2 || palette.some(row => row.length !== 3 || row.some(value => !Number.isInteger(value) || value < 0 || value > 255))) return '';
  return 'linear-gradient(to right, ' + palette.map(row => 'rgb(' + row.join(',') + ')').join(',') + ')';
}
