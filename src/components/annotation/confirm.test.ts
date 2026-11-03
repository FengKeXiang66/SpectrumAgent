import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { draftClient, requests, type ConfirmOptions, type DraftRequest, type InvokeDraft } from './draft-api.ts';
import { LARGE_MAT_BYTES, loadConfirmation, mayConfirm, needsAdditionalConfirmation } from './confirm.ts';
import { ConfirmCardView, type ConfirmCardViewProps } from './ConfirmCard.ts';
import { readFileSync } from 'node:fs';

test('2GiB boundary and plus one require exactly the shared extra approval', () => {
  assert.equal(LARGE_MAT_BYTES, 2 * 1024 ** 3);
  assert.equal(needsAdditionalConfirmation(LARGE_MAT_BYTES), false);
  assert.equal(needsAdditionalConfirmation(LARGE_MAT_BYTES + 1), true);
  assert.equal(mayConfirm(LARGE_MAT_BYTES, false), true);
  assert.equal(mayConfirm(LARGE_MAT_BYTES + 1, false), false);
  assert.equal(mayConfirm(LARGE_MAT_BYTES + 1, true), true);
  for (const invalid of [-1, NaN, Infinity, .5]) assert.equal(mayConfirm(invalid, true), false);
});

test('draft client projects only fixed confirm fields into the tenth command', async () => {
  const calls: { command: string; request: DraftRequest }[] = [];
  const send: InvokeDraft = async <T>(command: string, args: { request: DraftRequest }) => {
    calls.push({ command, request: args.request });
    return {} as T;
  };
  const api = draftClient(send);
  await api.get('cube');
  await api.confirm('cube', { revision: 2, overwrite: true, note: 'v2', url: '/health', key: 'secret', estimated_mat_bytes: 10 } as ConfirmOptions);
  assert.deepEqual(calls, [
    { command: 'annotations_draft_forward', request: { op: 'get_draft', cube_id: 'cube' } },
    { command: 'annotations_draft_forward', request: { op: 'confirm', cube_id: 'cube', body: { revision: 2, overwrite: true, note: 'v2' } } },
  ]);
  assert.deepEqual(requests.confirm('c', { revision: 0 }), { op: 'confirm', cube_id: 'c', body: { revision: 0 } });
});

test('mock forward fetches estimate then confirms the fetched revision', async () => {
  const calls: DraftRequest[] = [];
  const send: InvokeDraft = async <T>(_command: string, { request }: { request: DraftRequest }) => {
    calls.push(request);
    return (request.op === 'get_draft' ? { cube_id: 'c', revision: 7, estimated_mat_bytes: 12800, document: { ignored: true } }
      : { version_id: 'v', training_mat_id: 'm', version_no: 1, n_spectra: 16, overlap_conflicts: 0 }) as T;
  };
  const api = draftClient(send);
  const view = await loadConfirmation(api, 'c');
  assert.deepEqual(view, { cube_id: 'c', revision: 7, estimated_mat_bytes: 12800 });
  assert.equal(mayConfirm(view.estimated_mat_bytes, false), true);
  assert.equal((await api.confirm('c', { revision: view.revision })).training_mat_id, 'm');
  assert.deepEqual(calls, [{ op: 'get_draft', cube_id: 'c' }, { op: 'confirm', cube_id: 'c', body: { revision: 7 } }]);
});

test('fetch failure and invalid summaries block approval instead of assuming zero', async () => {
  const error = { error: 'ENGINE_NOT_READY', detail: 'offline' };
  await assert.rejects(loadConfirmation({ get: async () => { throw error; } }, 'c'), e => e === error);
  for (const view of [{ cube_id: 'other', revision: 1, estimated_mat_bytes: 0 },
    { cube_id: 'c', revision: -1, estimated_mat_bytes: 0 }, { cube_id: 'c', revision: 0, estimated_mat_bytes: -1 }]) {
    await assert.rejects(loadConfirmation({ get: async () => view }, 'c'), { error: 'INVALID_DRAFT_SUMMARY' });
  }
});

const actions = { onApprove() {}, onReject() {}, onAdditional() {}, onBack() {} };
function render(p: Partial<ConfirmCardViewProps>) {
  return renderToStaticMarkup(createElement(ConfirmCardView, { ...actions, view: null, error: '', disabled: false,
    additional: false, approveLabel: '批准', rejectLabel: '拒绝', ...p }));
}
test('confirmation card renders fetched byte count, loading, refusal and second dialog', () => {
  const loaded = render({ view: { cube_id: 'c', revision: 1, estimated_mat_bytes: 12800 } });
  assert.match(loaded, /estimated_mat_bytes: 12800 字节/);
  assert.match(loaded, /revision: 1/);
  assert.match(loaded, /<button>批准<\/button>/);
  assert.match(render({}), /disabled=""[^>]*>批准/);
  const failed = render({ error: 'ENGINE_NOT_READY：offline' });
  assert.match(failed, /role="alert"/);
  assert.match(failed, /<button>拒绝<\/button>/);
  assert.match(failed, /disabled=""[^>]*>批准/);
  const large = render({ view: { cube_id: 'c', revision: 1, estimated_mat_bytes: LARGE_MAT_BYTES + 1 }, additional: true });
  assert.match(large, /role="alertdialog"/);
  assert.match(large, /继续生成训练 MAT/);
});

test('only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned', () => {
  const rest = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  const agent = readFileSync(new URL('../assistant/AssistantBar.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(rest, /import ConfirmCard from/);
  assert.doesNotMatch(rest, /drafts\.confirm/);
  assert.doesNotMatch(rest, /confirmVersion/);
  assert.doesNotMatch(rest, /确认版本并生成训练 MAT/);
  assert.match(agent, /import ConfirmCard from/);
  assert.match(agent, /key=\{state.pending.check_id\}/);
  assert.match(agent, /check_id: state.pending!.check_id, decision: 'approve'/);
  assert.doesNotMatch(agent, /drafts.confirm/);
});
