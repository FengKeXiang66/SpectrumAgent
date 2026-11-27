import type { Step } from '../preprocess/types';

export type EditorKind = 'classification' | 'recipe';
export type ExperimentStep = { op: string; [key: string]: string | number | null | undefined };
export type EditorState = {
  kind: EditorKind; draft_id: string | null; revision: number | null;
  steps: (Step | ExperimentStep)[]; recipe_id: string | null; name: string;
  recipes: { id: string; name: string }[]; axis: number[]; bands: number; axis_cube_id: string | null; busy?: boolean;
  last_form_ok?: boolean; last_form_id?: string;
  members?: { cube_id: string; status: 'ready' | 'need_annotation' | 'need_preprocess'; recipe_id?: string | null }[];
};
export const classificationOperators = ['savgol', 'snv', 'l2', 'center', 'standard_scale', 'pca'];
export function recipeMemberStatus(data: EditorState | null, cubeId: string): 'ready' | 'need_annotation' | 'need_preprocess' {
  const member = data?.members?.find(row => row.cube_id === cubeId);
  if (!member) return 'need_annotation';
  return member.status === 'ready' && member.recipe_id !== data?.recipe_id ? 'need_preprocess' : member.status;
}
export function validateClassification(steps: ExperimentStep[]): void {
  if (steps.length > 30) throw new Error('最多配置 30 步。');
  for (const [index, step] of steps.entries()) {
    const fail = (message: string): never => { throw new Error(`第 ${index + 1} 步：${message}`); };
    if (!classificationOperators.includes(step.op)) fail('该算子不属于分类训练方案。');
    if (step.op === 'savgol') {
      if (!Number.isInteger(step.window) || Number(step.window) < 1 || Number(step.window) % 2 !== 1) fail('SG 窗口须为正奇数。');
      if (!Number.isInteger(step.polyorder) || Number(step.polyorder) < 0 || Number(step.polyorder) >= Number(step.window)) fail('SG 阶数须小于窗口。');
      if (![0, 1, 2].includes(Number(step.derivative)) || step.derivative == null || Number(step.derivative) > Number(step.polyorder)) fail('请选择有效的导数阶数。');
      if (typeof step.delta_nm !== 'number' || !Number.isFinite(step.delta_nm) || step.delta_nm <= 0) fail('请填写正数波长步长。');
    }
    if (step.op === 'pca' && (!Number.isInteger(step.n_components) || Number(step.n_components) < 1)) fail('请填写正整数主成分数。');
    if (step.op === 'snv' && step.ddof !== undefined && step.ddof !== 0 && step.ddof !== 1) fail('SNV ddof 只能为 0 或 1。');
    if (step.op === 'l2' && step.epsilon !== undefined && (typeof step.epsilon !== 'number' || !Number.isFinite(step.epsilon) || step.epsilon <= 0)) fail('epsilon 必须为正数。');
  }
}

export function formCommand(body: Record<string, unknown>): string {
  return '提交预处理表单 ' + JSON.stringify(body);
}
export function formInputLabel(content: string): string {
  if (!content.startsWith('提交预处理表单 ')) return content;
  try {
    const body = JSON.parse(content.slice('提交预处理表单 '.length));
    return `${body.kind === 'classification' ? '分类预处理' : '高级配方'}：${body.action === 'open' ? '打开草稿' : body.action === 'save' ? '保存配方' : '提交参数修改'}`;
  } catch { return '提交预处理表单'; }
}
