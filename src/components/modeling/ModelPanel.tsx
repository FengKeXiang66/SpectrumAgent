import { useEffect, useState } from 'react';
import { annotations } from '../annotation/api.ts';
import type { LabelSchema, Project } from '../annotation/types.ts';
import type { DatasetRecord } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import { preprocessing } from '../preprocess/api.ts';
import { modeling, type ImportResult, type Target } from './api.ts';
import RegistryPanel from './RegistryPanel.tsx';
import InferencePanel from './InferencePanel.tsx';
import './modeling.css';

export default function ModelPanel({ records, onClose, onOpenResults }: { records: DatasetRecord[]; onClose(): void; onOpenResults(run: string): void }) {
  const [view, setView] = useState<'training' | 'registry' | 'inference'>('training');
  const [projects, setProjects] = useState<Project[]>([]), [project, setProject] = useState('');
  const [schemas, setSchemas] = useState<LabelSchema[]>([]), [schema, setSchema] = useState('');
  const [cube, setCube] = useState(records[0]?.id ?? ''), [value, setValue] = useState('');
  const [targets, setTargets] = useState<Target[]>([]), [csv, setCSV] = useState(''), [imported, setImported] = useState<ImportResult | null>(null);
  const [choices, setChoices] = useState<Record<string, { id: string; version: string }[]>>({}), [selected, setSelected] = useState<Record<string, string>>({});
  const [strategy, setStrategy] = useState<'kfold' | 'loo'>('kfold'), [folds, setFolds] = useState(5), [ratio, setRatio] = useState(1 / 3), [lv, setLV] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); } catch (failure) { setError(failure instanceof Error ? failure.message : JSON.stringify(failure)); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    let live = true;
    void Promise.all([annotations.projects(), Promise.all(records.map(async record => {
      const runs = await preprocessing.listRuns(record.id);
      const ready = await Promise.all(runs.filter(row => row.status === 'succeeded').map(row => preprocessing.getRun(row.id)));
      return [record.id, ready.map(row => ({ id: row.id, version: row.annotation_version_id }))] as const;
    }))]).then(([projects, available]) => { if (live) { setProjects(projects); setProject(projects[0]?.id ?? ''); setChoices(Object.fromEntries(available)); } })
      .catch(failure => { if (live) setError(JSON.stringify(failure)); });
    return () => { live = false; };
  }, [records]);
  useEffect(() => {
    if (!project) return;
    let live = true;
    setSchema(''); setSchemas([]); setTargets([]);
    void Promise.all([annotations.labels(project), modeling.targets(project)]).then(([fields, values]) => {
      if (live) { setSchemas(fields.filter(field => field.field_type === 'continuous')); setTargets(values); }
    }).catch(failure => { if (live) setError(JSON.stringify(failure)); });
    return () => { live = false; };
  }, [project]);
  const importCSV = async (overwrite: boolean) => { setImported(await modeling.importCSV(project, csv, overwrite)); setTargets(await modeling.targets(project)); };
  const runIds = Object.values(selected).filter(Boolean);
  if (view === 'registry') return <RegistryPanel onClose={() => setView('training')} />;
  if (view === 'inference') return <InferencePanel records={records} onClose={() => setView('training')} />;
  return <section className="model-panel" aria-label="PLS 回归工作台">
    <header><button disabled={busy} onClick={onClose}>返回数据集</button><h2>PLS 回归</h2></header>
    <nav aria-label="建模操作"><button disabled={busy} onClick={() => setView('registry')}>模型注册</button><button disabled={busy} onClick={() => setView('inference')}>批量推理</button></nav>
    <p role="status">{message}</p>{error && <pre role="alert">{error}</pre>}
    <fieldset disabled={busy}><legend>样品连续量</legend>
      <label>项目<select value={project} onChange={e => setProject(e.target.value)}>{projects.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      <label>连续字段<select value={schema} onChange={e => setSchema(e.target.value)}><option value="">请选择</option>{schemas.map(row => <option key={row.id} value={row.id}>{row.tree_path}{row.unit ? ` (${row.unit})` : ''}</option>)}</select></label>
      {!schemas.length && <p>请先在标注面板定义连续字段，再回到此处填写样品取值。</p>}
      <label>样品<select value={cube} onChange={e => setCube(e.target.value)}>{records.map(row => <option key={row.id} value={row.id}>{displayName(row)}</option>)}</select></label>
      <label>测量值<input type="number" step="any" value={value} onChange={e => setValue(e.target.value)} /></label>
      <button disabled={!schema || !cube || !value.trim()} onClick={() => void work(async () => { await modeling.put(cube, schema, Number(value)); setTargets(await modeling.targets(project)); setMessage('已保存样品测量值。'); })}>保存测量值</button>
      <details><summary>已保存 {targets.length} 条</summary><ul>{targets.map(row => <li key={row.cube_id + row.schema_id}>{records.filter(record => record.id === row.cube_id).map(displayName)[0] ?? row.cube_id} · {row.tree_path}：{row.value}（{row.source === 'annotation' ? '手填' : '导入'}）</li>)}</ul></details>
      <p>CSV 表头：cube_name,schema,value；字段优先填完整路径，也可填项目内唯一名称。样品名称须唯一关联。</p>
      <input aria-label="选择连续量 CSV" type="file" accept=".csv,text/csv" onChange={e => { const file = e.target.files?.[0]; if (file) void work(async () => { if (file.size > 2 * 1024 * 1024) throw new Error('CSV 须小于 2 MiB'); setCSV(await file.text()); setImported(null); }); }} />
      <button disabled={!csv || !project} onClick={() => void work(() => importCSV(false))}>导入 CSV</button>
      {imported && <div><p>本次导入 {imported.imported} 条；未关联 {imported.unmatched.length} 条；待确认 {imported.pending_confirmation.length} 条；字段或值错误 {imported.invalid.length} 条；未知字段 {imported.unknown_fields.length} 条；越界 {imported.out_of_range.length} 条。</p>
        {[['未关联', imported.unmatched], ['待确认', imported.pending_confirmation], ['字段或值错误', imported.invalid], ['未知字段', imported.unknown_fields], ['越界', imported.out_of_range]].map(([name, rows]) => <details key={String(name)}><summary>{String(name)}</summary><pre>{JSON.stringify(rows, null, 2)}</pre></details>)}
        {!!imported.pending_confirmation.length && <button onClick={() => void work(() => importCSV(true))}>确认覆盖并重新导入</button>}</div>}
    </fieldset>
    <fieldset disabled={busy}><legend>训练配置</legend>
      <p>每个样品选一个已成功的预处理 run；均值谱使用该 run 绑定的标注版本，并排除背景。未填写目标值的样品会自动排除。</p>
      {records.map(row => <label key={row.id}>{displayName(row)}<select value={selected[row.id] ?? ''} onChange={e => setSelected({ ...selected, [row.id]: e.target.value })}>
        <option value="">不参与</option>{(choices[row.id] ?? []).map(run => <option key={run.id} value={run.id}>run {run.id} · 标注 {run.version}</option>)}</select></label>)}
      <label>测试集比例<input type="number" step="any" min="0.01" max="0.99" value={ratio} onChange={e => setRatio(Number(e.target.value))} /></label>
      <label>训练集内验证<select value={strategy} onChange={e => setStrategy(e.target.value as 'kfold' | 'loo')}><option value="kfold">KFold</option><option value="loo">留一法 LOO</option></select></label>
      {strategy === 'kfold' && <label>折数<input type="number" min={2} value={folds} onChange={e => setFolds(Number(e.target.value))} /></label>}
      {Math.round(runIds.length * (1 - ratio)) < 15 && <p>训练样品少于 15 个时，建议选择 LOO。</p>}
      <label>手动 LV（留空自动推荐）<input type="number" min={1} value={lv} onChange={e => setLV(e.target.value)} /></label>
      <button disabled={!schema || runIds.length < 4} onClick={() => void work(async () => {
        const row = await modeling.train({ task: 'regression', preprocess_run_ids: runIds, target_schema_id: schema, split_strategy: 'ks', test_ratio: ratio, cv_strategy: strategy, cv_folds: folds, seed: 17, ...(lv ? { n_components: Number(lv) } : {}) });
        if (row.status !== 'succeeded') throw new Error(JSON.stringify(row.error ?? '训练尚未成功，请重试。'));
        onOpenResults(row.run_id);
      })}>{busy ? '正在计算…' : '训练 PLS'}</button>
    </fieldset>
  </section>;
}
