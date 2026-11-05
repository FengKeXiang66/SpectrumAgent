import { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

export type SmokeMetrics = { nan_ratio: number; reflectance_range: [number, number]; bands: number; shape: [number, number, number]; elapsed_ms: number };

const HINT = '引擎自检：输入“运行冒烟测试”后发送，验证引擎能读 ENVI 并完成 SNV。仅诊断用，聊天请回智能助手页。';

export default function SmokePanel() {
  const [text, setText] = useState('');
  const [message, setMessage] = useState(HINT);
  const [busy, setBusy] = useState(false);
  const [metrics, setMetrics] = useState<SmokeMetrics | null>(null);
  const send = async () => {
    if (busy) return;
    if (text.trim() && text.trim() !== '运行冒烟测试') {
      setMessage('引擎自检只认“运行冒烟测试”这一句；聊天请回智能助手页。');
      return;
    }
    setBusy(true); setMetrics(null); setMessage('正在运行冒烟测试…');
    try {
      setMetrics(await invoke<SmokeMetrics>('run_smoke'));
      setMessage('冒烟测试完成。'); setText('');
    } catch {
      setMessage('冒烟测试未完成，请检查引擎状态与日志。');
    } finally { setBusy(false); }
  };
  return <section aria-label="引擎自检">
    <h3>引擎自检（诊断用）</h3>
    <p role="status">{message}</p>
    <form onSubmit={event => { event.preventDefault(); void send(); }}>
      <label htmlFor="smoke-input">冒烟测试</label>
      <input id="smoke-input" value={text} onChange={event => setText(event.target.value)} disabled={busy} placeholder="运行冒烟测试" />
      <button type="submit" disabled={busy}>{busy ? '运行中' : '发送'}</button>
    </form>
    {metrics && <pre aria-label="冒烟测试真实结果">{JSON.stringify(metrics, null, 2)}</pre>}
  </section>;
}
