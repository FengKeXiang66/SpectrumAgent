import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { acceptSnapshot, type ExitReason, type Snapshot } from './status';
import DatasetPanel from './components/datasets/DatasetPanel';
import { datasets } from './components/datasets/api';

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
  const input = useRef<HTMLInputElement>(null);
  const statusRef = useRef(status);
  statusRef.current = status;
  useEffect(() => {
    setBusy(false); setMetrics(null); setText('');
    setMessage('输入“运行冒烟测试”，或点击发送。');
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
      if (!event.ctrlKey || status.phase !== 'Ready') return;
      if (event.key.toLowerCase() === 'k') { event.preventDefault(); input.current?.focus(); }
      if (event.key === 'Enter') { event.preventDefault(); void send(); }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  });
  if (status.phase === 'Starting') return null;
  const failure = status.failure;
  return <div className="app" data-phase={status.phase}>
    <main>
      <h1>光谱数据 AI Agent · 数据接入</h1>
      <p aria-label="产品版本">版本 {__SPECTRUM_PRODUCT_VERSION__}</p>
      {status.phase === 'Ready' && <>
        <p role="status">引擎已就绪</p>
        <p>选择数据目录，查看数据集与单波段预览。</p>
        <p>进程 {status.pid} · 端口 {status.port} · 启动代次 {status.generation_id}</p>
        <DatasetPanel key={status.generation_id} api={datasets} />
        {metrics && <pre aria-label="冒烟测试真实结果">{JSON.stringify(metrics, null, 2)}</pre>}
      </>}
      {status.phase === 'Failed' && <section role="alert">
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
      </section>}
      {status.phase === 'Stopping' && <p role="status">正在关闭</p>}
    </main>
    <footer aria-label="常驻对话条">
      <p role="status">{status.phase === 'Stopping' ? '正在关闭' : status.phase === 'Failed' ? '引擎不可用，请查看失败原因与诊断入口。' : message}</p>
      <form onSubmit={event => { event.preventDefault(); void send(); }}>
        <label htmlFor="agent-input">hello 对话条</label>
        <input ref={input} id="agent-input" value={text} onChange={event => setText(event.target.value)} disabled={status.phase !== 'Ready' || busy} placeholder="运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送）" />
        <button type="submit" disabled={status.phase !== 'Ready' || busy}>{busy ? '运行中' : '发送'}</button>
      </form>
    </footer>
  </div>;
}

