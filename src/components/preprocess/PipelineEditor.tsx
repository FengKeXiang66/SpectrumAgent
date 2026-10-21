import { useState } from 'react';
import { axisAfter, compilePipeline, MODES, OPERATORS, targetAxis } from './pipeline.ts';
import type { Params, Step } from './types.ts';

function TargetEditor({ target, onChange }: { target: unknown; onChange: (axis: number[]) => void }) {
  const axis = Array.isArray(target) ? target as number[] : [];
  const [draft, setDraft] = useState([axis[0]?.toString() ?? '', axis.at(-1)?.toString() ?? '', axis.length ? String(axis.length) : '']);
  const [error, setError] = useState('');
  return <div className="pp-target">
    {['起', '止', '点数'].map((name, i) => <label key={name}>{name}<input type="number" step={i === 2 ? 1 : 'any'} value={draft[i]}
      onChange={event => setDraft(draft.map((s, j) => i === j ? event.target.value : s))} /></label>)}
    <button type="button" onClick={() => { try {
      if (draft.some(s => !s.trim())) throw new Error('请填写起、止、点数');
      onChange(targetAxis(...draft.map(Number) as [number, number, number])); setError('');
    } catch (error) { setError((error as Error).message); } }}>生成目标轴</button>
    <span>已生成 {axis.length} 点；修改后需重新生成。</span>{error && <span role="alert">{error}</span>}
  </div>;
}

export default function PipelineEditor({ steps, onChange, initialAxis, bands, disabled = false }: {
  steps: Step[]; onChange: (steps: Step[]) => void; initialAxis: number[]; bands: number; disabled?: boolean;
}) {
  const [op, setOp] = useState<string>('snv');
  const change = (index: number, params: Params) => onChange(steps.map((step, i) => i === index ? { ...step, params } : step));
  const move = (i: number, to: number) => { const next = [...steps]; [next[i], next[to]] = [next[to], next[i]]; onChange(next); };
  let problem = '';
  try { compilePipeline(steps, initialAxis, bands); } catch (error) { problem = (error as Error).message; }
  const numeric = (index: number, key: string, title: string, value: unknown) => <label key={key}>{title}
    <input type="number" step="any" value={typeof value === 'number' ? value : ''} onChange={e => change(index, { ...steps[index].params, [key]: e.target.value === '' ? null : Number(e.target.value) })} /></label>;
  const select = (index: number, key: string, values: string[], fallback = '') => <label key={key}>{key}<select value={String(steps[index].params[key] ?? fallback)}
    onChange={e => change(index, { ...steps[index].params, [key]: e.target.value })}><option value="" disabled>请选择</option>{values.map(value => <option key={value}>{value}</option>)}</select></label>;
  return <fieldset disabled={disabled} className="pp-editor"><legend>算子链 · v1</legend>
    <select aria-label="添加算子" value={op} onChange={e => setOp(e.target.value)}>{OPERATORS.map(name => <option key={name}
      disabled={['crop', 'resample'].includes(name) && !initialAxis.length}>{name}</option>)}</select>{' '}
    <button type="button" disabled={['crop', 'resample'].includes(op) && !initialAxis.length} onClick={() => onChange([...steps, { op, version: 1, params: {} }])}>添加一步</button>
    {!initialAxis.length && <p>数据集无波长轴，crop/resample 禁用。</p>}
    <ol>{steps.map((step, index) => {
      let currentAxis: number[] | null = null;
      try { currentAxis = axisAfter(steps.slice(0, index), initialAxis); } catch { /* Incomplete drafts cannot supply a source axis. */ }
      const p = step.params;
      return <li key={`${index}-${step.op}`}><strong>{step.op}@{step.version}</strong>{' '}
        <button type="button" disabled={index === 0} onClick={() => move(index, index - 1)}>上移</button>
        <button type="button" disabled={index === steps.length - 1} onClick={() => move(index, index + 1)}>下移</button>
        <button type="button" onClick={() => onChange(steps.filter((_, i) => i !== index))}>删除</button>
        <div className="pp-fields">
          {step.op.startsWith('sg_') && <>{numeric(index, 'window', 'window（奇数）', p.window)}{numeric(index, 'polyorder', 'polyorder < window', p.polyorder)}{select(index, 'mode', MODES, 'interp')}
            {step.op === 'sg_derivative' && <label>order<select value={String(p.order ?? '')} onChange={e => change(index, { ...p, order: Number(e.target.value) })}><option value="" disabled>请选择</option><option>1</option><option>2</option></select></label>}</>}
          {['snv', 'standardize'].includes(step.op) && select(index, 'zero_std', ['zeros', 'nan', 'error'], 'zeros')}
          {step.op === 'standardize' && select(index, 'method', ['standard', 'minmax', 'area', 'vector'])}
          {step.op === 'crop' && <>{[0, 1].map(i => <label key={i}>{i ? 'hi' : 'lo'}<input type="number" step="any" value={Array.isArray(p.range) && typeof p.range[i] === 'number' ? String(p.range[i]) : ''}
            onChange={e => { const range = Array.isArray(p.range) ? [...p.range] : [null, null]; range[i] = e.target.value === '' ? null : Number(e.target.value); change(index, { ...p, range }); }} /></label>)}</>}
          {step.op === 'resample' && <>{select(index, 'method', ['linear', 'spline'])}<TargetEditor target={p.target} onChange={target => change(index, { ...p, target })} /></>}
          {['crop', 'resample'].includes(step.op) && <p>source 自动取当前轴：{currentAxis?.length ?? 0} 波段；无当前轴时不可提交。</p>}
          {['pca', 'mnf', 'ica'].includes(step.op) && <>{numeric(index, 'n_components', 'n_components（必填）', p.n_components)}{numeric(index, 'random_state', 'random_state（默认 0）', p.random_state ?? 0)}</>}
          {step.op === 'continuum' && select(index, 'method', ['convex_hull', 'linear'])}
        </div>
      </li>;
    })}</ol>
    {problem && <p role="status">{problem}；当前链不可保存或提交。</p>}
    <p>reflectance 由 run 前置转换，不进入配方；MSC/EMSC：参考谱来源待定，阶段二。</p>
  </fieldset>;
}
