import test from 'node:test';
import assert from 'node:assert/strict';
import { createCatalogController, emptyCatalog, readCatalog } from './catalog.ts';
import type { CatalogPage, CatalogRecord, DatasetRecord } from './types.ts';

const row = (id: string, available = true): CatalogRecord => ({ id, display_name: id, shape: [2, 3, 4], wavelength_range: [400, 700], raw: false, source_path: 'Z:\\source\\'+id+'.hdr', available });
const page = (datasets: CatalogRecord[], total = datasets.length, offset = 0): CatalogPage => ({ datasets, total, limit: 100, offset });
function deferred<T>() { let resolve!: (value: T) => void, reject!: (error: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

test('C cold catalog follows every page and retains unavailable sources as visible summaries', async () => {
  const calls: number[] = [];
  const rows = await readCatalog({ catalog: async (_limit, offset = 0) => {
    calls.push(offset); return offset === 0 ? page([row('one')], 2) : page([row('missing', false)], 2, 1);
  } });
  assert.deepEqual(calls, [0, 1]);
  assert.deepEqual(rows.map(item => [item.id, item.available]), [['one', true], ['missing', false]]);
  assert.ok(rows.every(item => !('dataset' in item)));
});

test('C engine generation clears immediately and an older response cannot replace the new catalog', async () => {
  const old = deferred<CatalogPage>(), fresh = deferred<CatalogPage>(); let calls = 0, state = emptyCatalog();
  const controller = createCatalogController({ catalog: () => ++calls === 1 ? old.promise : fresh.promise }, next => { state = next; });
  controller.reset(1); const a = controller.load(); controller.cancel(); controller.reset(2);
  assert.equal(state.records.length, 0);
  const b = controller.load(); fresh.resolve(page([row('new')])); await b;
  old.resolve(page([row('old')])); await a;
  assert.deepEqual(state.records.map(item => item.id), ['new']); assert.equal(state.phase, 'ready');
});

test('C stale failures and disposed requests cannot overwrite a current success', async () => {
  const old = deferred<CatalogPage>(); let count = 0, state = emptyCatalog();
  const controller = createCatalogController({ catalog: () => ++count === 1 ? old.promise : Promise.resolve(page([row('new')])) }, next => { state = next; });
  controller.reset(1); const a = controller.load(); controller.reset(2); await controller.load();
  old.reject(new Error('old engine error')); await a;
  assert.equal(state.error, ''); assert.equal(state.records[0].id, 'new');
  controller.cancel(); await controller.load(); assert.equal(count, 2);
});

test('C current catalog failure is shown and explicit retry recovers', async () => {
  let fail = true, state = emptyCatalog();
  const controller = createCatalogController({ catalog: async () => { if (fail) throw { detail: '目录暂不可用' }; return page([row('recovered')]); } }, next => { state = next; });
  controller.reset(3); await controller.load(); assert.equal(state.phase, 'error'); assert.equal(state.error, '目录暂不可用');
  fail = false; await controller.load(); assert.equal(state.phase, 'ready'); assert.equal(state.error, '');
});

test('C three existing imports append only that batch; catalog refreshes global names without expanding visible scope', async () => {
  const all = [row('one'), row('two'), row('three'), row('unselected')];
  let state = emptyCatalog();
  const controller = createCatalogController({ catalog: async () => page(all.map(item => ({ ...item, display_name: item.id+'（反射率）' }))) }, next => { state = next; });
  controller.reset(4);
  const batch = all.slice(0, 3).map(item => ({ id: item.id, display_name: item.id, existing: true,
    dataset: { name: item.id, shape: item.shape, wavelengths: [400, 700], header_path: item.source_path, metadata: {} } } as DatasetRecord));
  await controller.imported(batch);
  assert.deepEqual(state.records.map(item => item.id), ['one', 'two', 'three']);
  assert.deepEqual(state.records.map(item => item.display_name), ['one（反射率）', 'two（反射率）', 'three（反射率）']);
  await controller.imported(batch); assert.equal(state.records.length, 3);
  controller.remove('two'); await controller.refreshNames(['unselected']);
  assert.deepEqual(state.records.map(item => item.id), ['one', 'three', 'unselected']);
});

test('C broken pagination fails instead of looping or silently hiding catalog rows', async () => {
  await assert.rejects(readCatalog({ catalog: async () => page([], 2) }), /分页不完整/);
});
