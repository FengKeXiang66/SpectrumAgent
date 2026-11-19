import { useEffect, useRef, useState } from 'react';
import { save } from '@tauri-apps/plugin-dialog';
import { modeling } from './api.ts';
import type { ClassificationAction, ClassificationEvaluation, Scope, Population } from './classification-types.ts';
import ClassificationWorkspace, { CurvePlot, displayMetric } from './ClassificationWorkspace.tsx';
import { failureMessage } from './chart.ts';
import { datasets } from '../datasets/api.ts';

type Point = { x: number; y: number };
type Ranking = { label: number; name: string; roc_auc: number | null; ap: number | null; roc: Point[]; pr: Point[]; positive: number; negative: number; undefined_reason: string | null };
type Curves = { evaluation_id: string; scope: Scope; classes: Ranking[]; macro_roc_auc: number | null; macro_ap: number | null;
  micro: Ranking; risk_coverage: { coverage: number; risk: number | null; accepted: number; rejected: number }[];
  histogram: { edges: number[]; correct: number[]; incorrect: number[] }; valid_roc_classes: number; valid_ap_classes: number;
  offset: number; total_classes: number; limitation: string };
type MapResult = { evaluation_id?: string; prediction_id?: string; cube_index?: number; width: number; height: number; original_width: number; original_height: number;
  level: number; tile_x: number; tile_y: number; png_base64: string; stats: { correct?: number; incorrect?: number; accepted: number; rejected: number; coverage: number | null }; limitation: string };
type Pixel = { evaluation_id: string; status: string; spectrum: number[] | null; wavelengths: number[]; wavelength_unit: string | null;
  processed_spectrum?: number[]; processed_axis?: number[] | null; region?: { count: number; total_pixels: number; mean: number[] | null; std: number[] | null; limitation: string } | null;
  row: number; column: number; true_label: number | null; predicted_label: number | null;
  items: { cube_index: number; row: number; column: number; true_label: number; predicted_label: number; confidence: number; fold_index: number }[]; total: number };
type Coefficients = { evaluation_id: string; features: { column: number; wavelength: number | null; unit: string | null }[];
  coefficients: number[][]; scale: string; limitation: string };
type Importance = { evaluation_id: string; status: string; top5: { feature_id: string; column: number; wavelength: number | null; unit: string | null; mean: number | null; std: number | null; metric_id: string }[];
  features: unknown[]; limitation: string };
type Interpretation = { evaluation_id: string; generator: string; cloud_called: boolean; cloud_error?: string; audit_id: string | null;
  token_usage: { total_tokens: number | null } | null; claims: { text: string; metric_id: string; run_id: string }[]; limitations: string[]; suggestions: string[] };
type ComparisonRow = { scope: string; population: string; name: string; difference: number | null; unit: string; metric_id: string; left_metric_id: string; right_metric_id: string; class_name?: string; fold_index?: number };
type Comparison = { comparable: boolean; differences: string[]; rows: ComparisonRow[]; per_class: ComparisonRow[]; folds: ComparisonRow[];
  paired: { population: string; scope: string; counts: number[][]; n: number }[]; evaluations: { evaluation_id: string; run_id: string; protocol: string; threshold: number }[]; limitation: string };
type Export = { export_id: string; filename: string; sha256: string; bytes: number };
type Job = { task_id: string; evaluation_id: string; kind: string; status: string; phase?: string; total: number; offset: number; limit: number; counts: Record<string, number>;
  result: unknown; error: string | null; items: { cube_id: string; status: string; prediction_id?: string; error?: string }[]; summary?: unknown };
type Choices = { baseline_evaluation_id: string | null; items: { evaluation_id: string; run_id: string; protocol: string; threshold: number; created_at: string }[] };
const palette = ['#0e6e8c', '#a06a12', '#17714a', '#9957b2', '#b83227', '#516879'];

export function ClassificationWorkbench({ initial }: { initial: ClassificationEvaluation }) {
  const [evaluation, setEvaluation] = useState(initial);
  const [view, setView] = useState<{ population: Population; normalization: 'count' | 'row' | 'column' }>({ population: 'accepted', normalization: 'count' });
  const [inspection, setInspection] = useState<{ scope: Scope; truth: number; predicted: number; ticket: number } | null>(null);
  return <ClassificationWorkspace key={evaluation.evaluation_id} evaluation={evaluation}
    onViewChange={setView}
    onInspect={(scope, truth, predicted) => setInspection({ scope, truth, predicted, ticket: Date.now() })}
    tools={<ClassificationTools key={evaluation.evaluation_id} evaluation={evaluation} onEvaluation={v => { setEvaluation(v); setView({ population: 'accepted', normalization: 'count' }); setInspection(null); }} inspection={inspection} view={view} />} />;
}

export default function ClassificationTools({ evaluation: ev, onEvaluation, inspection, view }: { evaluation: ClassificationEvaluation; onEvaluation(v: ClassificationEvaluation): void;
  view?: { population: Population; normalization: 'count' | 'row' | 'column' };
  inspection?: { scope: Scope; truth: number; predicted: number; ticket: number } | null }) {
  const [ranking, setRanking] = useState<Curves | null>(null), [scope, setScope] = useState<Scope>('pixel'), [offset, setOffset] = useState(0);
  const [map, setMap] = useState<MapResult | null>(null), [base, setBase] = useState<MapResult | null>(null), [pixel, setPixel] = useState<Pixel | null>(null);
  const [pixelQuery, setPixelQuery] = useState<Record<string, unknown>>({});
  const [cube, setCube] = useState(0), [layer, setLayer] = useState('prediction');
  const [level, setLevel] = useState(Math.max(0, Math.ceil(Math.log2(Math.max(...ev.cubes[0].shape.slice(0, 2)) / 256))));
  const [tileX, setTileX] = useState(0), [tileY, setTileY] = useState(0), [opacity, setOpacity] = useState(.85);
  const [hidden, setHidden] = useState<number[]>([]), [colors, setColors] = useState<Record<string, string>>({});
  const [coef, setCoef] = useState<Coefficients | null>(null), [importance, setImportance] = useState<Importance | null>(null);
  const [text, setText] = useState<Interpretation | null>(null), [comparison, setComparison] = useState<Comparison | null>(null);
  const [other, setOther] = useState(''), [name, setName] = useState('PLS-DA'), [modelId, setModelId] = useState('');
  const [choices, setChoices] = useState<Choices | null>(null), [choiceOffset, setChoiceOffset] = useState(0);
  const [truthVersion, setTruthVersion] = useState(''), [independent, setIndependent] = useState<ClassificationEvaluation | null>(null);
  const [cubeIds, setCubeIds] = useState(''), [threshold, setThreshold] = useState(ev.threshold);
  const [catalog, setCatalog] = useState<{ id: string; name: string }[]>([]);
  const [selectedCubes, setSelectedCubes] = useState<string[]>([]);
  const [region, setRegion] = useState({ row: 0, column: 0, end_row: 1, end_column: 1 });
  const [mapMode, setMapMode] = useState('pixel');
  const dragStart = useRef<{ row: number; column: number } | null>(null);
  const [job, setJob] = useState<Job | null>(null), [file, setFile] = useState<Export | null>(null), [format, setFormat] = useState('bundle');
  const [figure, setFigure] = useState('confusion-pixel');
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState<Record<string, boolean>>({});
  const live = useRef(true), sequence = useRef<Record<string, number>>({});
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const consume = (action: string, value: unknown) => {
    if (action === 'curves') setRanking(value as Curves);
    if (action === 'map') setMap(value as MapResult);
    if (action === 'base') setBase(value as MapResult);
    if (action === 'pixel') setPixel(value as Pixel);
    if (action === 'coefficients') setCoef(value as Coefficients);
    if (action === 'importance') setImportance(value as Importance);
    if (action === 'interpret') setText(value as Interpretation);
    if (action === 'compare') setComparison(value as Comparison);
    if (action === 'export') setFile(value as Export);
    if (action === 'choices') setChoices(value as Choices);
    if (action === 'evaluate_prediction') setIndependent(value as ClassificationEvaluation);
    if (action === 'threshold') onEvaluation(value as ClassificationEvaluation);
    if (action === 'register') { const m = value as { id: string; version: number }; setModelId(m.id); setNotice('已登记分类版本 v' + m.version + ' · ' + m.id); }
    if (action === 'baseline') setNotice((value as { baseline: boolean }).baseline ? '已登记为对比基线，未改变生产阶段。' : '已清除当前范围基线。');
  };
  const request = async (action: ClassificationAction, body: Record<string, unknown> = {}, target = action as string) => {
    if (action === 'pixel') { body = { limit: 50, ...body }; setPixelQuery(body); }
    const ticket = (sequence.current[target] ?? 0) + 1;
    sequence.current[target] = ticket;
    setBusy(v => ({ ...v, [target]: true })); setError('');
    try {
      const value = await modeling.classification<unknown>(ev.evaluation_id, action, body);
      if (!live.current || sequence.current[target] !== ticket) return;
      if (value && typeof value === 'object' && 'evaluation_id' in value && value.evaluation_id !== ev.evaluation_id && action !== 'threshold') throw new Error('响应评价身份不一致');
      if (value && typeof value === 'object' && 'task_id' in value) {
        const next = value as Job; setJob(next);
        if (next.status === 'succeeded' && next.result) consume(next.kind, next.result);
      }
      else consume(target, value);
    } catch (failure) { if (live.current && sequence.current[target] === ticket) setError(failureMessage(failure)); }
    finally { if (live.current && sequence.current[target] === ticket) setBusy(v => ({ ...v, [target]: false })); }
  };
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await modeling.classification<Job>(ev.evaluation_id, 'task', { task_id: job.task_id, limit: 50 });
        if (!active || !live.current) return;
        if (next.evaluation_id !== ev.evaluation_id) throw new Error('后台任务评价身份不一致');
        setJob(next);
        if (next.status === 'succeeded' && next.result) consume(next.kind, next.result);
        else if (next.status === 'failed') setError(next.error ?? '后台任务失败');
        else if (['queued', 'running'].includes(next.status)) timer = setTimeout(() => { void poll(); }, 1000);
      } catch (failure) { if (active) setError(failureMessage(failure)); }
    };
    timer = setTimeout(() => { void poll(); }, 500);
    return () => { active = false; clearTimeout(timer); };
  }, [job?.task_id, ev.evaluation_id]);
  const loadMap = (predictionId?: string) => {
    const body = { cube_index: cube, layer, level, tile_x: tileX, tile_y: tileY, hidden, colors, ...(predictionId ? { prediction_id: predictionId } : {}) };
    void request('map', body);
    if (!predictionId) void request('map', { ...body, layer: 'base' }, 'base');
  };
  const clearSpatial = () => {
    for (const key of ['map', 'base', 'pixel']) sequence.current[key] = (sequence.current[key] ?? 0)+1;
    setBusy(v => ({ ...v, map: false, base: false, pixel: false }));
    setMap(null); setBase(null); setPixel(null); dragStart.current = null;
  };
  useEffect(() => {
    if (inspection?.scope === 'pixel') void request('pixel', { cube_index: cube, true_label: inspection.truth, predicted_label: inspection.predicted, all_cubes: true, limit: 50 });
  }, [inspection?.ticket]);
  const download = async () => {
    if (!file) return;
    const destination = await save({ defaultPath: file.filename });
    if (!destination) return;
    try { const result = await modeling.downloadClassification(file.export_id, destination); setNotice('已保存 ' + result.bytes + ' 字节'); }
    catch (failure) { setError(failureMessage(failure)); }
  };
  const hasBase = !!base && !!map && !map.prediction_id && base.cube_index === map.cube_index && base.level === map.level
    && base.tile_x === map.tile_x && base.tile_y === map.tile_y;
  const backgroundBusy = !!job && ['queued', 'running'].includes(job.status)
    || ['importance', 'interpret', 'infer', 'export', 'evaluate_prediction'].some(k => busy[k]);
  const mapPosition = (event: { currentTarget: HTMLImageElement; clientX: number; clientY: number }) => {
    if (!map) return { row: 0, column: 0 };
    const rect = event.currentTarget.getBoundingClientRect(), scale = 2 ** map.level;
    return { column: Math.min(map.original_width-1, map.tile_x*256*scale+Math.max(0,Math.min(map.width-1,Math.floor((event.clientX-rect.left)/rect.width*map.width)))*scale),
      row: Math.min(map.original_height-1, map.tile_y*256*scale+Math.max(0,Math.min(map.height-1,Math.floor((event.clientY-rect.top)/rect.height*map.height)))*scale) };
  };
  return <>
    {error && <p className="cr-notice" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {job && <section className="cr-panel" aria-label="结果后台任务"><h4>后台任务 · {job.kind} · {job.status}</h4>
      {job.kind === 'inference' ? <p>图像 {job.total} · 成功 {job.counts.succeeded ?? 0} · 失败 {job.counts.failed ?? 0} · 待处理 {job.counts.pending ?? 0}</p> : <p>状态 {job.status} · 阶段 {job.phase ?? job.status} · 计算完成后结果显示在对应分区。</p>}
      {['queued', 'running'].includes(job.status) && <button onClick={() => void request('cancel', { task_id: job.task_id })}>取消剩余</button>}
      {job.kind === 'inference' && ['partial', 'failed', 'cancelled'].includes(job.status) && <button onClick={() => void request('retry', { task_id: job.task_id })}>重试失败与未完成图</button>}
      {job.items.map(i => <p key={i.cube_id}>{i.cube_id} · {i.status} {i.error}
        {i.prediction_id && <><button onClick={() => loadMap(i.prediction_id)}>查看预测图</button>
          <button disabled={!truthVersion || backgroundBusy} onClick={() => void request('evaluate_prediction', { prediction_id: i.prediction_id, annotation_version_id: truthVersion })}>绑定真值另建评价</button></>}</p>)}
      {job.total > 50 && <div className="cr-actions"><span>当前 {job.offset+1}–{Math.min(job.offset+job.items.length, job.total)} / {job.total}</span>
        <button disabled={job.offset === 0} onClick={() => void request('task', { task_id: job.task_id, offset: Math.max(0,job.offset-50), limit: 50 })}>上一页图像</button>
        <button disabled={job.offset+50 >= job.total} onClick={() => void request('task', { task_id: job.task_id, offset: job.offset+50, limit: 50 })}>下一页图像</button></div>}
      {job.summary != null && <details><summary>批量按像素汇总</summary><pre>{JSON.stringify(job.summary, null, 2)}</pre></details>}
    </section>}
    {independent && <section className="cr-panel"><h4>推理结果的冻结真值评价</h4><p>评价 {independent.evaluation_id} · 协议 {independent.protocol} · 本评价没有交叉验证折统计。</p>
      {independent.limitations.map(v => <p key={v}>{v}</p>)}<div className="cr-table"><table><thead><tr><th>层级</th><th>OA</th><th>AA</th><th>Kappa</th><th>macro-F1</th><th>覆盖率</th></tr></thead><tbody>
        {(['pixel', 'sample'] as const).map(s => { const v = independent.populations.accepted.scores[s]; return <tr key={s}><th>{s}</th><td>{displayMetric(v.oa, true)}</td><td>{displayMetric(v.aa, true)}</td><td>{displayMetric(v.kappa)}</td><td>{displayMetric(v.macro_f1)}</td><td>{displayMetric(v.coverage, true)}</td></tr>; })}</tbody></table></div>
      <details><summary>混淆矩阵、全体真值指标与完整证据</summary><pre>{JSON.stringify(independent.populations, null, 2)}</pre></details></section>}
    <section className="cr-panel"><h4>ROC / PR 与拒识诊断</h4><div className="cr-actions">
      <label>层级<select value={scope} onChange={e => setScope(e.target.value as Scope)}><option value="pixel">像素级</option><option value="sample">样品均值得分</option></select></label>
      <button disabled={busy.curves} onClick={() => void request('curves', { scope, offset, limit: 5 })}>计算并查看曲线</button>
      <button disabled={offset === 0} onClick={() => { const next = Math.max(0, offset - 5); setOffset(next); void request('curves', { scope, offset: next, limit: 5 }); }}>上一组类别</button>
      <button disabled={offset + 5 >= ev.classes.length} onClick={() => { const next = offset + 5; setOffset(next); void request('curves', { scope, offset: next, limit: 5 }); }}>下一组类别</button>
    </div>{ranking && <><p>macro ROC-AUC {displayMetric(ranking.macro_roc_auc)}（有效类别 {ranking.valid_roc_classes}） · macro AP {displayMetric(ranking.macro_ap)}（有效类别 {ranking.valid_ap_classes}） · micro ROC-AUC {displayMetric(ranking.micro.roc_auc)} · micro AP {displayMetric(ranking.micro.ap)}</p>
      <div className="cr-grid">{(['roc', 'pr'] as const).map(kind => <CurvePlot key={kind} title={kind === 'roc' ? 'OvR ROC' : 'OvR PR'} xLabel={kind === 'roc' ? 'FPR' : 'Recall'} yLabel={kind === 'roc' ? 'TPR' : 'Precision'}
        series={ranking.classes.map((c, i) => ({ name: c.name, color: palette[i % palette.length], points: c[kind] }))} />)}</div>
      <div className="cr-table"><table><thead><tr><th>类别</th><th>ROC-AUC</th><th>AP</th><th>正/负样本</th><th>状态</th></tr></thead><tbody>
        {ranking.classes.map(c => <tr key={c.label}><th>{c.name}</th><td>{displayMetric(c.roc_auc)}</td><td>{displayMetric(c.ap)}</td><td>{c.positive} / {c.negative}</td><td>{c.undefined_reason ?? '可计算'}</td></tr>)}</tbody></table></div>
      <CurvePlot title="像素风险与覆盖率" xLabel="Coverage" yLabel="接纳错误率" series={[{ name: '风险', color: '#b83227', points: ranking.risk_coverage.filter(p => p.risk != null).map(p => ({ x: p.coverage, y: p.risk! })) }]} /><p>{ranking.limitation}</p></>}
      {ranking && <CurvePlot title="像素最大得分分布（未校准）" xLabel="得分区间中点" yLabel="像素数" series={(['correct', 'incorrect'] as const).map((key, i) => ({ name: i ? '误分' : '正确', color: i ? '#b83227' : '#17714a', points: ranking.histogram[key].map((n, j) => ({ x: (ranking.histogram.edges[j]+ranking.histogram.edges[j+1])/2, y: n })) }))} />}
      <label>新拒识阈值<input type="number" min="0" max=".9999" step=".01" value={threshold} onChange={e => setThreshold(Number(e.target.value))} /></label>
      <button disabled={busy.threshold} onClick={() => void request('threshold', { threshold })}>生成派生评价快照</button>
    </section>
    <section className="cr-panel"><h4>OOF 空间结果与新数据预测图</h4><div className="cr-actions">
      <label>评价图像<select value={cube} onChange={e => { clearSpatial(); setCube(Number(e.target.value)); setTileX(0); setTileY(0); }} >{ev.cubes.map((c, i) => <option key={c.cube_id} value={i}>{c.name}</option>)}</select></label>
      <label>图层<select value={layer} onChange={e => { clearSpatial(); setLayer(e.target.value); }}>{[['prediction', '预测'], ['truth', '真值'], ['errors', '误分'], ['rejected', '拒识'], ['confidence', '未校准得分'], ['base', '灰度底图']].map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label>层级<input type="number" min="0" max="20" value={level} onChange={e => { clearSpatial(); setLevel(Number(e.target.value)); setTileX(0); setTileY(0); }} /></label>
      <label>瓦片X<input type="number" min="0" value={tileX} onChange={e => { clearSpatial(); setTileX(Number(e.target.value)); }} /></label><label>Y<input type="number" min="0" value={tileY} onChange={e => { clearSpatial(); setTileY(Number(e.target.value)); }} /></label>
      <button disabled={busy.map} onClick={() => loadMap()}>加载OOF瓦片</button>
      <label>叠加透明度<input type="range" min="0" max="1" step=".05" value={opacity} onChange={e => setOpacity(Number(e.target.value))} /></label>
      <label>查看方式<select value={mapMode} onChange={e => setMapMode(e.target.value)}><option value="pixel">点选光谱</option><option value="region">拖动框选谱统计</option></select></label>
    </div><div className="cr-legend">{ev.classes.map(c => <label key={c.id}><input type="checkbox" checked={!hidden.includes(c.label)} onChange={e => setHidden(v => e.target.checked ? v.filter(n => n !== c.label) : [...v, c.label])} />{c.name}
      <input type="color" value={colors[String(c.label)] ?? c.color} onChange={e => setColors(v => ({ ...v, [c.label]: e.target.value }))} /></label>)}</div>
      {map && <><div className="cr-map-stage" style={{ width: Math.min(560, 560*map.width/map.height) }}>{hasBase && base && <img className="cr-map" src={'data:image/png;base64,' + base.png_base64} alt="原始灰度底图" />}
        <img className={hasBase ? 'cr-map cr-overlay' : 'cr-map'} style={{ opacity: hasBase ? opacity : 1 }}
          src={'data:image/png;base64,' + map.png_base64} alt="分类结果瓦片" draggable={false}
          onPointerDown={e => { if (mapMode === 'region' && !map.prediction_id) { dragStart.current = mapPosition(e); e.currentTarget.setPointerCapture(e.pointerId); } }}
          onPointerUp={e => {
            const start = dragStart.current; dragStart.current = null;
            if (!start || mapMode !== 'region' || map.prediction_id) return;
            const end = mapPosition(e), scale = 2 ** map.level;
            const next = { row: Math.min(start.row, end.row), column: Math.min(start.column, end.column),
              end_row: Math.min(map.original_height, Math.max(start.row, end.row)+scale),
              end_column: Math.min(map.original_width, Math.max(start.column, end.column)+scale) };
            setRegion(next); void request('pixel', { cube_index: cube, ...next });
          }} onClick={e => {
            if (map.prediction_id || mapMode !== 'pixel') return;
            void request('pixel', { cube_index: cube, ...mapPosition(e), limit: 50 });
          }} /><div className="cr-map-scale" aria-label="像素比例尺" style={{ width: Math.max(1, Math.floor(map.width/5))/map.width*100+'%' }}>
            <span>{Math.max(1, Math.floor(map.width/5))*2**map.level} px</span></div></div>
        <p>当前图接纳 {map.stats.accepted} / 拒识 {map.stats.rejected} · 覆盖率 {displayMetric(map.stats.coverage, true)}{map.stats.incorrect != null && ' · 误分 ' + map.stats.incorrect}</p><p>{map.limitation}</p></>}
      <div className="cr-actions">{ev.populations.accepted.scores.pixel.top_errors.slice(0, 5).map(e => <button key={e.true_label + '-' + e.predicted_label}
        onClick={() => void request('pixel', { cube_index: cube, true_label: e.true_label, predicted_label: e.predicted_label, all_cubes: true, limit: 50 })}>
        {ev.classes[e.true_label].name} → {ev.classes[e.predicted_label].name} 下钻</button>)}</div>
      {inspection?.scope === 'sample' && <details open><summary>矩阵筛选的多数投票组</summary>{ev.sample_rows.filter(r => r.true_label === inspection.truth && r.predicted_label === inspection.predicted).map(r => <p key={r.group}>组{r.group} · 真值{r.n_true} · 接纳{r.n_accepted}</p>)}</details>}
      <details><summary>区域谱统计</summary>{(['row', 'column', 'end_row', 'end_column'] as const).map(key => <label key={key}>{key}<input type="number" min="0" value={region[key]} onChange={e => setRegion(v => ({ ...v, [key]: Number(e.target.value) }))} /></label>)}
        <button onClick={() => void request('pixel', { cube_index: cube, ...region })}>统计框选范围</button></details>
      {pixel && <><p>位置 {pixel.row},{pixel.column} · {pixel.status} · 真实 {pixel.true_label == null ? '未评价' : ev.classes[pixel.true_label].name} · 预测 {pixel.predicted_label == null ? '未评价' : pixel.predicted_label < 0 ? '拒识' : ev.classes[pixel.predicted_label].name}</p>
        {pixel.spectrum && <CurvePlot title="当前像素原始反射谱" xLabel={pixel.wavelength_unit ?? '波段（单位未知）'} yLabel="光谱值" series={[{ name: '原始谱', color: '#0e6e8c', points: pixel.spectrum.map((v, i) => ({ x: pixel.wavelengths[i] ?? i + 1, y: v })) }]} />}
        {pixel.processed_spectrum && <CurvePlot title="对应外层折的预处理谱" xLabel={pixel.processed_axis ? pixel.wavelength_unit ?? '波长单位未知' : '变换后特征'} yLabel="变换值" series={[{ name: '冻结预处理', color: '#17714a', points: pixel.processed_spectrum.map((v, i) => ({ x: pixel.processed_axis?.[i] ?? i + 1, y: v })) }]} />}
        {pixel.region && <><p>选区总像素 {pixel.region.total_pixels} · 评价像素 {pixel.region.count} · {pixel.region.limitation}</p>
          {pixel.region.mean && <CurvePlot title="选区评价像素平均谱" xLabel={pixel.wavelength_unit ?? '波段'} yLabel="平均光谱" series={[{ name: '均值', color: '#0e6e8c', points: pixel.region.mean.map((v, i) => ({ x: pixel.wavelengths[i] ?? i+1, y: v })) }]} />}
          {pixel.region.std && <CurvePlot title="选区评价像素谱标准差" xLabel={pixel.wavelength_unit ?? '波段'} yLabel="光谱SD" series={[{ name: '标准差（非置信区间）', color: '#a06a12', points: pixel.region.std.map((v, i) => ({ x: pixel.wavelengths[i] ?? i+1, y: v })) }]} />}</>}
        <details><summary>筛选对象 {pixel.total} 个（每页50条）</summary>
          <button disabled={Number(pixelQuery.offset ?? 0) === 0} onClick={() => void request('pixel', { ...pixelQuery, offset: Math.max(0,Number(pixelQuery.offset ?? 0)-50) })}>前50个对象</button>
          <button disabled={Number(pixelQuery.offset ?? 0)+50 >= pixel.total} onClick={() => void request('pixel', { ...pixelQuery, offset: Number(pixelQuery.offset ?? 0)+50 })}>后50个对象</button>
          {pixel.items.map(p => <p key={p.cube_index + '-' + p.row + '-' + p.column}><button onClick={() => { clearSpatial(); setCube(p.cube_index); void request('pixel', { cube_index: p.cube_index, row: p.row, column: p.column }); }}>图{p.cube_index + 1} · {p.row},{p.column}</button> · 真值 {p.true_label} · 预测 {p.predicted_label} · 得分 {displayMetric(p.confidence)} · 外层折 {p.fold_index + 1}</p>)}</details></>}
    </section>
    <section className="cr-panel"><h4>分类系数与特征重要性</h4><button onClick={() => void request('coefficients')}>读取分类系数</button>
      <button disabled={backgroundBusy} onClick={() => void request('importance', { repeats: 5 })}>计算完整留出置换重要性（5次）</button>
      {coef && <><CurvePlot title="分类别有符号系数" xLabel={coef.features[0]?.unit ?? '特征列/成分'} yLabel="系数"
        series={coef.coefficients.map((ys, i) => ({ name: ev.classes[i].name, color: palette[i % palette.length], points: ys.map((v, j) => ({ x: coef.features[j].wavelength ?? coef.features[j].column, y: v })) }))} /><p>{coef.limitation}</p></>}
      {importance && <><p>{importance.status} · {importance.limitation}</p><div className="cr-table"><table><thead><tr><th>Top5特征</th><th>macro-F1下降</th><th>折SD</th><th>出处</th></tr></thead><tbody>{importance.top5.map(r => <tr key={r.feature_id}><th>{r.wavelength != null ? r.wavelength + ' ' + (r.unit ?? '单位未知') : '特征' + r.column}</th><td>{displayMetric(r.mean)}</td><td>{displayMetric(r.std)}</td><td><code>{r.metric_id}</code></td></tr>)}</tbody></table></div>
        <details><summary>完整结果</summary><pre>{JSON.stringify(importance.features, null, 2)}</pre></details></>}
    </section>
    <section className="cr-panel"><h4>登记模型与批量推理</h4><div className="cr-actions"><label>名称<input value={name} onChange={e => setName(e.target.value)} /></label>
      <button onClick={() => void request('register', { name })}>登记分类版本</button><button onClick={() => void request('baseline', { ...(modelId ? { model_id: modelId } : { name }) })}>设为对比基线</button>
      <button onClick={() => void request('baseline', { ...(modelId ? { model_id: modelId } : { name }), clear: true })}>清除当前范围基线</button></div>
      <button onClick={() => { void datasets.catalog(100, 0).then(page => { if (live.current) setCatalog(page.datasets.filter(c => c.available).map(c => ({ id: c.id, name: c.display_name }))); }).catch(f => setError(failureMessage(f))); }}>选择已导入图像</button>
      {!!catalog.length && <div className="cr-table">{catalog.map(c => <label key={c.id}><input type="checkbox" checked={selectedCubes.includes(c.id)}
        onChange={e => setSelectedCubes(v => e.target.checked ? [...v, c.id] : v.filter(id => id !== c.id))} />{c.name}</label>)}</div>}
      <details><summary>通过标识指定其他图像</summary><label>图像标识（空格、逗号或换行分隔）<textarea value={cubeIds} onChange={e => setCubeIds(e.target.value)} /></label></details>
      <button disabled={backgroundBusy} onClick={() => void request('infer', { ...(modelId ? { model_id: modelId } : { name }), cube_ids: [...new Set([...selectedCubes, ...cubeIds.split(/[\s,，]+/).filter(Boolean)])], threshold })}>提交整图分类推理</button>
      <label>冻结真值（可选，须与单图匹配）<select value={ev.cubes.some(c => c.annotation_version_id === truthVersion) ? truthVersion : ''} onChange={e => setTruthVersion(e.target.value)}><option value="">未绑定真值</option>{ev.cubes.map(c => <option key={c.cube_id} value={c.annotation_version_id}>{c.name} · 当前评价冻结版</option>)}</select></label>
      <details><summary>指定其他冻结真值标识</summary><input aria-label="其他冻结真值标识" value={truthVersion} onChange={e => setTruthVersion(e.target.value)} /></details>
      <p>采用冻结变换；无真值仅报告预测分布，未校准得分不代表正确概率。</p>
    </section>
    <section className="cr-panel"><h4>实验对比与引用解读</h4>
      <button onClick={() => { setChoiceOffset(0); void request('choices', { limit: 50, offset: 0 }); }}>选择实验与当前基线</button>
      {choices && <><label>已有评价<select value={other} onChange={e => setOther(e.target.value)}><option value="">选择评价</option>{choices.items.map(c => <option key={c.evaluation_id} value={c.evaluation_id}>{c.evaluation_id === choices.baseline_evaluation_id ? '当前基线 · ' : ''}{c.created_at.slice(0,16)} · {c.protocol} · 阈值{c.threshold} · {c.evaluation_id.slice(0,8)}</option>)}</select></label>
        <button disabled={!choices.baseline_evaluation_id} onClick={() => setOther(choices.baseline_evaluation_id ?? '')}>采用当前基线</button>
        <button disabled={choiceOffset === 0} onClick={() => { const next = Math.max(0, choiceOffset-50); setChoiceOffset(next); void request('choices', { limit: 50, offset: next }); }}>前50条</button>
        <button disabled={choices.items.length < 50} onClick={() => { const next = choiceOffset+50; setChoiceOffset(next); void request('choices', { limit: 50, offset: next }); }}>后50条</button></>}
      <label>比较评价ID<input value={other} onChange={e => setOther(e.target.value)} /></label>
      <button onClick={() => void request('compare', { comparison_id: other })}>核验可比性并比较</button><button onClick={() => void request('interpret', { ...(other ? { comparison_id: other } : {}) })}>生成本地事实摘要</button>
      <button disabled={backgroundBusy} onClick={() => void request('interpret', { cloud: true, ...(other ? { comparison_id: other } : {}) })}>云端引用解读</button>
      {comparison && <><p>{comparison.comparable ? '可比' : '不可比：' + comparison.differences.join('、')} · {comparison.limitation}</p><div className="cr-table"><table><thead><tr><th>层级/总体</th><th>指标</th><th>当前减对比</th><th>出处</th></tr></thead><tbody>
        {comparison.rows.map(r => <tr key={r.metric_id}><td>{r.scope}/{r.population}</td><th>{r.name}</th><td>{r.difference == null ? '不适用' : r.unit === 'percentage_points' ? (r.difference * 100).toFixed(3) + '个百分点' : displayMetric(r.difference)}</td><td><code>{r.metric_id}</code></td></tr>)}</tbody></table></div>
        <details><summary>双方身份与逐类、逐折差异</summary>{comparison.evaluations?.map(e => <p key={e.evaluation_id}><code>{e.run_id} / {e.evaluation_id}</code> · {e.protocol} · 阈值 {e.threshold}</p>)}
          <div className="cr-table"><table><thead><tr><th>层级/总体</th><th>类别/折</th><th>指标</th><th>差值（原单位）</th><th>差值 / 双方出处</th></tr></thead><tbody>
            {[...(comparison.per_class ?? []), ...(comparison.folds ?? [])].map(r => <tr key={r.metric_id}><td>{r.scope}/{r.population}</td><td>{r.class_name ?? '折'+((r.fold_index ?? 0)+1)}</td><th>{r.name}</th><td>{displayMetric(r.difference)}</td><td><code>{r.metric_id}<br />{r.left_metric_id}<br />{r.right_metric_id}</code></td></tr>)}
          </tbody></table></div></details>
        <details><summary>同对象正确/误分/拒识配对计数</summary>{comparison.paired?.map(p => <div key={p.scope+p.population}><p>{p.scope}/{p.population} · n={p.n}；行当前、列对比，顺序：误分、正确、拒识。</p><table><tbody>{p.counts.map((r, i) => <tr key={i}>{r.map((n,j) => <td key={j}>{n}</td>)}</tr>)}</tbody></table></div>)}</details></>}
      {text && <><h5>已证实事实</h5>{text.claims.map(c => <p key={c.metric_id}>{c.text}<br /><code>{c.metric_id}</code></p>)}<h5>局限</h5>{text.limitations.map(v => <p key={v}>{v}</p>)}<h5>建议</h5>{text.suggestions.map(v => <p key={v}>{v}</p>)}<p>待验证假说：未获得带来源假说。</p>
        <p>生成方式 {text.generator} · 云端 {text.cloud_called ? '已调用' : '未生成云端解读'} · token {text.token_usage?.total_tokens ?? '未知'} · 审计 {text.audit_id ?? '无云端调用'} {text.cloud_error}</p></>}
    </section>
    <section className="cr-panel"><h4>图件、数据与报告导出</h4><div className="cr-actions"><label>格式<select value={format} onChange={e => setFormat(e.target.value)}>
      {['bundle', 'html', 'pdf', 'docx', 'json', 'csv', 'png', 'svg'].map(v => <option key={v} value={v}>{v === 'bundle' ? '完整报告及图件包' : v.toUpperCase()}</option>)}</select></label>
      {['png', 'svg'].includes(format) && <label>图件<select value={figure} onChange={e => setFigure(e.target.value)}>
        {['confusion-pixel', 'confusion-sample', 'lv', ...(ev.bands ? ['ipls'] : []), 'risk-coverage', 'coefficients', ...(importance?.top5.length ? ['importance'] : []), 'current-map', ...ev.cubes.map((_, i) => 'oof-map-'+i),
          ...(['pixel', 'sample'] as const).flatMap(s => Array.from({ length: Math.ceil(ev.classes.length/5) }, (_, i) => [s+'-roc-'+i*5, s+'-pr-'+i*5]).flat())].map(v => <option key={v} value={v}>{v}</option>)}</select></label>}
      <button disabled={backgroundBusy} onClick={() => void request('export', { format, figure, ...view, scope, cube_index: cube, layer, level, tile_x: tileX, tile_y: tileY,
        hidden, colors, opacity, ...(other ? { comparison_id: other } : {}), ...(map?.prediction_id ? { prediction_id: map.prediction_id } : {}) })}>生成导出产物</button>{file && <button onClick={() => void download()}>保存 {file.filename}</button>}</div>
      {file && <p>{file.bytes.toLocaleString()}字节 · SHA256 <code>{file.sha256}</code> · 快照 {ev.evaluation_id}</p>}
    </section>
  </>;
}
