// UI acceptance only. In-memory synthetic data; no sidecar, NAS or user files.
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from '/src/App';
import '/src/style.css';

let generation = 1, callbackId = 0;
const callbacks = new Map<number, (event: unknown) => void>(), listeners = new Map<number, string>();
const id = (number: number) => `00000000-0000-0000-0000-${String(number).padStart(12, '0')}`;
const source = (number: number) => `\\\\qa-nas\\spectral\\sample-${number}`;
let rows = [1, 2, 3, 4].map(number => ({ id: id(number), display_name: `样品 ${number}`, shape: [2, 2, 4] as [number, number, number],
  wavelength_range: [400, 700], raw: false, source_path: source(number)+'.hdr', available: number !== 4 }));
let trash: unknown[] = [], counter = 5;
let paths = { source_path: '\\\\qa-nas\\spectral', output_root: '\\\\qa-nas\\future-output', data_root: 'C:\\QA\\SpectrumAgent', output_enabled: false };
const ledger: unknown[] = [];
const snapshot = () => ({ generation_id: generation, phase: 'Ready', pid: 2531, port: 14201, boot_id: `fixture-${generation}`, failure: null, cleanup_complete: true });
const detail = (row: typeof rows[number]) => ({ id: row.id, display_name: row.display_name, existing: true,
  dataset: { name: row.display_name, shape: row.shape, wavelengths: [400, 500, 600, 700], fwhm: null, dtype: 'float32', interleave: 'bip',
    data_path: row.source_path.replace('.hdr', '.img'), header_path: row.source_path, metadata: { value_mode: 'reflectance' } } });
const canvas = document.createElement('canvas'); canvas.width = 2; canvas.height = 2;
const context = canvas.getContext('2d')!; context.fillStyle = '#278a83'; context.fillRect(0, 0, 2, 2);
const png = canvas.toDataURL().split(',')[1];
const globals = window as unknown as Record<string, unknown>;
globals.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: (_event: string, eventId: number) => listeners.delete(eventId) };
globals.__TAURI_INTERNALS__ = { transformCallback: (callback: (event: unknown) => void) => { callbacks.set(++callbackId, callback); return callbackId; },
  invoke: async (command: string, args: { request?: Record<string, unknown>; handler?: number; event?: string; options?: { multiple?: boolean } } = {}) => {
    const request = args.request ?? {}, op = request.op;
    if (command === 'plugin:event|listen') { listeners.set(args.handler!, args.event!); return args.handler; }
    if (command === 'plugin:event|unlisten' || command === 'boot_probe') return;
    if (command === 'engine_status') return snapshot();
    if (command === 'plugin:dialog|open') return args.options?.multiple ? [source(1), source(2), source(3)] : 'smb://qa-nas/selected-by-browse';
    ledger.push({ command, ...request }); document.getElementById('qa-ledger')!.textContent = JSON.stringify(ledger, null, 2);
    if (command === 'agent_forward') return { skill_name: '合成 UI 夹具', skill_version_id: null, skill_version_no: 2, tool_catalogue_version: 2, tool_count: 0, sessions_by_skill: {} };
    if (command === 'annotations_forward' && op === 'projects') return [{ id: id(99), name: '默认项目' }];
    if (command === 'settings_forward') {
      if (op === 'get_project_paths') return paths;
      if (op === 'put_project_paths') { paths = { ...paths, ...(request.body as object) }; return paths; }
      return { base_url: '', model: '', temperature: '', max_tokens: '', timeout_ms: '', egress_enabled: false, has_key: false };
    }
    if (command === 'datasets_forward') {
      if (op === 'catalog') return { datasets: rows.slice(Number(request.offset), Number(request.offset)+Number(request.limit)), total: rows.length, limit: request.limit, offset: request.offset };
      if (op === 'preview') return { id: request.id, band: 0, width: 2, height: 2, mime: 'image/png', png_base64: png };
      if (op === 'get') return detail(rows.find(row => row.id === request.id)!);
      if (op === 'delete_preview') return { cube_id: request.id, annotation_versions: 2, preprocess_runs: 1, training_runs: 1, inference_runs: 0,
        directories: [{ path: `annotations/${request.id}/v1`, bytes: 1234 }, { path: `exports/${request.id}`, bytes: 2000 }], total_bytes: 3234, preview_token: 'ui-bound-preview', expires_at: '2026-11-05T01:00:00Z' };
      if (op === 'delete') {
        const row = rows.find(row => row.id === request.id)!;
        trash.push({ deletion_id: id(50+trash.length), cube_id: row.id, display_name: row.display_name, source_path: row.source_path, total_bytes: 3234, status: 'READY',
          created_at: '2026-11-05T00:00:00Z', expires_at: '2026-12-05T00:00:00Z', row }); rows = rows.filter(item => item.id !== request.id);
        return { deletion_id: id(50), cube_id: request.id };
      }
      if (op === 'recycle_list') return { items: trash, count: trash.length, total_bytes: trash.length*3234 };
      if (op === 'restore') {
        const item = (trash as ({ deletion_id: string; cube_id: string; source_path: string; row: typeof rows[number] })[]).find(row => row.deletion_id === request.deletion_id)!;
        if (rows.some(row => row.source_path === item.source_path)) throw { error: 'RESTORE_CONFLICT', detail: '同路径已有活跃数据集' };
        rows.push(item.row); trash = (trash as { deletion_id: string }[]).filter(row => row.deletion_id !== request.deletion_id);
        return { cube_id: item.cube_id, deletion_id: item.deletion_id, restored: true };
      }
      if (op === 'import') {
        const header = String(request.path)+'.hdr'; let row = rows.find(row => row.source_path === header);
        if (!row && (trash as { source_path: string }[]).some(item => item.source_path === header) && !request.confirm_new) throw { error: 'REIMPORT_CONFIRMATION_REQUIRED' };
        const existing = !!row;
        if (!row) { row = { ...rows[0], id: id(counter++), display_name: '重新导入的样品', source_path: header, available: true }; rows.push(row); }
        return { datasets: [{ ...detail(row), existing }], all_datasets: rows.map(detail), summary: { total: 1, imported: existing ? 0 : 1, existing: existing ? 1 : 0 } };
      }
    }
    throw { error: 'QA_UNEXPECTED_REQUEST', detail: '夹具未实现此操作' };
  } };
const controls = document.getElementById('qa-controls')!;
controls.style.cssText = 'padding:8px;background:#fff6dc';
controls.textContent = '合成 IPC 验收环境：不会读写真实数据。 ';
const next = document.createElement('button'); next.textContent = '模拟引擎换代';
next.onclick = () => { generation++; rows = rows.map(row => ({ ...row, display_name: `第 ${generation} 代 · ${row.display_name}` }));
  for (const [handler, event] of listeners) if (event === 'engine-status') callbacks.get(handler)?.({ event, id: handler, payload: snapshot() }); };
controls.append(next);
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
