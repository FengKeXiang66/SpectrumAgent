import { useEffect, useState } from 'react';
import { displayName, type DatasetReference } from '../datasets/types.ts';
import { preprocessing } from '../preprocess/api.ts';
import { modeling, type ClassificationBody, type ClassificationResult, type TrainingProgress } from './api.ts';
import { currentWorkspace, type CurrentMember } from '../preprocess/current';
import { extractNearDuplicates, preflightAlerts } from './preflight-alert-store.ts';
import { failureMessage } from './chart.ts';

export type ClassificationSummary = { version: string; labels: number; recipes: number; classes: number | null; pixels: number | null };
export type ClassificationEvidence = { preflight: unknown; trained: ClassificationResult | null; events: { at: string; text: string }[] };
export type ClassificationAudit = { count: number; missingLabels: number; missingRuns: number;
  classes: number | null; pixels: number | null; members: { name: string; annotation: string; run: string | null }[] };

export default function ClassificationPanel({ records, busy, work, onOpenResults, embedded = false, onSummary, onEvidence, onAudit }: {
  records: DatasetReference[]; choices: Record<string, { id: string; version: string }[]>; busy: boolean;
  work(action: () => Promise<void>): Promise<void>; onOpenResults(id: string): void;
  embedded?: boolean; onSummary?: (summary: ClassificationSummary) => void; onEvidence?: (evidence: ClassificationEvidence) => void;
  onAudit?: (audit: ClassificationAudit) => void;
}) {
  const [lv, setLV] = useState(''), [threshold, setThreshold] = useState(0), [seed, setSeed] = useState(17);
  const [bandSelection, setBandSelection] = useState<'full' | 'ipls'>('full');
  const [metadata, setMetadata] = useState<{ pixels: number; classes: number } | null>(null);
  const [metadataError, setMetadataError] = useState(''), [preflight, setPreflight] = useState<unknown>(null);
  const [trained, setTrained] = useState<ClassificationResult | null>(null);
  const [training, setTraining] = useState<TrainingProgress | null>(null);
  const [trainingError, setTrainingError] = useState('');
  const [members, setMembers] = useState<CurrentMember[]>([]), [selected, setSelected] = useState<Record<string,boolean>>({});
  const [inputError, setInputError] = useState(''), [loading, setLoading] = useState(true);
  const [sequence] = useState({ current: 0, live: true, list: 0, training: false });
  const [events, setEvents] = useState<{ at: string; text: string }[]>([]);
  const note = (text: string) => setEvents(rows => [...rows, { at: new Date().toLocaleTimeString('zh-CN', { hour12: false }), text }]);
  const recordsKey = records.map(row => row.id).join('|');
  useEffect(() => { sequence.live = true; return () => { sequence.live = false; sequence.current++; sequence.list++; }; }, [sequence]);
  const refresh = async () => {
    const ticket = ++sequence.list; setLoading(true); setInputError('');
    try {
      const state = await currentWorkspace.state();
      if (sequence.live && ticket === sequence.list) {
        setMembers(state.members.filter(row => records.some(record => record.id === row.cube_id)));
        setSelected(old => Object.fromEntries(records.map(row => [row.id, old[row.id] ?? true])));
      }
    } catch (e) { if (sequence.live && ticket === sequence.list) setInputError(failureMessage(e)); }
    finally { if (sequence.live && ticket === sequence.list) setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [recordsKey]);
  const selectedMembers = members.filter(row => selected[row.cube_id]);
  const missingAnnotations = selectedMembers.filter(row => !row.annotation_id).length;
  const missingRuns = selectedMembers.filter(row => !row.run_id);
  const bound = selectedMembers.filter(row => row.run_id && row.annotation_id).map(row => ({
    cube_id: row.cube_id, annotation_version_id: row.annotation_id!, preprocess_run_id: row.run_id!, recipe_version_id: row.recipe_input_id!
  }));
  const binding = JSON.stringify(bound);
  useEffect(() => {
    let live = true;
    setMetadata(null); setMetadataError(''); setPreflight(null); setTrained(null);
    const members = JSON.parse(binding) as typeof bound;
    if (!members.length || members.some(member => !member.preprocess_run_id)) return;
    void (async () => {
      let pixels = 0;
      const labels = new Set<string>();
      for (const member of members) {
        const report = await preprocessing.getArtifact(member.preprocess_run_id!, 'report');
        if (report.run_id !== member.preprocess_run_id || report.annotation_version_id !== member.annotation_version_id) {
          throw new Error('预处理报告与当前标注不一致');
        }
        for (const item of report.curves.classes) {
          if (item.label_index < 0 || item.count <= 0) continue;
          const label = report.label_index[String(item.label_index)];
          if (!label) throw new Error('预处理报告缺少类别映射');
          labels.add(label); pixels += item.count;
        }
      }
      if (live) setMetadata({ pixels, classes: labels.size });
    })().catch(failure => { if (live) setMetadataError(failureMessage(failure)); });
    return () => { live = false; };
  }, [binding]);
  const body = (): ClassificationBody => {
    if (!Number.isFinite(threshold) || threshold < 0 || threshold >= 1) throw new Error('置信度阈值须在 [0,1)');
    if (!Number.isInteger(seed)) throw new Error('随机种子须为整数');
    if (lv && (!Number.isInteger(Number(lv)) || Number(lv) < 1 || Number(lv) > 20)) throw new Error('手动 LV 须为 1–20 的整数');
    return { task: 'classification', cube_ids: bound.map(row => row.cube_id), annotation_version_ids: bound.map(row => row.annotation_version_id), preprocess_run_ids: bound.map(row => row.preprocess_run_id),
      target: 'label', cv_strategy: 'group_kfold', cv_folds: 5, split_strategy: 'none', seed, confidence_threshold: threshold, evaluation_protocol: 'nested_group_cv',
      ...(lv ? { n_components: Number(lv) } : {}), ...(bandSelection === 'ipls' ? { band_selection: 'ipls' as const } : {}) };
  };
  const resolvedReady = !loading && !inputError && selectedMembers.length > 0 && !missingAnnotations && !missingRuns.length && metadata !== null && metadata.classes >= 2 && metadata.pixels > 0;
  const ready = resolvedReady && bound.length >= 5;
  const preflightReady = resolvedReady && bound.length >= 4;
  const boundRecipes = [...new Set(bound.map(row => row.recipe_version_id))];
  const boundAnnotations = [...new Set(bound.map(row => row.annotation_version_id))];
  useEffect(() => { onSummary?.({ version: `${selectedMembers.length} 个样品`, labels: boundAnnotations.length, recipes: boundRecipes.length, classes: metadata?.classes ?? null, pixels: metadata?.pixels ?? null }); }, [selectedMembers.length, boundAnnotations.length, boundRecipes.length, metadata, onSummary]);
  useEffect(() => { onEvidence?.({ preflight, trained, events }); }, [preflight, trained, events, onEvidence]);
  useEffect(() => {
    onAudit?.({ count: selectedMembers.length, missingLabels: missingAnnotations, missingRuns: missingRuns.length,
      classes: metadata?.classes ?? null, pixels: metadata?.pixels ?? null,
      members: selectedMembers.map(member => ({ name: displayName(records.find(record => record.id === member.cube_id) ?? { id: member.cube_id, display_name: member.cube_id }), annotation: member.annotation_id?.slice(0, 8) ?? '缺标注', run: member.run_id?.slice(0,8) ?? null })) });
  }, [binding, selectedMembers.length, missingAnnotations, missingRuns.length, metadata, records, onAudit]);
  const train = async (request: ClassificationBody) => {
    if (sequence.training) return;
    sequence.training = true;
    setTrained(null);
    setTrainingError('');
    note('正在提交分类训练任务。');
    try {
      const row = await modeling.train(request, progress => { if (sequence.live) setTraining(progress); });
      if (row.task !== 'classification' || row.status !== 'succeeded' || !row.confusion) {
        throw row.error ?? new Error('分类训练尚未成功');
      }
      if (!sequence.live) return;
      setTraining(null);
      preflightAlerts.set([]);
      setTrained(row);
      note(`训练完成，run ${row.run_id.slice(0, 8)}。`);
    } catch (reason: unknown) {
      if (sequence.live) {
        const uncertain = !!reason && typeof reason === 'object' && 'error' in reason && reason.error === 'TRAINING_STATUS_UNAVAILABLE';
        if (!uncertain) setTraining(null);
      }
      if (sequence.live) setTrainingError(failureMessage(reason));
    } finally { sequence.training = false; }
  };
  useEffect(() => {
    const pending = modeling.pendingTraining?.();
    if (pending) void train(pending);
  }, []);
  return <section className={embedded ? 'classification-panel classification-config' : 'classification-panel'} aria-label="PLS-DA 分类配置">
    <div className="md-col-left">
    <section className="md-data-card"><h3>当前数据</h3><p>{bound.length} 个处理就绪的样品 · {metadata ? `${metadata.classes} 类 · ${metadata.pixels} 像素` : '正在读取类别与像素数'}</p></section>
    <fieldset disabled={busy || !!training || loading}><legend>参与建模的样品</legend>
      <button onClick={() => void refresh()}>刷新当前结果</button>
      {members.map(member => <label key={member.cube_id}><input type="checkbox" checked={!!selected[member.cube_id]} onChange={e => setSelected(old => ({...old,[member.cube_id]:e.target.checked}))} />{displayName(records.find(row => row.id === member.cube_id) ?? {id:member.cube_id,display_name:member.cube_id})} · {member.status === 'ready' ? '就绪' : member.status === 'need_annotation' ? '请先标注' : '请先预处理'}</label>)}
      {inputError && <p role="alert">{inputError}</p>}
      {!!missingRuns.length && <p>选中的样品尚有 {missingRuns.length} 项需要预处理。</p>}
      <p>训练至少需要 5 个样品；可选诊断至少需要 4 个样品，诊断结果不影响训练。</p>
      {metadataError && <p role="alert">{metadataError}</p>}
    </fieldset>
    <fieldset disabled={busy || !!training || loading}><legend>分组验证与超参</legend>
      <label>波段选择<select value={bandSelection} onChange={event => setBandSelection(event.target.value as 'full' | 'ipls')}>
        <option value="full">全波段</option><option value="ipls">iPLS 区间扫描（20 个区间）</option>
      </select></label>
      <details className="md-help"><summary>划分与校验说明</summary>
        <p>外层5折GroupKFold评价；内层分组选LV及波段。无物理样品身份时按图像组代理。</p>
        <p>同一样品的全部像素始终在同一侧；可直接训练，不执行光谱相似度或数据泄漏检查。</p>
        <p>不设每类最小组数；训练折缺类时允许继续，并在诊断和结果中标明覆盖情况。</p>
        <p>训练前会核验当前标注与配方是否发生变化。</p>
      </details>
      <label>随机种子<input type="number" step={1} value={seed} onChange={event => setSeed(Number(event.target.value))} /></label>
      <label>手动 LV（1–20，留空使用 CV 最小建议）<input type="number" min={1} max={20} value={lv} onChange={event => setLV(event.target.value)} /></label>
      <label>置信度阈值<input type="number" min={0} max={1} step="any" value={threshold} onChange={event => setThreshold(Number(event.target.value))} /></label>
      <details className="md-help"><summary>超参与指标说明</summary>
        <p>训练后返回CV最小与容差建议（历史称拐点），并保留逐外层折与最终模型选择。</p>
        <p>默认0不拒识；softmax是未校准分类得分。结果同时给全体与接纳指标及覆盖率。</p>
      </details>
      <button className="modeling-primary" disabled={!preflightReady} onClick={() => void work(async () => {
        if (!preflightReady) return;
        body();
        const result = await modeling.preflight({ cube_ids: bound.map(member => member.cube_id), annotation_version_ids: bound.map(member => member.annotation_version_id),
          preprocess_run_ids: bound.map(member => member.preprocess_run_id!), task: 'classification', target: 'label', cv_strategy: 'group_kfold', cv_folds: 5, seed, evaluation_protocol: 'nested_group_cv' });
        setPreflight(result);
        const alerts = extractNearDuplicates(result);
        if (alerts.length) preflightAlerts.set(alerts);
        note(alerts.length ? `可选诊断已返回：发现 ${alerts.length} 对近似重复样品，不影响训练。` : '可选诊断已返回，结果见诊断卡片；不影响训练。');
      })}>可选诊断（不影响训练）</button>
      <button className="modeling-primary" disabled={!ready || !!training} onClick={() => {
        if (!ready || sequence.training || training) return;
        try { return train(body()); } catch (reason) { setTrainingError(failureMessage(reason)); }
      }}>{busy ? '正在计算…' : '训练 PLS-DA'}</button>
    </fieldset>
    </div><div className="md-col-right">
    {trainingError && <p role="alert">{trainingError}</p>}
    {training && <section aria-label="分类训练进度" role="status">
      <h3>{training.status === 'unavailable' ? '训练状态待确认' : training.status === 'reconnecting' ? '正在恢复训练连接' : '分类训练进行中'}</h3>
      <p>{training.status === 'submitting' ? '正在提交任务' : training.status === 'queued' ? '等待后台开始训练' : '后台正在训练或等待状态更新'} · 已等待 {training.elapsed} 秒。</p>
      {training.status === 'unavailable' && <button disabled={busy} onClick={() => {
        if (sequence.training) return;
        const pending = modeling.pendingTraining();
        if (pending) return train(pending);
      }}>继续查询训练状态</button>}
    </section>}
    {training && <p>可通过页面顶部「训练任务」查看逐折进度、完整日志及取消操作；切换页面后训练继续。</p>}
    {preflight !== null && <PreflightCard preflight={preflight} />}
    {trained && <section aria-label="分类训练完成"><h3>分类训练完成</h3>
      <p>CV 最小建议 LV：{trained.by_cv_min ?? '不适用'}；RMSE 拐点建议 LV：{trained.by_elbow ?? '不适用'}；使用 LV：{trained.selected_lv ?? '不适用'}</p>
      <button onClick={() => onOpenResults(trained.run_id)}>查看分类结果</button>
    </section>}
    {events.length > 0 && <section className="md-exec-log" aria-label="执行记录"><h3>执行记录</h3>
      <ol>{events.map((event, index) => <li key={index}><time>{event.at}</time><span>{event.text}</span></li>)}</ol>
    </section>}
    </div>
  </section>;
}

export function PreflightCard({ preflight, records = [] }: { preflight: unknown; records?: DatasetReference[] }) {
  const object = (value: unknown): Record<string, unknown> =>
    value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const report = object(object(preflight).leak_report);
  const group = object(report.group_cross_fold).violation_count;
  const duplicate = object(report.duplicate_content).duplicate_count;
  const reason = object(report.preprocess_full_fit).reason;
  const near = object(report.near_duplicate_spectra), nearCount = near.pair_count;
  const support = object(report.class_support);
  const supportWarnings = Array.isArray(support.warnings) ? support.warnings.filter((v): v is string => typeof v === 'string') : [];
  const supportClasses = Array.isArray(support.classes) ? support.classes.map(object) : [];
  const pairs = Array.isArray(near.pairs) ? near.pairs as { cube_ids?: unknown; similarity?: unknown }[] : [];
  const label = (id: unknown) => {
    if (typeof id !== 'string') return '未知';
    const name = records.find(record => record.id === id)?.display_name;
    return name ? `${name}（${id.slice(0, 8)}）` : id.slice(0, 8);
  };
  const examples = pairs.slice(0, 3).map(pair => {
    const ids = Array.isArray(pair.cube_ids) ? pair.cube_ids : [];
    return `${label(ids[0])} ↔ ${label(ids[1])} · ${typeof pair.similarity === 'number' ? pair.similarity.toFixed(5) : '—'}`;
  }).join('；');
  const blocked = object(preflight).passed === false || report.passed === false || object(preflight).status === 'failed';
  const steps: { key: string; title: string; state: 'pass' | 'warning' | 'neutral'; description: string }[] = [];
  if (typeof group === 'number' && Number.isFinite(group)) steps.push({ key: 'group_cross_fold', title: '分组跨折泄漏',
    state: group === 0 ? 'pass' : 'warning', description: group === 0 ? '未发现分组跨折泄漏。' : '检测到分组跨折泄漏，请查看完整 JSON。' });
  if (typeof duplicate === 'number' && Number.isFinite(duplicate)) steps.push({ key: 'duplicate_content', title: '重复内容',
    state: duplicate === 0 ? 'pass' : 'warning', description: duplicate === 0 ? '未发现重复内容。' : '检测到重复内容，请查看完整 JSON。' });
  if (typeof nearCount === 'number' && Number.isFinite(nearCount)) steps.push({ key: 'near_duplicate_spectra', title: '近似重复光谱',
    state: nearCount === 0 ? 'pass' : 'warning', description: nearCount === 0 ? '未发现超过阈值的近似重复样品。'
      : `发现 ${nearCount} 对相似度达到阈值的近似重复样品（阈值 ${near.threshold ?? '—'}）${examples ? `：${examples}` : ''}，可能虚高指标；请核对样品后重新处理。` });
  if (typeof reason === 'string') steps.push({ key: 'preprocess_full_fit', title: '全数据拟合（已知接受项）',
    state: 'neutral', description: reason });
  if (support.policy === 'allow_missing_classes') steps.push({ key: 'class_support', title: '类别覆盖（不阻断）',
    state: supportWarnings.length ? 'warning' : 'pass',
    description: [...supportWarnings, ...supportClasses.map(c => `${c.name}：${c.groups} 组 / ${c.pixels} 像素`)].join('；') });
  return <section className="classification-preflight" aria-label="分类预检结果">
    <header className="md-card-head"><h3>分类诊断结果</h3><span className="md-card-note" data-state={blocked ? 'bad' : undefined}>{blocked ? '发现问题 · 不影响训练' : report.passed === true ? '诊断通过 · 不影响训练' : '请查看诊断详情'}</span></header>
    <div className="preflight-steps">{steps.map(step => <div key={step.key} className="preflight-step" data-preflight-step={step.key} data-state={step.state}>
      <span className="preflight-state" aria-label={step.state === 'pass' ? '通过' : step.state === 'neutral' ? '提示' : '需关注'}>{step.state === 'pass' ? '✓' : '!'}</span>
      <div><h4>{step.title}</h4><p>{step.description}</p></div>
    </div>)}</div>
    <details><summary>查看完整 JSON</summary><pre>{JSON.stringify(preflight, null, 2)}</pre></details>
  </section>;
}
