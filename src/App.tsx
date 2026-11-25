import { useCallback, useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { acceptSnapshot, type ExitReason, type Snapshot } from './status';
import './ui/tokens.css';
import './ui/components.css';
import DatasetPanel from './components/datasets/DatasetPanel';
import { datasets } from './components/datasets/api';
import Composer from './components/assistant/Composer';
import useSession from './components/assistant/useSession';
import S01 from './screens/S01';
import S04 from './screens/S04';
import S08 from './screens/S08';
import S02 from './screens/S02';
import S09 from './screens/S09';
import S10 from './screens/S10';
import S11 from './screens/S11';
import { modeling } from './components/modeling/api';
import TrainingTaskDock from './components/modeling/TrainingTaskDock';
import { failureMessage } from './components/modeling/chart';
import type { CatalogRecord, DatasetRecord, DatasetReference } from './components/datasets/types';
import { describeError } from './components/datasets/types';
import { createCatalogController, emptyCatalog } from './components/datasets/catalog';
import ProjectPathsPanel from './components/settings/ProjectPathsPanel';
import AnnotationWorkbench from './components/annotation/AnnotationWorkbench';
import ProjectLabels from './components/annotation/ProjectLabels';
import PreprocessWorkspace from './components/preprocess/PreprocessWorkspace';
import ModelPanel from './components/modeling/ModelPanel';
import AppShell from './shell/AppShell';
import { SCREEN_TITLE, type Screen } from './shell/screens';
import type { WorkspaceContext, BatchScope } from './components/assistant/api';
import { selectWorkspace, workspaceDisplay, type WorkspaceDisplay } from './components/assistant/presentation';
import type { WorkspaceEventData } from './components/assistant/sse';

const reasons: Record<string, string> = {
  SpawnFailed: '无法启动引擎，请检查程序文件是否完整。',
  JobSetupFailed: '无法建立引擎进程保护。', ResumeFailed: '无法恢复引擎主线程。',
  ProcessIdentityFailed: '无法确认引擎进程身份。', ExitedBeforeReady: '引擎在就绪前退出，请检查程序文件与日志。',
  HandshakeInvalid: '握手文件校验失败，请通过数据目录检查文件并查看日志。',
  StartupTimeout: '引擎启动超过 30 秒，请查看日志。', HealthIdentityMismatch: '引擎健康响应身份不匹配。',
  SmokeIdentityMismatch: '冒烟响应身份不匹配，已停止连接。', EngineExitedAfterReady: '引擎意外退出。',
};
const initial: Snapshot = { generation_id: 0, phase: 'Starting', pid: null, port: null, boot_id: null, failure: null, cleanup_complete: false };

function reasonCode(reason: ExitReason): string {
  if (typeof reason === 'string') return reason === 'StartupDeadline' ? '启动超时' : '工作线程不可用';
  if ('ProcessExit' in reason) return `退出码：${reason.ProcessExit.code}`;
  if ('Win32' in reason) return `Win32 错误码：${reason.Win32.code}（${reason.Win32.api}）`;
  return `身份校验：${reason.IdentityMismatch.layer}`;
}

export default function App() {
  const [status, setStatus] = useState<Snapshot>(initial);
  const [shellError, setShellError] = useState('');
  const [workspace, setWorkspace] = useState<WorkspaceContext>({});
  const [records, setRecords] = useState<CatalogRecord[]>([]);
  const [catalog, setCatalog] = useState(emptyCatalog);
  const [catalogController] = useState(() => createCatalogController(datasets, next => { setRecords(next.records); setCatalog(next); }));
  const [refreshVersions, setRefreshVersions] = useState<Record<string, number>>({});
  const [navigation, setNavigation] = useState<WorkspaceEventData | null>(null);
  const [annotationBatch, setAnnotationBatch] = useState<BatchScope | null>(null);
  const annotationBatchRef = useRef<BatchScope | null>(null);
  const [workspaceName, setWorkspaceName] = useState('');
  const [previewCandidates, setPreviewCandidates] = useState<Record<string, string>>({});
  const [screen, setScreen] = useState<Screen>('s03');
  const [selected, setSelected] = useState<DatasetRecord | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [dashboardRuns, setDashboardRuns] = useState<Awaited<ReturnType<typeof modeling.runs>>>([]);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState('');
  const [navigationError, setNavigationError] = useState('');
  const [opening, setOpening] = useState(false);
  const openingTicket = useRef(0);
  const annotationNavigationBlocked=useRef(false);
  const localDisplay = useRef<WorkspaceDisplay>({});
  const changeWorkspace = useCallback((next: WorkspaceContext) => {
    localDisplay.current = workspaceDisplay(localDisplay.current, next, catalogController.snapshot().records);
    setWorkspace(current => selectWorkspace(current, next)); setNavigation(null); setWorkspaceName(localDisplay.current.display_name ?? '');
    setSelected(current => current?.id === next.cube_id ? current : null);
  }, [catalogController]);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const session = useSession({ enabled: status.phase === 'Ready', generation: status.generation_id, bootId: status.boot_id,
    workspace, records, displayName: workspaceName, onWorkspaceChange: changeWorkspace,
    onSessionReset: () => {
      openingTicket.current++; setOpening(false); setSelected(null); setPreviewCandidates({});
      setNavigation(null); setNavigationError(''); setWorkspaceName(''); localDisplay.current={}; setScreen('s01');
    },
    onWorkspaceDisplayChange: selection => {
      localDisplay.current = workspaceDisplay(localDisplay.current, selection, catalogController.snapshot().records);
      setWorkspaceName(localDisplay.current.display_name ?? '');
    },
    onWorkspaceNavigate: selection => {
      if(annotationNavigationBlocked.current){setNavigationError('请先完成当前标注提交，或确认、清除未提交的区域后再导航。');return;}
      annotationBatchRef.current = null; setAnnotationBatch(null); setNavigation(selection);
    },
    onBatchReset: () => { annotationBatchRef.current = null; setAnnotationBatch(null); },
    onBatchOpen: scope => {
      if (scope.generation !== statusRef.current.generation_id || statusRef.current.phase !== 'Ready') return;
      if(annotationNavigationBlocked.current){setNavigationError('请先完成当前标注提交，或确认、清除未提交的区域后再打开任务。');return;}
      const target = scope.result.openCubeId;
      if (!target || !scope.result.readyMembers.some(item => item.cubeId === target)) return;
      annotationBatchRef.current = scope; setAnnotationBatch(scope);
      setNavigation({ cube_id: target, stage: 'annotation' });
    },
    onPreviewCandidate: (cubeId, candidateRef) => setPreviewCandidates(current => ({ ...current, [cubeId]: candidateRef })),
    onDataChanged: cubeIds => setRefreshVersions(current => {
      const next = { ...current };
      for (const cubeId of cubeIds) next[cubeId] = (next[cubeId] ?? 0) + 1;
      return next;
    }) });
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const statusRef = useRef(status);
  statusRef.current = status;
  const openDataset = useCallback(async (id: string, nextScreen: Screen) => {
    if (statusRef.current.phase !== 'Ready') return;
    if(annotationNavigationBlocked.current){setNavigationError('请等待标注提交完成，并确认或清除未提交的区域后再切换。');return;}
    const startingSession = sessionRef.current.active?.id;
    const selectionEpoch = sessionRef.current.selectionEpoch;
    if (sessionRef.current.state.busy || sessionRef.current.loading) return;
    if (sessionRef.current.active) {
      const accepted=await sessionRef.current.selectCube(id);
      if (!accepted) return;
    }
    if (startingSession!==sessionRef.current.active?.id) return;
    const batch = annotationBatchRef.current;
    if (nextScreen === 's05' && batch && (batch.generation !== statusRef.current.generation_id
        || !(batch.onDemand ? batch.targetCubeIds?.includes(id) : batch.result.readyMembers.some(item => item.cubeId === id)))) {
      setNavigationError('目标不在当前批次就绪集合中，已停止打开。'); return;
    }
    if (catalogController.snapshot().phase !== 'ready') { setNavigationError('请等待数据目录加载完成，或重新加载后再打开。'); return; }
    const ticket = ++openingTicket.current, generation = statusRef.current.generation_id;
    const acceptedEpoch = sessionRef.current.currentEpoch();
    const current = () => ticket === openingTicket.current && generation === statusRef.current.generation_id
      && statusRef.current.phase === 'Ready' && startingSession === sessionRef.current.active?.id
      && sessionRef.current.isCurrentEpoch(acceptedEpoch) && (selectionEpoch<=acceptedEpoch);
    setOpening(true); setNavigationError(''); setSelected(null);
    try {
      await catalogController.refreshNames([id]);
      if (!current()) return;
      const latest = catalogController.snapshot();
      if (latest.phase !== 'ready') throw new Error(latest.error || '无法核验数据目录，请重试。');
      const row = latest.records.find(record => record.id === id);
      if (!row?.available) throw new Error('源文件不可用，已停止打开工作台；请检查源文件后重新加载。');
      const detail = await datasets.get(id);
      if (!current()) return;
      if (detail.id !== id) throw new Error('读取的数据与选择不一致，请重试。');
      changeWorkspace({ cube_id: id }); setSelected({ ...detail, display_name: row.display_name }); setScreen(nextScreen);
    } catch (failure) { if (current()) { setNavigationError(describeError(failure)); setScreen('s03'); } }
    finally { if (current()) setOpening(false); }
  }, [catalogController, changeWorkspace]);
  useEffect(() => {
    setShellError('');
    setWorkspace({}); setRecords([]); setRefreshVersions({}); setNavigation(null); setWorkspaceName(''); setPreviewCandidates({});
    localDisplay.current = {};
    annotationBatchRef.current = null; setAnnotationBatch(null);
    setScreen('s03'); setSelected(null); setNavigationError('');
    openingTicket.current++; setOpening(false); catalogController.reset(status.generation_id);
  }, [status.generation_id, catalogController]);
  useEffect(() => {
    if (status.phase !== 'Ready') return;
    void catalogController.load(status.generation_id);
    return () => catalogController.cancel();
  }, [status.phase, status.generation_id, catalogController]);
  useEffect(() => {
    localDisplay.current = workspaceDisplay(localDisplay.current, localDisplay.current, records);
    setWorkspaceName(localDisplay.current.display_name ?? '');
    setSelected(current => {
      if (!current) return current;
      const row = records.find(record => record.id === current.id);
      return row?.available ? { ...current, display_name: row.display_name } : null;
    });
  }, [records]);
  useEffect(() => {
    let disposed = false;
    const accept = (next: Snapshot) => {
      if (disposed) return;
      setStatus(previous => acceptSnapshot(previous, next));
    };
    // Subscribe before snapshot to cover the startup/registration race.
    const subscription = listen<Snapshot>('engine-status', event => accept(event.payload));
    void subscription.then(() => invoke<Snapshot>('engine_status')).then(accept)
      .catch(() => { if (!disposed) setShellError('无法读取外壳状态，请查看日志。'); });
    return () => { disposed = true; void subscription.then(unlisten => unlisten()); };
  }, []);
  useEffect(() => {
    if (!navigation) return;
    if (navigation.stage !== 'annotation') { setNavigation(null); return; }
    void openDataset(navigation.cube_id, 's05');
  }, [navigation, openDataset]);
  useEffect(() => {
    if (screen !== 's02' || status.phase !== 'Ready') return;
    let live = true;
    setDashboardLoading(true); setDashboardError(''); setDashboardRuns([]);
    void modeling.runs().then(rows => { if (live) setDashboardRuns(rows.filter(row => row.task === 'regression')); })
      .catch(failure => { if (live) setDashboardError(failureMessage(failure)); })
      .finally(() => { if (live) setDashboardLoading(false); });
    return () => { live = false; };
  }, [screen, status.phase, status.generation_id]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (screen === 's01' || !event.ctrlKey || status.phase !== 'Ready') return;
      if (event.target instanceof Element && event.target.closest('.composer')) return;
      if (event.key.toLowerCase() === 'k') { event.preventDefault(); composerInput.current?.focus(); }
      if (event.key === 'Enter') { event.preventDefault(); void session.request({ content: session.content }); }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  });
  if (status.phase === 'Starting') return <div className="app" data-phase="Starting">
    <main className="failure-page" aria-busy="true">
      <h1>光谱数据 AI Agent</h1>
      <section role="status" aria-live="polite"><h2>正在启动本地工作台…</h2>
        <p>正在加载本地数据与处理服务，就绪后即可继续操作。</p>
      </section>
      {shellError && <p role="alert">{shellError}</p>}
    </main>
  </div>;
  const failure = status.failure;
  if (status.phase === 'Failed') return <div className="app" data-phase={status.phase}>
    <main className="failure-page">
      <h1>光谱数据 AI Agent</h1>
      <section role="alert">
        <h2>引擎启动或运行失败</h2>
        <p>{failure ? reasons[failure.kind] ?? '引擎发生错误，请查看日志。' : '无法获取失败详情，请查看日志。'}</p>
        {failure && <>
          <p>{reasonCode(failure.exit_reason)}</p>
          {failure.engine_error && <p>引擎短码：{failure.engine_error}</p>}
          <p>握手路径：<code>{failure.handshake_path}</code></p>
          <p>日志路径：<code>{failure.log_path}</code></p>
          <p>数据目录：<code>{failure.data_directory}</code></p>
        </>}
        <button disabled={!status.cleanup_complete} onClick={() => { void invoke('retry_engine').catch(() => setShellError('重试未执行，请查看日志。')); }}>重试</button>
        <button onClick={() => { void invoke('open_data_directory').catch(() => setShellError('无法打开数据目录。')); }}>打开数据目录</button>
        {shellError && <p role="alert">{shellError}</p>}
        {!status.cleanup_complete && <p>上一代引擎尚未完成清理，暂不能重试。</p>}
      </section>
    </main>
  </div>;
  if (status.phase === 'Stopping') return <p role="status">正在关闭</p>;

  const navigationSession = session.active?.id;
  const navigationEpoch = session.currentEpoch();
  const navigationGeneration = status.generation_id;
  const navigationCurrent = () => navigationSession === sessionRef.current.active?.id
    && navigationGeneration === statusRef.current.generation_id && sessionRef.current.isCurrentEpoch(navigationEpoch);
  const openScreen = (next: Screen, record?: DatasetReference, run?: string) => {
    if (!navigationCurrent()) return;
    if(annotationNavigationBlocked.current){setNavigationError('请等待标注提交完成，并确认或清除未提交的区域后再切换。');return;}
    openingTicket.current++; setOpening(false);
    setNavigation(null); setNavigationError('');
    if (next === 's04' || next === 's05' || next === 's06') { annotationBatchRef.current = null; setAnnotationBatch(null); }
    if (run !== undefined) setRunId(run);
    if (next === 's06' && record) { void openDataset(record.id, next); return; }
    if (next === 's04' || next === 's05') {
      const id = record?.id ?? workspace.cube_id ?? selected?.id ?? records.find(row => row.available)?.id;
      if (id) { void openDataset(id, next); return; }
      setSelected(null);
    }
    if (session.state.busy && ['s04','s05','s06','s07'].includes(next)) return;
    setScreen(next);
  };
  const renderScreen = () => {
    switch (screen) {
      case 's01': return <S01 session={session} />;
      case 's03': return <>
        <p role="status">引擎已就绪</p>
        <p>选择数据目录，查看数据集与单波段预览。</p>
        <p>进程 {status.pid} · 端口 {status.port} · 启动代次 {status.generation_id}</p>
        <ProjectPathsPanel key={`paths-${status.generation_id}`} />
        <DatasetPanel key={status.generation_id} api={datasets} records={records} phase={catalog.phase} error={catalog.error}
          onReload={() => { void catalogController.load(status.generation_id); }} onImported={rows => catalogController.imported(rows)}
          onDeleted={async id => {
            catalogController.remove(id);
            if (workspace.cube_id === id) { changeWorkspace({}); void session.selectCube(null); }
            setSelected(current => current?.id === id ? null : current);
            await catalogController.refreshNames();
          }} onOpen={openScreen} />
      </>;
      case 's04': return selected ? <S04 key={selected.id} record={selected} api={datasets} onClose={() => setScreen('s03')} />
        : <section aria-label="S04 数据查看器"><p>请先在数据屏选择数据集。</p><button onClick={() => setScreen('s03')}>返回数据屏</button></section>;
      case 's05': return selected ? <AnnotationWorkbench key={selected.id} record={selected}
        records={annotationBatch ? (annotationBatch.targetCubeIds??annotationBatch.result.readyMembers.map(item=>item.cubeId)).flatMap(id => records.filter(row => row.id === id && row.available)) : records.filter(row => row.available)} datasets={datasets}
        batch={annotationBatch ? { datasetVersionId: annotationBatch.result.datasetVersionId, memberCount: annotationBatch.targetCubeIds?.length??annotationBatch.result.memberCount,
          readyCubeIds: annotationBatch.result.readyMembers.map(item => item.cubeId), onDemand:annotationBatch.onDemand } : undefined}
        prepareOnDemand={annotationBatch?.onDemand ? id=>session.prepareCube(id,annotationBatch.authorizationId) : undefined}
        onCanvasFocus={(id,focused)=>session.focusCanvas(id,focused)}
        onNavigationGuardChange={blocked=>{annotationNavigationBlocked.current=blocked;}}
        onReturnToAssistant={() => setScreen('s01')}
        onWorkspaceChange={next => { if (navigationCurrent()) changeWorkspace(next); }} refreshVersion={refreshVersions[selected.id] ?? 0}
        previewCandidateRef={previewCandidates[selected.id]}
        onNavigate={next => {
          if (!navigationCurrent()) return;
          if (annotationBatchRef.current && !(annotationBatchRef.current.onDemand ? annotationBatchRef.current.targetCubeIds?.includes(next.id) : annotationBatchRef.current.result.readyMembers.some(item => item.cubeId === next.id))) {
            setNavigationError('目标不在当前批次就绪集合中，已停止换图。'); return;
          }
          void openDataset(next.id, 's05');
        }} />
        : <ProjectLabels onOpenData={() => setScreen('s03')} />;
      case 's06': return <PreprocessWorkspace records={records} phase={catalog.phase} initialRecord={selected} refreshVersion={Object.values(refreshVersions).reduce((a,b)=>a+b,0)}/>;
      case 's07': return catalog.phase === 'ready' ? <ModelPanel records={records.filter(row => row.available)} onOpenResults={run => openScreen('s08', undefined, run)} />
        : <p role="status">请先返回数据屏加载数据目录。</p>;
      case 's08': return <S08 runId={runId} onOpen={id => openScreen('s08', undefined, id)} onBackToList={() => setRunId(null)} onClose={() => setScreen('s07')} />;
      case 's02': return <S02 records={records} runs={dashboardRuns} loading={dashboardLoading} error={dashboardError} status={status}
        onOpenData={() => openScreen('s03')} onOpenRun={id => openScreen('s08', undefined, id)} onContinueAnnotation={() => openScreen('s05')} />;
      case 's09': return <S09 records={records} />;
      case 's10': return <S10 onOpenData={() => openScreen('s03')} />;
      case 's11': return <S11 onBack={() => openScreen('s02')} />;
      default: return <section className="screen-placeholder" data-screen={screen} aria-label={`${SCREEN_TITLE[screen]}（后续批次启用）`}>
        <p>本屏在后续批次启用。</p>
        <button onClick={() => setScreen('s03')}>返回数据屏</button>
      </section>;
    }
  };
  return <div className="app" data-phase={status.phase}>
    <AppShell screen={screen} onNavigate={next => openScreen(next)} topActions={<>
      <span aria-label="产品版本">版本 {__SPECTRUM_PRODUCT_VERSION__}</span>
      <TrainingTaskDock ready={status.phase === 'Ready'} bootId={status.boot_id} onOpenResults={id => openScreen('s08', undefined, id)} />
      <button onClick={() => openScreen('s11')}>设置</button>
    </>} assistant={screen === 's01' ? null : <Composer session={session} screen={screen} inputRef={composerInput} onExpand={() => openScreen('s01')} />}>
      {(navigationError || shellError) && <pre role="alert">{navigationError || shellError}</pre>}
      {opening && <p role="status">正在核验源文件并读取数据详情…</p>}
      {renderScreen()}
    </AppShell>
  </div>;
}

