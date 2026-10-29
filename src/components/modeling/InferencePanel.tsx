import { useEffect, useState } from 'react';
import type { DatasetRecord } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import { preprocessing } from '../preprocess/api.ts';
import { modeling, stageLabels, inferenceWarning, mapSource, clippingMessage, paletteGradient,
  type RegisteredModel, type InferenceResult, type ConcentrationMap } from './api.ts';
import { failureMessage } from './chart.ts';

type Choice = { id: string; version: string; recipe: string };
type Item = { cube: string; result?: InferenceResult; map?: ConcentrationMap; error?: string; mapError?: string };
export default function InferencePanel({ records, onClose }: { records: DatasetRecord[]; onClose(): void }) {
  const [models, setModels] = useState<RegisteredModel[]>([]), [model, setModel] = useState('');
  const [choices, setChoices] = useState<Record<string, Choice[]>>({}), [selected, setSelected] = useState<Record<string, string>>({});
  const [items, setItems] = useState<Item[]>([]), [domain, setDomain] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [progress, setProgress] = useState('');
  useEffect(() => {
    let live = true;
    void Promise.all([modeling.models(), Promise.all(records.map(async row => {
      const runs = await preprocessing.listRuns(row.id);
      const ready = await Promise.all(runs.filter(run => run.status === 'succeeded').map(run => preprocessing.getRun(run.id)));
      return [row.id, ready.map(run => ({ id: run.id, version: run.annotation_version_id, recipe: run.recipe_version_id }))] as const;
    }))]).then(([available, runs]) => { if (live) { setModels(available); setChoices(Object.fromEntries(runs)); } })
      .catch(failure => { if (live) setError(failureMessage(failure)); });
    return () => { live = false; };
  }, [records]);
  const chosen = models.find(row => row.id === model);
  const batch = async () => {
    setBusy(true); setError(''); setItems([]);
    const inputs = records.flatMap(row => {
      const run = choices[row.id]?.find(run => run.id === selected[row.id]);
      return run ? [{ cube: row.id, run }] : [];
    });
    const completed: Item[] = [];
    try {
      for (const [index, input] of inputs.entries()) {
        setProgress('正在推理 ' + (index + 1) + '/' + inputs.length);
        const item: Item = { cube: input.cube };
        try {
          item.result = await modeling.infer({ model_id: model, cube_id: input.cube,
            preprocess_run_id: input.run.id, annotation_version_id: input.run.version });
          try { item.map = await modeling.inferenceMap(item.result.id); } catch (failure) { item.mapError = failureMessage(failure); }
        } catch (failure) { item.error = failureMessage(failure); }
        completed.push(item); setItems([...completed]);
      }
      setProgress('已处理 ' + inputs.length + '/' + inputs.length);
    } finally { setBusy(false); }
  };
  return <section className="model-panel" aria-label="批量含量推理">
    <header><button disabled={busy} onClick={onClose}>返回回归工作台</button><h2>批量含量推理</h2></header>
    <p className="model-science-warning">{inferenceWarning}</p>
    <p>标定由注册时重建得出，非训练时实测值，可审计不可反证。</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}><legend>选择模型与样品</legend>
      <label>注册模型<select value={model} onChange={e => { setModel(e.target.value); setSelected({}); }}>
        <option value="">请选择</option>{models.map(row => <option key={row.id} value={row.id}>{row.name} v{row.version} · {stageLabels[row.stage]}</option>)}</select></label>
      {chosen && <p>固定训练量程 {chosen.applicability.y_min}–{chosen.applicability.y_max}；{chosen.quality_label}</p>}
      <p>每个样品选择一个已成功的预处理记录，标注版本随记录绑定。服务会核验配方版本与模型训练一致。</p>
      {records.map(row => <label key={row.id}>{displayName(row)}<select value={selected[row.id] ?? ''} onChange={e => setSelected({ ...selected, [row.id]: e.target.value })}>
        <option value="">不参与</option>{(choices[row.id] ?? []).map(run => <option key={run.id} value={run.id}>run {run.id} · 标注 {run.version} · 配方 {run.recipe}</option>)}</select></label>)}
      <button disabled={!model || !Object.values(selected).some(Boolean)} onClick={() => void batch()}>开始批量推理</button>
    </fieldset>
    <p role="status">{progress}</p>
    <label><input type="checkbox" checked={domain} onChange={e => setDomain(e.target.checked)} />显示适用性图（红＝任一特征越出训练范围；绿＝范围内）</label>
    {items.map(item => <article className="model-inference-item" key={item.cube}>
      <h3>{records.filter(row => row.id === item.cube).map(displayName)[0] ?? item.cube}</h3>
      {item.error && <p role="alert">{item.error}。若请求超时或中断，请先核对已有记录，避免重复提交。</p>}
      {item.result?.stats && <><strong>{item.result.stats.quality_label}</strong>
        <p className="model-science-warning">{item.result.stats.warning}</p>
        <p>{clippingMessage(item.result.stats)}</p>
        <dl><div><dt>像素预测均值</dt><dd>{item.result.stats.pixel_mean}</dd></div>
          <div><dt>样品均值谱预测</dt><dd>{item.result.stats.sample_prediction}</dd></div>
          <div><dt>前景像素数</dt><dd>{item.result.stats.n_foreground} / {item.result.stats.n_pixels}</dd></div>
          <div><dt>域外前景像素</dt><dd>{item.result.stats.out_of_domain_count}（{(item.result.stats.out_of_domain_fraction * 100).toFixed(1)}%）</dd></div>
          <div><dt>标准差 / 最小 / 最大</dt><dd>{item.result.stats.std} / {item.result.stats.min} / {item.result.stats.max}</dd></div></dl>
        <p>全局训练残差区间：{item.result.stats.residual_interval.mean} ± {item.result.stats.residual_interval.sd ?? '不适用'}（1 SD；{item.result.stats.residual_interval.low ?? '不适用'}–{item.result.stats.residual_interval.high ?? '不适用'}）</p>
        <p>分位数：{Object.entries(item.result.stats.quantiles).map(([key, value]) => key + '：' + value).join('；')}</p>
      </>}
      {item.mapError && <p role="alert">含量图不可用：{item.mapError}。统计结果保留。</p>}
      {item.map && <figure>
        <img className="model-concentration-image" src={mapSource(item.map, domain)} alt={domain ? '适用性图：红色域外，绿色范围内' : '固定训练量程的含量趋势图'} />
        <figcaption>{domain ? '红色：域外；绿色：范围内。' : '固定训练 Y 量程；全局残差 ±1 SD 见上方。'}浅灰：未标注；深灰：背景。统计仅含已标前景。</figcaption>
        <div className="model-colorbar" style={{ background: paletteGradient(item.map.palette) }} aria-label="固定训练量程彩色色带" />
        <div className="model-colorbar-labels"><span>{item.map.low}</span><span>{item.map.high}</span></div>
        <div className="model-residual-band" aria-label="全局训练残差一标准差带">全局残差带：{item.map.stats.residual_interval.mean} ± {item.map.stats.residual_interval.sd ?? '不适用'}（1 SD）</div>
      </figure>}
      {item.result && <p>推理记录：{item.result.id} · {item.result.status}</p>}
    </article>)}
  </section>;
}
