import test from 'node:test';
import assert from 'node:assert/strict';
import { draftClient, requests, type DraftRequest, type InvokeDraft } from './draft-api.ts';
import type { Seed } from './types.ts';

test('storeGesture projects exactly point, box or doodle and strips nested extras', () => {
  for (const [seed, expected] of [
    [{ point: [2, 3, 99], path: '/private' }, { point: [2, 3] }],
    [{ box: [0, 4, 1, 5, 99], label: 'extra' }, { box: [0, 4, 1, 5] }],
    [{ doodle: [[1, 2, 99], [3, 4]], document: {} }, { doodle: [[1, 2], [3, 4]] }],
  ]) {
    const request = requests.storeGesture('cube', seed as Seed);
    assert.deepEqual(request, { op: 'store_gesture', cube_id: 'cube', body: { seed: expected } });
    if (request.op !== 'store_gesture') throw new Error('wrong operation');
    assert.notEqual(request.body.seed, seed);
  }
});

test('gesture projection adds no absent variant fields or optional defaults', () => {
  const request = requests.storeGesture('c', { point: [0, 0] });
  assert.equal(JSON.stringify(request), '{"op":"store_gesture","cube_id":"c","body":{"seed":{"point":[0,0]}}}');
  assert.equal('gesture_ref' in request, false);
  assert.equal('kind' in request, false);
});

test('gesture client uses only annotations_draft_forward and preserves server reference', async () => {
  const calls: { command: string; request: DraftRequest }[] = [];
  const result = { gesture_ref: 'g-server-owned', kind: 'doodle' };
  const send: InvokeDraft = async <T>(command: string, { request }: { request: DraftRequest }) => {
    calls.push({ command, request }); return result as T;
  };
  assert.deepEqual(await draftClient(send).storeGesture('c', { doodle: [[1, 2]] }), result);
  assert.deepEqual(calls, [{ command: 'annotations_draft_forward', request: { op: 'store_gesture', cube_id: 'c', body: { seed: { doodle: [[1, 2]] } } } }]);
});

test('gesture store failure reaches caller without a fabricated reference', async () => {
  const error = { error: 'GESTURE_STORE_FAILED', detail: 'unavailable' };
  await assert.rejects(draftClient(async () => { throw error; }).storeGesture('c', { point: [1, 2] }), value => value === error);
});
