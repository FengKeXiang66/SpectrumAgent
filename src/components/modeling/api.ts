import { invoke } from '@tauri-apps/api/core';

export type Target = { cube_id: string; schema_id: string; tree_path: string; value: number; source: 'annotation' | 'import' };
export type ImportResult = { imported: number; unmatched: unknown[]; pending_confirmation: unknown[]; invalid: unknown[]; unknown_fields: unknown[]; out_of_range: unknown[] };
export type TrainBody = { task: 'regression'; preprocess_run_ids: string[]; target_schema_id: string; split_strategy: 'ks';
  cv_strategy: 'kfold' | 'loo'; cv_folds: number; test_ratio: number; seed: number; n_components?: number };
export type Result = { run_id: string; status: string; n_samples: number; n_pixels_used: number; selected_lv: number;
  best_lv: number; metrics: Record<string, number | null>; quality_label: string | null; leak_report: unknown; error: unknown };
export type Sweep = { best_lv: number; elbow_lv: number; selected_lv: number; curve: { n_components: number; rmsecv: number; sd: number }[] };
export type PreflightBody = { cube_ids: string[]; annotation_version_ids: string[]; preprocess_run_ids: string[];
  task: 'classification'; target: 'label'; cv_strategy: 'group_kfold' | 'random'; cv_folds: number; seed: number };
export type Request = { op: 'list_targets'; project_id: string } | { op: 'put_target'; cube_id: string; schema_id: string; value: number }
  | { op: 'import_targets'; project_id: string; csv_text: string; overwrite: boolean } | { op: 'create_run'; body: TrainBody }
  | { op: 'preflight_run'; body: PreflightBody } | { op: 'list_runs' } | { op: 'get_run' | 'lv_sweep'; id: string };
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
    runs: () => forward<{ id: string; task: string; status: string }[]>({ op: 'list_runs' }),
    run: (id: string) => forward<Result>({ op: 'get_run', id }),
    sweep: (id: string) => forward<Sweep>({ op: 'lv_sweep', id }),
  };
}
export const modeling = modelingClient();
export const metricLabels: Record<string, string> = { rmse: 'RMSEC', r2: 'R²C', rmsep: 'RMSEP', r2p: 'R²P', rpd: 'RPD', rer: 'RER', bias: '偏差' };
