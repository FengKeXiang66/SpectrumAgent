import type { DatasetRecord } from '../components/datasets/types';
import type { Snapshot, Phase } from '../status';
import '../components/modeling/modeling.css';
import './light-screens.css';

const PHASE_TITLE: Record<Phase, string> = { Starting: '正在启动', Ready: '已就绪', Failed: '失败', Stopping: '正在关闭' };

export default function S02({ records, runs, loading, error, status, onOpenData, onOpenRun, onContinueAnnotation }: {
  records: DatasetRecord[]; runs: { id: string; task: string; status: string }[]; loading: boolean; error: string;
  status: Pick<Snapshot, 'phase' | 'generation_id'>;
  onOpenData(): void; onOpenRun(id: string): void; onContinueAnnotation(): void;
}) {
  return <section className="model-panel" aria-label="工作台">
    <h2>工作台</h2>
    <div className="model-registry-list light-screen-cards">
      <article aria-label="数据集概览"><h3>数据集</h3><p>已登记 {records.length} 个数据集。</p><button onClick={onOpenData}>查看全部</button></article>
      <article aria-label="回归运行概览"><h3>回归运行</h3>
        {loading ? <p role="status">正在读取回归运行记录…</p> : error ? <p role="alert">{error}</p> : <>
          <p>共 {runs.length} 条回归运行。</p>
          {runs.length ? <ul aria-label="最近回归运行">{runs.slice(0, 3).map(row => <li key={row.id}>
            <button onClick={() => onOpenRun(row.id)}>{row.id.slice(0, 8)} · {row.status}</button>
          </li>)}</ul> : <p>暂无回归运行记录。</p>}
        </>}
      </article>
      <article aria-label="引擎概览"><h3>引擎</h3><p>相位：{PHASE_TITLE[status.phase]}；代次：{status.generation_id}</p></article>
      <article aria-label="快捷入口"><h3>快捷入口</h3><button onClick={onContinueAnnotation}>继续标注</button></article>
    </div>
  </section>;
}
