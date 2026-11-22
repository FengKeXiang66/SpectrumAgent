import test from 'node:test';
import assert from 'node:assert/strict';
import { createBlockEditQueue } from '../src/components/annotation/block-edits.ts';

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

test('rapid clicks keep order, capture labels and preserve a write/undo step per click', async () => {
  const first = deferred(), sent = [], states = [], activity = [];
  let pending = [], reads = 0, inFlight = 0, peak = 0;
  const queue = createBlockEditQueue({
    submit: async edit => {
      peak = Math.max(peak, ++inFlight);
      sent.push(edit);
      if (sent.length === 1) await first.promise;
      inFlight--;
    },
    read: async () => { reads++; return sent.length; },
    onRead: value => states.push(value),
    onPending: value => { pending = value; },
    onActive: value => activity.push(value),
    onError: async error => { throw error; },
  });
  const original = { blockId: 5, action: 'confirm', labelId: 'A' };
  queue.enqueue(original);
  original.blockId = 999; original.labelId = 'wrong';
  const edits = Array.from({ length: 11 }, (_, i) => ({ blockId: i % 3,
    action: i % 3 === 0 ? 'erase' : i % 3 === 1 ? 'uncertain' : 'confirm',
    ...(i % 3 === 2 ? { labelId: i < 5 ? 'A' : 'B' } : {}) }));
  for (const edit of edits) assert.equal(queue.enqueue(edit), true);
  assert.equal(pending.length, 12); // acknowledged locally before any I/O finishes
  assert.equal(sent.length, 1);
  first.resolve();
  await queue.idle();
  assert.deepEqual(sent.map(({ sequence, ...edit }) => edit), [{ blockId: 5, action: 'confirm', labelId: 'A' }, ...edits]);
  assert.equal(peak, 1);
  assert.equal(reads, 3);
  assert.deepEqual(states, [4, 8, 12]);
  assert.equal(pending.length, 0);
  assert.deepEqual(activity, [true, false]);
});

test('a click arriving during overlay refresh is neither erased nor marked synchronized early', async () => {
  const reading = deferred(), entered = deferred(), sent = [], snapshots = [], pendingStates = [];
  let reads = 0;
  const queue = createBlockEditQueue({
    submit: async edit => { sent.push(edit.blockId); },
    read: async () => { const value = sent.slice(); if (++reads === 1) { entered.resolve(); await reading.promise; } return value; },
    onRead: value => snapshots.push(value),
    onPending: value => pendingStates.push(value.map(edit => edit.blockId)),
    onActive() {}, onError: async error => { throw error; },
  });
  queue.enqueue({ blockId: 1, action: 'erase' });
  await entered.promise;
  queue.enqueue({ blockId: 2, action: 'uncertain' });
  reading.resolve(); await queue.idle();
  assert.deepEqual(sent, [1, 2]);
  assert.deepEqual(snapshots, [[1], [1, 2]]);
  assert.deepEqual(pendingStates, [[1], [1, 2], [2], []]);
});

test('an ambiguous committed write is reconciled once, never replayed, and stops later clicks', async () => {
  const transport = deferred(), recovery = deferred(), entered = deferred(), calls = [], errors = [];
  let pending = [], reads = 0;
  const failure = new Error('connection lost after commit');
  const queue = createBlockEditQueue({
    submit: async edit => { calls.push(edit.blockId); await transport.promise; throw failure; },
    read: async () => { reads++; }, onRead() {},
    onPending: value => { pending = value; }, onActive() {},
    onError: async (error, count) => { errors.push([error, count]); entered.resolve(); await recovery.promise; },
  });
  queue.enqueue({ blockId: 1, action: 'confirm', labelId: 'A' });
  queue.enqueue({ blockId: 2, action: 'erase' });
  transport.resolve(); await entered.promise;
  assert.equal(queue.enqueue({ blockId: 3, action: 'erase' }), false);
  recovery.resolve(); await queue.idle();
  assert.deepEqual(calls, [1]); assert.equal(reads, 0);
  assert.deepEqual(errors, [[failure, 2]]); assert.equal(pending.length, 0);
});

test('disposing a workbench cannot submit queued clicks or attach responses to another image', async () => {
  const gate = deferred(), sent = [], callbacks = [];
  const queue = createBlockEditQueue({
    submit: async edit => { sent.push(edit.blockId); await gate.promise; },
    read: async () => { callbacks.push('read'); }, onRead: () => callbacks.push('apply'),
    onPending() {}, onActive: value => callbacks.push(value), onError: async () => callbacks.push('error'),
  });
  queue.enqueue({ blockId: 1, action: 'erase' });
  queue.enqueue({ blockId: 2, action: 'erase' });
  queue.dispose(); gate.resolve(); await queue.idle();
  assert.deepEqual(sent, [1]); assert.deepEqual(callbacks, [true]);
  assert.equal(queue.enqueue({ blockId: 3, action: 'erase' }), false);
});
