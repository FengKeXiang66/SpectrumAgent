import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import AnnotationCanvas from '../../src/components/annotation/canvas/AnnotationCanvas.tsx';
import { decodeSegments, hitTest } from '../../src/components/annotation/canvas/segments.ts';
import { editThenRead } from '../../src/components/annotation/working.ts';
import { DEFAULT_LUT } from '../../src/components/annotation/display/display.ts';
import '../../src/components/annotation/annotation.css';

const request = async (path, body?) => {
  const response = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};
const fixture = await request('/fixture');
const map = { png: fixture.report.segments_png, shape: fixture.report.segments_shape, counts: fixture.report.block_counts };
const metrics = {};
function App() {
  const [working, setWorking] = useState(fixture.working), [output, setOutput] = useState('就绪'), [busy, setBusy] = useState(false);
  const api = { working: () => request('/working') };
  const edit = async (id, uncertain = false, erase = false) => {
    setWorking(await editThenRead(api, 'probe', () => request('/regions', { geometry: { superpixels: [id] },
      action: erase ? 'erase' : uncertain ? 'uncertain' : 'confirm', ...(!erase && !uncertain ? { label_id: fixture.labels[2].id } : {}) })));
  };
  const run = async (fn) => { setBusy(true); try { await fn(); } catch (error) { setOutput(String(error)); } finally { setBusy(false); } };
  const decode = async () => {
    const image = new Image(); image.src = `data:image/png;base64,${map.png}`;
    const start = performance.now(); await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 231;
    const ctx = canvas.getContext('2d')!; ctx.imageSmoothingEnabled = false; ctx.drawImage(image, 0, 0);
    const decoded = decodeSegments(ctx.getImageData(0, 0, 640, 231).data, map);
    metrics.decodeMs = performance.now() - start;
    metrics.probes = fixture.probes.filter(([r, c, id]) => hitTest(decoded, r, c) === id).length;
    metrics.base64Bytes = map.png.length;
    metrics.blocks = map.counts.length;
    setOutput(JSON.stringify(metrics));
  };
  const drags = async () => {
    await request('/reset', {});
    const canvas = document.querySelector('canvas')!;
    // Synthetic PointerEvents lack an active native pointer; only capture plumbing is substituted.
    const capture = canvas.setPointerCapture, has = canvas.hasPointerCapture;
    canvas.setPointerCapture = () => {}; canvas.hasPointerCapture = () => false;
    const rect = canvas.getBoundingClientRect();
    const fire = (type, x, y) => canvas.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerId: 12, button: 0, clientX: x, clientY: y }));
    try {
      for (let i = 0; i < 20; i++) {
        const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
        fire('pointerdown', x, y); fire('pointermove', x + 4, y); fire('pointerup', x + 4, y);
        await new Promise(requestAnimationFrame);
      }
    } finally { canvas.setPointerCapture = capture; canvas.hasPointerCapture = has; }
    setOutput(JSON.stringify(await request('/snapshot')));
  };
  const hover = async () => {
    await request('/reset', {});
    const canvas = document.querySelector('canvas')!, rect = canvas.getBoundingClientRect();
    const samples = [];
    for (let i = 0; i < 20; i++) {
      const start = performance.now();
      flushSync(() => canvas.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: rect.left + 20 + i * 10, clientY: rect.top + rect.height / 2 })));
      samples.push(performance.now() - start);
    }
    metrics.hoverMaxMs = Math.max(...samples); metrics.hoverSamplesMs = samples;
    setOutput(JSON.stringify({ ...metrics, state: await request('/snapshot') }));
  };
  return <main style={{ width: 980 }}><h1>TASK-12 本地验收</h1>
    <button disabled={busy} onClick={() => run(decode)}>校验 id 与性能</button>
    <button disabled={busy} onClick={() => run(drags)}>20 次拖拽</button>
    <button disabled={busy} onClick={() => run(hover)}>20 次悬停</button>
    <button disabled={busy} onClick={() => run(async () => { await request('/reset', {}); for (let i = 0; i < 100; i++) await edit(i); setOutput(JSON.stringify(await request('/snapshot'))); })}>100 次点选写入</button>
    <button disabled={busy} onClick={() => run(async () => {
      const before = await request('/snapshot');
      for (let i = 100; i < 130; i++) await edit(i);
      for (let i = 0; i < 30; i++) { await request('/undo', {}); setWorking(await request('/working')); }
      const after = await request('/snapshot');
      setOutput(JSON.stringify({ before, after, pixelExact: before.sha256 === after.sha256, clicks: 30, undos: 30 }));
    })}>30 次点选并撤销</button>
    <button disabled={busy} onClick={() => run(async () => setOutput(JSON.stringify(await request('/snapshot'))))}>读取状态</button>
    <pre id="results" style={{ whiteSpace: 'pre-wrap' }}>{output}</pre>
    <AnnotationCanvas shape={fixture.shape} base={fixture.report.overlay} segmentation={null} segments={map} labels={fixture.labels} working={working}
      selectedKey={null} manualStretch={false} lut={DEFAULT_LUT} inspection="edit" tool="click" prompt="point" disabled={false} panHeld={false} draft={null} brushPrompt={false}
      onSpectrum={() => { throw new Error('unexpected spectrum'); }} onSeed={() => { throw new Error('unexpected diffusion'); }} onGeometry={() => { throw new Error('unexpected geometry'); }}
      onErase={() => { throw new Error('unexpected erase'); }} onBlockClick={(id, uncertain) => run(() => edit(id, uncertain))} onBlockErase={id => run(() => edit(id, false, true))} />
  </main>;
}
createRoot(document.getElementById('root')!).render(<App />);
