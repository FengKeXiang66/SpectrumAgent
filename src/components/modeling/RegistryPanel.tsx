import { useEffect, useState } from 'react';
import { modeling, stageLabels, regressionProtocolLabel, type RegisteredModel, type ModelStage, type RunRow } from './api.ts';
import { failureMessage, type CoefficientInput } from './chart.ts';
import CoefficientChart from './CoefficientChart.tsx';

export default function RegistryPanel({ onClose }: { onClose(): void }) {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [rows, setRows] = useState<RegisteredModel[]>([]), [run, setRun] = useState(''), [name, setName] = useState('');
  const [busy, setBusy] = useState(false), [registering, setRegistering] = useState(false), [error, setError] = useState('');
  const [charts, setCharts] = useState<Record<string, CoefficientInput>>({});
  const refresh = async () => { const [history, models] = await Promise.all([modeling.runs(), modeling.models()]); setRuns(history); setRows(models); };
  useEffect(() => { void refresh().catch(failure => setError(failureMessage(failure))); }, []);
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); await refresh(); } catch (failure) { setError(failureMessage(failure)); } finally { setBusy(false); setRegistering(false); }
  };
  const loadCoefficients = async (row: RegisteredModel) => {
    setCharts(previous => ({ ...previous, [row.id]: { loading: true, qualityLabel: row.quality_label } }));
    try {
      const result = await modeling.coefficients(row.id);
      setCharts(previous => ({ ...previous, [row.id]: { result } }));
    } catch (failure) {
      setCharts(previous => ({ ...previous, [row.id]: { error: failureMessage(failure), qualityLabel: row.quality_label } }));
    }
  };
  return <section className="model-panel ui-page" aria-label="模型注册">
    <header><button disabled={busy} onClick={onClose}>返回回归工作台</button><h2>模型注册</h2></header>
    <p>成功的分类及回归训练可登记为模型。分类使用训练时冻结状态，仅开放实验和候选；对比基线不等于生产。</p>
    <p>新回归训练直接注册训练状态快照；历史回归仍使用注册时重建，需要原始数据可读。新旧训练协议的成绩不能直接排名。</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}><legend>注册模型</legend>
      <label>成功的训练记录<select value={run} onChange={e => setRun(e.target.value)}><option value="">请选择</option>
        {runs.filter(row => row.status === 'succeeded').map(row => <option key={row.id} value={row.id}>{row.task} · {row.id}{row.task === 'regression' ? ' · ' + regressionProtocolLabel(row.training_protocol) : ''}</option>)}</select></label>
      <label>模型名称（留空自动生成）<input maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label>
      <button disabled={!run} onClick={() => { setRegistering(true); void work(async () => { await modeling.register(run, name.trim() || undefined); }); }}>
        {registering ? '正在核验并注册…' : '注册模型'}</button>
    </fieldset>
    {registering && <p role="status">正在核验模型产物；历史回归还需重读训练数据，请稍候。</p>}
    <button disabled={busy} onClick={() => void work(refresh)}>刷新模型</button>
    {!rows.length && <p>尚无注册模型。</p>}
    <div className="model-registry-list">{rows.map(row => <article key={row.id}>
      <h3>{row.name} <span className={'model-stage model-stage-' + row.stage}>{stageLabels[row.stage]}</span></h3>
      {row.quality_label && <strong>{row.quality_label}</strong>}
      {row.task === 'classification' ? <><p>分类 · 特征数 {row.applicability.n_features} · 评价 {row.evaluation_id}</p>
        <p>样品OA {row.metrics.oa ?? '不适用'} · AA {row.metrics.aa ?? '不适用'} · Kappa {row.metrics.kappa ?? '不适用'} · macro-F1 {row.metrics.macro_f1 ?? '不适用'}</p></>
        : <><p>{regressionProtocolLabel(row.training_protocol)}</p><p>目标：{row.target_schema_id}；训练量程：{row.applicability.y_min}–{row.applicability.y_max}；特征数：{row.applicability.n_features}</p>
        <p>RPD：{row.metrics.rpd ?? '不适用'}；RMSEP：{row.metrics.rmsep ?? '不适用'}</p></>}
      <label>阶段<select disabled={busy} value={row.stage} onChange={e => void work(async () => { await modeling.stage(row.id, e.target.value as ModelStage); })}>
        {Object.entries(stageLabels).filter(([value]) => row.task !== 'classification' || value !== 'production').map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <details><summary>训练信息与适用域</summary><p>训练记录：{row.run_id}</p><p>数据指纹：{row.data_fingerprint}</p><p>配方输入：{row.applicability.recipe_version_id}</p><p>波长轴：{row.applicability.wavelength_axis_sha256}</p></details>
      {row.task !== 'classification' && <button disabled={busy || charts[row.id]?.loading === true} onClick={() => void loadCoefficients(row)}>查看波段系数</button>}
      {row.task === 'classification' && <p>分类系数、重要性和基线操作位于对应的结果页。</p>}
      {charts[row.id] && <CoefficientChart input={charts[row.id]} />}
    </article>)}</div>
  </section>;
}
