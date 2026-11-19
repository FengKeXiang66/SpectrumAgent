import type { BandSelection, ClassScore, Sweep, FoldStatistic } from './api.ts';
export type Scope = 'pixel' | 'sample';
export type Population = 'all_labeled' | 'accepted';
export type ClassSupport = {
  policy: 'allow_missing_classes'; minimum_groups_per_class: null;
  classes: { label: number; name: string; pixels: number; groups: number }[];
  warnings: string[];
};
export type EvaluationScore = ClassScore & {
  per_class: (ClassScore['per_class'][number] & { support: number; predicted_count: number; tp: number; fp: number; fn: number; rejected_count: number })[];
  row_totals: number[]; column_totals: number[]; row_normalized: (number | null)[][]; column_normalized: (number | null)[][];
  total: number; accepted: number; rejected: number; correct: number; incorrect: number;
  coverage: number | null; correct_acceptance_ratio: number | null; metric_refs: Record<string, string>;
  effective_classes?: { aa: number; macro_f1: number };
  top_errors: { true_label: number; predicted_label: number; count: number; row_fraction: number | null }[];
};
export type PopulationReport = {
  scores: Record<Scope, EvaluationScore>;
  folds: ({ fold_index: number } & Record<Scope, ClassScore>)[];
  fold_summary: Record<Scope, Record<'oa' | 'aa' | 'kappa' | 'macro_f1', FoldStatistic & { n_effective: number }>>;
};
export type ClassificationEvaluation = {
  evaluation_id: string; run_id: string; schema_version: number; definition: string; protocol: string; group_kind: string;
  populations: Record<Population, PopulationReport>; threshold: number; n_images: number; n_samples: number; n_pixels: number;
  classes: { id: string; label: number; code: string; name: string; color: string; background: boolean }[];
  cubes: { cube_id: string; name: string; shape: number[]; group: number; annotation_version_id: string;
    n_valid: number; invalid_spectra: number; unlabeled: number; annotation_uncertain: number }[];
  sample_rows: { group: number; true_label: number; predicted_label: number | null; n_true: number; n_accepted: number; majority_fraction: number }[];
  operator: string; operator_version: number; seed: number; code_version: string | null; created_at: string;
  training_set_ref: string | null; lv: Sweep; bands: BandSelection | null; feature_count: number;
  class_support?: ClassSupport;
  fold_selected_lv: { fold_index: number; selected_lv: number }[];
  artifacts: Record<string, { artifact_id: string; sha256: string }>; limitations: string[]; duration_s: number; wavelength_unit: string | null;
};
export type ClassificationAction = 'curves' | 'map' | 'pixel' | 'coefficients' | 'importance' | 'compare' | 'interpret'
  | 'register' | 'baseline' | 'infer' | 'task' | 'cancel' | 'retry' | 'export' | 'threshold' | 'choices' | 'evaluate_prediction';
