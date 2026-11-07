import { useEffect, useState } from 'react';
import { metricLabels, modeling, type Result, type Sweep } from '../components/modeling/api';
import { failureMessage, regressionCharts } from '../components/modeling/chart';
import RegressionCharts from '../components/modeling/RegressionCharts';
import ClassificationResults from '../components/modeling/ClassificationResults';
import '../components/modeling/modeling.css';

export default function S08({ runId, onOpen, onBackToList, onClose }: {
  runId: string | null; onOpen(id: string): void; onBackToList(): void; onClose(): void;
}) {
  const [runs, setRuns] = useState<{ id: string; task: string; status: string }[]>([]);
  const [listLoading, setListLoading] = useState(true), [listError, setListError] = useState('');
  const [result, setResult] = useState<Result | null>(null), [sweep, setSweep] = useState<Sweep | null>(null);
  const [chartsRequested, setChartsRequested] = useState(false), [chartLoading, setChartLoading] = useState(false);
  const [runError, setRunError] = useState(''), [sweepError, setSweepError] = useState('');
  useEffect(() => {
    let live = true;
    const beginCharts = () => {
      setResult(null); setSweep(null);
      setChartsRequested(true); setChartLoading(true); setRunError(''); setSweepError('');
    };
    const acceptResult = async (row: Result) => {
      if (!live) return;
      setResult(row);
      if (row.task === 'classification') { setChartLoading(false); return; }
      try {
        if (row.status === 'succeeded') {
          const curve = await modeling.sweep(row.run_id);
          if (live) setSweep(curve);
        } else setSweepError('该记录尚未成功，暂无曲线产物。');
      } catch (failure) {
        // A missing LV artifact must not hide the run's metrics or prediction plots.
        if (live) setSweepError(failureMessage(failure));
      } finally { if (live) setChartLoading(false); }
    };
    const load = async (id: string) => {
      beginCharts();
      try {
        const row = await modeling.run(id);
        await acceptResult(row);
      } catch (failure) {
        if (live) { setRunError(failureMessage(failure)); setChartLoading(false); }
      }
    };
    if (runId !== null) void load(runId);
    else {
      setResult(null); setSweep(null); setChartsRequested(false);
      setRuns([]); setListLoading(true); setListError('');
      void modeling.runs().then(rows => {
        if (live) setRuns(rows.filter(row => row.task === 'regression' || row.task === 'classification'));
      }).catch(failure => { if (live) setListError(failureMessage(failure)); })
        .finally(() => { if (live) setListLoading(false); });
    }
    return () => { live = false; };
  }, [runId]);
  return <section className="model-panel" aria-label="结果屏">
    <header><button onClick={onClose}>返回建模屏</button><h2>{runId === null ? '结果与指标' : result?.task === 'classification' ? '分类结果' : '回归结果'}</h2>
      {runId !== null && <button onClick={onBackToList}>返回列表</button>}
    </header>
    {runId === null ? <section aria-label="训练运行列表">
      {listLoading && <p role="status">正在读取运行记录…</p>}
      {listError && <pre role="alert">{listError}</pre>}
      {!listLoading && !listError && (runs.length ? <table aria-label="训练运行记录">
        <thead><tr><th>运行 ID</th><th>任务</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>{runs.map(row => <tr key={row.id}><td>{row.id}</td><td>{row.task}</td><td>{row.status}</td>
          <td><button onClick={() => onOpen(row.id)}>查看结果 {row.id}</button></td></tr>)}</tbody>
      </table> : <><p>暂无回归运行记录。请先在建模屏完成训练。</p><p>暂无分类运行记录。请先在建模屏完成训练。</p></>)}
    </section> : <>
      {runError && <pre role="alert">{runError}</pre>}
      {result?.task === 'classification' && <ClassificationResults result={result} />}
      {result && result.task !== 'classification' && <section aria-label="回归结果"><h3>回归结果 · {result.status}</h3><p>样品 {result.n_samples} 个；实际使用前景像素 {result.n_pixels_used} 个。</p>
        <p>交叉验证最小建议 LV：{result.best_lv ?? '不适用'}；使用 LV：{result.selected_lv ?? '不适用'}{sweep ? `；拐点法建议 LV：${sweep.elbow_lv}` : ''}</p>
        {result.quality_label && <strong role="status">{result.quality_label}</strong>}
        <dl>{Object.entries(metricLabels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{result.metrics?.[key] ?? '不适用'}</dd></div>)}</dl>
        <details><summary>划分与泄漏预检</summary><pre>{JSON.stringify(result.leak_report, null, 2)}</pre></details>
        {result.error != null && <pre role="alert">{JSON.stringify(result.error, null, 2)}</pre>}
      </section>}
      {chartsRequested && result?.task !== 'classification' && <RegressionCharts charts={regressionCharts({ result, sweep, runError, sweepError, loading: chartLoading })} />}
    </>}
  </section>;
}
