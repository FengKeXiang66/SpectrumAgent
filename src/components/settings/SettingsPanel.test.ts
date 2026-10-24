import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Children, createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { SettingsPanelView } from './SettingsPanel.ts';
import { createSettingsForm, emptyForm } from './form.ts';
import { settingsClient, type InvokeSettings, type LLMConfig, type SettingsRequest } from './settings-forward.ts';

const config: LLMConfig = { base_url: 'https://mock.invalid/v1', model: 'test-model', temperature: '0.5', max_tokens: '32', timeout_ms: '1000' };
type Element = ReactElement<Record<string, unknown>>;
function find(node: ReactNode, tag: string, name?: string): Element {
  const found: Element[] = [];
  function visit(value: ReactNode) {
    if (!isValidElement<Record<string, unknown>>(value)) return;
    if (value.type === tag && (name === undefined || value.props.name === name || value.props.type === name)) found.push(value);
    Children.forEach(value.props.children as ReactNode, visit);
  }
  visit(node);
  assert.ok(found.length, `rendered ${tag} ${name ?? ''} exists`);
  return found[0];
}
function harness(send?: InvokeSettings, hasKey = false) {
  let state = emptyForm(), closed = 0;
  const calls: SettingsRequest[] = [];
  const mock: InvokeSettings = async <T>(_command: string, { request }: { request: SettingsRequest }) => {
    calls.push(request);
    if (request.op === 'put_key') { hasKey = request.key !== ''; return { has_key: hasKey } as T; }
    return { ...(request.op === 'put_llm' ? request.body : emptyForm().values), has_key: hasKey } as T;
  };
  const form = createSettingsForm(settingsClient(send ?? mock), next => { state = next; });
  const props = () => ({ state, onField: form.edit, onKey: form.editKey, onSave: form.save, onClose: () => { closed++; } });
  const tree = () => SettingsPanelView(props());
  return { form, calls, tree, state: () => state, closed: () => closed,
    render: () => renderToStaticMarkup(createElement(SettingsPanelView, props())),
    change(name: string, value: string) {
      const input = find(tree(), 'input', name);
      (input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } });
    },
    submit: () => (find(tree(), 'form').props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} }),
  };
}

test('settings modal starts with five empty fields, a password input and an unknown key status', () => {
  const h = harness();
  for (const name of Object.keys(config)) assert.equal(find(h.tree(), 'input', name).props.value, '');
  const password = find(h.tree(), 'input', 'key');
  assert.equal(password.props.type, 'password');
  assert.equal(password.props.autoComplete, 'new-password');
  assert.equal(password.props.value, '');
  assert.match(h.render(), /<dialog[^>]*aria-labelledby="llm-settings-title"/);
  assert.match(h.render(), /正在读取 key 配置状态/);
  assert.equal(find(h.tree(), 'button', 'submit').props.disabled, true);
});

test('rendered field changes and submit save the five-key config then key, and clear the password', async () => {
  const h = harness();
  await h.form.load();
  for (const [name, value] of Object.entries(config)) h.change(name, value);
  h.change('key', 'test-only-credential');
  assert.equal(find(h.tree(), 'input', 'key').props.type, 'password');
  await h.submit();
  assert.deepEqual(h.calls, [{ op: 'get_llm' }, { op: 'put_llm', body: config }, { op: 'put_key', key: 'test-only-credential' }]);
  assert.deepEqual(h.state().values, config);
  assert.equal(find(h.tree(), 'input', 'key').props.value, '');
  assert.match(h.render(), /key 已配置/);
  assert.match(h.render(), /配置与 key 已保存/);
  assert.doesNotMatch(h.render(), /test-only-credential/);
});

test('GET has_key renders both states without pre-filling a key, and blank key preserves existing credentials', async () => {
  for (const hasKey of [false, true]) {
    const h = harness(undefined, hasKey);
    await h.form.load();
    assert.match(h.render(), hasKey ? /key 已配置/ : /key 未配置/);
    assert.equal(find(h.tree(), 'input', 'key').props.value, '');
    await h.submit();
    assert.deepEqual(h.calls, [{ op: 'get_llm' }, { op: 'put_llm', body: emptyForm().values }]);
    assert.equal(h.state().hasKey, hasKey);
  }
});

test('GET failure disables saving and fields while the rendered cancel button remains usable', async () => {
  const calls: SettingsRequest[] = [];
  const h = harness(async (_command, { request }) => {
    calls.push(request); throw { error: 'ENGINE_NOT_READY', detail: '引擎不可用' };
  });
  await h.form.load();
  assert.match(h.render(), /ENGINE_NOT_READY：引擎不可用/);
  assert.equal(find(h.tree(), 'button', 'submit').props.disabled, true);
  assert.equal(find(h.tree(), 'input', 'key').props.disabled, true);
  const cancel = find(h.tree(), 'button', 'button');
  assert.equal(cancel.props.disabled, false);
  (cancel.props.onClick as () => void)();
  assert.equal(h.closed(), 1);
  await h.submit();
  assert.deepEqual(calls, [{ op: 'get_llm' }]);
});

test('nonempty URL and numeric validation blocks invalid saves without inventing provider limits', async () => {
  const h = harness();
  await h.form.load();
  for (const [field, value] of [['base_url', 'file:///tmp'], ['base_url', 'https://user:pass@mock.invalid/v1'],
    ['temperature', 'Infinity'], ['max_tokens', '0'], ['max_tokens', '1.5'], ['timeout_ms', '-1']]) {
    h.change(field, value);
    await h.submit();
    assert.ok(h.state().error.includes(field));
    assert.deepEqual(h.calls, [{ op: 'get_llm' }]);
    h.change(field, '');
  }
  h.change('temperature', '-0.5'); // Backend accepts any finite temperature, with no provider range preset.
  h.change('max_tokens', '1');
  h.change('timeout_ms', '1');
  await h.submit();
  assert.equal(h.calls.length, 2);
  assert.equal(h.state().error, '');
});

test('backend 400 code and detail are rendered and a failed config save never submits the key', async () => {
  const calls: SettingsRequest[] = [];
  const h = harness(async <T>(_command: string, { request }: { request: SettingsRequest }) => {
    calls.push(request);
    if (request.op === 'get_llm') return { ...config, has_key: false } as T;
    throw { error: 'INVALID_REQUEST', detail: '请求参数不合法', context: {}, status_code: 400 };
  });
  await h.form.load();
  h.change('key', 'test-only-credential');
  await h.submit();
  assert.match(h.render(), /400 · INVALID_REQUEST：请求参数不合法/);
  assert.deepEqual(calls.map(request => request.op), ['get_llm', 'put_llm']);
  assert.equal(find(h.tree(), 'button', 'submit').props.disabled, false);
});

test('failed key write reports partial save, clears its input and redacts credentials in errors', async () => {
  const h = harness(async <T>(_command: string, { request }: { request: SettingsRequest }) => {
    if (request.op === 'put_key') throw { error: 'INVALID_REQUEST', detail: `invalid ${request.key}`, status_code: 400 };
    return { ...config, has_key: false } as T;
  });
  await h.form.load();
  h.change('key', 'test-only-credential');
  await h.submit();
  assert.equal(find(h.tree(), 'input', 'key').props.value, '');
  assert.match(h.render(), /配置已保存，key 未保存/);
  assert.match(h.render(), /400 · INVALID_REQUEST/);
  assert.doesNotMatch(h.render(), /test-only-credential/);
  assert.equal(h.state().hasKey, false);
});

test('saving prevents duplicate submits and disposing ignores an in-flight GET', async () => {
  let release: () => void = () => {};
  const pending = new Promise<void>(resolve => { release = resolve; });
  let puts = 0;
  const send: InvokeSettings = async <T>(_command: string, { request }: { request: SettingsRequest }) => {
    if (request.op === 'put_llm') { puts++; await pending; }
    return { ...config, has_key: false } as T;
  };
  const h = harness(send);
  await h.form.load();
  const save = h.submit();
  assert.equal(find(h.tree(), 'button', 'submit').props.disabled, true);
  await h.submit();
  assert.equal(puts, 1);
  release();
  await save;
  let updates = 0;
  const disposed = createSettingsForm(settingsClient(send), () => { updates++; });
  const load = disposed.load();
  disposed.dispose();
  await load;
  assert.equal(updates, 0);
});

test('App settings entry imports and opens SettingsPanel, preserving UI-to-configuration reachability', () => {
  const source = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
  assert.match(source, /import SettingsPanel from '\.\/components\/settings\/SettingsPanel'/);
  assert.match(source, /onClick=\{\(\) => setSettingsOpen\(true\)\}>设置<\/button>/);
  assert.match(source, /settingsOpen && status.phase === 'Ready' && <SettingsPanel/);
});
