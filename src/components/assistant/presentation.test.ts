import test from 'node:test';
import assert from 'node:assert/strict';
import { candidatePreviewKey, changedCubes, datasetChoices, proposedCandidates, readableText, selectWorkspace } from './presentation.ts';
import { friendlyError, initialChat, parseSse, reduceChat, requestError, type AgentEvent } from './sse.ts';
import type { DatasetRecord } from '../datasets/types.ts';
import type { Working } from '../annotation/types.ts';

const first = '00000000-0000-0000-0000-000000000001';
const second = '00000000-0000-0000-0000-000000000002';
const gesture = 'g-0123456789abcdef0123456789abcdef';
const list = (summary: Record<string, string | number>): AgentEvent => ({ event: 'step', data: {
  tool: 'datasets.list', seq: 1, status: 'ok', result_summary: summary,
} });

test('server-listed ordinals and names are usable without reimporting files in the current UI', () => {
  const choices = datasetChoices([list({ dataset_count: 2, dataset_2_id: first, dataset_2_name: '样品 B', dataset_1_id: second, dataset_1_name: '样品 A' })], []);
  assert.deepEqual(choices, [{ id: second, index: 1, label: '样品 A' }, { id: first, index: 2, label: '样品 B' }]);
  const text = readableText(`选择 ${first}，另一个 ${second}`, choices, []);
  assert.match(text, /2号 样品 B/); assert.match(text, /1号 样品 A/);
  assert.ok(!text.includes(first) && !text.includes(second));
});

test('legacy lists retain backend order while local names remain local', () => {
  const records = [{ id: second, dataset: { name: '本地样品' } }] as DatasetRecord[];
  const choices = datasetChoices([list({ count: 2, dataset_ids: `${second}, ${first}` })], records);
  assert.deepEqual(choices.map(choice => [choice.id, choice.index, choice.label]), [[second, 1, '本地样品'], [first, 2, '数据集 2']]);
  assert.equal(readableText(`版本 ${first}`, [], []), '版本 引用 00000000');
});

test('changing cubes clears an old gesture and same-cube followups retain it', () => {
  assert.deepEqual(selectWorkspace({ cube_id: first, gesture_ref: gesture }, { cube_id: second }), { cube_id: second });
  assert.deepEqual(selectWorkspace({ cube_id: first, gesture_ref: gesture }, { cube_id: first }), { cube_id: first, gesture_ref: gesture });
  assert.deepEqual(selectWorkspace({ cube_id: first, gesture_ref: gesture }, { cube_id: first, gesture_ref: undefined }), { cube_id: first, gesture_ref: undefined });
});

test('only successful annotation or preprocessing steps cause authoritative result refresh', () => {
  const events: AgentEvent[] = [
    list({ dataset_ids: first }),
    { event: 'step', data: { seq: 2, tool: 'annotations.draft_confirm', status: 'ok', result_summary: { cube_id: second } } },
    { event: 'step', data: { seq: 3, tool: 'preprocess.run', status: 'error', result_summary: { cube_id: first } } },
    { event: 'step', data: { seq: 4, tool: 'preprocess.run', status: 'ok', result_summary: { run_id: 'run-1' } } },
  ];
  assert.deepEqual(changedCubes(events, { cube_id: first }), [second, first]);
});

test('workspace SSE rejects paths, unbound geometry, unknown stage and invalid revisions', () => {
  const value = { cube_id: first, stage: 'annotation', display_name: '样品一', revision: 0 };
  assert.deepEqual(parseSse(`event: workspace\ndata: ${JSON.stringify(value)}\n\n`), [{ event: 'workspace', data: value }]);
  for (const invalid of [{ cube_id: '../health' }, { ...value, path: 'private' }, { ...value, stage: 'random' },
    { ...value, revision: -1 }, { ...value, gesture_ref: null }, { ...value, points: [[1, 2]] }]) {
    assert.throws(() => parseSse(`event: workspace\ndata: ${JSON.stringify(invalid)}\n\n`));
  }
});

test('request failures and SSE failures share human-readable error messages', () => {
  const request = requestError({ error: 'LLM_PROTOCOL', detail: 'LLM_PROTOCOL' });
  const state = reduceChat(initialChat, { type: 'events', events: [{ event: 'error', data: { code: 'LLM_PROTOCOL', detail: 'LLM_PROTOCOL' } }] });
  assert.equal(request, state.error); assert.ok(!request.includes('LLM_PROTOCOL'));
  assert.equal(requestError({ error: 'UNKNOWN_INTERNAL', detail: 'UNKNOWN_INTERNAL' }), '请求未完成，已保留当前结果。请重试或查看执行日志。');
  assert.deepEqual(reduceChat({ ...state, busy: false }, { type: 'reset' }), initialChat);
});

test('curated backend explanations survive both error delivery paths', () => {
  for (const [code, detail] of [
    ['LLM_HTTP', '模型服务鉴权失败，请检查密钥（HTTP 401）'],
    ['LLM_HTTP', '模型服务限流，请稍后重试（HTTP 429）'],
    ['LLM_HTTP', '模型响应格式不符合工具调用接口，请检查服务兼容性'],
    ['LLM_TOOL_PROTOCOL', '模型未返回有效的原生工具调用，请检查模型的工具调用兼容性'],
    ['LLM_OUTPUT_TRUNCATED', '模型输出达到长度上限，请提高输出上限后重试'],
    ['AGENT_NO_PROGRESS', '助手重复了相同操作，已停止重复执行并保留进度'],
    ['AGENT_BUDGET_EXCEEDED', '本次任务达到连续执行上限，已保留进度，请检查执行记录后继续'],
  ]) {
    assert.equal(requestError({ error: code, detail }), detail);
    assert.equal(reduceChat(initialChat, { type: 'events', events: [{ event: 'error', data: { code, detail } }] }).error, detail);
  }
  for (const code of ['LLM_TOOL_PROTOCOL', 'LLM_OUTPUT_TRUNCATED', 'AGENT_NO_PROGRESS', 'AGENT_BUDGET_EXCEEDED']) {
    assert.ok(!friendlyError(code, code).includes(code));
    assert.ok(!friendlyError(code, '').includes(code));
  }
});

test('AI preview focus uses the workflow reference rather than queue order or a diffusion identifier', () => {
  const reference = 'c-0123456789abcdef0123456789abcdef';
  const event: AgentEvent = { event: 'step', data: { seq: 5, tool: 'annotations.propose', status: 'ok',
    result_summary: { cube_id: second, status: 'preview', candidate_ref: reference } } };
  assert.deepEqual(proposedCandidates([event]), [{ cube_id: second, candidate_ref: reference }]);
  const working = { queue: [
    { id: reference, candidate_ref: 'c-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', superpixels: [1, 2] },
    { id: 'different-diffusion-id', candidate_ref: reference, superpixels: [3, 4] },
    { id: 'later-manual-preview', superpixels: [5, 6] },
  ] } as unknown as Working;
  assert.equal(candidatePreviewKey(working, reference), '3,4');
  assert.equal(candidatePreviewKey(working, 'missing'), null);
  assert.equal(candidatePreviewKey(null, reference), null);
  assert.deepEqual(proposedCandidates([{ ...event, data: { ...event.data, result_summary: { cube_id: second, status: 'need_seed' } } }]), []);
  assert.deepEqual(proposedCandidates([{ ...event, data: { ...event.data, status: 'error' } }]), []);
});
