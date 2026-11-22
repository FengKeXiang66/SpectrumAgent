import { useEffect, useRef, useState } from 'react';
import type { CatalogRecord, DatasetRecord } from '../datasets/types';
import { datasets } from '../datasets/api';
import { currentWorkspace, type CurrentState } from './current';
import { preprocessing } from './api';
import { recipeEvents } from './recipe-events';
import PipelineEditor from './PipelineEditor';
import { compilePipeline } from './pipeline';
import { describePreprocessError, type Report, type Step } from './types';
import CompareChart from './CompareChart';
import './preprocess.css';
import './preprocess-skin.css';
import './batch-workspace.css';

const editorKey = 'spectrumagent.current-recipe-editor';
function restoreEditor(): { id: string; steps: Step[]; name: string } | null {
  try { const row = JSON.parse(localStorage.getItem(editorKey) ?? 'null');
    return row && typeof row.id === 'string' && Array.isArray(row.steps) && typeof row.name === 'string' ? row : null;
  } catch { return null; }
}

export default function PreprocessWorkspace({ records, phase, initialRecord, refreshVersion = 0 }: {
  records: CatalogRecord[]; phase: string; initialRecord: DatasetRecord | null; refreshVersion?: number;
}) {
  const [state, setState] = useState<CurrentState>({ members: [], recipes: [] });
  const [restored] = useState(restoreEditor);
  const [recipeId, setRecipeId] = useState(restored?.id ?? ''), [steps, setSteps] = useState<Step[]>(restored?.steps ?? []);
  const [name, setName] = useState(restored?.name ?? ''), [selected, setSelected] = useState<Record<string, boolean>>({});
  const [sample, setSample] = useState(initialRecord), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [report, setReport] = useState<Report | null>(null);
  const [results, setResults] = useState<{ cube: string; message: string; run?: string }[]>([]);
  const lock = useRef(false), stop = useRef(false);
  const key = records.map(row => row.id).join('|');
  const refresh = async () => { const next = await currentWorkspace.state(); setState(next); return next; };
  useEffect(() => {
    let live = true;
    setSelected(old => Object.fromEntries(records.map(row => [row.id, old[row.id] ?? true])));
    void currentWorkspace.state().then(next => {
      if (!live) return;
      setState(next);
      if (!next.recipes.some(row => row.id === recipeId) && next.recipes[0]) { setRecipeId(next.recipes[0].id); setSteps(next.recipes[0].pipeline.steps); }
    }).catch(e => { if (live) setError(describePreprocessError(e)); });
    return () => { live = false; };
  }, [key, refreshVersion]);
  useEffect(() => {
    let live = true;
    if (!sample || !records.some(row => row.id === sample.id)) {
      const row = records.find(row => row.available);
      if (row) void datasets.get(row.id).then(value => { if (live) setSample(value); }).catch(e => { if (live) setError(describePreprocessError(e)); });
    }
    return () => { live = false; };
  }, [key]);
  useEffect(() => {
    if (!recipeId) return;
    try { localStorage.setItem(editorKey, JSON.stringify({ id: recipeId, steps, name })); } catch { /* SQL saved recipes remain available if browser storage is full. */ }
  }, [recipeId, steps, name]);
  const act = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await action(); } catch (e) { setError(describePreprocessError(e)); }
    finally { lock.current = false; setBusy(false); }
  };
  const pipeline = () => compilePipeline(steps, sample?.dataset.wavelengths ?? [], sample?.dataset.shape[2] ?? 0);
  const dirty = JSON.stringify(steps) !== JSON.stringify(state.recipes.find(row => row.id === recipeId)?.pipeline.steps);
  useEffect(() => {
    let live = true;
    const sync = () => { void currentWorkspace.state().then(next => {
      if (!live) return;
      setState(next);
      if (!dirty) { const recipe = next.recipes.find(row => row.id === recipeId); if (recipe) setSteps(recipe.pipeline.steps); }
    }).catch(e => { if (live) setError(describePreprocessError(e)); }); };
    recipeEvents.addEventListener('change',sync);
    return () => { live = false; recipeEvents.removeEventListener('change',sync); };
  }, [recipeId, dirty]);

  const run = async () => {
    stop.current = false; setResults([]); setReport(null);
    const rows = records.filter(row => selected[row.id] && row.available);
    const completed: typeof results = [];
    for (const [index, row] of rows.entries()) {
      if (stop.current) break;
      setMessage(`正在处理 ${index + 1}/${rows.length} · ${row.display_name}`);
      try {
        const result = await currentWorkspace.process(row.id, recipeId);
        if (result.status !== 'succeeded') throw result.error ?? new Error('处理失败');
        completed.push({ cube: row.id, message: '已完成', run: result.id });
      } catch (e) { completed.push({ cube: row.id, message: describePreprocessError(e) }); }
      setResults([...completed]);
    }
    await refresh(); setMessage(`处理结束：成功 ${completed.filter(row => row.run).length}/${rows.length}`);
  };
  return <section className="preprocess-workspace ui-page" aria-label="预处理工作台">
    <header><h2>预处理工作台</h2><p>保存当前配方，直接处理选中的样品。修改标注或配方后，重新处理即可继续建模。</p></header>
    {error && <p role="alert">{error}</p>}<p role="status">{message}</p>
    <fieldset disabled={busy}><legend>配方</legend>
      <label>当前配方<select value={recipeId} onChange={e => { const row = state.recipes.find(row => row.id === e.target.value); setRecipeId(e.target.value); setSteps(row?.pipeline.steps ?? []); }}>
        {state.recipes.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select></label>
      <label>代表样品<select value={sample?.id ?? ''} onChange={e => void act(async () => { setSample(await datasets.get(e.target.value)); })}>
        {records.filter(row => row.available).map(row => <option key={row.id} value={row.id}>{row.display_name}</option>)}
      </select></label>
      <PipelineEditor steps={steps} onChange={setSteps} initialAxis={sample?.dataset.wavelengths ?? []} bands={sample?.dataset.shape[2] ?? 0} />
      <button disabled={!recipeId || !dirty} onClick={() => void act(async () => { const next = await currentWorkspace.saveRecipe(recipeId, pipeline()); setState(next); setSteps(next.recipes.find(row => row.id === recipeId)!.pipeline.steps); setMessage('当前配方已保存。'); })}>保存配方</button>
      <label>新配方名称<input value={name} onChange={e => setName(e.target.value)} /></label>
      <button disabled={!name.trim()} onClick={() => void act(async () => { const row = await preprocessing.createRecipe({ code: `recipe-${crypto.randomUUID()}`, name: name.trim(), pipeline: pipeline() }); const next = await refresh(); setRecipeId(row.id); setSteps(next.recipes.find(r => r.id === row.id)!.pipeline.steps); setName(''); })}>创建配方</button>
    </fieldset>
    <fieldset disabled={busy}><legend>样品</legend>
      <button onClick={() => setSelected(Object.fromEntries(records.map(row => [row.id, true])))}>全选</button>
      <button onClick={() => setSelected({})}>取消全选</button>
      <ul>{records.map(row => <li key={row.id}><label><input type="checkbox" checked={!!selected[row.id]} disabled={!row.available} onChange={e => setSelected(old => ({ ...old, [row.id]: e.target.checked }))} />{row.display_name}</label>
        <span> · {state.members.find(item => item.cube_id === row.id)?.status === 'ready' ? '当前结果可用于建模' : '待处理'}</span>{state.members.find(item => item.cube_id === row.id)?.run_id && <button onClick={() => void act(async () => { setReport(await preprocessing.getArtifact(state.members.find(item => item.cube_id === row.id)!.run_id!, 'report')); })}>查看当前结果</button>}</li>)}</ul>
      {dirty && <p>请先保存配方修改。</p>}
      <button className="pp-primary" disabled={phase !== 'ready' || !recipeId || dirty || !records.some(row => row.available && selected[row.id])} onClick={() => void act(run)}>处理选中样品</button>
    </fieldset>
    {busy && <button onClick={() => { stop.current = true; }}>完成当前样品后停止</button>}
    <ul>{results.map(row => <li key={row.cube}>{records.find(r => r.id === row.cube)?.display_name} · {row.message}{row.run && <button disabled={busy} onClick={() => void act(async () => setReport(await preprocessing.getArtifact(row.run!, 'report')))}>查看结果</button>}</li>)}</ul>
    {report && <section><h3>处理结果</h3><CompareChart report={report} labels={[]} inputBands={records.find(row => row.id === report.cube_id)?.shape[2] ?? 0} /><pre>{JSON.stringify(report.metrics, null, 2)}</pre></section>}
  </section>;
}
