import { useEffect, useState } from 'react';
import { displayName, type DatasetReference } from '../components/datasets/types';
import { metricLabels, modeling, type Result, type RunRow } from '../components/modeling/api';
import ClassificationResults from '../components/modeling/ClassificationResults';
import { failureMessage } from '../components/modeling/chart';
import { preprocessing } from '../components/preprocess/api';
import type { RunSummary } from '../components/preprocess/types';
import '../components/modeling/modeling.css';

export default function S09({ records }: { records: DatasetReference[] }) {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [task, setTask] = useState<'all' | 'regression'>('regression');
  const [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [selectedRun, setSelectedRun] = useState(''), [result, setResult] = useState<Result | null>(null);
  const [detailLoading, setDetailLoading] = useState(false), [detailError, setDetailError] = useState('');
  const [datasetId, setDatasetId] = useState(''), [preprocessRuns, setPreprocessRuns] = useState<RunSummary[]>([]);
  const [preprocessLoading, setPreprocessLoading] = useState(false), [preprocessError, setPreprocessError] = useState('');
  useEffect(() => {
    let live = true;
    void modeling.runs().then(rows => { if (live) setRuns(rows); })
      .catch(failure => { if (live) setError(failureMessage(failure)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);
  useEffect(() => {
    let live = true;
    setResult(null); setDetailError('');
    if (!selectedRun) return;
    setDetailLoading(true);
    void modeling.run(selectedRun).then(row => { if (live) setResult(row); })
      .catch(failure => { if (live) setDetailError(failureMessage(failure)); })
      .finally(() => { if (live) setDetailLoading(false); });
    return () => { live = false; };
  }, [selectedRun]);
  useEffect(() => {
    let live = true;
    setPreprocessRuns([]); setPreprocessError(''); setPreprocessLoading(false);
    if (!datasetId) return;
    setPreprocessLoading(true);
    void preprocessing.listRuns(datasetId).then(rows => { if (live) setPreprocessRuns(rows); })
      .catch(failure => { if (live) setPreprocessError(failureMessage(failure)); })
      .finally(() => { if (live) setPreprocessLoading(false); });
    return () => { live = false; };
  }, [datasetId]);
  const regressionRuns = runs.filter(row => row.task === 'regression');
  const visibleRuns = task === 'regression' ? regressionRuns : runs;
  const classificationRuns = runs.filter(row => row.task === 'classification');
  return <section className="model-panel" aria-label="实验台账">
    <h2>实验台账</h2>
    <section aria-label="回归运行台账">
      <h3>回归运行</h3>
      <p>回归运行不含时间信息；预处理运行按数据集展示创建与结束时间。</p>
      <label>任务筛选<select value={task} onChange={event => setTask(event.target.value as 'all' | 'regression')}>
        <option value="all">全部</option><option value="regression">回归</option>
      </select></label>
      {loading && <p role="status">正在读取运行记录…</p>}
      {error && <pre role="alert">{error}</pre>}
      {!loading && !error && (visibleRuns.length ? <table aria-label="回归台账列表">
        <thead><tr><th>运行 ID</th><th>task</th><th>status</th></tr></thead>
        <tbody>{visibleRuns.map(row => <tr key={row.id}>
          <td><button title={row.id} onClick={() => setSelectedRun(row.id)}>{row.id.slice(0, 8)}</button></td><td>{row.task}</td><td>{row.status}</td>
        </tr>)}</tbody>
      </table> : <p>{task === 'regression' ? '暂无回归运行记录。请先在建模屏完成训练。' : '暂无运行记录。请先在建模屏完成训练。'}</p>)}
      {detailLoading && <p role="status">正在读取运行详情…</p>}
      {detailError && <pre role="alert">{detailError}</pre>}
      {result && result.task !== 'classification' && <section aria-label="运行详情"><h3>运行详情 · {(result.run_id ?? selectedRun).slice(0, 8)}</h3>
        <p>样品 {result.n_samples ?? '不适用'} 个；实际使用前景像素 {result.n_pixels_used ?? '不适用'} 个。</p>
        <p>使用 LV：{result.selected_lv ?? '不适用'}；交叉验证最小建议 LV：{result.best_lv ?? '不适用'}</p>
        {result.quality_label && <strong role="status">{result.quality_label}</strong>}
        <dl>{Object.entries(result.metrics ?? {}).map(([key, value]) => <div key={key}><dt>{metricLabels[key] ?? key}</dt><dd>{value ?? '不适用'}</dd></div>)}</dl>
        <details><summary>泄漏预检</summary><pre>{JSON.stringify(result.leak_report, null, 2)}</pre></details>
      </section>}
    </section>
    <section aria-label="分类运行台账"><h3>分类运行</h3><p>OA / Kappa 使用样品级指标；无分类训练产物时显示不适用。</p>
      {loading && <p role="status">正在读取分类运行记录…</p>}
      {error && <pre role="alert">{error}</pre>}
      {!loading && !error && (classificationRuns.length ? <table aria-label="分类台账列表">
        <thead><tr><th>run_id</th><th>task</th><th>status</th><th>OA</th><th>Kappa</th><th>LVs</th></tr></thead>
        <tbody>{classificationRuns.map(row => <tr key={row.id}>
          <td><button onClick={() => setSelectedRun(row.id)}>{row.id}</button></td><td>{row.task}</td><td>{row.status}</td>
          <td>{row.oa ?? '不适用'}</td><td>{row.kappa ?? '不适用'}</td><td>{row.lv ?? '不适用'}</td>
        </tr>)}</tbody>
      </table> : <p>暂无分类运行记录。请先在建模屏完成训练。</p>)}
      {selectedRun && result?.task === 'classification' && <ClassificationResults result={result} />}
    </section>
    <section aria-label="预处理运行台账"><h3>预处理运行</h3>
      <label>数据集<select value={datasetId} disabled={!records.length} onChange={event => setDatasetId(event.target.value)}>
        <option value="">请选择数据集</option>{records.map(record => <option key={record.id} value={record.id}>{displayName(record)}</option>)}
      </select></label>
      {!records.length ? <p>暂无已登记数据集。请先在数据屏登记数据。</p> : !datasetId ? <p>选择一个数据集查看其预处理运行</p> : <>
        {preprocessLoading && <p role="status">正在读取预处理运行…</p>}
        {preprocessError && <pre role="alert">{preprocessError}</pre>}
        {!preprocessLoading && !preprocessError && (preprocessRuns.length ? <table aria-label="预处理台账列表">
          <thead><tr><th>created_at</th><th>finished_at</th><th>status</th><th>b01_branch</th></tr></thead>
          <tbody>{preprocessRuns.map(row => <tr key={row.id}><td>{row.created_at}</td><td>{row.finished_at ?? '尚未结束'}</td><td>{row.status}</td><td>{row.b01_branch}</td></tr>)}</tbody>
        </table> : <p>该数据集暂无预处理运行。</p>)}
      </>}
    </section>
  </section>;
}
