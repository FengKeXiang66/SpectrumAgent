import { invoke } from '@tauri-apps/api/core';
import type { ClassificationEvaluation } from './classification-types.ts';
import type { ClassificationAction } from './classification-types.ts';
import { trainingMonitor, type TrainingJob, type TrainingProgress, type TrainingEvent } from './training.ts';
export type { TrainingProgress } from './training.ts';

export type Target = { cube_id: string; schema_id: string; tree_path: string; value: number; source: 'annotation' | 'import' };
export type ImportResult = { imported: number; unmatched: unknown[]; pending_confirmation: unknown[]; invalid: unknown[]; unknown_fields: unknown[]; out_of_range: unknown[] };
export type RegressionBody = { task: 'regression'; preprocess_run_ids: string[]; target_schema_id: string; split_strategy: 'ks';
  cv_strategy: 'kfold' | 'loo'; cv_folds: number; test_ratio: number; seed: number; n_components?: number };
export type ClassificationBody = { task: 'classification'; cube_ids: string[]; annotation_version_ids: string[];
  preprocess_run_ids: string[]; target: 'label'; cv_strategy: 'group_kfold'; cv_folds: number; seed: number;
  split_strategy: 'none'; confidence_threshold: number; n_components?: number; max_components?: number; band_selection?: 'ipls'; recipe_version_id?: string;
  evaluation_protocol?: 'nested_group_cv' | 'exploratory_group_cv'; sample_groups?: Record<string, string> };
export type TrainBody = RegressionBody | ClassificationBody;
export type Prediction = { cube_id: string; y_true: number; y_pred: number; residual: number; set: 'calibration' | 'prediction' };
export type RegressionResult = { task?: 'regression'; run_id: string; status: string; n_samples: number; n_pixels_used: number; selected_lv: number | null;
  best_lv: number | null; metrics: Record<string, number | null>; quality_label: string | null; leak_report: unknown; error: unknown;
  predictions?: Prediction[]; semi_quantitative?: boolean; training_protocol?: string };
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
export type BandInterval = { index: number; start_col: number; end_col: number; rmsecv: number; sd: number };
export type BandSelection = { method: 'ipls'; n_intervals: number; keep: number; lv: number; definition: string;
  intervals: BandInterval[]; indices: number[]; curve: BandInterval[]; limitation: string;
  comparison: Record<'pixel' | 'sample', Record<'full' | 'selected', { oa: number | null; kappa: number | null }>> };
export type ClassificationResult = Omit<RegressionResult, 'task' | 'metrics' | 'predictions' | 'quality_label'> & {
  task: 'classification'; metrics: Record<'pixel' | 'sample', { oa: number | null; kappa: number | null }>;
  confusion?: ClassConfusion; bands?: BandSelection; evaluation?: ClassificationEvaluation; by_cv_min: number | null; by_elbow: number | null; predictions?: never; quality_label?: null };
export type Result = RegressionResult | ClassificationResult;
export type RunRow = { id: string; task: string; status: string; training_protocol?: string; oa?: number | null; kappa?: number | null; lv?: number | null };
export type PreflightBody = { cube_ids: string[]; annotation_version_ids: string[]; preprocess_run_ids: string[];
  task: 'classification'; target: 'label'; cv_strategy: 'group_kfold' | 'random'; cv_folds: number; seed: number; evaluation_protocol?: 'nested_group_cv' | 'exploratory_group_cv' };
export type ModelStage = 'experiment' | 'candidate' | 'production';
export type RegisteredModel = { id: string; run_id: string; name: string; version: number; stage: ModelStage;
  task?: 'classification' | 'regression'; evaluation_id?: string; training_protocol?: string;
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
  | { op: 'submit_training'; id: string; body: ClassificationBody } | { op: 'get_training_job'; id: string }
  | { op: 'list_training_jobs' } | { op: 'training_events'; id: string; after: number; limit: number }
  | { op: 'cancel_training' | 'training_partial'; id: string } | { op: 'continue_training'; id: string; new_id: string }
  | { op: 'download_training'; id: string; destination: string; kind: 'events' | 'partial' }
  | { op: 'register_model'; run_id: string; name?: string } | { op: 'list_models' }
  | { op: 'set_model_stage'; id: string; stage: ModelStage }
  | ({ op: 'create_inference' } & InferenceBody) | { op: 'get_inference' | 'get_inference_map'; id: string }
  | { op: 'get_coefficients'; model_id: string }
  | { op: 'classification'; evaluation_id: string; action: ClassificationAction; body: Record<string, unknown> }
  | { op: 'download_classification'; export_id: string; destination: string };
type Send = <T>(command: string, args: { request: Request }) => Promise<T>;
export function modelingClient(send: Send = invoke) {
  const forward = <T>(request: Request) => send<T>('models_forward', { request });
  const training = trainingMonitor({
    submit: (id, body) => forward<TrainingJob>({ op: 'submit_training', id, body }),
    status: id => forward<TrainingJob>({ op: 'get_training_job', id }),
    result: id => forward<Result>({ op: 'get_run', id }),
    list: () => forward<{ items: TrainingJob[]; engine_boot_id: string }>({ op: 'list_training_jobs' }),
    events: (id, after) => forward<{ events: TrainingEvent[]; cursor: number }>({ op: 'training_events', id, after, limit: 50 }),
    cancel: id => forward<TrainingJob>({ op: 'cancel_training', id }),
    resume: (id, new_id) => forward<TrainingJob>({ op: 'continue_training', id, new_id }),
  });
  return {
    targets: (project: string) => forward<Target[]>({ op: 'list_targets', project_id: project }),
    put: (cube: string, schema: string, value: number) => {
      if (!Number.isFinite(value)) return Promise.reject(new Error('连续量须为有限数值'));
      return forward<Target>({ op: 'put_target', cube_id: cube, schema_id: schema, value });
    },
    importCSV: (project: string, text: string, overwrite = false) => forward<ImportResult>({ op: 'import_targets', project_id: project, csv_text: text, overwrite }),
    train: (body: TrainBody, onProgress?: (progress: TrainingProgress) => void) => body.task === 'classification'
      ? training.train(body, onProgress ?? (() => {})) : forward<Result>({ op: 'create_run', body }),
    training,
    trainingEvents: (id: string, after = 0) => forward<{ events: TrainingEvent[]; cursor: number }>({ op: 'training_events', id, after, limit: 50 }),
    trainingPartial: (id: string) => forward<Record<string, unknown>>({ op: 'training_partial', id }),
    downloadTraining: (id: string, destination: string, kind: 'events' | 'partial') => forward<{ saved: boolean; bytes: number }>({ op: 'download_training', id, destination, kind }),
    pendingTraining: training.pending,
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
    classification: <T>(evaluation_id: string, action: ClassificationAction, body: Record<string, unknown> = {}) =>
      forward<T>({ op: 'classification', evaluation_id, action, body }),
    downloadClassification: (export_id: string, destination: string) =>
      forward<{ saved: boolean; bytes: number }>({ op: 'download_classification', export_id, destination }),
  };
}
export const modeling = modelingClient();
export const metricLabels: Record<string, string> = { rmse: 'RMSEC', r2: 'R²C', rmsep: 'RMSEP', r2p: 'R²P', rpd: 'RPD', rer: 'RER', bias: '偏差' };
export function regressionProtocolLabel(protocol?: string): string {
  if (protocol === 'sample_pls_foldwise_v1') return '训练折内拟合 · 训练状态快照';
  if (!protocol || protocol === 'sample_pls_full_fit_legacy') return '历史全量拟合 · 注册时重建';
  return '其他训练协议，请核对记录';
}

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
