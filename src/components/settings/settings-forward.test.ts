import test from 'node:test';
import assert from 'node:assert/strict';
import { requests, settingsClient, type InvokeSettings, type LLMConfig, type SettingsRequest } from './settings-forward.ts';

const config: LLMConfig = { base_url: 'https://mock.invalid/v1', model: 'test-model', temperature: '0.5', max_tokens: '32', timeout_ms: '1000', egress_enabled: true };

test('settings GET and two PUT operations use only settings_forward with exact bodies', async () => {
  const calls: { command: string; request: SettingsRequest }[] = [];
  const send: InvokeSettings = async <T>(command: string, { request }: { request: SettingsRequest }) => {
    calls.push({ command, request });
    return { ...config, has_key: request.op === 'put_key' } as T;
  };
  const api = settingsClient(send);
  assert.deepEqual(await api.getLLM(), { ...config, has_key: false });
  assert.deepEqual(await api.putLLM(config), { ...config, has_key: false });
  assert.deepEqual(await api.putKey('test-only-credential'), { has_key: true });
  assert.deepEqual(calls, [
    { command: 'settings_forward', request: { op: 'get_llm' } },
    { command: 'settings_forward', request: { op: 'put_llm', body: config } },
    { command: 'settings_forward', request: { op: 'put_key', key: 'test-only-credential' } },
  ]);
});

test('settings projections exclude credentials and view or route extras from config and responses', async () => {
  const extra = { ...config, key: 'test-only-credential', has_key: true, op: 'put_key', url: '/health', busy: true };
  assert.deepEqual(requests.putLLM(extra), { op: 'put_llm', body: config });
  assert.deepEqual(requests.getLLM(), { op: 'get_llm' });
  const api = settingsClient(async <T>() => extra as T);
  assert.deepEqual(await api.getLLM(), { ...config, has_key: true });
  assert.deepEqual(await api.putLLM(extra), { ...config, has_key: true });
  assert.deepEqual(await api.putKey('replacement'), { has_key: true });
});

test('settings forward preserves the backend 400 envelope unchanged', async () => {
  const error = { error: 'INVALID_REQUEST', detail: '请求参数不合法', context: {}, status_code: 400 };
  const api = settingsClient(async () => { throw error; });
  await assert.rejects(api.getLLM(), actual => actual === error);
  await assert.rejects(api.putLLM(config), actual => actual === error);
  await assert.rejects(api.putKey('test-only-credential'), actual => actual === error);
});

test('egress false remains boolean through config PUT and GET projections', async () => {
  const disabled = { ...config, egress_enabled: false };
  const calls: SettingsRequest[] = [];
  const api = settingsClient(async <T>(_command: string, { request }: { request: SettingsRequest }) => {
    calls.push(request);
    return { ...disabled, has_key: false } as T;
  });
  assert.deepEqual(await api.putLLM(disabled), { ...disabled, has_key: false });
  assert.deepEqual(await api.getLLM(), { ...disabled, has_key: false });
  assert.deepEqual(calls, [{ op: 'put_llm', body: disabled }, { op: 'get_llm' }]);
  assert.equal(typeof (calls[0] as { body: LLMConfig }).body.egress_enabled, 'boolean');
});
