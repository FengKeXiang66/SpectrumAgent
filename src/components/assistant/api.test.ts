import test from 'node:test';
import assert from 'node:assert/strict';
import { agentClient, requests, type AgentRequest, type InvokeAgent, type MessageBody } from './api.ts';

test('all agent operations invoke only agent_forward with exact projection', async () => {
  const calls: { command: string; request: AgentRequest }[] = [];
  const send: InvokeAgent = async <T>(command: string, args: { request: AgentRequest }) => {
    calls.push({ command, request: args.request });
    return { events: [] } as T;
  };
  const api = agentClient(send);
  await api.createSession();
  assert.deepEqual(await api.sendMessage('session-1', { content: '查询' }), { events: [] });
  await api.sendMessage('session-1', { check_id: 'check-1', decision: 'approve' });
  await api.getSteps('session-1');
  assert.deepEqual(calls, [
    { command: 'agent_forward', request: { op: 'create_session' } },
    { command: 'agent_forward', request: { op: 'send_message', id: 'session-1', body: { content: '查询' } } },
    { command: 'agent_forward', request: { op: 'send_message', id: 'session-1', body: { check_id: 'check-1', decision: 'approve' } } },
    { command: 'agent_forward', request: { op: 'get_steps', id: 'session-1' } },
  ]);
});

test('view state, URL, key and mixed-body extras cannot enter IPC', () => {
  assert.deepEqual(requests.sendMessage('s', { content: '查询', check_id: 'c', decision: 'approve', key: 'secret',
    url: '/health', busy: true, estimated_mat_bytes: 2 } as MessageBody), { op: 'send_message', id: 's', body: { content: '查询' } });
  assert.deepEqual(requests.sendMessage('s', { check_id: 'c', decision: 'reject', view: 'hidden', key: 'secret' } as MessageBody),
    { op: 'send_message', id: 's', body: { check_id: 'c', decision: 'reject' } });
});

test('structured preflight HTTP status and errors pass through unchanged', async () => {
  const error = { error: 'INVALID_REQUEST', detail: '参数不合法', context: {}, status_code: 400 };
  const send: InvokeAgent = async () => { throw error; };
  await assert.rejects(agentClient(send).sendMessage('s', { content: '查询' }), actual => actual === error);
});
