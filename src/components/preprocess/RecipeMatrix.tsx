import { useEffect, useRef, useState } from 'react';
import { annotations } from '../annotation/api.ts';
import type { Label } from '../annotation/types.ts';
import type { CatalogRecord } from '../datasets/types.ts';
import { preprocessing } from './api.ts';
import CompareChart from './CompareChart';
import { verifiedReceipt } from './batch-plan.ts';
import { MetricsView, type PreprocessDesignState } from './PreprocessPanel';
import { describePreprocessError, type Metrics, type PreprocessRun, type Report, type RunBatchResult } from './types.ts';
import './preprocess.css';
import './preprocess-skin.css';

type Cell = { recipeVersionId: string; cubeId: string; runId: string | null; status: string; errorCode: string | null };

export default function RecipeMatrix({ records, selectedIds, bindings, design, recordId, bands }: {
  records: CatalogRecord[]; selectedIds: string[]; bindings: Record<string, string>;
  design: PreprocessDesignState | null; recordId: string; bands: number;
}) {
  const [chosen, setChosen] = useState<string[]>([]);
  const [cells, setCells] = useState<Cell[]>([]);
  const [metrics, setMetrics] = useState<Record<string, Metrics>>({});
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [projectId, setProjectId] = useState(''), [adopted, setAdopted] = useState<string[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [openRunId, setOpenRunId] = useState<string | null>(null);
  const [openDetail, setOpenDetail] = useState<PreprocessRun | null>(null), [openReport, setOpenReport] = useState<Report | null>(null);
  const live = useRef(true), openTicket = useRef(0);
  const versions = design?.recipes.flatMap(recipe => recipe.versions.map(version => ({ recipe, version }))) ?? [];
  const members = records.filter(record => selectedIds.includes(record.id) && bindings[record.id]);
  useEffect(() => {
    if (!recordId) return;
    let valid = true;
    void Promise.all([annotations.projects(), annotations.versions(recordId)])
      .then(async ([projects, saved]) => {
        const project = projects.find(item => item.id === saved.working.project_id);
        if (!project || !valid) return;
        setProjectId(project.id);
        const [chosenRecipes, schemas] = await Promise.all([preprocessing.listProjectRecipes(project.id), annotations.labels(project.id)]);
        if (valid) { setAdopted(chosenRecipes.map(recipe => recipe.id)); setLabels(schemas.flatMap(schema => schema.labels)); }
      }).catch(failure => { if (valid) setError(describePreprocessError(failure)); });
    return () => { valid = false; };
  }, [recordId]);
  useEffect(() => {
    const pending = cells.flatMap(cell => cell.runId && !metrics[cell.runId] ? [cell.runId] : []);
    if (!pending.length) return;
    let cancelled = false, cursor = 0;
    const load = async () => {
      while (cursor < pending.length && !cancelled) {
        const runId = pending[cursor++];
        try {
          const row = await preprocessing.getRun(runId);
          if (cancelled) return;
          if (row.metrics) setMetrics(previous => ({ ...previous, [runId]: row.metrics! }));
        } catch { /* A missing summary never removes the fixed run identity. */ }
      }
    };
    void Promise.all(Array.from({ length: Math.min(4, pending.length) }, load));
    return () => { cancelled = true; };
  }, [cells, metrics]);
  const runSelected = async () => {
    if (!chosen.length || !members.length) return;
    setBusy(true); setError(''); setCells([]); setMetrics({}); setOpenDetail(null); setOpenReport(null); setOpenRunId(null);
    try {
      const collected: Cell[] = [];
      for (const recipeVersionId of chosen) {
        const items = members.map(member => ({ cube_id: member.id, annotation_version_id: bindings[member.id], recipe_version_id: recipeVersionId }));
        for (let offset = 0; offset < items.length; offset += 32) {
          const batch = items.slice(offset, offset + 32);
          const receipt: RunBatchResult = await preprocessing.createRunBatch({ items: batch }, crypto.randomUUID());
          const verified = verifiedReceipt(receipt, batch);
          collected.push(...verified.items.map(item => ({ recipeVersionId, cubeId: item.cube_id,
            runId: item.run_id, status: item.status, errorCode: item.error_code })));
          setMessage(`已完成 ${collected.length} / ${chosen.length * members.length} 项`);
        }
      }
      setCells(collected);
      setMessage(`已提交 ${chosen.length} 个配方 × ${members.length} 个样品，共 ${collected.length} 项。`);
    } catch (failure) { if (live.current) setError(describePreprocessError(failure)); }
    finally { if (live.current) setBusy(false); }
  };
  const open = async (runId: string) => {
    if (!runId) return;
    const ticket = ++openTicket.current;
    setOpenRunId(runId); setOpenDetail(null); setOpenReport(null); setError('');
    try {
      const row = await preprocessing.getRun(runId);
      if (!live.current || ticket !== openTicket.current) return;
      setOpenDetail(row);
      if (row.status === 'succeeded') {
        const report = await preprocessing.getArtifact(runId, 'report');
        if (live.current && ticket === openTicket.current) setOpenReport(report);
      }
    } catch (failure) { if (live.current) setError(describePreprocessError(failure)); }
  };
  const exportEnvi = async () => {
    if (!openDetail) return;
    setBusy(true); setError('');
    try {
      const exported = await preprocessing.exportRun(openDetail.id);
      const row = await preprocessing.getRun(openDetail.id);
      if (!live.current) return;
      setOpenDetail(row);
      if (row.status === 'succeeded') setOpenReport(await preprocessing.getArtifact(row.id, 'report'));
      setMessage(`导出完成：${exported.manifest_relative_path}`);
    } catch (failure) { if (live.current) setError(describePreprocessError(failure)); }
    finally { if (live.current) setBusy(false); }
  };
  const toggleAdopt = async (recipeId: string) => {
    if (!projectId) { setError('尚未取得当前项目，无法设置采用标记。'); return; }
    const wasAdopted = adopted.includes(recipeId);
    setBusy(true); setError('');
    try {
      if (wasAdopted) await preprocessing.deselectRecipe(projectId, recipeId);
      else await preprocessing.selectRecipe(projectId, recipeId);
      setAdopted(await preprocessing.listProjectRecipes(projectId).then(rows => rows.map(row => row.id)));
      setMessage(wasAdopted ? '已取消该配方的项目采用标记。' : '已标记为该项目采用的配方。');
    } catch (failure) { if (live.current) setError(describePreprocessError(failure)); }
    finally { if (live.current) setBusy(false); }
  };
  return <section className="pp-matrix-card" aria-label="多配方试验"><header className="pp-matrix-head">
    <h3>多配方筛选</h3><p className="pp-hint">勾选配方版本与样品，一次运行后横向比较，再把看中的配方标记为本项目采用（可多选、可取消；标记只是记录偏好，不绑定建模用的配方版本）。</p>
  </header>
    <div className="pp-matrix-picker">{versions.length ? versions.map(({ recipe, version }) => <label className="pp-matrix-choice" key={version.id}>
      <input type="checkbox" checked={chosen.includes(version.id)} onChange={e => setChosen(ids => e.target.checked ? [...ids, version.id] : ids.filter(id => id !== version.id))} />
      <span>{recipe.name} · v{version.version_no}</span></label>) : <p>先在「配方设计」页保存至少一个配方版本。</p>}</div>
    <div className="pp-matrix-actions"><button className="pp-primary" disabled={busy || !chosen.length || !members.length}
      onClick={() => { void runSelected(); }}>运行 {chosen.length} 个配方 × {members.length} 个样品</button></div>
    <p role="status">{message}</p>{error && <pre role="alert">{error}</pre>}
    {!!cells.length && <div className="pp-matrix-scroll"><table className="pp-matrix-table"><thead><tr><th>配方版本</th>{members.map(member => <th key={member.id}>{member.display_name}</th>)}<th>项目采用</th></tr></thead><tbody>
      {chosen.map(versionId => { const entry = versions.find(item => item.version.id === versionId); const recipeId = entry?.recipe.id ?? '';
        return <tr key={versionId}><th>{entry?.recipe.name ?? versionId.slice(0, 8)} · v{entry?.version.version_no ?? '—'}</th>
          {members.map(member => { const cell = cells.find(item => item.recipeVersionId === versionId && item.cubeId === member.id); const summary = cell?.runId ? metrics[cell.runId] : undefined;
            return <td key={member.id}>{cell ? <button className={openRunId === cell.runId ? 'pp-matrix-cell is-open' : 'pp-matrix-cell'} disabled={!cell.runId || busy}
              onClick={() => { if (cell.runId) void open(cell.runId); }}>{cell.status === 'succeeded' ? (summary ? `SNR ${summary.snr.mean?.toFixed(3) ?? '—'}` : '读取中…') : cell.status}<small>{cell.runId ? cell.runId.slice(0, 8) : cell.errorCode ?? '无运行'}</small></button> : '—'}</td>; })}
          <td><button className={adopted.includes(recipeId) ? 'pp-adopted' : ''} disabled={busy || !recipeId || !projectId}
            onClick={() => { void toggleAdopt(recipeId); }}>{adopted.includes(recipeId) ? '取消采用' : '标记为采用'}</button></td></tr>; })}
    </tbody></table></div>}
    {openDetail && <section className="pp-matrix-detail" aria-label="比较详情"><header><h3>{openDetail.status} · {openDetail.id}</h3><div className="pp-matrix-detail-actions">
      <button disabled={busy || openDetail.status !== 'succeeded'} onClick={() => { void exportEnvi(); }}>显式导出 ENVI</button>
      <button onClick={() => { openTicket.current++; setOpenRunId(null); setOpenDetail(null); setOpenReport(null); }}>关闭</button></div></header>
      <ul aria-label="ENVI 导出产物">{openDetail.artifacts.filter(item => item.kind === 'processed_cube').map(item =>
        <li key={item.id}><code>{item.relative_path}</code> · SHA256 <code>{item.sha256}</code></li>)}</ul>
      {openDetail.metrics && <MetricsView metrics={openDetail.metrics} runId={openReport?.run_id ?? openDetail.id} steps={openReport?.steps} />}
      {openReport && <CompareChart report={openReport} labels={labels} inputBands={bands} />}</section>}
  </section>;
}
