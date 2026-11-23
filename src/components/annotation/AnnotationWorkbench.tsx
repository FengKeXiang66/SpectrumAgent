import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import type { DatasetRecord, DatasetReference, DatasetTransport, MeanSpectrum, Preview, SpectrumRegion } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import { annotations } from './api.ts';
import { describeAnnotationError, type AnnotationApi, type ExportResult, type Geometry, type JsonProjectionStatus, type LabelBody, type LabelSchema, type Png, type Quality, type Seed, type SegmentsMap, type SuperpixelReport, type Working } from './types.ts';
import { annotationBadge } from './annotationStatus.ts';
import SpectrumReview from './SpectrumReview.tsx';
import { eraseAndRefresh, formatReviewCos, formatReviewNumber } from './spectrumReview.ts';
import { candidateKey, editThenRead, orderedLabels, readWorking, recoverSelection, selectedCandidate, statistics } from './working.ts';
import { bindingProblem, changeLabelKey, chord, defaultPreferences, labelKey, resolveShortcut, type Command, type Preferences, type Tool } from './shortcuts.ts';
import AnnotationCanvas, { type PromptMode } from './canvas/AnnotationCanvas.tsx';
import LabelPanel from './LabelPanel.tsx';
import CandidateQueue from './CandidateQueue.tsx';
import { drafts } from './draft-api.ts';
import DisplayToolbar, { SpectrumReadout } from './display/DisplayToolbar.tsx';
import { DEFAULT_LUT, changeLut, displayRequest, type DisplayMode, type InspectionMode, type LutParameters } from './display/display.ts';
import './annotation.css';
import './annotation-skin.css';
import type { WorkspaceContext } from '../assistant/api.ts';
import { candidatePreviewKey } from '../assistant/presentation.ts';
import { createBlockEditQueue, type BlockEditQueue, type PendingBlockEdit } from './block-edits.ts';

type Props = { record: DatasetRecord; records: DatasetReference[]; datasets: DatasetTransport;
  api?: AnnotationApi; onNavigate(record: DatasetReference): void;
  batch?: { datasetVersionId: string | null; memberCount: number; readyCubeIds: string[]; onDemand?:boolean }; onReturnToAssistant?(): void;
  prepareOnDemand?(id:string):Promise<void>;
  onCanvasFocus?(id:string,focused:boolean):Promise<void>;
  onNavigationGuardChange?(blocked:boolean):void;
  onWorkspaceChange?(context: WorkspaceContext): void; refreshVersion?: number; previewCandidateRef?: string };
const preferenceKey = 'spectrum.annotation.shortcuts.v1';
const seenKey = 'spectrum.annotation.shortcuts.seen.v1';
const commandNames: Record<Command, string> = { confirm: '确认候选', undo: '撤销', diffuse: '扩散工具', brush: '画笔/涂鸦提示',
  polygon: '多边形', erase: '橡皮', click: '点选', previous: '上一张', next: '下一张', save: '保存', pan: '平移' };
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

export default function AnnotationWorkbench({ record, records, datasets, api = annotations, onNavigate,
  onWorkspaceChange, refreshVersion = 0, previewCandidateRef, batch, onReturnToAssistant, prepareOnDemand, onCanvasFocus, onNavigationGuardChange }: Props) {
  const id = record.id;
  const [working, setWorking] = useState<Working | null>(null);
  const focusCallback=useRef(onCanvasFocus);focusCallback.current=onCanvasFocus;
  useEffect(()=>{
    return()=>{void focusCallback.current?.(id,false).catch(()=>undefined);};
  },[id]);
  const [schemas, setSchemas] = useState<LabelSchema[]>([]);
  const [hasSaved, setHasSaved] = useState(false), [projectName, setProjectName] = useState('');
  // undefined = listing not read yet; null = engine did not return the field.
  const [projectionStatus, setProjectionStatus] = useState<JsonProjectionStatus | null | undefined>(undefined);
  const [base, setBase] = useState<Preview | null>(null), [segmentation, setSegmentation] = useState<Png | null>(null);
  const [segments, setSegments] = useState<SegmentsMap | null>(null);
  const [displayMode, setDisplayMode] = useState<DisplayMode>('auto');
  const [displayRgb, setDisplayRgb] = useState<[number, number, number]>([0, 1, 2]);
  const [displayBand, setDisplayBand] = useState(0);
  const [displayStretch, setDisplayStretch] = useState<'auto' | 'manual'>('auto');
  const [displayLut, setDisplayLut] = useState<LutParameters>({ ...DEFAULT_LUT });
  const [displayError, setDisplayError] = useState('');
  const [inspection, setInspection] = useState<InspectionMode>('edit');
  const [spectrum, setSpectrum] = useState<MeanSpectrum | null>(null);
  const [spectrumBusy, setSpectrumBusy] = useState(false), [spectrumError, setSpectrumError] = useState('');
  const spectrumTicket = useRef(0);
  const [selectedId, setSelectedId] = useState<string | null>(null), [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [tool, setTool] = useState<Tool>('click'), [tab, setTab] = useState<'superpixels' | 'diffuse' | 'prompt' | 'review'>('superpixels');
  const [prompt, setPrompt] = useState<PromptMode>('point'), [draft, setDraft] = useState<Geometry | null>(null);
  // Display defaults with provenance: TASK-04 §5.2, calibrated compactness.
  const [parameters, setParameters] = useState({ n_segments: 200, compactness: .5, pca_components: 5 });
  // TASK-04 §5.3: S1 example default / S05 UI guard default, both adjustable.
  const [threshold, setThreshold] = useState(.92), [queueMinimum, setQueueMinimum] = useState(.60);
  const [force, setForce] = useState(false), [lastSeed, setLastSeed] = useState<Seed | null>(null);
  const [lastGestureRef, setLastGestureRef] = useState<string | null>(null);
  const [draftRevision, setDraftRevision] = useState<number | null>(null);
  const [note, setNote] = useState('');
  // Keep save-and-next navigation attached to the save result.
  const postSave = useRef<((saved: boolean) => void) | null>(null);
  const [exportResult, setExportResult] = useState<ExportResult | null>(null), [exportStale, setExportStale] = useState(true);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [lastDiffusion, setLastDiffusion] = useState<{ min: number; enqueued: boolean; blocked: number } | null>(null);
  const [preferences, setPreferences] = useState(loadPreferences), [panHeld, setPanHeld] = useState(false);
  const [help, setHelp] = useState(() => { try { return localStorage.getItem(seenKey) !== 'yes'; } catch { return true; } });
  const [busy, setBusy] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState('正在读取工作态…');
  const [synchronized, setSynchronized] = useState(false);
  const guardCallback=useRef(onNavigationGuardChange);guardCallback.current=onNavigationGuardChange;
  useEffect(()=>{
    guardCallback.current?.(busy||!!draft);
    return()=>guardCallback.current?.(false);
  },[busy,draft]);
  const alive = useRef(true), busyRef = useRef(true);
  const clickQueue = useRef<BlockEditQueue | null>(null), clickingRef = useRef(false);
  const [clicking, setClicking] = useState(false);
  const [pendingClicks, setPendingClicks] = useState<readonly PendingBlockEdit[]>([]);
  const loadTicket = useRef(0);
  const segmentationRef = useRef<string | null>(null);
  const seenRefresh = useRef(refreshVersion);
  const focusedPreview = useRef<string | null>(null);
  const thresholdOnFocus = useRef(threshold), minimumOnFocus = useRef(queueMinimum);
  const labels = orderedLabels(schemas), stats = statistics(working);
  // A version is only meaningful once at least one pixel carries a label;
  // browsing (zero labeled pixels) must never publish an empty version.
  const hasLabels = (stats?.labeled_pixels ?? 0) > 0;
  const navigationRecords = batch && !batch.onDemand ? batch.readyCubeIds.flatMap(cube => records.filter(item => item.id === cube)) : records;
  const position = navigationRecords.findIndex(item => item.id === id);
  const dirty = !!working?.params && (['n_segments', 'compactness', 'pca_components'] as const).some(key => parameters[key] !== working.params![key]);
  const batchReady = !batch || !!working?.params && working.superpixel_count > 0
    && working.params.n_segments === 200 && working.params.compactness === .5 && working.params.pca_components === 5
    && working.params.k === 3 && working.params.block_size === 32 && working.params.feature_version === 'pca-global-zscore-clip3-unit-v1';
  const ready = !!segments && !!working?.params && !dirty && synchronized && batchReady;
  const selected = selectedCandidate(working, selectedKey);
  const badge = annotationBadge(projectionStatus, Number(hasSaved));
  useEffect(() => {
    if (!previewCandidateRef || focusedPreview.current === previewCandidateRef) return;
    const key = candidatePreviewKey(working, previewCandidateRef);
    if (key !== null) { setSelectedKey(key); setDraft(null); focusedPreview.current = previewCandidateRef; }
  }, [previewCandidateRef, working]);
  const geometry = draft ?? (selected ? { superpixels: selected.superpixels } : null);
  const validThresholds = Number.isFinite(threshold) && threshold >= -1 && threshold <= 1
    && Number.isFinite(queueMinimum) && queueMinimum >= -1 && queueMinimum <= 1;

  useEffect(() => {
    setHasSaved(false);
    setProjectionStatus(undefined); // never show the previous cube's badge
    setDraftRevision(null); setLastGestureRef(null);
  }, [id]);

  useEffect(() => {
    onWorkspaceChange?.({ cube_id: id, gesture_ref: lastGestureRef ?? undefined });
  }, [id, lastGestureRef, onWorkspaceChange]);

  const applyWorking = (next: Working) => {
    setWorking(next); setSelectedKey(previous => recoverSelection(next, previous));
    if (next.params) setParameters({ n_segments: next.params.n_segments, compactness: next.params.compactness, pca_components: next.params.pca_components });
  };
  const applySegmentation = (report: SuperpixelReport) => {
    setSegmentation(report.overlay);
    setSegments({ png: report.segments_png, shape: report.segments_shape, counts: report.block_counts });
  };
  const applyRead = (loaded: Awaited<ReturnType<AnnotationApi['getSuperpixels']>>) => {
    if (segmentationRef.current && segmentationRef.current !== loaded.segmentation_ref) {
      setLastGestureRef(null); setLastSeed(null); setLastDiffusion(null); setDraft(null); setSelectedKey(null);
    }
    segmentationRef.current = loaded.segmentation_ref;
    if (loaded.status === 'ready') applySegmentation(loaded.report);
    else { setSegments(null); setSegmentation(null); }
  };
  const loadMetadata = async (next: Working, isLive = () => alive.current) => {
    const [tree, listing, projects] = await Promise.all([api.labels(next.project_id), api.current(id), api.projects()]);
    if (!isLive()) return;
    setSchemas(tree); setHasSaved(!!listing.current);
    // Only the backend's disk truth decides the badge; versions alone cannot.
    setProjectionStatus(listing.json_projection ?? null);
    setProjectName(projects.find(project => project.id === next.project_id)?.name ?? next.project_id);
    // listing.working is intentionally not a second source for rendering.
  };
  useEffect(() => {
    let disposed = false;
    const ticket = ++loadTicket.current;
    const isLive = () => !disposed && alive.current && ticket === loadTicket.current;
    alive.current = true;
    busyRef.current = true; setBusy(true); setSynchronized(false);
    setSegments(null); setSegmentation(null);
    setQuality(null);
    setExportResult(null); setExportStale(true);
    void (async () => {
      try {
        if(focusCallback.current)await focusCallback.current(id,true);
        if(!isLive())return;
        let loaded: Awaited<ReturnType<AnnotationApi['getSuperpixels']>> | null = null;
        let loadFailure: unknown = null;
        try { loaded = await api.getSuperpixels(id); } catch (failure) { loadFailure = failure; }
        if (!isLive()) return;
        if (loaded?.status !== 'ready' && !loadFailure && prepareOnDemand) {
          setMessage('正在为当前图片准备超像素…');
          await prepareOnDemand(id);
          if (!isLive()) return;
          loaded=await api.getSuperpixels(id);
          if(!isLive())return;
          if(loaded.status!=='ready')throw new Error('分割准备后仍不可读取，请核查任务状态');
        }
        if (loaded) applyRead(loaded);
        const currentDraft = await drafts.get(id);
        if (!isLive()) return;
        setDraftRevision(currentDraft.revision);
        const next = await readWorking(api, id);
        if (!isLive()) return;
        applyWorking(next);
        await loadMetadata(next, isLive);
        if (!isLive()) return;
        if (isLive() && loadFailure) setError(describeAnnotationError(loadFailure));
        if (isLive()) setMessage(loadFailure
          ? '分割读取失败；可刷新工作态后重试，仍失败时请核查后显式重新准备。'
          : loaded?.status === 'ready'
          ? '超像素已就绪。请选择标签，然后点击超像素块赋类；下一张将保留当前草稿。'
          : '尚未准备分割；可显式生成超像素，已有像素标注保留。');
        if (isLive()) setSynchronized(loaded?.status === 'ready');
      } catch (failure) { if (isLive()) setError(describeAnnotationError(failure)); }
      finally { if (isLive()) { setBusy(false); busyRef.current = false; } }
    })();
    return () => { disposed = true; alive.current = false; loadTicket.current++; };
  }, [api, datasets, id]);
  useEffect(() => {
    let cancelled = false;
    setBase(null); setDisplayError('');
    let selection;
    try { selection = displayRequest(displayMode, displayBand, displayRgb, displayStretch === 'manual' ? 'none' : 'auto', record.dataset.shape[2]); }
    catch (failure) { setDisplayError(describeAnnotationError(failure)); return; }
    void datasets.preview(id, selection).then(png => { if (!cancelled) setBase(png); })
      .catch(failure => { if (!cancelled) setDisplayError(describeAnnotationError(failure)); });
    return () => { cancelled = true; };
  }, [datasets, id, displayMode, displayRgb, displayBand, displayStretch, record.dataset.shape]);
  useEffect(() => {
    spectrumTicket.current++; setSpectrum(null); setSpectrumError(''); setSpectrumBusy(false);
    return () => { spectrumTicket.current++; };
  }, [id]);
  const readSpectrum = async (region: SpectrumRegion) => {
    const ticket = ++spectrumTicket.current;
    setSpectrumBusy(true); setSpectrumError('');
    try {
      const next = await datasets.spectraMean(id, region);
      if (ticket === spectrumTicket.current) setSpectrum(next);
    } catch (failure) { if (ticket === spectrumTicket.current) setSpectrumError(describeAnnotationError(failure)); }
    finally { if (ticket === spectrumTicket.current) setSpectrumBusy(false); }
  };
  useEffect(() => { try { localStorage.setItem(preferenceKey, JSON.stringify(preferences)); } catch { /* Optional preferences only. */ } }, [preferences]);

  const recoverWorking = async (isLive: () => boolean) => {
    try {
      if (!isLive()) return;
      const loaded = await api.getSuperpixels(id);
      if (!isLive()) return;
      applyRead(loaded);
      const recovered = await readWorking(api, id);
      await loadMetadata(recovered, isLive);
      if (isLive()) { applyWorking(recovered); setSynchronized(loaded.status === 'ready'); }
    } catch { /* Leave editing disabled until a successful explicit refresh. */ }
  };
  const execute = async (operation: () => Promise<unknown>, success: string, metadata = false, afterRead?: (next: Working) => void): Promise<boolean> => {
    if (busyRef.current) return false;
    const ticket = loadTicket.current;
    const isLive = () => alive.current && ticket === loadTicket.current;
    busyRef.current = true; setBusy(true); setSynchronized(false); setError(''); setMessage('正在处理…');
    try {
      const next = await editThenRead(api, id, operation);
      if (!isLive()) return false;
      if (metadata) await loadMetadata(next, isLive);
      if (!isLive()) return false;
      applyWorking(next); setSynchronized(true);
      afterRead?.(next);
      if (isLive()) setMessage(success);
      return true;
    } catch (failure) {
      // A transport failure can follow a successful server write. Re-read the
      // sidecar instead of enabling edits against an obsolete queue/geometry.
      await recoverWorking(isLive);
      if (isLive()) setError(describeAnnotationError(failure));
      return false;
    } finally { if (isLive()) { setBusy(false); busyRef.current = false; } }
  };
  const refreshWorkState = async () => {
    if (busyRef.current) return;
    const ticket = loadTicket.current;
    const isLive = () => alive.current && ticket === loadTicket.current;
    busyRef.current = true; setBusy(true); setSynchronized(false); setError(''); setMessage('正在刷新工作态与超像素…');
    try {
      // Reconcile project label changes before attempting to attach segmentation.
      const next = await readWorking(api, id);
      if (!isLive()) return;
      applyWorking(next);
      const loaded = await api.getSuperpixels(id);
      if (!isLive()) return;
      applyRead(loaded);
      // Attachment can restore block summaries or invalidate old candidates.
      const attached = await readWorking(api, id);
      if (!isLive()) return;
      applyWorking(attached);
      await loadMetadata(attached, isLive);
      if (!isLive()) return;
      setSynchronized(loaded.status === 'ready');
      setMessage(loaded.status === 'ready'
        ? '工作态与超像素已刷新。'
        : '工作态已刷新；尚未准备分割，可显式生成超像素，已有像素标注保留。');
    } catch (failure) {
      if (isLive()) {
        setSegments(null); setSegmentation(null); setSynchronized(false);
        setError(describeAnnotationError(failure));
        setMessage('刷新未完成，超像素尚不可用；请核查错误后重试。');
      }
    } finally { if (isLive()) { setBusy(false); busyRef.current = false; } }
  };
  useEffect(() => {
    const ticket = loadTicket.current;
    const isLive = () => alive.current && ticket === loadTicket.current;
    const queue = createBlockEditQueue({
      submit: edit => api.regions(id, { superpixels: [edit.blockId] }, edit.action, edit.labelId),
      read: () => readWorking(api, id),
      onRead: next => {
        if (isLive()) { applyWorking(next); setMessage('点击标注已读回，可继续点选。'); }
      },
      onPending: next => { if (isLive()) setPendingClicks(next); },
      onActive: active => {
        if (!isLive()) return;
        clickingRef.current = active; setClicking(active);
        busyRef.current = active; setBusy(active);
        if (active) {
          guardCallback.current?.(true);
          setError(''); setQuality(null); setExportStale(true); setDraft(null);
          setMessage('可连续点选；点击正在按顺序保存。');
        }
      },
      onError: async (failure, interrupted) => {
        if (!isLive()) return;
        setSynchronized(false);
        await recoverWorking(isLive);
        if (isLive()) {
          setError(`${describeAnnotationError(failure)}\n${interrupted} 次点击的同步已中断；已尝试读取实际标注，请核对后重新点击未完成区域。`);
          setMessage('点击同步中断；未自动重试，避免重复提交。');
        }
      },
    });
    clickQueue.current = queue;
    setPendingClicks([]); setClicking(false); clickingRef.current = false;
    return () => { queue.dispose(); if (clickQueue.current === queue) clickQueue.current = null; };
  }, [api, datasets, id]);
  const editBlock = (blockId: number, action: 'confirm' | 'uncertain' | 'erase') => {
    if (!ready || (busyRef.current && !clickingRef.current)) return;
    if (action === 'confirm' && !selectedId) { setError('请先选择一个已登记标签。'); return; }
    clickQueue.current?.enqueue({ blockId, action, ...(action === 'confirm' ? { labelId: selectedId! } : {}) });
  };
  useEffect(() => {
    if (seenRefresh.current === refreshVersion || busy) return;
    seenRefresh.current = refreshVersion;
    setExportStale(true);
    const ticket = loadTicket.current;
    void execute(async () => {
      const loaded = await api.getSuperpixels(id);
      if (!alive.current || ticket !== loadTicket.current) return;
      applyRead(loaded);
      const current = await drafts.get(id);
      if (alive.current) setDraftRevision(current.revision);
      if (alive.current) setQuality(null);
    }, '已同步助手执行后的标注状态。', true);
  }, [refreshVersion, busy, id]);
  const edit = async (action: 'confirm' | 'uncertain' | 'erase', target = geometry) => {
    if (!ready || !target) { setError('先生成超像素并选中候选，或完成一个多边形。'); return false; }
    if (action === 'confirm' && !selectedId) { setError('请先选择一个已登记标签。'); return false; }
    setExportStale(true);
    setQuality(null);
    const succeeded = await execute(() => api.regions(id, target, action, action === 'confirm' ? selectedId! : undefined),
      action === 'confirm' ? '区域已确认；工作图与统计已读回。' : action === 'uncertain' ? '区域已记为不确定（-2）。' : '区域已擦除；候选队列由 sidecar 保留。');
    if (succeeded) { setDraft(null); setQuality(null); }
    return succeeded;
  };
  const refreshReview = async () => {
    if (!ready) return false;
    return execute(async () => {
      const result = await api.validate(id);
      if (alive.current) setQuality(result);
    }, '质量校验与谱线复核已刷新。');
  };
  const reviewBlockErase = (blockId: number) => eraseAndRefresh(blockId,
    block => edit('erase', { superpixels: [block] }), refreshReview);
  const generate = async () => {
    setQuality(null);
    const ticket = loadTicket.current;
    if (await execute(async () => {
      await api.superpixels(id, { ...parameters, force });
      if (!alive.current || ticket !== loadTicket.current) return;
      const loaded = await api.getSuperpixels(id);
      if (!alive.current || ticket !== loadTicket.current) return;
      if (loaded.status !== 'ready') throw new Error('已提交分割当前不可读，请核查后重试。');
      applyRead(loaded);
    }, '分割已准备并持久化；像素标注和撤销保留。分割引用变化时，旧候选与手势已失效。')) { setDraft(null); setQuality(null); setLastSeed(null); setLastDiffusion(null); }
  };
  const diffuse = async (seed: Seed) => {
    if (!ready || !validThresholds) return;
    let admitted = false;
    await execute(async () => {
      const gesture = await drafts.storeGesture(id, seed);
      if (!alive.current) return;
      setLastGestureRef(gesture.gesture_ref); setLastSeed(seed); setDraft(null);
      const result = await api.diffuse(id, seed, { threshold, queue_min_similarity: queueMinimum });
      admitted = result.enqueued;
      if (alive.current) setLastDiffusion({ min: result.candidate.min_similarity, enqueued: result.enqueued, blocked: result.not_queued_reasons.below_queue_min_similarity });
      // Do not store result.queue: the subsequent GET working owns rendering.
    }, '扩散完成；右栏与高亮已按 working.queue 刷新。', false, next => {
      if (admitted && next.queue.length) setSelectedKey(candidateKey(next.queue[next.queue.length - 1]));
    });
  };
  const save = async (): Promise<boolean> => {
    if (!hasLabels) { setError('本图尚无已标注像素，请先确认标签后再保存并聚合。'); postSave.current = null; return false; }
    if (Array.from(note).length > 2000) { setError('保存备注超过 2000 字符，请缩短后再保存并聚合。'); postSave.current = null; return false; }
    if (!ready) { setError('工作态尚未成功读回，请先刷新后再保存并聚合。'); postSave.current = null; return false; }
    const saved = await execute(async () => {
      const result = await api.save(id, { ...(note ? { note } : {}) });
      if (alive.current) { setQuality(result.quality); setExportResult(result.export); setExportStale(false); }
    }, '当前标注已保存并聚合样本谱。', true);
    const after = postSave.current;
    postSave.current = null;
    after?.(saved);
    return saved;
  };
  const canNavigate = (delta: number) => {
    const target = navigationRecords[position + delta];
    return !draft && !busyRef.current && synchronized && position >= 0 && !!target
      && (!batch || batch.onDemand || batch.readyCubeIds.includes(target.id));
  };
  const navigate = (delta: number) => {
    if (draft) { setError('请先确认或清除尚未提交的区域，再切换图片。'); return; }
    if (canNavigate(delta)) onNavigate(navigationRecords[position + delta]);
  };
  const saveAndNavigate = (delta: number) => {
    if (draft) { setError('请先确认或清除尚未提交的区域，再切换图片。'); return; }
    if (!canNavigate(delta)) return;
    postSave.current = saved => {
      if (saved && canNavigate(delta)) {
        // The parent navigation guard is updated by a React effect, so it is
        // still "busy" on the tick execute() resolves. Release it synchronously
        // or App.openDataset rejects this post-save switch (save succeeds but
        // the workbench stays on the same image).
        guardCallback.current?.(false);
        onNavigate(navigationRecords[position + delta]);
      }
    };
    void save();
  };
  const leaveWorkbench=(leave?:()=>void)=>{
    if(busyRef.current)return;
    if(draft){setError('请先确认或清除尚未提交的区域，再离开工作台。');return;}
    leave?.();
  };
  const chooseTool = (next: Tool) => { setTool(next); setDraft(null); if (next === 'brush') setPrompt('doodle'); else if (next === 'diffuse') { setTab('diffuse'); setPrompt('point'); } };
  const undo = async () => { setQuality(null); setExportStale(true); if (await execute(() => api.undo(id), '已撤销一步；统计与工作图来自恢复后的 sidecar。')) setDraft(null); };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest('dialog')) return;
      const editing = target instanceof HTMLElement && !!target.closest('input,textarea,select,[contenteditable="true"]');
      const action = resolveShortcut(event, labels, preferences, editing);
      if (!action || (busyRef.current && !clickingRef.current)) return;
      if ('labelId' in action) { event.preventDefault(); setSelectedId(action.labelId); return; }
      if (busyRef.current) return;
      if (event.repeat && action.command !== 'pan') return;
      event.preventDefault();
      switch (action.command) {
        case 'confirm': void edit('confirm'); break;
        case 'undo': void undo(); break;
        case 'save': postSave.current = null; void save(); break;
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
    if (!await execute(() => api.addLabel(body), '标签已新建；已从后端重新读取标签与工作态。', true)) throw new Error('新建未完成，请查看工作台错误详情。');
    setQuality(null);
  };
  const deleteLabel = async (labelId: string) => {
    if (!await execute(() => api.deleteLabel(labelId), '标签已永久删除。', true)) throw new Error('删除未完成，请查看工作台错误详情。');
    setSelectedId(previous => previous === labelId ? null : previous);
    setQuality(null); setExportStale(true);
  };
  return <section className="annotation-workbench ui-page" aria-label="S05 标注工作台">
    <header className="annotation-heading">
      <div><h2>标注工作台 <small>{displayName(record)}</small></h2><p>{projectName || '读取项目中…'} · L1 辅助标注</p></div>
      {batch && <div className="annotation-hint" aria-label="临时标注批次">
        <p>本次范围 · 就绪 {batch.readyCubeIds.length} / {batch.memberCount} · 当前 {displayName(record)}</p>
        <button disabled={busy} onClick={()=>leaveWorkbench(onReturnToAssistant)}>返回助手</button>
        <label>{batch.onDemand?'本次标注范围':'本批就绪样品'}<select value={id} disabled={busy || position < 0} onChange={event => {
          const target = navigationRecords.find(item => item.id === event.target.value);
          if(draft){setError('请先确认或清除尚未提交的区域，再切换图片。');return;}
          if (!busyRef.current && synchronized && target && (batch.onDemand || batch.readyCubeIds.includes(target.id))) onNavigate(target);
        }}>{navigationRecords.map((item, index) => <option key={item.id} value={item.id}>批内 {index + 1} · {displayName(item)}</option>)}</select></label>
      </div>}
      <ol className="annotation-levels" aria-label="标注层级，当前 L1">{['L0 手工', 'L1 辅助 · 当前', 'L2 半自动', 'L3 自动+抽检', 'L4 自动闭环'].map((level, i) => <li key={level} aria-current={i === 1 ? 'step' : undefined}>{level}</li>)}</ol>
    </header>
    <div className={`annotation-json-status annotation-json-status-${badge.tone}`} role="status" aria-live="polite" aria-label="本图标注状态">
      <strong className="annotation-json-status-label">{badge.label}</strong>
      <span className="annotation-json-status-detail">{badge.detail}</span>
    </div>
    <p className="annotation-note">机器只给候选区域，不赋标签。L2 的簇命名、历史迁移与自动赋标属阶段二；当前先积累人工确认的标注。</p>
    <div className="annotation-status"><p role="status">{message}</p><button disabled={busy} onClick={() => { void refreshWorkState(); }}>刷新工作态</button><button onClick={() => setHelp(!help)}>快捷键 / 设置</button></div>
    {error && <pre className="annotation-error" role="alert">{error}</pre>}
    {batch && !busy && !batchReady && <p className="annotation-warning" role="alert">当前批次分割已失效或参数已变化，点选暂不可用。请返回助手重新核验，或按单图流程核查后重试。</p>}
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
        {working && <LabelPanel labels={labels} projectId={working.project_id} selectedId={selectedId}
          disabled={busy} allowSelection={clicking} onSelect={setSelectedId} onAdd={addLabel} onDelete={deleteLabel} />}
        <section className="annotation-card"><h3>工具</h3><div className="annotation-tools">{(['diffuse', 'click', 'brush', 'polygon', 'erase'] as const).map(next =>
          <button key={next} disabled={busy} className={tool === next ? 'selected' : ''} aria-pressed={tool === next} onClick={() => chooseTool(next)}>{commandNames[next]} <kbd>{preferences.bindings[next]}</kbd></button>)}</div></section>
        <section className="annotation-card"><h3>本图统计</h3><dl className="annotation-statistics">
          <dt>超像素数</dt><dd>{working?.superpixel_count ?? '—'}</dd><dt>已确认</dt><dd>{stats ? `${stats.labeled_percent.toFixed(2)}%` : '—'}</dd>
          <dt>不确定</dt><dd>{stats ? `${stats.uncertain_percent.toFixed(2)}%` : '—'}</dd><dt>留白</dt><dd>{stats ? `${stats.blank_percent.toFixed(2)}%` : '—'}</dd>
          <dt>待确认（并集）</dt><dd>{stats?.pending_pixels.toLocaleString() ?? '—'} px</dd>
        </dl>{stats && <div className="annotation-progress" role="progressbar" aria-label="已标注像素占比" aria-valuenow={Number(stats.labeled_percent.toFixed(2))} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${Math.max(0, Math.min(100, stats.labeled_percent))}%` }} /></div>}<p className="annotation-hint">统计来自 sidecar 当前工作态；未分割时为空态。</p>
        </section>
      </aside>
      <div className="annotation-center">
        <section className="annotation-card">
          <div className="annotation-tabs" role="tablist" aria-label="标注分段">{([['superpixels', '超像素'], ['diffuse', '扩散'], ['prompt', '提示分割'], ['review', '谱线复核']] as const).map(([value, title]) =>
            <button role="tab" key={value} aria-selected={tab === value} disabled={busy || (value === 'review' && !ready)} onClick={() => { setTab(value); setDraft(null); if (value === 'review') { void refreshReview(); } else if (value !== 'superpixels') { setTool('diffuse'); setPrompt(value === 'diffuse' ? 'point' : 'box'); } }}>{title}</button>)}</div>
          {tab === 'review' ? <SpectrumReview quality={quality} labels={labels} bands={record.dataset.shape[2]} wavelengths={record.dataset.wavelengths}
            disabled={busy || !ready} onRefresh={() => { void refreshReview(); }} onBlockErase={blockId => { void reviewBlockErase(blockId); }} /> : <>
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
            <label>入队下限（默认 0.60）<input type="number" min={-1} max={1} step="any" value={queueMinimum} disabled={busy} onFocus={() => { minimumOnFocus.current = queueMinimum; }} onChange={event => setQueueMinimum(Number(event.target.value))} onBlur={() => { if (lastSeed && validThresholds && minimumOnFocus.current !== queueMinimum) void diffuse(lastSeed); }} /></label>
            <label>提示方式<select disabled={busy} value={prompt} onChange={event => { setPrompt(event.target.value as PromptMode); setTool('diffuse'); setTab('prompt'); }}><option value="point">单击</option><option value="box">框选</option><option value="doodle">涂鸦</option></select></label>
          </div>
          <p className="annotation-hint">已有种子时，阈值输入完成、移出输入框即重新扩散预览；也可点击“扩散到相似区域”。</p>
          {lastGestureRef && <p className="annotation-hint">最近的画布提示已自动带入对话，可直接说“用刚才的提示”。</p>}
          {draftRevision === 0 && <p className="annotation-hint">当前无标注草稿：手势需先建立首个标注（画布多边形或运行扩散）</p>}
          {!validThresholds && <p className="annotation-warning">两项余弦阈值都须为 [-1,1] 内的有限数。</p>}
          {lastDiffusion && <p className={lastDiffusion.enqueued ? 'annotation-hint' : 'annotation-warning'}>本次候选最小种子相似度 {lastDiffusion.min.toFixed(4)} · {lastDiffusion.enqueued ? '已入队' : `被护栏拦下，未入队 ${lastDiffusion.blocked} 项`}。</p>}
          <details className="annotation-hint"><summary>默认值与相似度口径</summary>SLIC 默认值来自 TASK-04 §5.2（11 cube 标定 compactness=0.5）；扩散默认 0.92 来自需求场景 S1；入队默认 0.60（原 0.80 来自 UI 原型 S05，2026-10-29 实测下调）。增长比较邻接对原谱均值；报告比较种子原谱。均为可调默认值。</details>
          {dirty && <p className="annotation-warning">参数已改，先重新生成超像素；已有标注按像素保留。</p>}
          {!busy && !synchronized && <p className="annotation-warning">工作态尚未成功读回，请先刷新；编辑暂不可用。</p>}
          <DisplayToolbar bands={record.dataset.shape[2]} wavelengths={record.dataset.wavelengths} band={displayBand} onBand={setDisplayBand}
            mode={displayMode} onMode={setDisplayMode} rgb={displayRgb} onRgb={setDisplayRgb}
            stretch={displayStretch} onStretch={setDisplayStretch} lut={displayLut} onLut={next => setDisplayLut(previous => changeLut(previous, next))}
            inspection={inspection} onInspection={setInspection} />
          {displayError && <p role="alert">{displayError}</p>}
          {base?.bands && <p>伪彩 {(['R', 'G', 'B'] as const).map((channel, i) => `${channel}${base.wavelengths?.[i] === undefined ? `#${base.bands![i]}` : `${base.wavelengths[i]} nm`}`).join(' / ')}{base.fallback ? '（自动退化）' : ''}</p>}
          <AnnotationCanvas shape={record.dataset.shape} base={base} segmentation={segmentation} segments={segments} labels={labels} working={working} selectedKey={selectedKey}
            manualStretch={displayStretch === 'manual'} lut={displayLut}
            inspection={inspection} onSpectrum={region => { void readSpectrum(region); }}
            tool={tool} prompt={prompt} disabled={busy || !ready} panHeld={panHeld} draft={draft} brushPrompt={tab === 'prompt'}
            blockClicksEnabled={ready && (!busy || clicking)} pendingClicks={pendingClicks}
            onSeed={seed => { void diffuse(seed); }} onGeometry={value => { setDraft(value); setSelectedKey(null); setMessage('多边形已选；选择标签后确认，或标记为不确定。'); }}
            onErase={value => { void edit('erase', value); }}
            onBlockClick={(blockId, uncertain) => editBlock(blockId, uncertain ? 'uncertain' : 'confirm')}
            onBlockErase={blockId => editBlock(blockId, 'erase')} />
          {pendingClicks.length > 0 && <p role="status">正在同步 {pendingClicks.length} 次点击，可继续点选或切换标签。斜纹是待同步预览，统计以后台读回为准；同步完成后再保存、撤销、切图或退出。</p>}
          {spectrumBusy && <p role="status">正在读取光谱…</p>}{spectrumError && <p role="alert">{spectrumError}</p>}
          {spectrum && <SpectrumReadout spectrum={spectrum} wavelengths={record.dataset.wavelengths} />}
          <div className="annotation-actions">
            <button className="annotation-primary" disabled={busy || !ready || !geometry || !selectedId} onClick={() => { void edit('confirm'); }}>确认选中候选 / 区域</button>
            <button disabled={busy || !ready || !lastSeed || !validThresholds} onClick={() => { if (lastSeed) void diffuse(lastSeed); }}>扩散到相似区域（按当前阈值）</button>
            <button disabled={busy || !ready || !geometry} onClick={() => { void edit('uncertain'); }}>标记“不确定”</button>
            <button disabled={busy} onClick={() => { void undo(); }}>撤销一步</button>
          </div>
          <nav className="annotation-navigation" aria-label="切换数据集">
            <button disabled={busy || position <= 0} onClick={() => navigate(-1)}>← 上一张</button>
            <span>{batch ? '批内 ' : ''}{position + 1} / {navigationRecords.length} · {displayName(record)}</span>
            <span style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button disabled={busy || position < 0 || position >= navigationRecords.length - 1} onClick={() => navigate(1)}>下一张 →</button>
              <button className="annotation-primary" disabled={busy || !ready || !hasLabels || !canNavigate(1)} onClick={() => saveAndNavigate(1)}>保存并下一张 →</button>
            </span>
          </nav>
          </>}
        </section>
        <section className="annotation-card" aria-label="保存与校验">
          <details style={{ fontSize: 13 }}>
            <summary>保存与校验</summary>
            <label>备注（可选，≤2000 字符）<textarea value={note} onChange={event => setNote(event.target.value)} /></label>
            <p role="status">JSON 投影：{exportResult && !exportResult.ok ? '失败' : exportStale ? '过期' : '最新'}<small> · 仅表示本次工作态与已保存投影的相对新旧，不代表文件是否存在</small></p>
            {exportResult?.path && <div><label>JSON 绝对路径<textarea aria-label="JSON 绝对路径" rows={3} readOnly value={exportResult.path} onFocus={event => event.currentTarget.select()} /></label>
              <button disabled={busy} onClick={() => { void invoke('open_exports_directory', { cubeId: id }).catch(() => setError('无法打开 JSON 所在文件夹。')); }}>打开所在文件夹</button></div>}
            {exportResult && !exportResult.ok && exportResult.error && <p role="alert" className="annotation-error" style={{ color: '#a12622' }}>标注已保存；JSON 投影失败：{exportResult.error}。请再次保存以重试导出。</p>}
            <button disabled={busy || !ready} onClick={() => { void refreshReview(); }}>校验当前工作态</button>
            {quality && <div className="annotation-quality"><h4>质量校验 · 当前原谱均值</h4><p>余弦阈值 {quality.threshold}（{quality.threshold_level}）· 可疑 {quality.suspicious.length} 项 · 高方差 {quality.high_variance.superpixel_ids.length} 项</p>
              <p className="annotation-hint">{quality.reference}</p><ul>{quality.suspicious.map(item => <li key={`${item.superpixel_id}:${item.label_index}`}>#{item.superpixel_id} · {labels[item.label_index]?.code} · {item.pixel_count} px · cos {formatReviewCos(item.cos)}</li>)}</ul>
              <p>高方差超像素：{quality.high_variance.superpixel_ids.join('、') || '无'}；τ={formatReviewNumber(quality.high_variance.tau)}</p>
              {Object.entries(quality.not_applicable).map(([name, reason]) => <p key={name}>{name}：{reason}</p>)}
            </div>}
          </details>
        </section>
      </div>
      <CandidateQueue working={working} labels={labels} selectedKey={selectedKey} disabled={busy || !ready} canSave={hasLabels}
        onSelect={key => { setSelectedKey(key); setDraft(null); }} onSave={() => { postSave.current = null; void save(); }} />
    </div>
  </section>;
}
