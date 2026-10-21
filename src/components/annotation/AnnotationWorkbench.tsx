import { useEffect, useRef, useState } from 'react';
import type { DatasetRecord, DatasetTransport } from '../datasets/types.ts';
import { annotations } from './api.ts';
import { describeAnnotationError, type AnnotationApi, type CatalogItem, type Geometry, type LabelBody, type LabelSchema, type Png, type Quality, type Seed, type Version, type Working } from './types.ts';
import { candidateKey, editThenRead, estimateRemaining, orderedLabels, readWorking, recoverSelection, selectedCandidate, statistics } from './working.ts';
import { bindingProblem, changeLabelKey, chord, defaultPreferences, labelKey, resolveShortcut, type Command, type Preferences, type Tool } from './shortcuts.ts';
import AnnotationCanvas, { type PromptMode } from './canvas/AnnotationCanvas.tsx';
import LabelPanel from './LabelPanel.tsx';
import CandidateQueue from './CandidateQueue.tsx';
import DisplayToolbar from './display/DisplayToolbar.tsx';
import './annotation.css';

type Props = { record: DatasetRecord; records: DatasetRecord[]; datasets: DatasetTransport;
  api?: AnnotationApi; onNavigate(record: DatasetRecord): void; onClose(): void };
const preferenceKey = 'spectrum.annotation.shortcuts.v1';
const seenKey = 'spectrum.annotation.shortcuts.seen.v1';
const commandNames: Record<Command, string> = { confirm: '确认候选', undo: '撤销', diffuse: '扩散工具', brush: '画笔/涂鸦提示',
  polygon: '多边形', erase: '橡皮', previous: '上一张', next: '下一张', save: '保存', pan: '平移' };
function loadPreferences(): Preferences {
  try {
    const stored = JSON.parse(localStorage.getItem(preferenceKey) ?? 'null') as Preferences | null;
    if (stored && typeof stored.enabled === 'boolean' && stored.bindings && stored.labelKeys
        && Object.keys(stored.bindings).length === Object.keys(defaultPreferences().bindings).length
        && Object.keys(defaultPreferences().bindings).every(key => typeof stored.bindings[key as Command] === 'string')
        && !bindingProblem(stored.bindings)) return stored;
  } catch { /* Storage is optional. Sidecar working data is never stored here. */ }
  return defaultPreferences();
}

export default function AnnotationWorkbench({ record, records, datasets, api = annotations, onNavigate, onClose }: Props) {
  const id = record.id;
  const [working, setWorking] = useState<Working | null>(null);
  const [schemas, setSchemas] = useState<LabelSchema[]>([]), [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [versions, setVersions] = useState<Version[]>([]), [projectName, setProjectName] = useState('');
  const [base, setBase] = useState<Png | null>(null), [segmentation, setSegmentation] = useState<Png | null>(null);
  const [displayBand, setDisplayBand] = useState(0);
  const [displayStretch, setDisplayStretch] = useState<'auto' | 'none'>('auto');
  const [selectedId, setSelectedId] = useState<string | null>(null), [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [tool, setTool] = useState<Tool>('diffuse'), [tab, setTab] = useState<'superpixels' | 'diffuse' | 'prompt'>('superpixels');
  const [prompt, setPrompt] = useState<PromptMode>('point'), [draft, setDraft] = useState<Geometry | null>(null);
  // Display defaults with provenance: TASK-04 §5.2, calibrated compactness.
  const [parameters, setParameters] = useState({ n_segments: 800, compactness: .5, pca_components: 5 });
  // TASK-04 §5.3: S1 example default / S05 UI guard default, both adjustable.
  const [threshold, setThreshold] = useState(.92), [queueMinimum, setQueueMinimum] = useState(.80);
  const [force, setForce] = useState(false), [lastSeed, setLastSeed] = useState<Seed | null>(null);
  const [note, setNote] = useState(''), [overwrite, setOverwrite] = useState(false), [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [quality, setQuality] = useState<Quality | null>(null), [history, setHistory] = useState<Png | null>(null), [historyId, setHistoryId] = useState('');
  const [lastDiffusion, setLastDiffusion] = useState<{ min: number; enqueued: boolean; blocked: number } | null>(null);
  const [preferences, setPreferences] = useState(loadPreferences), [panHeld, setPanHeld] = useState(false);
  const [help, setHelp] = useState(() => { try { return localStorage.getItem(seenKey) !== 'yes'; } catch { return true; } });
  const [busy, setBusy] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState('正在读取工作态…');
  const [synchronized, setSynchronized] = useState(false);
  const alive = useRef(true), busyRef = useRef(true);
  const thresholdOnFocus = useRef(threshold), minimumOnFocus = useRef(queueMinimum);
  const timing = useRef<{ started: number; labeled: number } | null>(null);
  const labels = orderedLabels(schemas), stats = statistics(working);
  const position = records.findIndex(item => item.id === id);
  const dirty = !!working?.params && (['n_segments', 'compactness', 'pca_components'] as const).some(key => parameters[key] !== working.params![key]);
  const ready = !!working?.params && !dirty && synchronized;
  const selected = selectedCandidate(working, selectedKey);
  const geometry = draft ?? (selected ? { superpixels: selected.superpixels } : null);
  const validThresholds = Number.isFinite(threshold) && threshold >= -1 && threshold <= 1
    && Number.isFinite(queueMinimum) && queueMinimum >= -1 && queueMinimum <= 1;
  const seconds = timing.current ? estimateRemaining(timing.current.started, timing.current.labeled, stats, performance.now()) : null;

  const applyWorking = (next: Working) => {
    setWorking(next); setSelectedKey(previous => recoverSelection(next, previous));
    if (next.params) setParameters({ n_segments: next.params.n_segments, compactness: next.params.compactness, pca_components: next.params.pca_components });
    if (!timing.current) timing.current = { started: performance.now(), labeled: statistics(next)?.labeled_pixels ?? 0 };
  };
  const loadMetadata = async (next: Working, isLive = () => alive.current) => {
    const [tree, items, listing, projects] = await Promise.all([api.labels(next.project_id), api.catalog(), api.versions(id), api.projects()]);
    if (!isLive()) return;
    setSchemas(tree); setCatalog(items); setVersions(listing.versions);
    setProjectName(projects.find(project => project.id === next.project_id)?.name ?? next.project_id);
    // listing.working is intentionally not a second source for rendering.
  };
  useEffect(() => {
    let disposed = false;
    const isLive = () => !disposed && alive.current;
    alive.current = true;
    void (async () => {
      try {
        let next = await readWorking(api, id);
        if (!isLive()) return;
        applyWorking(next);
        await loadMetadata(next, isLive);
        if (!isLive()) return;
        // Same effective parameters retrieve the existing engine result; this
        // restores contours without calling diffuse or rebuilding the queue.
        if (next.params) {
          const report = await api.superpixels(id, { n_segments: next.params.n_segments,
            compactness: next.params.compactness, pca_components: next.params.pca_components });
          next = await readWorking(api, id);
          if (!isLive()) return;
          setSegmentation(report.overlay); applyWorking(next);
        }
        if (isLive()) setMessage(next.params ? '已恢复 sidecar 工作态与候选队列。' : '先生成超像素，再在图上给出提示。');
        if (isLive()) setSynchronized(true);
      } catch (failure) { if (isLive()) setError(describeAnnotationError(failure)); }
      finally { if (isLive()) { setBusy(false); busyRef.current = false; } }
    })();
    return () => { disposed = true; alive.current = false; };
  }, [api, datasets, id]);
  useEffect(() => {
    let cancelled = false;
    setBase(null);
    void datasets.preview(id, { band: displayBand, stretch: displayStretch, size: 'full' }).then(png => { if (!cancelled) setBase(png); })
      .catch(failure => { if (!cancelled) setError(describeAnnotationError(failure)); });
    return () => { cancelled = true; };
  }, [datasets, id, displayBand, displayStretch]);
  useEffect(() => { try { localStorage.setItem(preferenceKey, JSON.stringify(preferences)); } catch { /* Optional preferences only. */ } }, [preferences]);

  const execute = async (operation: () => Promise<unknown>, success: string, metadata = false, afterRead?: (next: Working) => void): Promise<boolean> => {
    if (busyRef.current) return false;
    busyRef.current = true; setBusy(true); setSynchronized(false); setError(''); setMessage('正在处理…');
    try {
      const next = await editThenRead(api, id, operation);
      if (!alive.current) return false;
      if (metadata) await loadMetadata(next);
      if (!alive.current) return false;
      applyWorking(next); setSynchronized(true);
      afterRead?.(next);
      if (alive.current) setMessage(success);
      return true;
    } catch (failure) {
      // A transport failure can follow a successful server write. Re-read the
      // sidecar instead of enabling edits against an obsolete queue/geometry.
      try {
        const recovered = await readWorking(api, id);
        await loadMetadata(recovered);
        if (alive.current) { applyWorking(recovered); setSynchronized(true); }
      } catch { /* Leave editing disabled until a successful explicit refresh. */ }
      if (alive.current) setError(describeAnnotationError(failure));
      return false;
    } finally { if (alive.current) { setBusy(false); busyRef.current = false; } }
  };
  const edit = async (action: 'confirm' | 'uncertain' | 'erase', target = geometry) => {
    if (!ready || !target) { setError('先生成超像素并选中候选，或完成一个多边形。'); return; }
    if (action === 'confirm' && !selectedId) { setError('请先选择一个已登记标签。'); return; }
    setQuality(null);
    if (await execute(() => api.regions(id, target, action, action === 'confirm' ? selectedId! : undefined),
      action === 'confirm' ? '区域已确认；工作图与统计已读回。' : action === 'uncertain' ? '区域已记为不确定（-2）。' : '区域已擦除；候选队列由 sidecar 保留。')) { setDraft(null); setQuality(null); }
  };
  const generate = async () => {
    setQuality(null);
    if (await execute(async () => {
      const report = await api.superpixels(id, { ...parameters, force });
      if (alive.current) setSegmentation(report.overlay);
    }, '超像素已生成；已标注与不确定像素保留，候选按参数变化处理。')) { setDraft(null); setQuality(null); setLastSeed(null); setLastDiffusion(null); }
  };
  const diffuse = async (seed: Seed) => {
    if (!ready || !validThresholds) return;
    setLastSeed(seed); setDraft(null);
    let admitted = false;
    await execute(async () => {
      const result = await api.diffuse(id, seed, { threshold, queue_min_similarity: queueMinimum });
      admitted = result.enqueued;
      if (alive.current) setLastDiffusion({ min: result.candidate.min_similarity, enqueued: result.enqueued, blocked: result.not_queued_reasons.below_queue_min_similarity });
      // Do not store result.queue: the subsequent GET working owns rendering.
    }, '扩散完成；右栏与高亮已按 working.queue 刷新。', false, next => {
      if (admitted && next.queue.length) setSelectedKey(candidateKey(next.queue[next.queue.length - 1]));
    });
  };
  const save = async (confirmed = false) => {
    if (!ready || Array.from(note).length > 2000) return;
    if (overwrite && !confirmed) { setConfirmOverwrite(true); return; }
    setConfirmOverwrite(false);
    await execute(async () => {
      const result = await api.save(id, { ...(note ? { note } : {}), ...(overwrite ? { overwrite: true, confirm: true } : {}) });
      if (alive.current) setQuality(result.quality);
    }, overwrite ? '最新版本已覆写并重新聚合。' : '新版本已保存并聚合样本谱。', true);
  };
  const navigate = (delta: number) => { if (!busyRef.current && records[position + delta]) onNavigate(records[position + delta]); };
  const chooseTool = (next: Tool) => { setTool(next); setDraft(null); if (next === 'brush') setPrompt('doodle'); else if (next === 'diffuse') { setTab('diffuse'); setPrompt('point'); } };
  const undo = async () => { setQuality(null); if (await execute(() => api.undo(id), '已撤销一步；统计与工作图来自恢复后的 sidecar。')) setDraft(null); };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      const editing = target instanceof HTMLElement && !!target.closest('input,textarea,select,[contenteditable="true"]');
      const action = resolveShortcut(event, labels, preferences, editing);
      if (!action || busyRef.current) return;
      if ('labelId' in action) { event.preventDefault(); setSelectedId(action.labelId); return; }
      if (event.repeat && action.command !== 'pan') return;
      event.preventDefault();
      switch (action.command) {
        case 'confirm': void edit('confirm'); break;
        case 'undo': void undo(); break;
        case 'save': void save(); break;
        case 'previous': navigate(-1); break;
        case 'next': navigate(1); break;
        case 'pan': setPanHeld(true); break;
        default: chooseTool(action.command);
      }
    };
    const onUp = (event: KeyboardEvent) => { if (chord(event) === preferences.bindings.pan) setPanHeld(false); };
    const blur = () => setPanHeld(false);
    window.addEventListener('keydown', onKey); window.addEventListener('keyup', onUp); window.addEventListener('blur', blur);
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('keyup', onUp); window.removeEventListener('blur', blur); };
  });

  const parametersValid = Number.isInteger(parameters.n_segments) && parameters.n_segments > 0 && Number.isFinite(parameters.compactness) && parameters.compactness > 0;
  const closeHelp = () => { setHelp(false); try { localStorage.setItem(seenKey, 'yes'); } catch { /* Optional. */ } };
  const addLabel = async (body: LabelBody) => {
    if (!await execute(() => api.addLabel(body), '标签 / schema 已登记；已从后端重新读取标签与工作态。', true)) throw new Error('登记未完成，请查看工作台错误详情。');
    setQuality(null);
  };
  return <section className="annotation-workbench" aria-label="S05 标注工作台">
    <header className="annotation-heading">
      <div><button disabled={busy} onClick={onClose}>← 返回数据集</button><h2>标注工作台 <small>{record.dataset.name}</small></h2><p>{projectName || '读取项目中…'} · L1 辅助标注</p></div>
      <ol className="annotation-levels" aria-label="标注层级，当前 L1">{['L0 手工', 'L1 辅助 · 当前', 'L2 半自动', 'L3 自动+抽检', 'L4 自动闭环'].map((level, i) => <li key={level} aria-current={i === 1 ? 'step' : undefined}>{level}</li>)}</ol>
    </header>
    <p className="annotation-note">机器只给候选区域，不赋标签。L2 的簇命名、历史迁移与自动赋标属阶段二；当前先积累人工确认的标注。</p>
    <div className="annotation-status"><p role="status">{message}</p><button disabled={busy} onClick={() => { void execute(async () => {}, '工作态已只读刷新。', true); }}>刷新工作态</button><button onClick={() => setHelp(!help)}>快捷键 / 设置</button></div>
    {error && <pre className="annotation-error" role="alert">{error}</pre>}
    {help && <div className="annotation-shortcut-help" role="dialog" aria-label="标注快捷键，可查可改可关闭" aria-modal="false">
      <h3>快捷键与操作提示</h3><p>数字键选标签；画笔手绘区域，提示分段中提供涂鸦提示；多边形完成后确认，橡皮拖框擦除。键位仅保存在本机。</p>
      <label><input type="checkbox" checked={preferences.enabled} onChange={event => setPreferences({ ...preferences, enabled: event.target.checked })} />启用快捷键</label>
      <div className="annotation-shortcut-grid">{(Object.keys(commandNames) as Command[]).map(command => <label key={command}>{commandNames[command]}
        <input readOnly aria-label={`${commandNames[command]}快捷键`} value={preferences.bindings[command] === ' ' ? 'Space' : preferences.bindings[command]}
          onKeyDown={event => {
            event.preventDefault(); event.stopPropagation(); if (['Control', 'Meta', 'Shift', 'Alt'].includes(event.key)) return;
            const bindings = { ...preferences.bindings, [command]: chord(event) }; const problem = bindingProblem(bindings);
            if (problem) setError(problem); else { setPreferences({ ...preferences, bindings }); setError(''); }
          }} /></label>)}</div>
      <details><summary>标签数字键（0 仅背景；未绑定标签仅鼠标）</summary>{labels.map(label => <label key={label.id}>{label.code}
        <select disabled={label.shortcut_key === null} value={labelKey(label, preferences) ?? ''} onChange={event => {
          try { setPreferences(changeLabelKey(labels, preferences, label.id, event.target.value === '' ? null : Number(event.target.value))); setError(''); }
          catch (failure) { setError(describeAnnotationError(failure)); }
        }}><option value="">仅鼠标</option>{Array.from({ length: 10 }, (_, key) => key).filter(key => key !== 0 || label.is_background).map(key => <option key={key}>{key}</option>)}</select>
      </label>)}</details>
      <p className="annotation-hint">Ctrl+K 聚焦底部对话条，Ctrl+Enter 发送；保留给全局外壳。</p>
      <button onClick={() => setPreferences(defaultPreferences())}>恢复默认键位</button><button className="annotation-primary" onClick={closeHelp}>知道了，关闭提示</button>
    </div>}
    <div className="annotation-columns">
      <aside className="annotation-left">
        {working && <LabelPanel projectId={working.project_id} schemas={schemas} labels={labels} catalog={catalog} selectedId={selectedId}
          preferences={preferences} disabled={busy} onSelect={setSelectedId} onAdd={addLabel} />}
        <section className="annotation-card"><h3>工具</h3><div className="annotation-tools">{(['diffuse', 'brush', 'polygon', 'erase'] as const).map(next =>
          <button key={next} disabled={busy} className={tool === next ? 'selected' : ''} aria-pressed={tool === next} onClick={() => chooseTool(next)}>{commandNames[next]} <kbd>{preferences.bindings[next]}</kbd></button>)}</div></section>
        <section className="annotation-card"><h3>本图统计</h3><dl className="annotation-statistics">
          <dt>超像素数</dt><dd>{working?.superpixel_count ?? '—'}</dd><dt>已确认</dt><dd>{stats ? `${stats.labeled_percent.toFixed(2)}%` : '—'}</dd>
          <dt>不确定</dt><dd>{stats ? `${stats.uncertain_percent.toFixed(2)}%` : '—'}</dd><dt>留白</dt><dd>{stats ? `${stats.blank_percent.toFixed(2)}%` : '—'}</dd>
          <dt>待确认（并集）</dt><dd>{stats?.pending_pixels.toLocaleString() ?? '—'} px</dd>
        </dl><p className="annotation-hint">统计来自 sidecar 当前工作态；未分割时为空态。</p>
          <p>预计剩余 {seconds === null ? '—（确认后估算）' : `${Math.ceil(seconds / 60)} 分钟`}<small> · 仅本地确认速度估计</small></p>
        </section>
      </aside>
      <div className="annotation-center">
        <section className="annotation-card">
          <div className="annotation-tabs" role="tablist" aria-label="标注分段">{([['superpixels', '超像素'], ['diffuse', '扩散'], ['prompt', '提示分割']] as const).map(([value, title]) =>
            <button role="tab" key={value} aria-selected={tab === value} onClick={() => { setTab(value); setDraft(null); if (value !== 'superpixels') { setTool('diffuse'); setPrompt(value === 'diffuse' ? 'point' : 'box'); } }}>{title}</button>)}</div>
          <p className="annotation-hint">{tab === 'superpixels' ? '先生成超像素；参数变化后重新生成，已有像素标注保留。' : tab === 'diffuse' ? '单击种子区域，按当前阈值扩散；候选由人工确认标签。' : '选择单击、半开框选或涂鸦提示，生成一个候选。多边形也可直接选区编辑。'}</p>
          <div className="annotation-parameters">
            <label>SLIC n<input type="number" min={1} step={1} disabled={busy} value={parameters.n_segments} onChange={event => setParameters({ ...parameters, n_segments: Number(event.target.value) })} /></label>
            <label>compactness<input type="number" min={0} step="any" disabled={busy} value={parameters.compactness} onChange={event => setParameters({ ...parameters, compactness: Number(event.target.value) })} /></label>
            <label>PCA 分量<select disabled={busy} value={parameters.pca_components} onChange={event => setParameters({ ...parameters, pca_components: Number(event.target.value) })}><option>3</option><option>5</option></select></label>
            <label><input type="checkbox" disabled={busy} checked={force} onChange={event => setForce(event.target.checked)} />强制重算</label>
            <button className="annotation-primary" disabled={busy || !working || !parametersValid} onClick={() => { void generate(); }}>生成超像素</button>
          </div>
          <div className="annotation-parameters">
            <label>扩散阈值（默认 0.92）<input type="number" min={-1} max={1} step="any" value={threshold} disabled={busy} onFocus={() => { thresholdOnFocus.current = threshold; }} onChange={event => setThreshold(Number(event.target.value))} onBlur={() => { if (lastSeed && validThresholds && thresholdOnFocus.current !== threshold) void diffuse(lastSeed); }} /></label>
            <label>入队下限（默认 0.80）<input type="number" min={-1} max={1} step="any" value={queueMinimum} disabled={busy} onFocus={() => { minimumOnFocus.current = queueMinimum; }} onChange={event => setQueueMinimum(Number(event.target.value))} onBlur={() => { if (lastSeed && validThresholds && minimumOnFocus.current !== queueMinimum) void diffuse(lastSeed); }} /></label>
            <label>提示方式<select disabled={busy} value={prompt} onChange={event => { setPrompt(event.target.value as PromptMode); setTool('diffuse'); setTab('prompt'); }}><option value="point">单击</option><option value="box">框选</option><option value="doodle">涂鸦</option></select></label>
          </div>
          <p className="annotation-hint">已有种子时，阈值输入完成、移出输入框即重新扩散预览；也可点击“扩散到相似区域”。</p>
          {!validThresholds && <p className="annotation-warning">两项余弦阈值都须为 [-1,1] 内的有限数。</p>}
          {lastDiffusion && <p className={lastDiffusion.enqueued ? 'annotation-hint' : 'annotation-warning'}>本次候选最小种子相似度 {lastDiffusion.min.toFixed(4)} · {lastDiffusion.enqueued ? '已入队' : `被护栏拦下，未入队 ${lastDiffusion.blocked} 项`}。</p>}
          <details className="annotation-hint"><summary>默认值与相似度口径</summary>SLIC 默认值来自 TASK-04 §5.2（11 cube 标定 compactness=0.5）；扩散默认 0.92 来自需求场景 S1；入队默认 0.80 来自 UI 原型 S05。增长比较邻接对原谱均值；报告比较种子原谱。均为可调默认值。</details>
          {dirty && <p className="annotation-warning">参数已改，先重新生成超像素；已有标注按像素保留。</p>}
          {!busy && !synchronized && <p className="annotation-warning">工作态尚未成功读回，请先刷新；编辑暂不可用。</p>}
          <DisplayToolbar bands={record.dataset.shape[2]} wavelengths={record.dataset.wavelengths} band={displayBand} onBand={setDisplayBand}
            stretch={displayStretch} onStretch={setDisplayStretch} />
          <AnnotationCanvas shape={record.dataset.shape} base={base} segmentation={segmentation} working={working} selectedKey={selectedKey}
            tool={tool} prompt={prompt} disabled={busy || !ready} panHeld={panHeld} draft={draft} brushPrompt={tab === 'prompt'}
            onSeed={seed => { void diffuse(seed); }} onGeometry={value => { setDraft(value); setSelectedKey(null); setMessage('多边形已选；选择标签后确认，或标记为不确定。'); }}
            onErase={value => { void edit('erase', value); }} />
          <div className="annotation-actions">
            <button className="annotation-primary" disabled={busy || !ready || !geometry || !selectedId} onClick={() => { void edit('confirm'); }}>确认选中候选 / 区域</button>
            <button disabled={busy || !ready || !lastSeed || !validThresholds} onClick={() => { if (lastSeed) void diffuse(lastSeed); }}>扩散到相似区域（按当前阈值）</button>
            <button disabled={busy || !ready || !geometry} onClick={() => { void edit('uncertain'); }}>标记“不确定”</button>
            <button disabled={busy} onClick={() => { void undo(); }}>撤销一步</button>
          </div>
          <nav className="annotation-navigation" aria-label="切换数据集"><button disabled={busy || position <= 0} onClick={() => navigate(-1)}>← 上一张</button><span>{position + 1} / {records.length} · {record.dataset.name}</span><button disabled={busy || position >= records.length - 1} onClick={() => navigate(1)}>下一张 →</button></nav>
        </section>
        <section className="annotation-card" aria-label="保存与版本">
          <h3>保存与版本</h3><label>版本备注（可选，≤2000 字符）<textarea value={note} onChange={event => setNote(event.target.value)} /></label>
          <label><input type="checkbox" disabled={!versions.length || busy} checked={overwrite} onChange={event => setOverwrite(event.target.checked)} />覆写最新版本（需再次确认）</label>
          <button disabled={busy || !ready || Array.from(note).length > 2000} onClick={() => { void save(); }}>保存并聚合</button>
          {confirmOverwrite && <div role="alertdialog" aria-label="确认覆写最新版本" className="annotation-overwrite"><p>将用当前工作态重写最新版本 v{versions[0]?.version_no}，版本号与首次创建时间保留。</p><button disabled={busy} onClick={() => { void save(true); }}>确认覆写最新版本</button><button onClick={() => setConfirmOverwrite(false)}>取消</button></div>}
          <details><summary>版本记录（{versions.length}）</summary><ul>{versions.map(version => <li key={version.id}>v{version.version_no} · {version.labeled_pixels.toLocaleString()} px · {version.created_at}
            <button disabled={busy} onClick={() => { void execute(async () => { const png = await api.versionOverlay(id, version.id); if (alive.current) { setHistory(png); setHistoryId(version.id); } }, '历史叠加图已读取；当前工作态不变。'); }}>查看叠加图</button></li>)}</ul>
            {history && <div className="annotation-history"><p>历史版本 UUID：{historyId} · 只读叠加图</p><img alt="历史版本标注叠加图" src={`data:image/png;base64,${history.png_base64}`} /><button onClick={() => setHistory(null)}>关闭历史图</button></div>}
          </details>
          <button disabled={busy || !ready} onClick={() => { void execute(async () => { const result = await api.validate(id); if (alive.current) setQuality(result); }, '质量校验已完成。'); }}>校验当前工作态</button>
          {quality && <div className="annotation-quality"><h4>质量校验 · 当前原谱均值</h4><p>余弦阈值 {quality.threshold}（{quality.threshold_level}）· 可疑 {quality.suspicious.length} 项 · 高方差 {quality.high_variance.superpixel_ids.length} 项</p>
            <p className="annotation-hint">{quality.reference}</p><ul>{quality.suspicious.map(item => <li key={`${item.superpixel_id}:${item.label_index}`}>#{item.superpixel_id} · {labels[item.label_index]?.code} · {item.pixel_count} px · cos {item.cos.toFixed(6)}</li>)}</ul>
            <p>高方差超像素：{quality.high_variance.superpixel_ids.join('、') || '无'}；τ={quality.high_variance.tau}</p>
            {Object.entries(quality.not_applicable).map(([name, reason]) => <p key={name}>{name}：{reason}</p>)}
          </div>}
        </section>
      </div>
      <CandidateQueue working={working} labels={labels} selectedKey={selectedKey} disabled={busy} onSelect={key => { setSelectedKey(key); setDraft(null); }} onSave={() => { void save(); }} />
    </div>
  </section>;
}
