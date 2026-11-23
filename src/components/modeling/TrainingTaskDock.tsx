import { useEffect, useState, useSyncExternalStore } from 'react';
import { save } from '@tauri-apps/plugin-dialog';
import { modeling } from './api';
import { failureMessage } from './chart';
import type { TrainingEvent, TrainingJob } from './training';
import './training-progress.css';

const phases: Record<string, string> = { queued: '等待训练', validation: '校验绑定引用', prepared: '输入与分折已核验', source_verify: '核验源数据',
  dataset: '读取像素与应用配方', dataset_image: '图像读取完成', check: '训练诊断记录', run: '建立训练记录',
  inner_preprocess: '折内拟合预处理', lv: '选择潜变量', ipls: '扫描 iPLS 区间', fit: '拟合分类模型',
  outer: '外层留出评价', fold_complete: '外层评价完成', baseline_complete: '全波段基线完成', checkpoint: '保存完成单元',
  reused: '复用已完成单元', summarize: '汇总评价', publish: '保存正式结果', fit_warning: '拟合警告' };
const statuses: Record<TrainingJob['status'], string> = { queued: '已受理', running: '训练中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
function clock(seconds: number) { const s = Math.max(0, Math.floor(seconds)); return `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`; }
function metric(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '不适用'; }
function object(value: unknown): Record<string, unknown> { return value !== null && typeof value === 'object' ? value as Record<string, unknown> : {}; }
export function eventText(event: TrainingEvent): string {
  const where = event.branch === 'final' ? '最终模型' : event.branch === 'full_baseline' ? '全波段基线' : event.outer_fold !== undefined ? `外层折 ${Number(event.outer_fold) + 1}` : '';
  let detail = '';
  if (event.phase === 'lv' || event.phase === 'ipls') detail = `${event.completed}/${event.total} · RMSECV=${metric(event.rmsecv)}${event.selection ? ` · ${event.selection === 'selected' ? '选中区间' : '全波段'}` : ''}`;
  if (event.phase === 'dataset') detail = `图像 ${Number(event.image_index) + 1}/${event.total_images} · 行 ${event.rows_read}/${event.total_rows}`;
  if (event.phase === 'dataset_image') detail = `图像 ${event.completed}/${event.total} · 有效 ${event.valid} · 非有限谱 ${event.invalid} · 未标注 ${event.unlabeled} · 留白 ${event.annotation_uncertain}`;
  if (event.phase === 'check') detail = (event.status === 'skipped'
    ? '光谱相似度与数据泄漏检查已跳过'
    : `${event.passed ? '通过' : '未通过'} · 跨折分组 ${event.group_violations} · 重复 ${event.duplicate_count}`)
    + (Array.isArray(event.warnings) && event.warnings.length ? ' · ' + event.warnings.join('；') : '');
  if (event.phase === 'fold_complete') { const score = object(object(object(event.metrics).all_labeled).pixel); detail = `全体像素 OA=${metric(score.oa)} · Kappa=${metric(score.kappa)}`; }
  if (event.phase === 'checkpoint' || event.phase === 'reused') detail = String(event.unit ?? '');
  if (event.phase === 'fit_warning') detail = String(event.code ?? '');
  return [where, phases[event.phase] ?? event.phase, detail].filter(Boolean).join(' · ');
}

export default function TrainingTaskDock({ ready, bootId, onOpenResults }: { ready: boolean; bootId: string | null; onOpenResults(id: string): void }) {
  const view = useSyncExternalStore(modeling.training.subscribe, modeling.training.snapshot);
  const [expanded, setExpanded] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [history, setHistory] = useState<TrainingEvent[] | null>(null), [partial, setPartial] = useState<Record<string, unknown> | null>(null);
  const job = view.job;
  useEffect(() => { modeling.training.reset(); }, [bootId]);
  useEffect(() => {
    if (!ready) return;
    let live = true, timer: ReturnType<typeof setTimeout>;
    const discover = async () => { try { await modeling.training.discover(); } catch { /* Engine startup or a temporary disconnect: retry discovery. */ }
      if (live) timer = setTimeout(() => { void discover(); }, 10000); };
    void discover(); return () => { live = false; clearTimeout(timer); };
  }, [ready, bootId]);
  useEffect(() => { setHistory(null); setPartial(null); setError(''); }, [job?.job_id]);
  useEffect(() => { if (!expanded) return; const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close); }, [expanded]);
  const action = async (fn: () => Promise<unknown>) => { setBusy(true); setError(''); try { await fn(); } catch (reason) { setError(failureMessage(reason)); } finally { setBusy(false); } };
  const more = async () => {
    if (!job) return;
    const id = job.job_id, page = await modeling.trainingEvents(id, history?.at(-1)?.seq ?? 0);
    if (modeling.training.snapshot().job?.job_id === id) setHistory(rows => [...(rows ?? []), ...page.events]);
  };
  const active = job?.status === 'running' || job?.status === 'queued';
  const exportDiagnostic = async (kind: 'events' | 'partial') => {
    if (!job) return;
    const path = await save({ defaultPath: `training-${job.job_id}-${kind}.${kind === 'events' ? 'jsonl' : 'json'}` });
    if (path) await modeling.downloadTraining(job.job_id, path, kind);
  };
  const rows = history ?? view.events.slice(-12);
  return <>
    <button className="training-dock-button" onClick={() => setExpanded(true)}>训练任务{job ? ` · ${statuses[job.status]}` : ''}</button>
    {expanded && <div className="training-overlay"><section className="training-dialog" role="dialog" aria-modal="true" aria-label="PLS-DA 训练任务" onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), summary, a[href], select:not(:disabled), input:not(:disabled)')];
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}>
      <header><div><span className="training-eyebrow">PLS-DA / 后台任务</span><h2>训练进度</h2></div><button autoFocus onClick={() => setExpanded(false)}>转到后台</button></header>
      {!job ? <p role="status">当前引擎会话暂无训练任务。可从「建模训练」或对话发起。</p> : <>
        <div className="training-task-summary"><strong>{job.cancel_requested && active ? '正在取消，等待当前计算单元结束' : statuses[job.status]}</strong>
          <span>已完成外层折 {job.completed_folds?.length ?? 0}/{job.total_folds ?? '—'} · 复用 {job.reused_folds?.length ?? 0} 折</span>
          {job.band_selection === 'ipls' && <span>全波段基线 {job.baseline_folds?.length ?? 0}/{job.total_folds ?? '—'} 折</span>}
          <span>已运行 {clock(job.elapsed_s ?? view.progress?.elapsed ?? 0)} · {active ? job.eta_seconds != null ? `全程约剩余 ${Math.max(1, Math.ceil(job.eta_seconds / 5) * 5)} 秒（同输入历史估算）` : job.stage_eta_seconds != null ? `当前阶段约剩余 ${Math.max(1, Math.ceil(job.stage_eta_seconds / 5) * 5)} 秒（估算）；全程估算中` : '剩余时间估算中' : '任务已结束'}</span>
        </div>
        <dl className="training-identity"><div><dt>任务</dt><dd>{job.job_id}</dd></div><div><dt>训练输入</dt><dd>当前样品处理结果</dd></div>
          <div><dt>阶段</dt><dd>{phases[job.phase ?? ''] ?? job.phase ?? '等待状态'}{job.current?.branch === 'final' ? ' · 最终模型' : job.current?.outer_fold != null ? ` · 外层折 ${Number(job.current.outer_fold) + 1}` : ''}</dd></div>
          {job.retry_of && <div><dt>继续自</dt><dd>{job.retry_of}</dd></div>}</dl>
        {view.progress?.status === 'unavailable' || view.progress?.status === 'reconnecting' ? <p className="training-notice" role="status">连接暂不可用；后台可能仍在运行，请继续查询原任务。</p> : null}
        {job.status === 'cancelled' && <p className="training-notice">用户取消，指标不完整。已保存的完成单元可查看及复用，不能用作完整报告或正式基线。</p>}
        {job.error != null && <p role="alert">{failureMessage(job.error)}</p>}
        <div className="training-actions">
          {active && <button disabled={busy || job.cancel_requested || job.cancelable === false} onClick={() => void action(modeling.training.cancel)}>取消任务</button>}
          <button disabled={busy} onClick={() => void action(modeling.training.refresh)}>继续查询状态</button>
          {(job.status === 'cancelled' || job.status === 'failed') && <button disabled={busy} onClick={() => void action(modeling.training.resume)}>继续未完成</button>}
          <button disabled={busy} onClick={() => void action(async () => { const id = job.job_id; const result = await modeling.trainingPartial(id); if (modeling.training.snapshot().job?.job_id === id) setPartial(result); })}>查看已完成折</button>
          {job.status === 'succeeded' && job.run_id && <button onClick={() => { onOpenResults(job.run_id!); setExpanded(false); }}>查看完整结果</button>}
          <button disabled={busy} onClick={() => void action(more)}>{history === null ? '查看完整日志' : '加载下一页日志'}</button>
          <button disabled={busy} onClick={() => void action(() => exportDiagnostic('events'))}>导出完整日志</button>
          <button disabled={busy} onClick={() => void action(() => exportDiagnostic('partial'))}>导出部分诊断</button>
        </div>
        <h3>{history === null ? '最近执行记录' : '完整日志 · 按页读取（每页 50 条）'}</h3>
        <p className="training-muted">{history === null ? '当前仅显示最近 12 条；完整历史可分页查看。' : `已读取 ${history.length} 条；下方显示末 300 条。`}时间与数值由训练算子返回。</p>
        <ol className="training-log">{rows.slice(-300).map(event => <li key={event.seq}><time>{clock(event.elapsed_s)}</time><span>{eventText(event)}</span></li>)}</ol>
        {partial && <section className="training-partial"><h3>已完成折诊断 · 非完整评价</h3><p>完成 {Array.isArray(partial.completed_folds) ? partial.completed_folds.length : 0}/{String(partial.total_folds)} 折 · 已评价 {String(partial.n_evaluated_pixels)} / {String(partial.n_planned_pixels ?? '未知')} 像素。</p>
          {partial.baseline_required === true && <p>全波段基线完成 {Array.isArray(partial.baseline_completed_folds) ? partial.baseline_completed_folds.length : 0}/{String(partial.total_folds)} 折；完成范围与主模型分别记录。</p>}
          <PartialScores populations={object(partial.populations)} /><details><summary>诊断原始数据</summary><pre>{JSON.stringify(partial, null, 2)}</pre></details></section>}
      </>}
      {error && <p role="alert">{error}</p>}
    </section></div>}
  </>;
}

function PartialScores({ populations }: { populations: Record<string, unknown> }) {
  return <div className="training-table-scroll"><table><thead><tr><th>评价范围</th><th>层级</th><th>OA</th><th>AA</th><th>Kappa</th><th>macro-F1</th></tr></thead><tbody>
    {Object.entries(populations).flatMap(([name, population]) => Object.entries(object(object(population).scores)).map(([scope, value]) => {
      const score = object(value); return <tr key={name + scope}><th>{name === 'accepted' ? '接纳' : '全体已标'}</th><td>{scope === 'pixel' ? '像素' : '样品'}</td>
        {['oa', 'aa', 'kappa', 'macro_f1'].map(k => <td key={k}>{metric(score[k])}</td>)}</tr>;
    }))}</tbody></table></div>;
}
