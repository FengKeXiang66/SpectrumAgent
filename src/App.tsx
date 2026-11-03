import { useCallback, useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { acceptSnapshot, type ExitReason, type Snapshot } from './status';
import DatasetPanel from './components/datasets/DatasetPanel';
import { datasets } from './components/datasets/api';
import Composer from './components/assistant/Composer';
import useSession from './components/assistant/useSession';
import S01 from './screens/S01';
import SettingsPanel from './components/settings/SettingsPanel';
import type { DatasetRecord } from './components/datasets/types';
import { describeError, mergeRecords } from './components/datasets/types';
import AnnotationWorkbench from './components/annotation/AnnotationWorkbench';
import PreprocessPanel from './components/preprocess/PreprocessPanel';
import ModelPanel from './components/modeling/ModelPanel';
import AppShell from './shell/AppShell';
import { SCREEN_TITLE, type Screen } from './shell/screens';
import type { WorkspaceContext } from './components/assistant/api';
import { selectWorkspace } from './components/assistant/presentation';
import type { WorkspaceEventData } from './components/assistant/sse';

type Metrics = { nan_ratio: number; reflectance_range: [number, number]; bands: number; shape: [number, number, number]; elapsed_ms: number };
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
  const [text, setText] = useState('');
  const [message, setMessage] = useState('输入“运行冒烟测试”，或点击发送。');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [workspace, setWorkspace] = useState<WorkspaceContext>({});
  const [records, setRecords] = useState<DatasetRecord[]>([]);
  const [refreshVersions, setRefreshVersions] = useState<Record<string, number>>({});
  const [navigation, setNavigation] = useState<WorkspaceEventData | null>(null);
  const [workspaceName, setWorkspaceName] = useState('');
  const [previewCandidates, setPreviewCandidates] = useState<Record<string, string>>({});
  const [screen, setScreen] = useState<Screen>('s03');
  const [selected, setSelected] = useState<DatasetRecord | null>(null);
  const [navigationError, setNavigationError] = useState('');
  const changeWorkspace = useCallback((next: WorkspaceContext) => {
    setWorkspace(current => selectWorkspace(current, next)); setNavigation(null); setWorkspaceName('');
    if (next.cube_id) setSelected(current => records.find(record => record.id === next.cube_id) ?? current);
  }, [records]);
  const composerInput = useRef<HTMLInputElement>(null);
  const session = useSession({ enabled: status.phase === 'Ready', generation: status.generation_id,
    workspace, records, displayName: workspaceName, onWorkspaceChange: changeWorkspace,
    onWorkspaceNavigate: selection => { setNavigation(selection); setWorkspaceName(selection.display_name ?? ''); },
    onPreviewCandidate: (cubeId, candidateRef) => setPreviewCandidates(current => ({ ...current, [cubeId]: candidateRef })),
    onDataChanged: cubeIds => setRefreshVersions(current => {
      const next = { ...current };
      for (const cubeId of cubeIds) next[cubeId] = (next[cubeId] ?? 0) + 1;
      return next;
    }) });
  const statusRef = useRef(status);
  statusRef.current = status;
  useEffect(() => {
    setBusy(false); setMetrics(null); setText('');
    setMessage('输入“运行冒烟测试”，或点击发送。');
    setWorkspace({}); setRecords([]); setRefreshVersions({}); setNavigation(null); setWorkspaceName(''); setPreviewCandidates({});
    setScreen('s03'); setSelected(null); setNavigationError('');
  }, [status.generation_id]);
  useEffect(() => {
    let disposed = false;
    const accept = (next: Snapshot) => {
      if (disposed) return;
      setStatus(previous => acceptSnapshot(previous, next));
    };
    // Subscribe before snapshot to cover the startup/registration race.
    const subscription = listen<Snapshot>('engine-status', event => accept(event.payload));
    void subscription.then(() => invoke<Snapshot>('engine_status')).then(accept)
      .catch(() => { if (!disposed) setMessage('无法读取外壳状态，请查看日志。'); });
    return () => { disposed = true; void subscription.then(unlisten => unlisten()); };
  }, []);
  useEffect(() => {
    if (!navigation) return;
    let cancelled = false;
    setNavigationError('');
    const show = (record: DatasetRecord) => {
      if (cancelled) return;
      setSelected(record);
      if (navigation.stage === 'annotation') setScreen('s05');
      else if (navigation.stage === 'preprocess') setScreen('s06');
      else setScreen(current => current === 's07' ? 's03' : current);
    };
    const record = records.find(item => item.id === navigation.cube_id);
    if (record) show(record);
    else {
      setScreen('s03'); setSelected(null);
      void datasets.get(navigation.cube_id).then(next => {
        if (cancelled) return;
        if (next.id !== navigation.cube_id) throw new Error('读取的数据与助手选择不一致，请重试。');
        setRecords(current => mergeRecords(current, [next])); show(next);
      }).catch(failure => { if (!cancelled) setNavigationError(describeError(failure)); });
    }
    return () => { cancelled = true; };
  }, [navigation, records]);
  const send = async () => {
    if (status.phase !== 'Ready' || busy) return;
    if (text.trim() && text.trim() !== '运行冒烟测试') {
      setMessage('当前地基演示仅支持冒烟测试');
      return;
    }
    const generation = status.generation_id;
    setBusy(true); setMetrics(null); setMessage('正在运行冒烟测试…');
    try {
      const result = await invoke<Metrics>('run_smoke');
      if (statusRef.current.generation_id === generation && statusRef.current.phase === 'Ready') {
        setMetrics(result); setMessage('冒烟测试完成。'); setText('');
      }
    } catch {
      if (statusRef.current.generation_id === generation) setMessage('冒烟测试未完成，请检查引擎状态与日志。');
    } finally {
      if (statusRef.current.generation_id === generation) setBusy(false);
    }
  };
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
  if (status.phase === 'Starting') return null;
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
        <button disabled={!status.cleanup_complete} onClick={() => { setMetrics(null); void invoke('retry_engine').catch(() => setMessage('重试未执行，请查看日志。')); }}>重试</button>
        <button onClick={() => { void invoke('open_data_directory').catch(() => setMessage('无法打开数据目录。')); }}>打开数据目录</button>
        {!status.cleanup_complete && <p>上一代引擎尚未完成清理，暂不能重试。</p>}
      </section>
    </main>
  </div>;
  if (status.phase === 'Stopping') return <p role="status">正在关闭</p>;

  const openScreen = (next: Screen, record?: DatasetRecord) => {
    setNavigation(null); setNavigationError('');
    if (record) setSelected(record);
    else if (next === 's05' || next === 's06') {
      setSelected(records.find(item => item.id === workspace.cube_id) ?? selected ?? records[0] ?? null);
    }
    setScreen(next);
  };
  const renderScreen = () => {
    switch (screen) {
      case 's01': return <S01 session={session} smoke={{ text, setText, message, busy, metrics, send }} />;
      case 's03': return <>
        <p role="status">引擎已就绪</p>
        <p>选择数据目录，查看数据集与单波段预览。</p>
        <p>进程 {status.pid} · 端口 {status.port} · 启动代次 {status.generation_id}</p>
        <DatasetPanel key={status.generation_id} api={datasets} records={records} onRecordsChange={setRecords}
          selectedRecord={selected} onWorkspaceChange={changeWorkspace} onOpen={openScreen} />
      </>;
      case 's05': return selected ? <AnnotationWorkbench key={selected.id} record={selected} records={records} datasets={datasets}
        onWorkspaceChange={changeWorkspace} refreshVersion={refreshVersions[selected.id] ?? 0}
        previewCandidateRef={previewCandidates[selected.id]}
        onNavigate={next => { setSelected(next); changeWorkspace({ cube_id: next.id }); }} onClose={() => setScreen('s03')} />
        : <section aria-label="S05 标注工作台"><p>请先在数据屏选择数据集。</p><button onClick={() => setScreen('s03')}>返回数据屏</button></section>;
      case 's06': return selected ? <PreprocessPanel key={selected.id} record={selected} refreshVersion={refreshVersions[selected.id] ?? 0} onClose={() => setScreen('s03')} />
        : <section aria-label="S06 预处理工作台"><p>请先在数据屏选择数据集。</p><button onClick={() => setScreen('s03')}>返回数据屏</button></section>;
      case 's07': return <ModelPanel records={records} onClose={() => setScreen('s03')} />;
      default: return <section className="screen-placeholder" data-screen={screen} aria-label={`${SCREEN_TITLE[screen]}（后续批次启用）`}>
        <p>本屏在后续批次启用。</p>
        <button onClick={() => setScreen('s03')}>返回数据屏</button>
      </section>;
    }
  };
  return <div className="app" data-phase={status.phase}>
    <AppShell screen={screen} onNavigate={next => openScreen(next)} topActions={<>
      <span aria-label="产品版本">版本 {__SPECTRUM_PRODUCT_VERSION__}</span>
      <button onClick={() => setSettingsOpen(true)}>设置</button>
    </>} assistant={screen === 's01' ? null : <Composer session={session} screen={screen} inputRef={composerInput} onExpand={() => setScreen('s01')} />}>
      {navigationError && <pre role="alert">{navigationError}</pre>}
      {renderScreen()}
    </AppShell>
    {settingsOpen && status.phase === 'Ready' && <SettingsPanel key={status.generation_id} onClose={() => setSettingsOpen(false)} />}
  </div>;
}

