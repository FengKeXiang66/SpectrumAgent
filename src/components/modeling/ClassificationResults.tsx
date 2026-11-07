import type { ClassificationResult } from './api.ts';
import './modeling-skin.css';

export default function ClassificationResults({ result }: { result: ClassificationResult }) {
  const confusion = result.confusion;
  if (!confusion) return <section aria-label="分类结果"><h3>分类结果 · {result.status}</h3><p role="status">该记录尚无分类训练产物；请先完成 PLS-DA 训练。</p></section>;
  const show = (value: number | null | undefined) => value ?? '不适用';
  const names = { oa: 'OA', aa: 'AA（macro recall）', kappa: 'Kappa', macro_f1: 'macro-F1' } as const;
  return <section className="classification-results" aria-label="分类结果">
    <h3>分类结果 · {result.status}</h3>
    <p>run {result.run_id}；样品 {show(result.n_samples)} 个；已标像素 {show(result.n_pixels_used)} 个。</p>
    <p>GroupKFold · sample_id · {result.confusion?.folds.length} 折；CV 最小建议 LV：{show(result.by_cv_min)}；RMSE 拐点建议 LV：{show(result.by_elbow)}；使用 LV：{show(result.selected_lv)}</p>
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
  </section>;
}
