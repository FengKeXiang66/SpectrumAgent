import test from 'node:test';
import assert from 'node:assert/strict';
import { Children, isValidElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createDatasetActions, emptyActions } from './actions.ts';
import { DatasetDialog, RecycleSummary } from './RecycleView.ts';
import type { CatalogRecord, DatasetRecord, DatasetTransport, DeletePreview, ImportResponse, RecycleRecord } from './types.ts';

const record: CatalogRecord = { id: 'old', display_name: '样品', shape: [2, 3, 4], wavelength_range: [400, 700], raw: false, source_path: '\\\\nas\\share\\sample.hdr', available: true };
const preview: DeletePreview = { cube_id: 'old', annotation_versions: 2, preprocess_runs: 3, training_runs: 4, inference_runs: 5, total_bytes: 1234, directories: [{ path: 'annotations/old/v1', bytes: 1234 }], preview_token: 'bound-token', expires_at: '2026-11-05T00:05:00Z' };
const recycled: RecycleRecord = { deletion_id: 'deletion', cube_id: 'old', display_name: '样品', source_path: record.source_path, total_bytes: 1234, status: 'READY', created_at: '2026-11-05T00:00:00Z', expires_at: '2026-12-05T00:00:00Z' };
const tick = () => new Promise<void>(resolve => setImmediate(resolve));
function button(tree: ReactNode, label: string): () => void {
  let action: (() => void) | undefined;
  const visit = (node: ReactNode) => {
    if (!isValidElement<{ children?: ReactNode; onClick?: () => void }>(node)) return;
    if (node.type === 'button' && node.props.children === label) action = node.props.onClick;
    Children.forEach(node.props.children, visit);
  };
  visit(tree); assert.ok(action, `button ${label} is wired`); return action;
}
function harness(overrides: Partial<DatasetTransport> = {}) {
  const calls: unknown[] = [], batches: DatasetRecord[][] = []; let state = emptyActions();
  const api = { chooseDirectories: async () => ['selected'], importDirectory: async () => { throw new Error('unexpected import'); },
    deletePreview: async () => preview, delete: async (...args: unknown[]) => { calls.push(['delete', ...args]); return {} as never; },
    restore: async (...args: unknown[]) => { calls.push(['restore', ...args]); return { cube_id: 'old', deletion_id: 'deletion', restored: true }; },
    ...overrides } as DatasetTransport;
  const actions = createDatasetActions(api, { imported: async rows => { batches.push(rows); }, deleted: async id => { calls.push(['removed', id]); }, restored: async id => { calls.push(['restored', id]); } }, next => { state = next; });
  return { actions, calls, batches, state: () => state };
}

test('C delete preview opens the impact dialog; only its confirm button sends strict deletion', async () => {
  const h = harness(), pending = h.actions.requestDelete(record); await tick();
  assert.deepEqual(h.calls, []); const dialog = h.state().dialog!;
  const tree = DatasetDialog({ dialog, onDecision: h.actions.decide });
  const html = renderToStaticMarkup(tree);
  for (const text of ['30 天内可恢复', '不会立即释放', 'annotations/old/v1', '标注版本', '预处理运行', '训练运行', '推理运行', '1,234 B']) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /bound-token/);
  button(tree, '确认移入回收站')(); await pending;
  assert.deepEqual(h.calls, [['delete', 'old', 'bound-token', true], ['removed', 'old']]);
});

test('C cancelling or unmounting a deletion confirmation never sends deletion', async () => {
  for (const dispose of [false, true]) {
    const h = harness(), pending = h.actions.requestDelete(record); await tick();
    if (dispose) h.actions.dispose(); else button(DatasetDialog({ dialog: h.state().dialog!, onDecision: h.actions.decide }), '取消')();
    await pending; assert.deepEqual(h.calls, []);
  }
});

test('C existing active import never asks confirmation and ignores all_datasets in the UI', async () => {
  const selected = [{ id: 'one' }, { id: 'two' }, { id: 'three' }] as DatasetRecord[];
  const result: ImportResponse = { datasets: selected, all_datasets: [...selected, { id: 'unselected' } as DatasetRecord], summary: { total: 3, imported: 0, existing: 3 } };
  const h = harness({ importDirectory: async () => result }); await h.actions.choose(false);
  assert.equal(h.state().dialog, null); assert.deepEqual(h.batches, [selected]);
  assert.match(h.state().message, /该路径已有数据集。.*本次选中 3 个（新增 0 \/ 已有 3）/);
});

test('C only REIMPORT_CONFIRMATION_REQUIRED prompts, with a selected new-id choice and no request until click', async () => {
  const requests: unknown[] = [];
  const h = harness({ importDirectory: async (...args) => {
    requests.push(args); if (!args[2]) throw { error: 'REIMPORT_CONFIRMATION_REQUIRED' };
    return { datasets: [{ id: 'new' } as DatasetRecord], all_datasets: [], summary: { total: 1, imported: 1, existing: 0 } };
  } });
  const pending = h.actions.choose(true); await tick();
  assert.deepEqual(requests, [['selected', true]]);
  const tree = DatasetDialog({ dialog: h.state().dialog!, onDecision: h.actions.decide }), html = renderToStaticMarkup(tree);
  assert.match(html, /type="radio"[^>]*checked/);
  for (const text of ['新建 id', '从头标注', '30 天', '双份空间']) assert.ok(html.includes(text));
  button(tree, '确认新建数据集')(); await pending;
  assert.deepEqual(requests, [['selected', true], ['selected', true, true]]);
  assert.match(h.state().message, /新增 1 \/ 已有 0/);
});

test('C reimport cancellation and concurrent active-record conflict never silently retry or reuse', async () => {
  let requests = 0;
  const cancel = harness({ importDirectory: async () => { requests++; throw { error: 'REIMPORT_CONFIRMATION_REQUIRED' }; } });
  const pending = cancel.actions.choose(false); await tick(); cancel.actions.decide(false); await pending;
  assert.equal(requests, 1); assert.deepEqual(cancel.batches, []);
  const conflict = harness({ importDirectory: async () => { throw { error: 'REIMPORT_ACTIVE_EXISTS', detail: '已有并发活跃数据集，请重试' }; } });
  await conflict.actions.choose(false); assert.equal(conflict.state().dialog, null); assert.match(conflict.state().error, /并发活跃/);
});

test('C restore requires the UI button, renders refusal reason, and incomplete items cannot restore', async () => {
  const h = harness({ restore: async () => { throw { detail: '同路径已有活跃数据集' }; } });
  const pending = h.actions.requestRestore(recycled); await tick(); assert.deepEqual(h.calls, []);
  button(DatasetDialog({ dialog: h.state().dialog!, onDecision: h.actions.decide }), '确认恢复')(); await pending;
  assert.match(h.state().error, /同路径已有活跃数据集.*\n.*先把新的也删进回收站/);
  assert.deepEqual(h.calls, []);
  const incomplete = harness(); await incomplete.actions.requestRestore({ ...recycled, status: 'INCOMPLETE' });
  assert.equal(incomplete.state().dialog, null); assert.deepEqual(incomplete.calls, []);
  await incomplete.actions.requestRestore({ ...recycled, expires_at: '2000-01-01T00:00:00Z' });
  assert.equal(incomplete.state().dialog, null); assert.match(incomplete.state().error, /超过 30 天/);
});

test('C S11 recycle summary includes retained space, count, per-item dates and incomplete cleanup refusal', () => {
  const html = renderToStaticMarkup(RecycleSummary({ value: { items: [{ ...recycled, status: 'INCOMPLETE' }], count: 1, total_bytes: 1234 } }));
  for (const text of ['1 个条目', '1,234 B', '仍占本机磁盘空间', '预计释放日期', '2026', '禁止恢复与自动清理']) assert.ok(html.includes(text));
});
