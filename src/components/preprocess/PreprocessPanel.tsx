import { useEffect, useRef, useState } from 'react';
import { annotations } from '../annotation/api.ts';
import type { Label, Project, Version } from '../annotation/types.ts';
import type { DatasetRecord } from '../datasets/types.ts';
import { preprocessing, recoverRun, submitRun } from './api.ts';
import { compilePipeline } from './pipeline.ts';
import { describePreprocessError, PHASE_TWO, type CompareResult, type Metrics, type PreprocessRun, type Recipe, type Report, type RunSummary, type Step } from './types.ts';
import CompareChart from './CompareChart';
import PipelineEditor from './PipelineEditor';
import './preprocess.css';

function MetricsView({ metrics }: { metrics: Metrics }) {
  return <section aria-label="后端指标"><h3>后端逐像素指标</h3><dl className="pp-metrics">
    {Object.entries(metrics.snr).map(([key, value]) => <div key={key}><dt>SNR {key}</dt><dd>{value ?? '不适用'}</dd></div>)}
    {(['snr_nan_count', 'nan_spectra_skipped', 'interclass_distance', 'intraclass_variance', 'fisher'] as const).filter(key => key in metrics).map(key =>
      <div key={key}><dt>{key}</dt><dd>{metrics[key] ?? '不适用'}</dd></div>)}
  </dl><p>{metrics.source}</p><p>{metrics.variance_definition}</p>
    {metrics.excluded_classes.map(item => <p key={item.label_index}>label_index {item.label_index} · {item.pixel_count}：{item.reason}</p>)}
    {[...metrics.boundaries, ...metrics.limitations].map((text, i) => <p key={i}>{text}</p>)}
  </section>;
}

export default function PreprocessPanel({ record, onClose }: { record: DatasetRecord; onClose: () => void }) {
  const [recipes, setRecipes] = useState<Recipe[]>([]), [selected, setSelected] = useState<Recipe[]>([]);
  const [project, setProject] = useState<Project | null>(null), [labels, setLabels] = useState<Label[]>([]);
  const [versions, setVersions] = useState<Version[]>([]), [annotationVersion, setAnnotationVersion] = useState('');
  const [recipeId, setRecipeId] = useState(''), [recipeVersion, setRecipeVersion] = useState('');
  const [steps, setSteps] = useState<Step[]>([]), [metadata, setMetadata] = useState({ code: '', name: '', description: '', note: '' });
  const [run, setRun] = useState<PreprocessRun | null>(null), [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]), [comparison, setComparison] = useState<CompareResult | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState('');
  const recovery = useRef<{ recipe: string; before: RunSummary[] } | null>(null);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    void Promise.all([preprocessing.listRecipes(), annotations.projects(), annotations.versions(record.id), preprocessing.listRuns(record.id)])
      .then(async ([library, projects, saved, rows]) => {
        if (!live.current) return;
        setRecipes(library); setVersions(saved.versions); setAnnotationVersion(saved.versions.at(-1)?.id ?? ''); setHistory(rows);
        const current = projects[0] ?? null; setProject(current);
        if (current) {
          const [chosen, schemas] = await Promise.all([preprocessing.listProjectRecipes(current.id), annotations.labels(current.id)]);
          if (live.current) { setSelected(chosen); setLabels(schemas.flatMap(schema => schema.labels)); }
        }
      }).catch(error => { if (live.current) setError(describePreprocessError(error)); });
    return () => { live.current = false; };
  }, [record.id]);
  const task = async (work: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await work(); } catch (error) { if (live.current) setError(describePreprocessError(error)); }
    finally { if (live.current) setBusy(false); }
  };
  const showRun = async (row: PreprocessRun) => {
    if (!live.current) return;
    setRun(row); setReport(null);
    if (row.status === 'succeeded') {
      const data = await preprocessing.getArtifact(row.id, 'report');
      if (live.current) setReport(data);
    }
  };
  const refresh = async () => {
    const rows = await preprocessing.listRuns(record.id);
    if (!live.current) return;
    setHistory(rows);
    if (recovery.current) {
      const found = await recoverRun(preprocessing, record.id, recovery.current.recipe, recovery.current.before);
      if (found) { setMessage('任务可能已完成'); recovery.current = null; await showRun(found); }
    }
  };
  const load = async (id: string, versionId?: string) => {
    const recipe = await preprocessing.getRecipe(id);
    if (!live.current) return;
    const version = recipe.versions.find(v => v.id === versionId) ?? recipe.versions.at(-1);
    setRecipeId(id); setRecipeVersion(version?.id ?? ''); setSteps(structuredClone(version?.pipeline.steps ?? []));
    setMetadata({ code: recipe.code, name: recipe.name, description: recipe.description ?? '', note: '' }); setMessage('编辑后须保存为新版本；历史版本不覆写。');
  };
  let invalid = '';
  try { compilePipeline(steps, record.dataset.wavelengths, record.dataset.shape[2]); } catch (error) { invalid = (error as Error).message; }
  const currentVersion = recipes.find(r => r.id === recipeId)?.versions.find(v => v.id === recipeVersion);
  let changed = true;
  try { changed = JSON.stringify(compilePipeline(steps, record.dataset.wavelengths, record.dataset.shape[2])) !== JSON.stringify(currentVersion?.pipeline); } catch { /* Invalid drafts cannot run. */ }
  const submit = async () => {
    const before = await preprocessing.listRuns(record.id);
    recovery.current = { recipe: recipeVersion, before };
    setMessage('正在同步执行，等待后端终态…');
    let result;
    try { result = await submitRun(preprocessing, record.id, { annotation_version_id: annotationVersion, recipe_version_id: recipeVersion }, before); }
    catch (error) { recovery.current = null; throw error; }
    if (!result.run) {
      setMessage('状态暂未恢复，请手动刷新最近 run；尚未判定任务失败。');
      return;
    }
    recovery.current = null; setMessage(result.interrupted ? '任务可能已完成' : `后端状态：${result.run.status}`);
    await showRun(result.run); await refresh();
  };
  const save = async (newVersion: boolean) => {
    const pipeline = compilePipeline(steps, record.dataset.wavelengths, record.dataset.shape[2]);
    if (metadata.note.length > 2000) throw new Error('note 最多 2000 字符');
    let id = recipeId, versionId: string;
    if (newVersion) { const version = await preprocessing.addVersion(id, { pipeline, note: metadata.note || null }); versionId = version.id; }
    else {
      const recipe = await preprocessing.createRecipe({ ...metadata, pipeline }); id = recipe.id; versionId = recipe.versions.at(-1)!.id;
    }
    setRecipes(await preprocessing.listRecipes()); await load(id, versionId); setMessage('已保存不可变配方版本。');
  };
  return <section className="preprocess-panel" aria-label="S06 预处理工作台">
    <header><button disabled={busy} onClick={onClose}>返回数据集</button><h2>S06 · {record.dataset.name}</h2><span>项目：{project?.name ?? '未获取'}</span></header>
    <p role="status">{message}</p>{error && <pre role="alert">{error}{error.startsWith('INVALID_REQUEST') ? '\n请检查 code 是否重复及配方参数。' : ''}</pre>}
    <div className="pp-layout"><aside><h3>配方库（按 code）</h3><button disabled={busy} onClick={() => { setRecipeId(''); setRecipeVersion(''); setSteps([]); setMetadata({ code: '', name: '', description: '', note: '' }); }}>新建草稿</button>
      {recipes.map(recipe => <section key={recipe.id}><strong>{recipe.code}</strong> · {recipe.name}
        <button disabled={busy} onClick={() => { void task(() => load(recipe.id)); }}>载入</button>
        {recipe.versions.map(version => <label className="pp-compare-choice" key={version.id}><input type="checkbox" checked={compareIds.includes(version.id)} disabled={busy}
          onChange={e => setCompareIds(e.target.checked ? [...compareIds, version.id] : compareIds.filter(id => id !== version.id))} />对比 v{version.version_no}</label>)}
        <button disabled={busy || !project} onClick={() => { void task(async () => { if (!project) return;
          if (selected.some(r => r.id === recipe.id)) await preprocessing.deselectRecipe(project.id, recipe.id);
          else await preprocessing.selectRecipe(project.id, recipe.id);
          setSelected(await preprocessing.listProjectRecipes(project.id));
        }); }}>{selected.some(r => r.id === recipe.id) ? '取消项目选用' : '项目选用'}</button>
      </section>)}<p>项目选用为只读关联；取消不会删除配方。</p>
    </aside><div className="pp-main">
      <fieldset disabled={busy}><legend>命名与版本</legend>{(['code', 'name', 'description', 'note'] as const).map(key => <label key={key}>{key}<input value={metadata[key]} maxLength={key === 'note' ? 2000 : undefined}
        onChange={e => setMetadata({ ...metadata, [key]: e.target.value })} /></label>)}
        {recipeId && <label>配方版本<select value={recipeVersion} onChange={e => { void task(() => load(recipeId, e.target.value)); }}>
          {recipes.find(r => r.id === recipeId)?.versions.map(v => <option key={v.id} value={v.id}>v{v.version_no}</option>)}</select></label>}
        <button disabled={!!invalid || !metadata.code.trim() || !metadata.name.trim()} onClick={() => { void task(() => save(false)); }}>保存为新配方</button>
        <button disabled={!!invalid || !recipeId} onClick={() => { void task(() => save(true)); }}>保存为新版本</button>
      </fieldset>
      <PipelineEditor steps={steps} onChange={setSteps} initialAxis={record.dataset.wavelengths} bands={record.dataset.shape[2]} disabled={busy} />
      <fieldset disabled={busy}><legend>执行与对比</legend><label>标注版本<select value={annotationVersion} onChange={e => setAnnotationVersion(e.target.value)}>
        <option value="">请选择已保存标注版本</option>{versions.map(v => <option key={v.id} value={v.id}>v{v.version_no} · {v.created_at}</option>)}</select></label>
        {!versions.length && <p>先在 S05 标注并保存</p>}{changed && recipeVersion && <p>草稿已变更，请先保存为新版本再执行。</p>}
        <button disabled={!annotationVersion || !recipeVersion || !!invalid || changed} onClick={() => { void task(submit); }}>提交 run</button>
        <button disabled={!annotationVersion || !compareIds.length} onClick={() => { void task(async () => {
          setComparison(await preprocessing.compare(record.id, { annotation_version_id: annotationVersion, recipe_version_ids: compareIds })); await refresh();
        }); }}>对比所选版本</button>
      </fieldset>
      <button disabled={busy} onClick={() => { void task(refresh); }}>刷新最近 run / 恢复状态</button>
      <ul>{history.map(row => <li key={row.id}><button disabled={busy} onClick={() => { void task(async () => showRun(await preprocessing.getRun(row.id))); }}>{row.id.slice(0, 8)} · {row.status}</button> {row.error_code} · {row.created_at}</li>)}</ul>
      {run && <section aria-label="run 详情"><h3>{run.status} · {run.id}</h3>{run.error && <pre role="alert">{describePreprocessError(run.error)}</pre>}
        {run.metrics && <MetricsView metrics={run.metrics} />}</section>}
      {report && <><CompareChart report={report} labels={labels} inputBands={record.dataset.shape[2]} />{report.steps.filter(s => ['pca', 'mnf', 'ica'].includes(s.op)).map((step, i) => <section key={i}>
        <h3>{step.op} · {step.op === 'ica' ? '分量重构能量占比' : '解释方差占比'}</h3>
        {step.op === 'ica' && <p>{String(step.meta.variance_definition ?? '')}</p>}
        <p>explained_variance_ratio：{JSON.stringify(step.meta.explained_variance_ratio)}</p><p>cumulative_explained_variance：{JSON.stringify(step.meta.cumulative_explained_variance)}</p>
      </section>)}{report.not_applicable.map(text => <p key={text}>{text}</p>)}</>}
      {comparison && <section aria-label="配方对比"><h3>Fisher 主排序</h3><table><thead><tr><th>rank</th><th>run</th><th>recipe_version</th><th>Fisher</th></tr></thead>
        <tbody>{comparison.ranking.map(row => <tr key={row.run_id}><td>{row.rank}</td><td>{row.run_id}</td><td>{row.recipe_version_id}</td><td>{row.fisher}</td></tr>)}</tbody></table>
        {comparison.runs.map(row => <section key={row.id}><button disabled={busy} onClick={() => { void task(() => showRun(row)); }}>查看 {row.id.slice(0, 8)} · {row.status}</button>
          {row.metrics?.fisher == null && <p>未参与排名：{row.error ? describePreprocessError(row.error) : '后端 Fisher 为 null；详见 excluded_classes / limitations。'}</p>}{row.metrics && <MetricsView metrics={row.metrics} />}</section>)}
        {comparison.boundaries.map(text => <p key={text}>{text}</p>)}<p>{comparison.selection}</p>
      </section>}
      <ul>{PHASE_TWO.map(text => <li key={text}>{text}</li>)}</ul>
    </div></div>
  </section>;
}
