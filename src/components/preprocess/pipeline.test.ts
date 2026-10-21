import assert from 'node:assert/strict';
import test from 'node:test';
import { axisAfter, compilePipeline, curveRuns, OPERATORS, targetAxis } from './pipeline.ts';
import type { Params, Step } from './types.ts';
const step = (op: string, params: Params = {}): Step => ({ op, version: 1, params });
const source = [400, 410, 420, 430, 440];
test('operator directory matches explicit R15 names and excludes run B01 / unresolved reference methods', () => {
  assert.deepEqual(OPERATORS, ['sg_smooth', 'sg_derivative', 'snv', 'standardize', 'crop', 'resample', 'pca', 'mnf', 'ica', 'continuum']);
  for (const op of ['reflectance', 'msc', 'emsc']) assert.throws(() => compilePipeline([step(op)], source, 5));
});
test('axisAfter is pure, crop closed, resample replaces, decomposition removes axis', () => {
  const steps = [step('crop', { range: [410, 430] }), step('resample', { target: [412, 420, 428] })];
  const original = structuredClone(steps);
  assert.deepEqual(axisAfter(steps, source), [412, 420, 428]);
  assert.deepEqual(axisAfter(steps.slice(0, 1), source), [410, 420, 430]);
  assert.equal(axisAfter([...steps, step('pca', { n_components: 2 })], source), null);
  assert.deepEqual(steps, original); assert.deepEqual(source, [400, 410, 420, 430, 440]);
});
test('crop→resample→crop supplies EACH current source, never stale saved source', () => {
  const pipeline = compilePipeline([step('crop', { range: [410, 430], source: [0, 1] }),
    step('resample', { target: targetAxis(410, 430, 5), method: 'spline' }), step('crop', { range: [415, 425] })], source, 5);
  assert.deepEqual(pipeline.steps.map(s => s.params.source), [source, [410, 420, 430], [410, 415, 420, 425, 430]]);
  assert.deepEqual(axisAfter(pipeline.steps, source), [415, 420, 425]);
});
test('schema-direction validation: odd SG, STRICT polynomial bound, derivative order/mode', () => {
  for (const params of [{ window: 4, polyorder: 2 }, { window: 3, polyorder: 3 }, { window: 3, polyorder: -1 }, { window: 3, polyorder: 2, mode: 'bad' }] as Params[]) {
    assert.throws(() => compilePipeline([step('sg_smooth', params)], source, 5));
  }
  assert.throws(() => compilePipeline([step('sg_derivative', { window: 3, polyorder: 2, order: 3 })], source, 5));
  assert.doesNotThrow(() => compilePipeline([step('sg_derivative', { window: 3, polyorder: 2, order: 1, mode: 'mirror' })], source, 5));
});
test('all exposed methods accept valid schema choices; unknown keys and absent components reject', () => {
  for (const method of ['standard', 'minmax', 'area', 'vector']) for (const zero_std of ['zeros', 'nan', 'error']) {
    assert.doesNotThrow(() => compilePipeline([step('standardize', { method, zero_std }), step('snv', { zero_std })], source, 5));
  }
  for (const method of ['linear', 'convex_hull']) assert.doesNotThrow(() => compilePipeline([step('continuum', { method })], source, 5));
  for (const op of ['pca', 'mnf', 'ica']) {
    for (const n of [undefined, 0, 6, 1.5]) assert.throws(() => compilePipeline([step(op, n === undefined ? {} : { n_components: n })], source, 5));
    assert.doesNotThrow(() => compilePipeline([step(op, { n_components: 2, random_state: 0 })], source, 5));
  }
  assert.throws(() => compilePipeline([step('snv', { unknown: 1 })], source, 5));
  assert.throws(() => compilePipeline([], source, 5));
});
test('no wavelengths disables axis operators; lo<hi, nonempty crop, target finite/increasing enforce', () => {
  assert.throws(() => compilePipeline([step('crop', { range: [410, 430] })], [], 5));
  assert.throws(() => compilePipeline([step('pca', { n_components: 2 }), step('crop', { range: [410, 430] })], source, 5));
  for (const range of [[430, 410], [410, 410], [1, 2]]) assert.throws(() => compilePipeline([step('crop', { range })], source, 5));
  for (const target of [[410], [420, 410], [410, Infinity]]) assert.throws(() => compilePipeline([step('resample', { target, method: 'linear' })], source, 5));
});
test('move/delete/repeat preserve order and compile legal explicit steps', () => {
  const steps = [step('snv'), step('continuum', { method: 'linear' }), step('snv')];
  [steps[0], steps[1]] = [steps[1], steps[0]]; steps.splice(2, 1); steps.push(step('snv'));
  assert.deepEqual(compilePipeline(steps, source, 5).steps.map(s => s.op), ['continuum', 'snv', 'snv']);
});
test('target creation is axis-only; chart gaps retain separate strokes and values', () => {
  assert.deepEqual(targetAxis(400, 440, 3), [400, 420, 440]);
  assert.throws(() => targetAxis(1, 0, 3)); assert.throws(() => targetAxis(0, 1, 1));
  assert.deepEqual(curveRuns([1, null, 3, 4, NaN, null, 7]), [[[0, 1]], [[2, 3], [3, 4]], [[6, 7]]]);
});
