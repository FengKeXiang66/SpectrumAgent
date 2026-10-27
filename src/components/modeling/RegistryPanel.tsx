import { useEffect, useState } from 'react';
import { modeling, stageLabels, type RegisteredModel, type ModelStage } from './api.ts';
import { failureMessage } from './chart.ts';

export default function RegistryPanel({ onClose }: { onClose(): void }) {
  const [runs, setRuns] = useState<{ id: string; task: string; status: string }[]>([]);
  const [rows, setRows] = useState<RegisteredModel[]>([]), [run, setRun] = useState(''), [name, setName] = useState('');
  const [busy, setBusy] = useState(false), [registering, setRegistering] = useState(false), [error, setError] = useState('');
  const refresh = async () => { const [history, models] = await Promise.all([modeling.runs(), modeling.models()]); setRuns(history); setRows(models); };
  useEffect(() => { void refresh().catch(failure => setError(failureMessage(failure))); }, []);
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); await refresh(); } catch (failure) { setError(failureMessage(failure)); } finally { setBusy(false); setRegistering(false); }
  };
  return <section className="model-panel" aria-label="模型注册">
    <header><button disabled={busy} onClick={onClose}>返回回归工作台</button><h2>模型注册</h2></header>
    <p>将成功的回归记录注册为版本。生产版本采用显式切换，同一连续字段最多一个生产版本；旧版本回落为候选。</p>
    <p>标定由注册时重建得出，非训练时实测值，可审计不可反证。训练数据须仍可读取。</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}><legend>注册新版本</legend>
      <label>成功的回归记录<select value={run} onChange={e => setRun(e.target.value)}><option value="">请选择</option>
        {runs.filter(row => row.task === 'regression' && row.status === 'succeeded').map(row => <option key={row.id} value={row.id}>{row.id}</option>)}</select></label>
      <label>模型名称（留空自动生成）<input maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label>
      <button disabled={!run} onClick={() => { setRegistering(true); void work(async () => { await modeling.register(run, name.trim() || undefined); }); }}>
        {registering ? '正在计算标定…' : '注册模型版本'}</button>
    </fieldset>
    {registering && <p role="status">正在计算标定…需重读参与训练的全部数据，请稍候。</p>}
    <button disabled={busy} onClick={() => void work(refresh)}>刷新版本</button>
    {!rows.length && <p>尚无注册模型。</p>}
    <div className="model-registry-list">{rows.map(row => <article key={row.id}>
      <h3>{row.name} · v{row.version} <span className={'model-stage model-stage-' + row.stage}>{stageLabels[row.stage]}</span></h3>
      {row.quality_label && <strong>{row.quality_label}</strong>}
      <p>目标：{row.target_schema_id}；训练量程：{row.applicability.y_min}–{row.applicability.y_max}；特征数：{row.applicability.n_features}</p>
      <p>RPD：{row.metrics.rpd ?? '不适用'}；RMSEP：{row.metrics.rmsep ?? '不适用'}</p>
      <label>阶段<select disabled={busy} value={row.stage} onChange={e => void work(async () => { await modeling.stage(row.id, e.target.value as ModelStage); })}>
        {Object.entries(stageLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <details><summary>版本与适用域</summary><p>训练记录：{row.run_id}</p><p>数据指纹：{row.data_fingerprint}</p><p>配方版本：{row.applicability.recipe_version_id}</p><p>波长轴：{row.applicability.wavelength_axis_sha256}</p></details>
    </article>)}</div>
  </section>;
}
