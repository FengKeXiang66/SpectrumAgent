import { useEffect, useState } from 'react';
import { annotations } from '../annotation/api.ts';
import type { LabelSchema, Project } from '../annotation/types.ts';
import type { DatasetReference } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import { modeling, type ImportResult, type Target } from './api.ts';
import { failureMessage } from './chart.ts';
import { currentWorkspace, type CurrentMember } from '../preprocess/current';
import RegistryPanel from './RegistryPanel.tsx';
import InferencePanel from './InferencePanel.tsx';
import './modeling.css';
import './modeling-skin.css';

export default function ModelPanel({ records, onOpenResults, onConfigureClassification }: { records: DatasetReference[]; onOpenResults(run: string): void; onConfigureClassification(): void }) {
  const [view, setView] = useState<'training' | 'registry' | 'inference'>('training');
  const [task, setTask] = useState<'regression' | 'classification'>('regression');
  const [projects, setProjects] = useState<Project[]>([]), [project, setProject] = useState('');
  const [schemas, setSchemas] = useState<LabelSchema[]>([]), [schema, setSchema] = useState('');
  const [cube, setCube] = useState(records[0]?.id ?? ''), [value, setValue] = useState('');
  const [targets, setTargets] = useState<Target[]>([]), [csv, setCSV] = useState(''), [imported, setImported] = useState<ImportResult | null>(null);
  const [members, setMembers] = useState<CurrentMember[]>([]), [selected, setSelected] = useState<Record<string,boolean>>({});
  const [strategy, setStrategy] = useState<'kfold' | 'loo'>('kfold'), [folds, setFolds] = useState(5), [ratio, setRatio] = useState(1 / 3), [lv, setLV] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); } catch (failure) { setError(failureMessage(failure)); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    let live = true;
    void Promise.all([annotations.projects(), currentWorkspace.state()]).then(([projects, state]) => {
      if (live) { setProjects(projects); setProject(projects[0]?.id ?? ''); setMembers(state.members.filter(row => records.some(record => record.id === row.cube_id))); setSelected(Object.fromEntries(records.map(row => [row.id,true]))); }
    }).catch(failure => { if (live) setError(failureMessage(failure)); });
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
  const selectedMembers = members.filter(member => selected[member.cube_id]);
  const runIds = selectedMembers.every(member => member.run_id) ? selectedMembers.map(member => member.run_id!) : [];
  if (view === 'registry') return <RegistryPanel onClose={() => setView('training')} />;
  if (view === 'inference') return <InferencePanel records={records} onClose={() => setView('training')} />;
  return <section className="model-panel ui-page" aria-label={task === 'regression' ? 'PLS 回归工作台' : 'PLS-DA 分类工作台'}>
    <header className="md-page-head"><div><h2>建模训练</h2>
      <p className="md-subtitle">分类通过 AI 统一配置预处理、寻优和训练；回归使用已处理的样品。</p></div>
      <span className="md-head-task">当前任务：{task === 'regression' ? 'PLS 回归' : 'PLS-DA 分类'}</span></header>
    <p role="status">{message}</p>{error && <pre role="alert">{error}</pre>}
    <div className="md-workbench">
    <div className="md-col-left">
    <section className="md-task-card"><h3>任务</h3>
      <nav aria-label="建模任务" className="md-seg"><button disabled={busy} aria-pressed={task === 'classification'} onClick={() => setTask('classification')}>PLS-DA 分类</button><button disabled={busy} aria-pressed={task === 'regression'} onClick={() => setTask('regression')}>PLS 回归</button></nav>
      <dl className="md-task-fields">
        <div><dt>当前样品</dt><dd>{task === 'regression' ? `${selectedMembers.length} 个` : '在对话中选择'}</dd></div>
        <div><dt>标签来源</dt><dd>{task === 'regression' ? '连续量测量值' : '已保存区域标注'}</dd></div>
        <div><dt>预处理</dt><dd>{task === 'regression' ? `${runIds.length} 项就绪` : '在训练方案中配置'}</dd></div>
      </dl>
    </section>
    {task === 'classification' ? <section><h3>统一分类训练</h3><p>人工标注和导入标注使用相同的预处理与 PLS-DA 流程。保存标注后，在对话中指定训练和测试图片，让 AI 比较预处理与潜变量，再训练和评价。</p><button className="modeling-primary" onClick={onConfigureClassification}>在对话中配置预处理与训练</button></section> : <>
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
    </fieldset></>}
    </div><div className="md-col-right">
    {task === 'classification' ? <section><h3>训练流程</h3><p>标注 → 训练方案 → Study 寻优 → 采用方案 → 独立测试 → 归档与推理</p><p>建议先指定测试图片，再仅用训练集寻优。没有测试集时，可先做探索性寻优。</p></section> : <>
    <fieldset disabled={busy}><legend>训练配置</legend>
      <button onClick={() => void work(async () => { const state = await currentWorkspace.state(); setMembers(state.members.filter(row => records.some(record => record.id === row.cube_id))); })}>刷新当前结果</button>
      {members.map(member => <label key={member.cube_id}><input type="checkbox" checked={!!selected[member.cube_id]} onChange={e => setSelected(old => ({...old,[member.cube_id]:e.target.checked}))} />{displayName(records.find(row => row.id === member.cube_id) ?? {id:member.cube_id,display_name:member.cube_id})} · {member.run_id ? '就绪' : '请先预处理'}</label>)}
      <p role="status">已选 {selectedMembers.length} 个样品 · 就绪 {runIds.length} 项</p>
      <label>测试集比例<input type="number" step="any" min="0.01" max="0.99" value={ratio} onChange={e => setRatio(Number(e.target.value))} /></label>
      <label>训练集内验证<select value={strategy} onChange={e => setStrategy(e.target.value as 'kfold' | 'loo')}><option value="kfold">KFold</option><option value="loo">留一法 LOO</option></select></label>
      {strategy === 'kfold' && <label>折数<input type="number" min={2} value={folds} onChange={e => setFolds(Number(e.target.value))} /></label>}
      {Math.round(runIds.length * (1 - ratio)) < 15 && <p>训练样品少于 15 个时，建议选择 LOO。</p>}
      <label>手动 LV（留空自动推荐）<input type="number" min={1} value={lv} onChange={e => setLV(e.target.value)} /></label>
      <button className="modeling-primary" disabled={!schema || runIds.length < 4} onClick={() => void work(async () => {
        const row = await modeling.train({ task: 'regression', preprocess_run_ids: runIds, target_schema_id: schema, split_strategy: 'ks', test_ratio: ratio, cv_strategy: strategy, cv_folds: folds, seed: 17, ...(lv ? { n_components: Number(lv) } : {}) });
        if (row.status !== 'succeeded') throw new Error(JSON.stringify(row.error ?? '训练尚未成功，请重试。'));
        onOpenResults(row.run_id);
      })}>{busy ? '正在计算…' : '训练 PLS'}</button>
    </fieldset>
    <section className="md-secondary-card"><h3>模型管理</h3>
      <div className="md-secondary-actions">
        <button disabled={busy} onClick={() => setView('registry')}>模型注册</button>
        <button disabled={busy} onClick={() => setView('inference')}>批量推理</button>
      </div>
      <p>训练完成后可在此注册候选模型，或对已注册模型执行批量推理。</p>
    </section></>}
    </div>
    </div>
  </section>;
}
