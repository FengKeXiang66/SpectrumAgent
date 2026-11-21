import test from 'node:test';
import assert from 'node:assert/strict';
import { createBatchPlanController } from '../src/components/preprocess/batch-plan.ts';

function memoryStorage() {
  const values = new Map();
  return {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key)};
}

const members = [{cube_id: 'cube', name: '样品', annotation_version_id: 'annotation'}];
const receipt = {truncated: false, succeeded: 1, failed: 0,
  items: [{cube_id: 'cube', status: 'succeeded', run_id: 'saved-run'}]};

test('a new boot restores an unsubmitted plan and requires a fresh confirmation', () => {
  const storage = memoryStorage();
  const first = createBatchPlanController({}, storage);
  first.attach('boot-a', 'owner');
  const plan = first.create('draft', 1, 'recipe', members);
  first.invalidate();
  const second = createBatchPlanController({}, storage);
  second.attach('boot-b', 'owner');
  const restored = second.getSnapshot().plans[0];
  assert.equal(restored.id, plan.id);
  assert.equal(restored.boot, 'boot-b');
  assert.equal(restored.status, 'paused');
  assert.equal(restored.batches[0].status, 'not_submitted');
  assert.equal(restored.batches[0].confirmation, null);
});

test('an accepted submission is reconciled after restart without executing it again', async () => {
  const storage = memoryStorage();
  let release, submissions = 0;
  const pending = new Promise(resolve => { release = resolve; });
  const first = createBatchPlanController({
    confirmDraft: async () => ({confirmation_id: 'confirmation'}),
    executeDraft: async () => { submissions++; return pending; },
  }, storage);
  first.attach('boot-a', 'owner');
  const original = first.create('draft', 1, 'recipe', members);
  const execution = first.execute();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(first.getSnapshot().plans[0].batches[0].status, 'submitting');
  first.invalidate();
  release(receipt);
  await execution;
  const second = createBatchPlanController({
    getSubmission: async (ref, owner) => {
      assert.equal(ref, original.batches[0].ref);
      assert.equal(owner, 'owner');
      return {submission_ref: ref, operations: [{kind: 'preprocess.run_batch', status: 'succeeded', receipt}]};
    },
    executeDraft: async () => { throw new Error('must not execute twice'); },
  }, storage);
  second.attach('boot-b', 'owner');
  assert.equal(second.getSnapshot().plans[0].batches[0].status, 'unknown');
  await second.recover();
  const restored = second.getSnapshot().plans[0];
  assert.equal(restored.batches[0].receipt.items[0].run_id, 'saved-run');
  assert.equal(restored.status, 'completed');
  assert.equal(submissions, 1);
});

test('plans belonging to another session are not attached', () => {
  const storage = memoryStorage();
  const first = createBatchPlanController({}, storage);
  first.attach('boot-a', 'owner');
  first.create('draft', 1, 'recipe', members);
  const second = createBatchPlanController({}, storage);
  second.attach('boot-b', 'another-owner');
  assert.equal(second.getSnapshot().plans.length, 0);
});
