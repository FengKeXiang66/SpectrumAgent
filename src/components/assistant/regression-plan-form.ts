export const regressionPrefix = '提交回归训练方案 ';
export type RegressionDocument = {
  preprocess_run_ids?: string[]; target_schema_id?: string; split_strategy?: 'ks'; test_ratio?: number;
  cv_strategy?: 'kfold' | 'loo'; cv_folds?: number; seed?: number; n_components?: number | null; max_components?: number;
};
export type RegressionPlanView = {
  revision: number; status: string; document: RegressionDocument; review_digest: string | null; run_id: string | null;
  error: string | null; last_form_id: string | null; last_form_ok: boolean | null;
  members: { cube_id: string; name: string; run_id: string | null; status: string; recipe_name: string | null }[];
  schemas: { id: string; name: string; unit: string | null; project_id: string }[];
  targets: { cube_id: string; schema_id: string; value: number }[]; template: RegressionDocument;
  review: null | { training_protocol: string; input_stage: string; target_name: string; unit: string | null;
    pipeline: { steps: { op: string; version: number; params: Record<string, unknown> }[] };
    train_cube_ids: string[]; test_cube_ids: string[]; values: { cube_id: string; value: number }[];
    inner_folds: number; lv_upper_bound: number; coverage_repaired: boolean; metrics: string[]; note: string };
};
export function regressionCommand(body: Record<string, unknown>): string { return regressionPrefix + JSON.stringify(body); }
export function regressionInputLabel(text: string): string {
  if (!text.startsWith(regressionPrefix)) return text;
  try {
    const body = JSON.parse(text.slice(regressionPrefix.length));
    return `回归训练方案：${({ save: '保存参数（不训练）', review: '审阅输入和划分', execute: '确认方案并训练' } as Record<string,string>)[body.action] ?? '提交表单'}`;
  } catch { return '提交回归训练方案'; }
}
export function validateRegression(doc: RegressionDocument): void {
  if (!doc.preprocess_run_ids || doc.preprocess_run_ids.length < 4 || new Set(doc.preprocess_run_ids).size !== doc.preprocess_run_ids.length)
    throw new Error('至少选择四个不同样品的成功预处理结果。');
  if (!doc.target_schema_id) throw new Error('请选择连续量字段。');
  if (doc.split_strategy !== 'ks' || typeof doc.test_ratio !== 'number' || !Number.isFinite(doc.test_ratio) || doc.test_ratio <= 0 || doc.test_ratio >= 1)
    throw new Error('请选择 KS 划分并填写 0 到 1 之间的测试比例。');
  if (!['kfold', 'loo'].includes(doc.cv_strategy ?? '') || doc.cv_strategy === 'kfold' &&
      (!Number.isInteger(doc.cv_folds) || Number(doc.cv_folds) < 2 || Number(doc.cv_folds) > 256))
    throw new Error('请选择交叉验证方法并填写有效折数（2 到 256）。');
  if (!Number.isInteger(doc.seed) || Number(doc.seed) < 0 || Number(doc.seed) > 2**32-1) throw new Error('请填写有效的随机种子。');
  if (!Number.isInteger(doc.max_components) || Number(doc.max_components) < 1 || doc.n_components === undefined ||
      doc.n_components !== null && (!Number.isInteger(doc.n_components) || doc.n_components < 1))
    throw new Error('请选择自动或固定 LV，并填写正整数上限。');
}
