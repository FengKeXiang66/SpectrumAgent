import test from 'node:test';
import assert from 'node:assert/strict';
import { initialChat, parseSse, reduceChat, scalarText, type AgentEvent, type PlanDecision } from './sse.ts';

const step: AgentEvent = { event: 'step', data: { seq: 1, tool: 'datasets.list', status: 'ok', result_summary: { count: 2 } } };
const done: AgentEvent = { event: 'done', data: { content: '查询完成', step_count: 1 } };
const human: AgentEvent = { event: 'human_check', data: { check_id: 'check-1', tool: 'annotations.draft_confirm', summary: { revision: 2, overwrite: true }, reason: '标注版本确认' } };
const error: AgentEvent = { event: 'error', data: { code: 'LLM_TRANSPORT', detail: 'LLM_TRANSPORT' } };
const encode = (events: AgentEvent[]) => events.map(event => `event: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`).join('');

for (const [name, events] of [
  ['正常流', [step, done]], ['确认后挂起', [human]], ['错误收尾', [step, error]], ['空流', []],
] as const) test(`SSE ${name} retains order and JSON`, () => {
  assert.deepEqual(parseSse(encode([...events])), events);
  const state = reduceChat(initialChat, { type: 'events', events: [...events] });
  assert.deepEqual(state.entries, events);
  assert.equal(state.busy, false);
});

test('SSE accepts CRLF, multiline data, comments and final frame at EOF', () => {
  assert.deepEqual(parseSse(': comment\r\nevent: done\r\ndata: {"content":"完成",\r\ndata: "step_count":0}'),
    [{ event: 'done', data: { content: '完成', step_count: 0 } }]);
});

test('SSE rejects unknown events, missing event, malformed and nonobject data', () => {
  for (const text of ['event: other\ndata: {}\n\n', 'data: {}\n\n', 'event: done\ndata: invalid\n\n', 'event: done\ndata: []\n\n']) {
    assert.throws(() => parseSse(text));
  }
});

test('SSE collector retains every rejected step beyond eight', () => {
  const events = Array.from({ length: 10 }, (_, seq): AgentEvent => ({ event: 'step', data: {
    seq: seq + 1, tool: 'datasets.list', status: seq < 2 ? 'rejected' : 'ok', result_summary: seq < 2 ? { error: 'TOOL_SEQUENCE_LIMIT' } : { count: 2 },
  } }));
  assert.deepEqual(parseSse(encode([...events, done])), [...events, done]);
});

test('approve disables both controls and records executing until response', () => {
  const pending = reduceChat(initialChat, { type: 'events', events: [human] });
  const approved = reduceChat(pending, { type: 'decision', decision: 'approve' });
  assert.equal(approved.busy, true);
  assert.equal(approved.executing, true);
  assert.deepEqual(approved.pending, human.data);
  assert.equal(reduceChat(approved, { type: 'decision', decision: 'reject' }), approved);
  const finished = reduceChat(approved, { type: 'events', events: [step, done] });
  assert.equal(finished.pending, null);
  assert.equal(finished.executing, false);
  assert.deepEqual(finished.entries, [human, step, done]);
});

test('reject immediately closes confirmation card; server result remains ordered', () => {
  const pending = reduceChat(initialChat, { type: 'events', events: [human] });
  const rejected = reduceChat(pending, { type: 'decision', decision: 'reject' });
  assert.equal(rejected.pending, null);
  assert.equal(rejected.busy, true);
  assert.equal(rejected.executing, false);
  const events: AgentEvent[] = [{ event: 'step', data: { ...step.data, status: 'rejected', result_summary: { error: 'HUMAN_REJECTED' } } }, done];
  assert.deepEqual(reduceChat(rejected, { type: 'events', events }).entries, [human, ...events]);
});

test('pending check accepts ordinary dialogue and sequential checks replace pending id', () => {
  const pending = reduceChat(initialChat, { type: 'events', events: [human] });
  const sending = reduceChat(pending, { type: 'send', content: '确认保存' });
  assert.equal(sending.busy, true);
  assert.deepEqual(sending.pending, human.data);
  assert.equal(sending.entries.at(-1)?.event, 'user');
  const nextHuman: AgentEvent = { event: 'human_check', data: { ...human.data, check_id: 'check-2' } };
  const next = reduceChat(reduceChat(pending, { type: 'decision', decision: 'approve' }), { type: 'events', events: [step, nextHuman] });
  assert.equal(next.pending && 'check_id' in next.pending && next.pending.check_id, 'check-2');
  assert.equal(next.busy, false);
});

test('clarify and errors release busy state and keep messages in order', () => {
  const sending = reduceChat(initialChat, { type: 'send', content: '查询' });
  assert.equal(sending.busy, true);
  assert.equal(reduceChat(sending, { type: 'send', content: 'duplicate' }), sending);
  const clarified = reduceChat(sending, { type: 'events', events: [{ event: 'clarify', data: { question: '哪个数据集？' } }] });
  assert.deepEqual(clarified.entries.map(entry => entry.event), ['user', 'clarify']);
  assert.equal(clarified.pending, null);
  assert.equal(clarified.busy, false);
  const failed = reduceChat(sending, { type: 'events', events: [error] });
  assert.equal(failed.error, '无法连接模型服务，请检查网络或网关设置');
  assert.equal(reduceChat(sending, { type: 'failed', detail: 'ENGINE_NOT_READY' }).busy, false);
});

test('summary renderer displays scalars and excludes unexpected objects', () => {
  assert.equal(scalarText({ revision: 2, overwrite: false, note: null, id: 'cube-1', nested: {} } as never),
    'revision: 2 · overwrite: false · note: null · id: cube-1');
});

const plan: Extract<AgentEvent, { event: 'plan' }> = { event: 'plan', data: { plan_id: 'round-1', reason: '执行计划待确认',
  steps: [1, 2, 3].map(seq => ({ seq, tool: 'datasets.list', summary: {}, gpu: false, estimate_ms: null })) } };

test('plan SSE is accepted, accepts dialogue and cannot use the tool-decision path', () => {
  assert.deepEqual(parseSse(encode([plan])), [plan]);
  const pending = reduceChat(initialChat, { type: 'events', events: [plan] });
  assert.deepEqual(pending.pending, plan.data);
  assert.equal(reduceChat(pending, { type: 'send', content: '批准执行' }).busy, true);
  assert.deepEqual(reduceChat(pending, { type: 'send', content: '批准执行' }).pending, plan.data);
  assert.equal(reduceChat(pending, { type: 'decision', decision: 'approve' }), pending);
  assert.equal(reduceChat(initialChat, { type: 'plan', action: 'approve' }), initialChat);
});

test('unrecognized approval dialogue keeps its card while terminal outcomes clear it', () => {
  for (const card of [human, plan]) {
    const pending = reduceChat(initialChat, { type: 'events', events: [card] });
    const sending = reduceChat(pending, { type: 'send', content: '解释一下这一步' });
    const clarify: AgentEvent = { event: 'clarify', data: { question: '请明确批准或拒绝，原计划尚未执行。', keep_pending: true } };
    const waiting = reduceChat(sending, { type: 'events', events: [clarify] });
    assert.deepEqual(waiting.pending, card.data);
    assert.equal(waiting.busy, false);
    assert.equal(reduceChat(waiting, { type: 'send', content: '同意' }).busy, true);
    for (const terminal of [done, error, { event: 'clarify', data: { question: '请选择数据' } } as AgentEvent]) {
      assert.equal(reduceChat(sending, { type: 'events', events: [terminal] }).pending, null);
    }
    assert.deepEqual(parseSse(encode([clarify])), [clarify]);
  }
  assert.throws(() => parseSse('event: clarify\ndata: {"question":"批准吗","keep_pending":"true"}\n\n'));
});

test('plan actions preserve pending while executing and retain the decision with the original plan', () => {
  for (const decision of [{ action: 'approve' }, { action: 'skip', step_ref: 2, reason: '跳过' },
    { action: 'rollback', step_ref: 3, reason: '从末步开始' }, { action: 'reject', reason: '拒绝' }] satisfies PlanDecision[]) {
    const pending = reduceChat(initialChat, { type: 'events', events: [plan] });
    const next = reduceChat(pending, { type: 'plan', ...decision });
    assert.equal(next.busy, true);
    assert.equal(next.executing, decision.action !== 'reject');
    assert.deepEqual(next.pending, decision.action === 'reject' ? null : plan.data);
    assert.deepEqual(next.entries, [{ ...plan, decision }]);
    assert.equal(reduceChat(next, { type: 'plan', action: 'approve' }), next);
    const finished = reduceChat(next, { type: 'events', events: [done] });
    assert.equal(finished.pending, null);
    assert.deepEqual(finished.entries[0], { ...plan, decision });
  }
});

test('plan approval can suspend again at human check and all terminal events clear pending', () => {
  const pending = reduceChat(initialChat, { type: 'events', events: [plan] });
  const approved = reduceChat(pending, { type: 'plan', action: 'approve' });
  const checked = reduceChat(approved, { type: 'events', events: [human] });
  assert.deepEqual(checked.pending, human.data);
  assert.equal(reduceChat(checked, { type: 'plan', action: 'approve' }), checked);
  for (const event of [done, error, { event: 'clarify', data: { question: '补充' } } as AgentEvent]) {
    assert.equal(reduceChat(approved, { type: 'events', events: [event] }).pending, null);
  }
});
