import { useEffect, useState } from 'react';
import type { DatasetReference } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import { currentWorkspace } from '../preprocess/current';
import { modeling, stageLabels, inferenceWarning, mapSource, clippingMessage, paletteGradient,
  type RegisteredModel, type InferenceResult, type ConcentrationMap } from './api.ts';
import { failureMessage } from './chart.ts';

type Choice = { id: string; version: string };
type Item = { cube: string; result?: InferenceResult; map?: ConcentrationMap; error?: string; mapError?: string };
export default function InferencePanel({ records, onClose }: { records: DatasetReference[]; onClose(): void }) {
  const [models, setModels] = useState<RegisteredModel[]>([]), [model, setModel] = useState('');
  const [choices, setChoices] = useState<Record<string, Choice[]>>({}), [selected, setSelected] = useState<Record<string, string>>({});
  const [items, setItems] = useState<Item[]>([]), [domain, setDomain] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [progress, setProgress] = useState('');
  useEffect(() => {
    let live = true;
    void Promise.all([modeling.models(), currentWorkspace.state()]).then(([available, state]) => {
      if (live) { setModels(available.filter(row => row.applicability?.task === 'regression')); setChoices(Object.fromEntries(state.members.filter(row => records.some(record => record.id === row.cube_id)).map(row => [row.cube_id, row.annotation_id ? [{id:row.run_id ?? '',version:row.annotation_id}] : []]))); }
    })
      .catch(failure => { if (live) setError(failureMessage(failure)); });
    return () => { live = false; };
  }, [records]);
  const chosen = models.find(row => row.id === model);
  const snapshot = chosen?.training_protocol === 'sample_pls_foldwise_v1';
  const batch = async () => {
    setBusy(true); setError(''); setItems([]);
    const inputs = records.flatMap(row => {
      if (snapshot && selected[row.id] === 'whole_image') return [{ cube: row.id, run: null }];
      const run = choices[row.id]?.find(run => (run.id || `mask:${run.version}`) === selected[row.id] && (snapshot || !!run.id));
      return run ? [{ cube: row.id, run: run as Choice | null }] : [];
    });
    const completed: Item[] = [];
    try {
      for (const [index, input] of inputs.entries()) {
        setProgress('正在推理 ' + (index + 1) + '/' + inputs.length);
        const item: Item = { cube: input.cube };
        try {
          item.result = await modeling.infer({ model_id: model, cube_id: input.cube,
            ...(input.run ? { ...(snapshot ? {} : { preprocess_run_id: input.run.id }), annotation_version_id: input.run.version } : {}) });
          try { item.map = await modeling.inferenceMap(item.result.id); } catch (failure) { item.mapError = failureMessage(failure); }
        } catch (failure) { item.error = failureMessage(failure); }
        completed.push(item); setItems([...completed]);
      }
      setProgress('已处理 ' + inputs.length + '/' + inputs.length);
    } finally { setBusy(false); }
  };
  return <section className="model-panel ui-page" aria-label="批量含量推理">
    <header><button disabled={busy} onClick={onClose}>返回回归工作台</button><h2>批量含量推理</h2></header>
    <p className="model-science-warning">{inferenceWarning}</p>
    {chosen && <p>{snapshot ? '使用训练时保存的预处理与模型状态，不在预测数据上重新拟合。' : '历史模型标定由注册时重建；仍需有效标注及当前预处理引用。'}</p>}
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}><legend>选择模型与样品</legend>
      <label>注册模型<select value={model} onChange={e => { setModel(e.target.value); setSelected({}); }}>
        <option value="">请选择</option>{models.map(row => <option key={row.id} value={row.id}>{row.name} · {stageLabels[row.stage]}</option>)}</select></label>
      {chosen && <p>固定训练量程 {chosen.applicability.y_min}–{chosen.applicability.y_max}；{chosen.quality_label}</p>}
      <p>选择待预测样品。预测使用模型保存的预处理参数，当前配方调整不会修改已归档模型。</p>
      {snapshot && <p>新数据可直接选择整图预测，无需标注或预处理。整图统计包含背景，不能解释为目标物含量；需要限定区域时选择已有真实标注前景。</p>}
      {records.map(row => <label key={row.id}>{displayName(row)}<select value={selected[row.id] ?? ''} onChange={e => setSelected({ ...selected, [row.id]: e.target.value })}>
        <option value="">不参与</option>{snapshot && <option value="whole_image">整图预测（无需标注／预处理）</option>}
        {(choices[row.id] ?? []).filter(run => snapshot || !!run.id).map(run => <option key={run.version} value={run.id || `mask:${run.version}`}>使用已保存标注前景</option>)}</select></label>)}
      <button disabled={!model || !Object.values(selected).some(Boolean)} onClick={() => void batch()}>开始批量推理</button>
    </fieldset>
    <p role="status">{progress}</p>
    <label><input type="checkbox" checked={domain} onChange={e => setDomain(e.target.checked)} />显示适用性图（红＝任一特征越出训练范围；绿＝范围内）</label>
    {items.map(item => <article className="model-inference-item" key={item.cube}>
      <h3>{records.filter(row => row.id === item.cube).map(displayName)[0] ?? item.cube}</h3>
      {item.error && <p role="alert">{item.error}。若请求超时或中断，请先核对已有记录，避免重复提交。</p>}
      {item.result?.stats && <><strong>{item.result.stats.quality_label}</strong>
        <p className="model-science-warning">{item.result.stats.warning}</p>
        <p>标定来源：{item.result.stats.calibration_origin}；拟合范围：{item.result.stats.fit_scope ?? '未标注'}；
          溯源记录：{item.result.stats.calibration_provenance_present ? '有' : '无'}；run_id：{item.result.id}</p>
        <p>{clippingMessage(item.result.stats)}</p>
        <p>统计范围：{item.result.stats.statistics_scope === 'whole_image' ? '整图（包含背景）' : '已保存标注中的前景'}。</p>
        <dl><div><dt>像素预测均值</dt><dd>{item.result.stats.pixel_mean}</dd></div>
          <div><dt>{item.result.stats.statistics_scope === 'whole_image' ? '整图均值谱预测' : '前景均值谱预测'}</dt><dd>{item.result.stats.sample_prediction}</dd></div>
          <div><dt>参与统计的像素数</dt><dd>{item.result.stats.n_foreground} / {item.result.stats.n_pixels}</dd></div>
          <div><dt>域外前景像素</dt><dd>{item.result.stats.out_of_domain_count}（{(item.result.stats.out_of_domain_fraction * 100).toFixed(1)}%）</dd></div>
          <div><dt>标准差 / 最小 / 最大</dt><dd>{item.result.stats.std} / {item.result.stats.min} / {item.result.stats.max}</dd></div></dl>
        <p>全局训练残差区间：{item.result.stats.residual_interval.mean} ± {item.result.stats.residual_interval.sd ?? '不适用'}（1 SD；{item.result.stats.residual_interval.low ?? '不适用'}–{item.result.stats.residual_interval.high ?? '不适用'}）</p>
        <p>分位数：{Object.entries(item.result.stats.quantiles).map(([key, value]) => key + '：' + value).join('；')}</p>
      </>}
      {item.mapError && <p role="alert">含量图不可用：{item.mapError}。统计结果保留。</p>}
      {item.map && <figure>
        <img className="model-concentration-image" src={mapSource(item.map, domain)} alt={domain ? '适用性图：红色域外，绿色范围内' : '固定训练量程的含量趋势图'} />
        <figcaption>{domain ? '红色：域外；绿色：范围内。' : '固定训练 Y 量程；全局残差 ±1 SD 见上方。'}
          {item.map.stats.statistics_scope === 'whole_image' ? '本次统计整图，未排除背景。' : '浅灰：未标注；深灰：背景。统计仅含已标前景。'}</figcaption>
        <div className="model-colorbar" style={{ background: paletteGradient(item.map.palette) }} aria-label="固定训练量程彩色色带" />
        <div className="model-colorbar-labels"><span>{item.map.low}</span><span>{item.map.high}</span></div>
        <div className="model-residual-band" aria-label="全局训练残差一标准差带">全局残差带：{item.map.stats.residual_interval.mean} ± {item.map.stats.residual_interval.sd ?? '不适用'}（1 SD）</div>
      </figure>}
      {item.result && <p>推理记录：{item.result.id} · {item.result.status}</p>}
    </article>)}
  </section>;
}
