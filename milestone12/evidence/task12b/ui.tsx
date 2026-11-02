import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import AnnotationWorkbench from '../../src/components/annotation/AnnotationWorkbench.tsx';
import { annotationClient } from '../../src/components/annotation/api.ts';

const send = async (command, args = {}) => {
  const response = await fetch('/ipc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command, args }) });
  const value = await response.json(); if (!response.ok) throw value; return value;
};
window.__TAURI_INTERNALS__ = { invoke: send };
localStorage.setItem('spectrum.annotation.shortcuts.seen.v1', 'yes');
const fixtures = await (await fetch('/fixture')).json();
const api = annotationClient(send);
const datasets = { preview: id => send('datasets_test_preview', { id }) };
const records = fixtures.map(item => item.record);
function Harness() {
  const [position, setPosition] = useState(0), [refresh, setRefresh] = useState(0);
  const [tag, setTag] = useState(''), [status, setStatus] = useState('夹具就绪');
  const current = fixtures[position];
  return <>
    <aside aria-label="隔离验收控制"><strong>TASK-12b · 当前验收图：{current.name}</strong>
      {fixtures.map((item, i) => <button key={item.name} onClick={() => setPosition(i)}>切到图 {item.name}</button>)}
      <button onClick={async () => { const result = await send('test_external_overwrite', { id: current.record.id }); setRefresh(v => v + 1); setStatus(`外部补标并覆写完成：revision ${result.before.revision} → ${result.after.revision}`); }}>外部补标覆写并刷新</button>
      <label>证据标记<input aria-label="证据标记" value={tag} onChange={event => setTag(event.target.value)} /></label>
      <button onClick={async () => { await send('test_snapshot', { tag }); setStatus(`已记录：${tag}`); }}>记录验收快照</button>
      <p role="status">{status}</p>
    </aside>
    <AnnotationWorkbench record={current.record} records={records} datasets={datasets} api={api} refreshVersion={refresh}
      onNavigate={next => setPosition(records.findIndex(item => item.id === next.id))} onClose={() => {}} />
  </>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
