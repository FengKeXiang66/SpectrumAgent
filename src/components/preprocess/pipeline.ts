import type { Json } from '../annotation/types.ts';
import type { Pipeline, Step } from './types.ts';

// R15 names are exhaustive: reflectance is run-owned; MSC/EMSC await reference provenance.
export const OPERATORS = ['sg_smooth', 'sg_derivative', 'snv', 'standardize', 'crop', 'resample', 'pca', 'mnf', 'ica', 'continuum'] as const;
export const MODES = ['interp', 'mirror', 'constant', 'nearest', 'wrap'];
const reductions = ['pca', 'mnf', 'ica'];
export function axisAfter(steps: Step[], initialAxis: number[] | null): number[] | null {
  let axis = initialAxis?.length ? [...initialAxis] : null;
  for (const step of steps) {
    if (step.op === 'crop') {
      const range = step.params.range as number[];
      axis = axis?.filter(value => value >= range[0] && value <= range[1]) ?? null;
    } else if (step.op === 'resample') axis = [...step.params.target as number[]];
    else if (reductions.includes(step.op)) axis = null;
  }
  return axis;
}
export function targetAxis(start: number, end: number, count: number): number[] {
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end || !Number.isInteger(count) || count < 2) throw new Error('target 起止须有限递增，点数须为 ≥2 的整数');
  return Array.from({ length: count }, (_, i) => i === count - 1 ? end : start + (end - start) * i / (count - 1));
}
const integer = (value: Json | undefined, min: number): value is number => typeof value === 'number' && Number.isInteger(value) && value >= min;
const vector = (value: Json | undefined): value is number[] => Array.isArray(value) && value.length >= 2 && value.every((x, i) => typeof x === 'number' && Number.isFinite(x) && (i === 0 || x > Number(value[i - 1])));

// Only axis metadata is computed here. No spectra or quality metrics enter this module.
export function compilePipeline(steps: Step[], initialAxis: number[] | null, inputBands: number): Pipeline {
  if (!steps.length) throw new Error('算子链不能为空');
  let axis = initialAxis?.length ? [...initialAxis] : null, bands = inputBands;
  const compiled: Step[] = [];
  for (const [index, step] of steps.entries()) {
    const p = { ...step.params }, op = step.op;
    const fail = (detail: string): never => { throw new Error(`第 ${index + 1} 步 ${op}：${detail}`); };
    if (!(OPERATORS as readonly string[]).includes(op) || step.version !== 1) fail('未开放的算子或版本');
    const keys: Record<string, string[]> = { sg_smooth: ['window', 'polyorder', 'mode'], sg_derivative: ['window', 'polyorder', 'mode', 'order'],
      snv: ['zero_std'], standardize: ['method', 'zero_std'], crop: ['source', 'range'], resample: ['source', 'target', 'method'],
      pca: ['n_components', 'random_state'], mnf: ['n_components', 'random_state'], ica: ['n_components', 'random_state'], continuum: ['method'] };
    if (Object.keys(p).some(key => !keys[op].includes(key))) fail('未知参数');
    if (op.startsWith('sg_')) {
      if (!integer(p.window, 1) || p.window % 2 === 0) fail('window 须为正奇数');
      if (!integer(p.polyorder, 0) || Number(p.polyorder) >= Number(p.window)) fail('polyorder 必须严格小于 window');
      if (p.mode !== undefined && !MODES.includes(String(p.mode))) fail('mode 非法');
      if ((p.mode ?? 'interp') === 'interp' && Number(p.window) > bands) fail('interp 窗口不得超过当前 bands');
      if (op === 'sg_derivative' && p.order !== 1 && p.order !== 2) fail('order 仅 1 或 2');
    }
    if ((op === 'snv' || op === 'standardize') && p.zero_std !== undefined && !['zeros', 'nan', 'error'].includes(String(p.zero_std))) fail('zero_std 非法');
    if (op === 'standardize' && !['standard', 'minmax', 'area', 'vector'].includes(String(p.method))) fail('method 非法');
    if (op === 'crop' || op === 'resample') {
      if (!vector(axis)) fail('当前无有效波长轴；crop/resample 不可用');
      p.source = [...axis!];
      if (op === 'crop') {
        const range = p.range;
        if (!Array.isArray(range) || range.length !== 2 || !range.every(x => typeof x === 'number' && Number.isFinite(x)) || Number(range[0]) >= Number(range[1])) fail('lo < hi，且须有限');
        if (!axis!.some(x => x >= Number((range as Json[])[0]) && x <= Number((range as Json[])[1]))) fail('裁剪闭区间内没有波段');
      } else if (!vector(p.target) || !['linear', 'spline'].includes(String(p.method))) fail('target 须严格递增且至少两点；method 须为 linear/spline');
    }
    if (reductions.includes(op)) {
      if (!integer(p.n_components, 1) || Number(p.n_components) > bands) fail('n_components 必填且为 1..bands 的整数');
      if (p.random_state !== undefined && !integer(p.random_state, Number.MIN_SAFE_INTEGER)) fail('random_state 须为整数');
      bands = Number(p.n_components);
    }
    if (op === 'continuum' && !['convex_hull', 'linear'].includes(String(p.method))) fail('method 须为 convex_hull/linear');
    const next = { op, version: step.version, params: p };
    axis = axisAfter([next], axis);
    if (op === 'crop' || op === 'resample') bands = axis!.length;
    compiled.push(next);
  }
  return { steps: compiled };
}

// Canvas path segmentation only; null/non-finite values are never interpolated.
export function curveRuns(values: (number | null)[]): [number, number][][] {
  const runs: [number, number][][] = [];
  let current: [number, number][] = [];
  values.forEach((value, i) => {
    if (value === null || !Number.isFinite(value)) { if (current.length) runs.push(current); current = []; }
    else current.push([i, value]);
  });
  if (current.length) runs.push(current);
  return runs;
}
