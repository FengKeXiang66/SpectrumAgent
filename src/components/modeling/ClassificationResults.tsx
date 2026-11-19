import type { BandSelection, ClassificationResult } from './api.ts';
import { FRAME, extent, mapValue, niceTicks, type ChartModel } from './chart.ts';
import { ChartCanvas } from './RegressionCharts.tsx';
import './modeling-skin.css';
import { ClassificationWorkbench } from './ClassificationTools.tsx';

export function bandSelectionChart(bands: BandSelection): ChartModel {
  const chart: ChartModel = { kind: 'curve', title: '各区间 RMSECV', status: 'unavailable', message: '区间评分不适用',
    xLabel: '区间编号', yLabel: 'RMSECV', xTicks: [], yTicks: [], notes: [bands.limitation],
    qualityLabel: null, definition: bands.definition, legend: [{ label: '区间 RMSECV', color: '#2563a6' }],
    lines: [], points: [], bars: [], markers: [] };
  const x = extent(bands.curve.map(point => point.index)), y = extent(bands.curve.map(point => point.rmsecv));
  if (!x || !y || !bands.curve.every(point => Number.isFinite(point.index) && Number.isFinite(point.rmsecv))) return chart;
  return { ...chart, status: 'ready', message: '',
    xTicks: niceTicks(x, 6, true).map(value => ({ at: mapValue(value, x, FRAME.left, FRAME.right)!, label: String(value) })),
    yTicks: niceTicks(y).map(value => ({ at: mapValue(value, y, FRAME.bottom, FRAME.top)!, label: String(value) })),
    lines: [{ color: '#2563a6', points: bands.curve.map(point => ({
      x: mapValue(point.index, x, FRAME.left, FRAME.right)!, y: mapValue(point.rmsecv, y, FRAME.bottom, FRAME.top)! })) }] };
}

export default function ClassificationResults({ result }: { result: ClassificationResult }) {
  if (result.evaluation) return <ClassificationWorkbench key={result.evaluation.evaluation_id} initial={result.evaluation} />;
  const confusion = result.confusion;
  if (!confusion) return <section aria-label="分类结果"><h3>分类结果 · {result.status}</h3><p role="status">该记录尚无分类训练产物；请先完成 PLS-DA 训练。</p></section>;
  const show = (value: number | null | undefined) => value ?? '不适用';
  const names = { oa: 'OA', aa: 'AA（macro recall）', kappa: 'Kappa', macro_f1: 'macro-F1' } as const;
  return <section className="classification-results" aria-label="分类结果">
    <h3>分类结果 · {result.status}</h3>
    <p role="note">历史协议 legacy_definition：保留当时指标与来源。未提供新版评价证据，不能据此认定为嵌套交叉验证；建议按新协议重新训练。</p>
    <p>run {result.run_id}；样品 {show(result.n_samples)} 个；已标像素 {show(result.n_pixels_used)} 个。</p>
    <p>GroupKFold · 图像代理组 · {result.confusion?.folds.length} 折；CV 最小建议 LV：{show(result.by_cv_min)}；RMSE 拐点建议 LV：{show(result.by_elbow)}；使用 LV：{show(result.selected_lv)}</p>
    <p>置信度阈值：{show(confusion.threshold.confidence_threshold)}（0 为不启用拒识）；不确定像素：{show(confusion.threshold.uncertain_pixels)}；进入评价的像素：{show(confusion.threshold.accepted_pixels)}。</p>
    <div className="classification-scopes">{(['pixel', 'sample'] as const).map(scope => {
      const score = confusion.scores[scope], summary = confusion.fold_summary[scope];
      return <section key={scope} aria-label={scope === 'pixel' ? '像素级分类指标' : '样品级分类指标'}>
        <h4>{scope === 'pixel' ? '像素级' : '样品级（多数投票）'}</h4>
        <dl>{(Object.keys(names) as (keyof typeof names)[]).map(name => <div key={name}>
          <dt>{names[name]}</dt><dd>{show(name === 'oa' || name === 'kappa' ? result.metrics[scope]?.[name] : score[name])}</dd>
        </div>)}</dl>
        <p>算子 {confusion.manifest.operator} v{confusion.manifest.operator_version} · run {result.run_id}</p>
        <table aria-label={scope + ' 每类 F1'}><thead><tr><th>类别索引</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
          <tbody>{score.per_class.map(row => <tr key={row.label}><th>{row.label}</th><td>{show(row.precision)}</td><td>{show(row.recall)}</td><td>{show(row.f1)}</td></tr>)}</tbody>
        </table>
        <table aria-label={scope + ' 混淆矩阵'}><caption>混淆矩阵：行=真实，列=预测；不确定像素已排除</caption>
          <thead><tr><th>真实 / 预测</th>{score.labels.map(label => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{score.labels.map((label, i) => <tr key={label}><th>{label}</th>{score.labels.map((predicted, j) => <td key={predicted}>{show(score.confusion[i]?.[j])}</td>)}</tr>)}</tbody>
        </table>
        <table aria-label={scope + ' 折间统计'}><caption>折间均值 ± 标准差</caption><thead><tr><th>指标</th><th>均值</th><th>标准差</th></tr></thead>
          <tbody>{(Object.keys(names) as (keyof typeof names)[]).map(name => <tr key={name}><th>{names[name]}</th><td>{show(summary[name].mean)}</td><td>{show(summary[name].std)}</td></tr>)}
            {summary.per_class.map(row => <tr key={row.label}><th>类别 {row.label} F1</th><td>{show(row.f1.mean)}</td><td>{show(row.f1.std)}</td></tr>)}
          </tbody>
        </table>
      </section>;
    })}</div>
    <details><summary>逐折分类指标</summary><pre>{JSON.stringify(confusion.folds, null, 2)}</pre></details>
    <details><summary>分类泄漏预检</summary><pre>{JSON.stringify(result.leak_report, null, 2)}</pre></details>
    <p>随机种子 {confusion.manifest.seed}；代码版本 {confusion.manifest.code_version ?? '不适用'}。</p>
    {result.bands && <section className="classification-bands" aria-label="iPLS 波段选择结果">
      <h3>iPLS 波段选择结果</h3>
      <p>扫描 {show(result.bands.n_intervals)} 个区间，选中 {show(result.bands.keep)} 个；扫描与对比 LV：{show(result.bands.lv)}。</p>
      <p>{result.bands.definition}。{result.bands.limitation}。</p>
      <table aria-label="被选区间（特征列）"><caption>被选区间（特征列，起止列号从 1 开始）</caption>
        <thead><tr><th>区间编号</th><th>起始列</th><th>终止列</th><th>RMSECV</th><th>折间标准差</th></tr></thead>
        <tbody>{result.bands.intervals.map(interval => <tr key={interval.index}>
          <th>{show(interval.index)}</th><td>{show(interval.start_col)}</td><td>{show(interval.end_col)}</td>
          <td>{show(interval.rmsecv)}</td><td>{show(interval.sd)}</td>
        </tr>)}</tbody>
      </table>
      <figure className="model-chart"><h4>各区间 RMSECV</h4><ChartCanvas chart={bandSelectionChart(result.bands)} />
        <figcaption>横轴为区间编号，纵轴为保存的交叉验证 RMSECV。</figcaption>
      </figure>
      <table aria-label="降维前后 OA/Kappa 对比"><caption>降维前后 OA/Kappa 对比（同一分组折与扫描 LV）</caption>
        <thead><tr><th>评价层级</th><th>特征范围</th><th>OA</th><th>Kappa</th></tr></thead>
        <tbody>{(['pixel', 'sample'] as const).flatMap(scope => (['full', 'selected'] as const).map(range => <tr key={scope + range}>
          <th>{scope === 'pixel' ? '像素级' : '样品级'}</th><td>{range === 'full' ? '全波段' : '所选区间'}</td>
          <td>{show(result.bands!.comparison[scope][range].oa)}</td><td>{show(result.bands!.comparison[scope][range].kappa)}</td>
        </tr>))}</tbody>
      </table>
    </section>}
  </section>;
}
