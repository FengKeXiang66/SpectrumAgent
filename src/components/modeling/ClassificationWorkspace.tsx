import { useState, type ReactNode } from 'react';
import type { ClassificationEvaluation, EvaluationScore, Population, Scope } from './classification-types.ts';
import './classification-results.css';

export const displayMetric = (v: number | null | undefined, percent = false) => v == null ? '不适用' : percent ? (v * 100).toFixed(2) + '%' : v.toFixed(4);
const metricNames = { oa: 'OA 总体精度', aa: 'AA 平均召回率', kappa: 'Kappa', macro_f1: 'macro-F1' } as const;
export function Evidence({ evaluation, score }: { evaluation: ClassificationEvaluation; score?: EvaluationScore }) {
  return <details className="cr-evidence"><summary>查看数值出处</summary><dl>
    <dt>运行 / 评价</dt><dd><code>{evaluation.run_id} / {evaluation.evaluation_id}</code></dd>
    <dt>算子与定义</dt><dd>{evaluation.operator} v{evaluation.operator_version} · {evaluation.definition}</dd>
    <dt>标量证据</dt><dd>{score && Object.entries(score.metric_refs).map(([key, id]) =>
      <div key={id}><span>{key}</span><code>{id}</code></div>)}</dd>
  </dl></details>;
}
export function CurvePlot({ title, series, xLabel, yLabel, markers = [] }: { title: string; xLabel: string; yLabel: string;
  markers?: { x: number; name: string; color: string }[];
  series: { name: string; color: string; points: { x: number; y: number }[] }[] }) {
  const points = series.flatMap(s => s.points).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!points.length) return <p role="status">{title}：未获得可绘制结果</p>;
  const minX = Math.min(...points.map(p => p.x)), maxX = Math.max(...points.map(p => p.x));
  const minY = Math.min(...points.map(p => p.y)), maxY = Math.max(...points.map(p => p.y));
  const x = (v: number) => 52 + (v - minX) / (maxX - minX || 1) * 450;
  const y = (v: number) => 218 - (v - minY) / (maxY - minY || 1) * 182;
  return <figure className="cr-plot"><figcaption>{title}</figcaption><svg viewBox="0 0 540 264" role="img" aria-label={title}>
    <path d="M52 30 V218 H510" fill="none" stroke="#b5c2cc" />
    <text x="52" y="236">{minX.toFixed(2)}</text><text x="470" y="236">{maxX.toFixed(2)}</text>
    <text x="3" y="40">{maxY.toFixed(3)}</text><text x="3" y="218">{minY.toFixed(3)}</text>
    <text x="245" y="258">{xLabel}</text><text x="52" y="19">{yLabel}</text>
    {markers.map(m => <g key={m.name}><line x1={x(m.x)} x2={x(m.x)} y1="30" y2="218" stroke={m.color} strokeDasharray="4 3">
      <title>{m.name} = {m.x}</title></line></g>)}
    {series.map(s => <g key={s.name}><polyline fill="none" strokeWidth="2" stroke={s.color}
      points={s.points.map(p => x(p.x) + ',' + y(p.y)).join(' ')} />
      {s.points.length < 100 && s.points.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r="2.5" fill={s.color}>
        <title>{s.name} · {p.x} / {p.y}</title></circle>)}</g>)}
  </svg><div className="cr-legend">{series.map(s => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}{markers.map(m => <span key={m.name}>{m.name}={m.x}</span>)}</div></figure>;
}

export default function ClassificationWorkspace({ evaluation, tools, onInspect, onViewChange }: { evaluation: ClassificationEvaluation; tools?: ReactNode; onInspect?(scope: Scope, truth: number, predicted: number): void;
  onViewChange?(view: { population: Population; normalization: 'count' | 'row' | 'column' }): void }) {
  const [population, setPopulation] = useState<Population>('accepted');
  const [normalization, setNormalization] = useState<'count' | 'row' | 'column'>('count');
  const [classSort, setClassSort] = useState<'label' | 'f1' | 'recall'>('label');
  const names = new Map(evaluation.classes.map(c => [c.label, c.name]));
  const report = evaluation.populations[population], pixels = report.scores.pixel;
  const label = (n: number) => names.get(n) ?? String(n);
  return <div className="classification-results cr-workspace">
    <header className="cr-top"><div><h3>分类结果与指标</h3><p><code>{evaluation.run_id}</code> · 训练集 {evaluation.training_set_ref ?? '明确引用成员'}</p>
      <p>{evaluation.protocol === 'nested_group_cv' ? '嵌套分组交叉验证' : '探索性分组CV'} · {evaluation.group_kind === 'cube_proxy' ? '图像级代理组' : '物理样品组'}
        · {evaluation.operator} v{evaluation.operator_version} · {evaluation.feature_count} 个最终特征</p></div>
      <label>评价总体<select value={population} onChange={e => { const next = e.target.value as Population; setPopulation(next); onViewChange?.({ population: next, normalization }); }}>
        <option value="accepted">接纳子集（应用拒识）</option><option value="all_labeled">全体有效真值（argmax）</option></select></label></header>
    {!!evaluation.limitations.length && <aside className="cr-notice" role="note">{evaluation.limitations.map(v => <p key={v}>{v}</p>)}</aside>}
    {evaluation.class_support && <details className="cr-evidence"><summary>类别覆盖（不设每类最小组数）</summary>
      <div className="cr-table"><table><thead><tr><th>类别</th><th>图像 / 样品组数</th><th>有效真值像素</th></tr></thead>
        <tbody>{evaluation.class_support.classes.map(c => <tr key={c.label}><th>{c.name}</th><td>{c.groups}</td><td>{c.pixels.toLocaleString()}</td></tr>)}</tbody>
      </table></div></details>}
    <div className="cr-counts">{[
      ['图像 / 样品组', evaluation.n_images + ' / ' + evaluation.n_samples], ['有效真值像素', evaluation.n_pixels.toLocaleString()],
      ['接纳 / 拒识', pixels.accepted.toLocaleString() + ' / ' + pixels.rejected.toLocaleString()],
      ['覆盖率', displayMetric(pixels.coverage, true)], ['正确接纳比例', displayMetric(pixels.correct_acceptance_ratio, true)],
      ['最终模型LV', String(evaluation.lv.selected_lv)],
    ].map(([name, value]) => <div key={name}><span>{name}</span><strong>{value}</strong></div>)}</div>
    {(['pixel', 'sample'] as Scope[]).map(scope => {
      const score = report.scores[scope], stats = report.fold_summary[scope];
      return <section key={scope} className="cr-summary" aria-label={scope === 'pixel' ? '像素级核心指标' : '样品级核心指标'}>
        <h4>{scope === 'pixel' ? '像素级' : evaluation.group_kind === 'cube_proxy' ? '图像级多数投票' : '样品级多数投票'}
          <small> OOF合并 · {population === 'accepted' ? '接纳子集' : '全体'} · n={score.accepted}</small></h4>
        <div className="cr-metrics">{(Object.keys(metricNames) as (keyof typeof metricNames)[]).map(name => <article key={name}>
          <span>{metricNames[name]}</span><strong>{displayMetric(score[name], name === 'oa' || name === 'aa')}</strong>
          <small>折均值 {displayMetric(stats[name].mean, name === 'oa' || name === 'aa')} ± {displayMetric(stats[name].std, name === 'oa' || name === 'aa')} SD · 有效折 {stats[name].n_effective}</small>
        </article>)}</div><p>宏平均有效类别：AA {score.effective_classes?.aa ?? '未知'}；macro-F1 {score.effective_classes?.macro_f1 ?? '未知'}。无定义类别不补零。</p><Evidence evaluation={evaluation} score={score} />
      </section>;
    })}
    <nav className="cr-nav" aria-label="分类结果分区">{[['diagnosis', '分类诊断'], ['selection', '选模与波段'], ['detail', '逐折与样品'], ['tools', '空间、解释与导出'], ['provenance', '追溯']]
      .map(([id, name]) => <a key={id} href={'#cr-' + id}>{name}</a>)}</nav>
    <section id="cr-diagnosis" className="cr-panel"><h4>混淆矩阵与每类表现</h4>
      <div className="cr-actions"><label>矩阵数值<select value={normalization} onChange={e => { const next = e.target.value as typeof normalization; setNormalization(next); onViewChange?.({ population, normalization: next }); }}>
        <option value="count">计数</option><option value="row">真实类行占比</option><option value="column">预测类列占比</option></select></label>
        <label>类别排序<select value={classSort} onChange={e => setClassSort(e.target.value as typeof classSort)}>
          <option value="label">冻结顺序</option><option value="f1">F1从低到高</option><option value="recall">Recall从低到高</option></select></label></div>
      {(['pixel', 'sample'] as Scope[]).map(scope => {
        const score = report.scores[scope];
        const matrix = normalization === 'row' ? score.row_normalized : normalization === 'column' ? score.column_normalized : score.confusion;
        const rows = [...score.per_class].sort((a, b) => classSort === 'label' ? a.label - b.label : (a[classSort] ?? Infinity) - (b[classSort] ?? Infinity));
        return <div className="cr-diagnostic" key={scope}><h5>{scope === 'pixel' ? '像素级' : '多数投票级'} · 正确 {score.correct} / 误分 {score.incorrect}</h5>
          <div className="cr-table"><table><caption>行=真实；列=预测；拒识单独统计</caption>
            <thead><tr><th>真实＼预测</th>{score.labels.map(l => <th key={l}>{label(l)}</th>)}<th>合计</th></tr></thead>
            <tbody>{score.labels.map((l, i) => <tr key={l}><th>{label(l)}</th>{score.labels.map((p, j) =>
              <td key={p} style={{ background: i === j ? '#e7f3f7' : score.confusion[i][j] > 0 ? '#fdf4e3' : undefined }}
                title={'计数 ' + score.confusion[i][j] + '；行分母 ' + score.row_totals[i] + '；列分母 ' + score.column_totals[j]}>
                <button className="cr-cell-button" aria-label={label(l) + '预测为' + label(p) + '的' + scope + '对象'}
                  onClick={() => onInspect?.(scope, l, p)}>{normalization === 'count' ? matrix[i][j]?.toLocaleString() : displayMetric(matrix[i][j], true)}</button></td>)}<td>{score.row_totals[i]}</td></tr>)}
              <tr><th>合计</th>{score.column_totals.map((v, i) => <td key={i}>{v}</td>)}<td>{score.accepted}</td></tr></tbody></table></div>
          <div className="cr-table"><table><thead><tr><th>类别</th><th>Precision</th><th>Recall</th><th>F1</th><th>真实支持</th><th>预测数</th><th>拒识数</th></tr></thead>
            <tbody>{rows.map(c => <tr key={c.label}><th title={evaluation.classes[c.label]?.id}>{label(c.label)}</th>
              <td>{displayMetric(c.precision)}</td><td>{displayMetric(c.recall)}</td><td>{displayMetric(c.f1)}</td><td>{c.support}</td><td>{c.predicted_count}</td><td>{c.rejected_count}</td></tr>)}</tbody></table></div>
          <details><summary>主要混淆方向</summary>{score.top_errors.map(v => <p key={v.true_label + '-' + v.predicted_label}>{label(v.true_label)} → {label(v.predicted_label)}：{v.count} · 行占比 {displayMetric(v.row_fraction, true)}</p>)}</details>
        </div>;
      })}
    </section>
    <section id="cr-selection" className="cr-panel"><h4>潜变量与特征选择</h4>
      <p>CV最小建议 {evaluation.lv.best_lv}；容差建议（历史称拐点）{evaluation.lv.elbow_lv}；最终使用 {evaluation.lv.selected_lv}。</p>
      <CurvePlot title="内层 one-hot RMSECV vs 潜变量" xLabel="LV" yLabel="RMSECV"
        markers={[{ x: evaluation.lv.best_lv, name: 'CV最小', color: '#0e6e8c' }, { x: evaluation.lv.elbow_lv, name: '容差建议', color: '#a06a12' }, { x: evaluation.lv.selected_lv, name: '最终使用', color: '#17714a' }]}
        series={[{ name: 'RMSECV', color: '#0e6e8c', points: evaluation.lv.curve.map(p => ({ x: p.n_components, y: p.rmsecv })) },
          { name: '+1折SD', color: '#a06a12', points: evaluation.lv.curve.map(p => ({ x: p.n_components, y: p.rmsecv + p.sd })) }]} />
      <p>外层各折使用LV：{evaluation.fold_selected_lv.map(v => '折' + (v.fold_index + 1) + '=' + v.selected_lv).join(' · ')}。最终选模曲线不代表外层评价性能。</p>
      {evaluation.bands && <><CurvePlot title="iPLS 内层区间扫描" xLabel="区间" yLabel="RMSECV"
        series={[{ name: '区间RMSECV', color: '#0e6e8c', points: evaluation.bands.curve.map(p => ({ x: p.index, y: p.rmsecv })) }]} />
        <p>扫描LV {evaluation.bands.lv}；选中区间 {evaluation.bands.intervals.map(v => v.index).join('、')}；最终模型已使用所选特征。{evaluation.bands.limitation}</p>
        <div className="cr-table"><table><thead><tr><th>层级</th><th>路径</th><th>OA</th><th>Kappa</th></tr></thead><tbody>
          {(['pixel', 'sample'] as const).flatMap(s => (['full', 'selected'] as const).map(k =>
            <tr key={s + k}><th>{s}</th><td>{k}</td><td>{displayMetric(evaluation.bands!.comparison[s][k].oa, true)}</td><td>{displayMetric(evaluation.bands!.comparison[s][k].kappa)}</td></tr>))}
        </tbody></table></div></>}
    </section>
    <section id="cr-detail" className="cr-panel"><h4>逐折与样品明细</h4><div className="cr-table"><table><thead><tr><th>折</th><th>层级</th>{Object.values(metricNames).map(n => <th key={n}>{n}</th>)}</tr></thead>
      <tbody>{report.folds.flatMap(f => (['pixel', 'sample'] as Scope[]).map(s => <tr key={f.fold_index + s}><th>{f.fold_index + 1}</th><td>{s}</td>
        {(Object.keys(metricNames) as (keyof typeof metricNames)[]).map(n => <td key={n}>{displayMetric(f[s][n])}</td>)}</tr>))}</tbody></table></div>
      <details><summary>多数投票明细（全拒识对象仍保留）</summary><div className="cr-table"><table><thead><tr><th>组</th><th>真值主类</th><th>预测主类</th><th>真值/接纳数</th><th>主类比例</th></tr></thead>
        <tbody>{evaluation.sample_rows.map(r => <tr key={r.group}><td>{r.group}</td><td>{label(r.true_label)}</td><td>{r.predicted_label == null ? '拒识' : label(r.predicted_label)}</td><td>{r.n_true} / {r.n_accepted}</td><td>{displayMetric(r.majority_fraction, true)}</td></tr>)}</tbody></table></div></details>
      <details><summary>各图真值与排除范围</summary><div className="cr-table"><table><thead><tr><th>图像</th><th>组</th><th>有效真值</th><th>标注留白</th><th>标注不确定</th><th>已标无效谱</th></tr></thead><tbody>
        {evaluation.cubes.map(c => <tr key={c.cube_id}><th>{c.name}</th><td>{c.group}</td><td>{c.n_valid}</td><td>{c.unlabeled}</td><td>{c.annotation_uncertain}</td><td>{c.invalid_spectra}</td></tr>)}</tbody></table></div></details>
    </section>
    <section id="cr-tools">{tools}</section>
    <section id="cr-provenance" className="cr-panel"><h4>运行追溯</h4><p>种子 {evaluation.seed} · 代码 {evaluation.code_version ?? '未知'} · 用时 {evaluation.duration_s.toFixed(2)}秒</p>
      <p>评价 {evaluation.evaluation_id} · {evaluation.created_at}</p>
      <details><summary>结构化来源与状态</summary><pre>{JSON.stringify({ classes: evaluation.classes, cubes: evaluation.cubes, artifacts: evaluation.artifacts }, null, 2)}</pre></details>
    </section>
  </div>;
}
