import { useEffect, useState } from 'react';
import { displayName, type DatasetReference } from '../datasets/types.ts';
import { datasets } from '../datasets/api.ts';
import type { TrainingSetMembersResponse, TrainingSetVersion } from '../datasets/types.ts';
import { annotations } from '../annotation/api.ts';
import { preprocessing } from '../preprocess/api.ts';
import { modeling, type ClassificationBody, type ClassificationResult, type TrainingProgress } from './api.ts';
import { datasetVersionSelection } from './dataset-version-store.ts';
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
  const [confirmed, setConfirmed] = useState<Record<string, { id: string; number: number } | null>>({});
  const [annotationsLoading, setAnnotationsLoading] = useState(true), [annotationError, setAnnotationError] = useState('');
  const [lv, setLV] = useState(''), [threshold, setThreshold] = useState(0), [seed, setSeed] = useState(17);
  const [bandSelection, setBandSelection] = useState<'full' | 'ipls'>('full');
  const [metadata, setMetadata] = useState<{ pixels: number; classes: number } | null>(null);
  const [metadataError, setMetadataError] = useState(''), [preflight, setPreflight] = useState<unknown>(null);
  const [trained, setTrained] = useState<ClassificationResult | null>(null);
  const [training, setTraining] = useState<TrainingProgress | null>(null);
  const [trainingError, setTrainingError] = useState('');
  const [versionId, setVersionId] = useState(''), [versions, setVersions] = useState<TrainingSetVersion[]>([]);
  const [resolved, setResolved] = useState<TrainingSetMembersResponse | null>(null);
  const [versionError, setVersionError] = useState(''), [versionLoading, setVersionLoading] = useState(false);
  const [sequence] = useState({ current: 0, live: true, list: 0, training: false });
  const [events, setEvents] = useState<{ at: string; text: string }[]>([]);
  const note = (text: string) => setEvents(rows => [...rows, { at: new Date().toLocaleTimeString('zh-CN', { hour12: false }), text }]);
  const recordsKey = JSON.stringify([...new Set(records.map(record => record.id))]);
  useEffect(() => { sequence.live = true; return () => { sequence.live = false; sequence.current++; sequence.list++; }; }, [sequence]);
  const refreshVersions = async () => {
    const ticket = ++sequence.list;
    try {
      const rows = await datasets.trainingSets();
      if (sequence.live && ticket === sequence.list) setVersions(rows.filter(row => row.is_frozen === 1));
    } catch (failure) { if (sequence.live && ticket === sequence.list) setVersionError(failureMessage(failure)); }
  };
  useEffect(() => { void refreshVersions(); }, []);
  useEffect(() => {
    const sync = () => {
      const id = datasetVersionSelection.get();
      if (id && id !== versionId && versions.some(version => version.id === id)) void chooseVersion(id);
    };
    sync();
    return datasetVersionSelection.subscribe(sync);
  }, [versions, versionId]);
  useEffect(() => {
    let live = true;
    sequence.current++;
    setVersionId(''); setResolved(null);  setVersionLoading(false);
    setAnnotationsLoading(true); setAnnotationError(''); setConfirmed({}); setMetadata(null);
    const cubes = JSON.parse(recordsKey) as string[];
    void Promise.all(cubes.map(async cube => {
      // Persisted annotation versions are confirmed snapshots. Working drafts
      // are returned separately and never enter this selection.
      const listing = await annotations.versions(cube);
      const latest = [...listing.versions].sort((a, b) => b.version_no - a.version_no)[0];
      return [cube, latest ? { id: latest.id, number: latest.version_no } : null] as const;
    })).then(rows => { if (live) setConfirmed(Object.fromEntries(rows)); })
      .catch(failure => { if (live) setAnnotationError(failureMessage(failure)); })
      .finally(() => { if (live) setAnnotationsLoading(false); });
    return () => { live = false; };
  }, [recordsKey]);
  const visibleRecords = resolved ? resolved.members.map(member => records.find(record => record.id === member.cube_id)
    ?? { id: member.cube_id, display_name: member.cube_id }) : records;
  const missingAnnotations = resolved ? 0 : records.filter(record => !confirmed[record.id]).length;
  const selectedVersion = versions.find(version => version.id === versionId && version.is_frozen === 1);
  const gaps = resolved?.need_preprocess ?? [];
  const missingRuns = resolved?.members.filter(member => !member.preprocess_run_id) ?? [];
  const bound = versionId && resolved?.version_id === versionId ? resolved.members : [];
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
          throw new Error('预处理报告与训练集绑定的标注版本不一致');
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
  const verifyMembers = (id: string, result: TrainingSetMembersResponse) => {
    if (result.version_id !== id || !result.members.length || new Set(result.members.map(member => member.cube_id)).size !== result.members.length) {
      throw new Error('训练集成员响应不完整或版本归属不一致');
    }
  };
  const chooseVersion = async (id: string) => {
    const ticket = ++sequence.current;
    setVersionId(id); setResolved(null);  setVersionError(''); setMetadata(null); setPreflight(null); setTrained(null);
    datasetVersionSelection.set(id);
    if (!id) { setVersionLoading(false); return; }
    setVersionLoading(true);
    try {
      if (!versions.some(version => version.id === id && version.is_frozen === 1)) throw new Error('请选择已冻结的训练集版本');
      const result = await datasets.trainingSetMembers(id);
      verifyMembers(id, result);
      if (!sequence.live || ticket !== sequence.current) return;
      setResolved(result);
      note(`读取版本 ${id.slice(0, 8)} 的 ${result.members.length} 个成员`);
    } catch (failure) { if (sequence.live && ticket === sequence.current) setVersionError(failureMessage(failure)); }
    finally { if (sequence.live && ticket === sequence.current) setVersionLoading(false); }
  };
  const body = (): ClassificationBody => {
    if (!Number.isFinite(threshold) || threshold < 0 || threshold >= 1) throw new Error('置信度阈值须在 [0,1)');
    if (!Number.isInteger(seed)) throw new Error('随机种子须为整数');
    if (lv && (!Number.isInteger(Number(lv)) || Number(lv) < 1 || Number(lv) > 20)) throw new Error('手动 LV 须为 1–20 的整数');
    return { task: 'classification', cube_ids: [], annotation_version_ids: [], preprocess_run_ids: [], training_set_version_id: versionId,
      target: 'label', cv_strategy: 'group_kfold', cv_folds: 5, split_strategy: 'none', seed, confidence_threshold: threshold, evaluation_protocol: 'nested_group_cv',
      ...(lv ? { n_components: Number(lv) } : {}), ...(bandSelection === 'ipls' ? { band_selection: 'ipls' as const } : {}) };
  };
  const resolvedReady = !!selectedVersion && resolved?.version_id === versionId && bound.length === resolved.members.length
    && !gaps.length && !missingRuns.length && metadata !== null && metadata.classes >= 2 && metadata.pixels > 0 && !versionLoading;
  const ready = resolvedReady && bound.length >= 5;
  const preflightReady = resolvedReady && bound.length >= 4;
  const boundRecipes = [...new Set(resolved?.members.map(member => member.recipe_version_id) ?? [])];
  const boundAnnotations = [...new Set(resolved?.members.map(member => member.annotation_version_id) ?? [])];
  useEffect(() => {
    onSummary?.({ version: selectedVersion ? `${selectedVersion.member_count} 个样品 · ${selectedVersion.id.slice(0, 8)}` : '',
      labels: boundAnnotations.length, recipes: boundRecipes.length, classes: metadata?.classes ?? null, pixels: metadata?.pixels ?? null });
  }, [selectedVersion, boundAnnotations.length, boundRecipes.length, metadata, onSummary]);
  useEffect(() => { onEvidence?.({ preflight, trained, events }); }, [preflight, trained, events, onEvidence]);
  useEffect(() => {
    if (!resolved) return;
    onAudit?.({ count: resolved.members.length, missingLabels: missingAnnotations, missingRuns: resolved.need_preprocess.length,
      classes: metadata?.classes ?? null, pixels: metadata?.pixels ?? null,
      members: resolved.members.map(member => ({ name: displayName(records.find(record => record.id === member.cube_id)
        ?? { id: member.cube_id, display_name: member.cube_id }), annotation: member.annotation_version_id.slice(0, 8),
        run: member.preprocess_run_id?.slice(0, 8) ?? null })) });
  }, [resolved, metadata, missingAnnotations, records, onAudit]);
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
        const alerts = extractNearDuplicates(reason);
        if (alerts.length) {
          preflightAlerts.set(alerts);
          note(`训练被预检阻断：发现 ${alerts.length} 对近似重复样品，已标记到数据集版本页。`);
        }
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
    <section className="md-data-card"><h3>任务与数据</h3><dl>
      <div><dt>数据集版本</dt><dd>{selectedVersion ? `${selectedVersion.member_count} 个样品 · ${selectedVersion.id.slice(0, 8)}` : '尚未选定'}</dd></div>
      <div><dt>标签来源</dt><dd>{boundAnnotations.length ? `已确认标注 ${boundAnnotations.length} 个` : '等待版本绑定'}</dd></div>
      <div><dt>预处理配方</dt><dd>{boundRecipes.length ? `绑定版本 ${boundRecipes.length} 个` : '等待版本绑定'}</dd></div>
      <div><dt>类别</dt><dd>{metadata ? `${metadata.classes} 类 · ${metadata.pixels} 像素` : '读取版本中'}</dd></div>
    </dl></section>
    <section aria-label="数据集版本">
      <label>已冻结训练集<select aria-label="已冻结训练集" value={versionId} onFocus={() => { void refreshVersions(); }} onChange={event => { void chooseVersion(event.target.value); }}>
        <option value="">请选择已冻结训练集</option>{versions.map(version => <option key={version.id} value={version.id}>{version.member_count} 个样品 · {version.confirmed_at?.replace('T', ' ').slice(0, 16)} · {version.id.slice(0, 8)}</option>)}
      </select></label>
      <button onClick={() => { void refreshVersions(); }}>刷新版本与配方</button>
      {versionLoading && <p role="status">正在处理训练集版本…</p>}
      {versionError && <p role="alert">{versionError}</p>}
    </section>
    <fieldset className="md-members-fieldset" disabled={busy || !!training || versionLoading || annotationsLoading}><legend>版本成员与标注</legend>
      <p>成员与标注版本随冻结版本固定，这里不提供逐样品勾选；需增减样品请到「数据集版本」页重新生成版本。</p>
      {resolved ? <ul className="md-members" aria-label="版本成员">{visibleRecords.map(record => {
        const member = resolved.members.find(row => row.cube_id === record.id);
        const annotation = confirmed[record.id];
        return <li key={record.id}><span>{displayName(record)}</span><code>{(member?.annotation_version_id ?? annotation?.id ?? '缺标注').slice(0, 8)}</code>
          {member && !member.preprocess_run_id && <em>缺预处理 run</em>}</li>;
      })}</ul> : <p role="status">请先选择已冻结训练集版本。</p>}
      <p role="status">{annotationsLoading ? '正在读取确认版标注…' : `冻结成员 ${bound.length} 个；缺标注 ${missingAnnotations} 个。`}</p>
      {annotationError && <p role="alert">{annotationError}</p>}
      <p role="status">{metadata ? `确认版已标像素 ${metadata.pixels} 个，类别 ${metadata.classes} 个。` : bound.length ? '正在读取绑定版本的实际类别与像素数…' : '请预览并冻结训练集，或选择已有冻结版本。'}</p>
      {versionId && gaps.length > 0 && <ul aria-label="训练集预处理缺口">{gaps.map(member => <li key={member.cube_id}>{member.cube_id} · 标注 {member.annotation_version_id} · 配方 {member.recipe_version_id}：先补跑缺失的预处理</li>)}</ul>}
      {versionId && missingRuns.length > 0 && <p>先补跑缺失的预处理，再重新选择此冻结版本以读取成员。</p>}
      {versionId && bound.length < 5 && <p>训练至少需要 5 个样品；预检至少需要 4 个成员。</p>}
      {metadataError && <p role="alert">{metadataError}</p>}
    </fieldset>
    <fieldset disabled={busy || !!training || versionLoading}><legend>分组验证与超参</legend>
      <label>波段选择<select value={bandSelection} onChange={event => setBandSelection(event.target.value as 'full' | 'ipls')}>
        <option value="full">全波段</option><option value="ipls">iPLS 区间扫描（20 个区间）</option>
      </select></label>
      <details className="md-help"><summary>划分与校验说明</summary>
        <p>外层5折GroupKFold评价；内层分组选LV及波段。无物理样品身份时按图像组代理。</p>
        <p>同一样品的全部像素始终在同一侧；训练前强制泄漏预检，失败即阻断。</p>
        <p>不设每类最小组数；训练折缺类时允许继续，并在预检和结果中标明覆盖情况。</p>
        <p>预检不含版本一致性；版本与配方一致性在训练发起时校验。</p>
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
        note(alerts.length ? `分类预检已返回：发现 ${alerts.length} 对近似重复样品，已标记到数据集版本页。` : '分类预检已返回，结果见预检卡片。');
      })}>分类预检</button>
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
      : `发现 ${nearCount} 对相似度达到阈值的近似重复样品（阈值 ${near.threshold ?? '—'}）${examples ? `：${examples}` : ''}，可能虚高指标；请核对后重新冻结版本。` });
  if (typeof reason === 'string') steps.push({ key: 'preprocess_full_fit', title: '全数据拟合（已知接受项）',
    state: 'neutral', description: reason });
  if (support.policy === 'allow_missing_classes') steps.push({ key: 'class_support', title: '类别覆盖（不阻断）',
    state: supportWarnings.length ? 'warning' : 'pass',
    description: [...supportWarnings, ...supportClasses.map(c => `${c.name}：${c.groups} 组 / ${c.pixels} 像素`)].join('；') });
  return <section className="classification-preflight" aria-label="分类预检结果">
    <header className="md-card-head"><h3>分类预检结果</h3><span className="md-card-note" data-state={blocked ? 'bad' : undefined}>{blocked ? '未通过 · 已阻断训练' : report.passed === true ? '预检通过' : '请查看预检详情'}</span></header>
    <div className="preflight-steps">{steps.map(step => <div key={step.key} className="preflight-step" data-preflight-step={step.key} data-state={step.state}>
      <span className="preflight-state" aria-label={step.state === 'pass' ? '通过' : step.state === 'neutral' ? '提示' : '需关注'}>{step.state === 'pass' ? '✓' : '!'}</span>
      <div><h4>{step.title}</h4><p>{step.description}</p></div>
    </div>)}</div>
    <details><summary>查看完整 JSON</summary><pre>{JSON.stringify(preflight, null, 2)}</pre></details>
  </section>;
}
