import test from 'node:test';
import assert from 'node:assert/strict';
import { Children, isValidElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createDatasetActions, emptyActions } from './actions.ts';
import { DatasetDialog } from './RecycleView.ts';
import type { CatalogRecord, DatasetRecord, DatasetTransport, DeletePreview, ImportResponse } from './types.ts';

const record: CatalogRecord = { id: 'old', display_name: '样品', shape: [2, 3, 4], wavelength_range: [400, 700], raw: false, source_path: '\\\\nas\\share\\sample.hdr', available: true };
const preview: DeletePreview = { cube_id: 'old', annotation_versions: 2, preprocess_runs: 3, training_runs: 4, inference_runs: 5, total_bytes: 1234, directories: [{ path: 'annotations/old/v1', bytes: 1234 }], preview_token: 'bound-token', expires_at: '2026-11-05T00:05:00Z' };
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
    deletePreview: async () => preview,
    delete: async (...args: unknown[]) => { calls.push(['delete', ...args]); return { pending_directories: [] } as never; },
    ...overrides } as DatasetTransport;
  const actions = createDatasetActions(api, { imported: async rows => { batches.push(rows); }, deleted: async id => { calls.push(['removed', id]); } }, next => { state = next; });
  return { actions, calls, batches, state: () => state };
}

test('C delete preview opens the permanent impact dialog; only its confirm button sends deletion', async () => {
  const h = harness(), pending = h.actions.requestDelete(record); await tick();
  assert.deepEqual(h.calls, []); const dialog = h.state().dialog!;
  const tree = DatasetDialog({ dialog, onDecision: h.actions.decide });
  const html = renderToStaticMarkup(tree);
  for (const text of ['永久删除', '不可恢复', '原始 ENVI', 'annotations/old/v1', '标注版本', '预处理运行', '训练运行', '推理运行', '1,234 B']) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /bound-token|30 天内可恢复|移入回收站/);
  button(tree, '确认永久删除')(); await pending;
  assert.deepEqual(h.calls, [['delete', 'old', 'bound-token', true], ['removed', 'old']]);
  assert.match(h.state().message, /已永久删除.*不可恢复/);
});

test('C cancelling or unmounting a deletion confirmation never sends deletion', async () => {
  for (const dispose of [false, true]) {
    const h = harness(), pending = h.actions.requestDelete(record); await tick();
    if (dispose) h.actions.dispose(); else button(DatasetDialog({ dialog: h.state().dialog!, onDecision: h.actions.decide }), '取消')();
    await pending; assert.deepEqual(h.calls, []);
  }
});

test('C a pending cleanup directory is reported instead of claiming full success', async () => {
  const h = harness({ delete: async () => ({ pending_directories: ['exports/old'] } as never) });
  const pending = h.actions.requestDelete(record); await tick();
  button(DatasetDialog({ dialog: h.state().dialog!, onDecision: h.actions.decide }), '确认永久删除')(); await pending;
  assert.match(h.state().message, /待下次启动清理/);
});

test('C existing active import never asks confirmation and ignores all_datasets in the UI', async () => {
  const selected = [{ id: 'one' }, { id: 'two' }, { id: 'three' }] as DatasetRecord[];
  const result: ImportResponse = { datasets: selected, all_datasets: [...selected, { id: 'unselected' } as DatasetRecord], summary: { total: 3, imported: 0, existing: 3 } };
  const h = harness({ importDirectory: async () => result }); await h.actions.choose(false);
  assert.equal(h.state().dialog, null); assert.deepEqual(h.batches, [selected]);
  assert.match(h.state().message, /该路径已有数据集。.*本次选中 3 个（新增 0 \/ 已有 3）/);
});

test('C every import is a plain first import with no confirm_new flag', async () => {
  const requests: unknown[] = [];
  const result: ImportResponse = { datasets: [{ id: 'new' } as DatasetRecord], all_datasets: [], summary: { total: 1, imported: 1, existing: 0 } };
  const h = harness({ importDirectory: async (...args) => { requests.push(args); return result; } });
  await h.actions.choose(true);
  assert.deepEqual(requests, [['selected', true]]);
  assert.equal(h.state().dialog, null);
  assert.match(h.state().message, /新增 1 \/ 已有 0/);
});

test('C no import error opens a fresh-id confirmation or silently retries', async () => {
  const requests: unknown[] = [];
  const h = harness({ importDirectory: async (...args) => { requests.push(args); throw { error: 'REIMPORT_ACTIVE_EXISTS', detail: '已有并发活跃数据集，请重试' }; } });
  await h.actions.choose(true);
  assert.deepEqual(requests, [['selected', true]]);
  assert.equal(h.state().dialog, null);
  assert.match(h.state().error, /并发活跃/);
});
