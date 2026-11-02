import React from 'react';
import { createRoot } from 'react-dom/client';
import AnnotationWorkbench from '../../src/components/annotation/AnnotationWorkbench.tsx';
import { annotationClient } from '../../src/components/annotation/api.ts';

const send = async (command, args = {}) => {
  const response = await fetch('/ipc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command, args }) });
  const value = await response.json(); if (!response.ok) throw value; return value;
};
window.__TAURI_INTERNALS__ = { invoke: send };
localStorage.setItem('spectrum.annotation.shortcuts.seen.v1', 'yes');
const record = await (await fetch('/fixture')).json();
const api = annotationClient(send);
const datasets = { preview: () => send('datasets_test_preview') };
createRoot(document.getElementById('root')!).render(<>
  <aside><strong>TASK-13 隔离验收</strong><button onClick={() => fetch('/fail', { method: 'POST', body: JSON.stringify({ enabled: false }) })}>恢复投影写入</button></aside>
  <AnnotationWorkbench record={record} records={[record]} datasets={datasets} api={api} onNavigate={() => {}} onClose={() => {}} />
</>);
