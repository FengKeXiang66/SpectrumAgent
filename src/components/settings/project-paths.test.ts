import test from 'node:test';
import assert from 'node:assert/strict';
import { Children, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createPathForm, emptyPathForm, type PathServices } from './project-path-form.ts';
import { ProjectPathsView } from './ProjectPathsView.ts';
import { requests, settingsClient, type ProjectPaths, type SettingsRequest } from './settings-forward.ts';
import { normalizePath, pathPrefill } from '../datasets/paths.ts';
import { datasetClient } from '../datasets/api.ts';

const saved: ProjectPaths = { source_path: 'C:\\source', output_root: '\\\\nas\\future', data_root: 'D:\\actual', output_enabled: false };
type Element = ReactElement<Record<string, unknown>>;
function find(node: ReactNode, tag: string, name?: string): Element {
  let result: Element | undefined;
  function visit(value: ReactNode) {
    if (!isValidElement<Record<string, unknown>>(value)) return;
    if (value.type === tag && (name === undefined || value.props.name === name || value.props.type === name)) result ??= value;
    Children.forEach(value.props.children as ReactNode, visit);
  }
  visit(node); assert.ok(result, `${tag} ${name ?? ''} exists`); return result;
}
function harness(overrides: Partial<PathServices> = {}, search = '') {
  let state = emptyPathForm(); const calls: unknown[] = [];
  const form = createPathForm({ projects: async () => [{ id: 'default', name: '默认项目' }],
    getProjectPaths: async id => { calls.push(['get', id]); return saved; },
    putProjectPaths: async (id, values) => { calls.push(['put', id, values]); return { ...saved, ...values }; },
    chooseDirectory: async () => 'smb://nas/browse/selected', ...overrides }, next => { state = next; }, search);
  const props = () => ({ state, onEdit: form.edit, onBrowse: form.browse, onSave: form.save, onRetry: form.load });
  return { form, calls, state: () => state, tree: () => ProjectPathsView(props()), render: () => renderToStaticMarkup(ProjectPathsView(props())) };
}

test('C SMB and URL prefills become UNC strings, preserving independent empty and absent fields', () => {
  assert.equal(normalizePath('smb://nas/share/批次%201'), '\\\\nas\\share\\批次 1');
  assert.equal(normalizePath('C:\\source'), 'C:\\source');
  assert.deepEqual(pathPrefill('?src=smb%3A%2F%2Fnas%2Fshare%2Fbatch&out='), { source_path: '\\\\nas\\share\\batch', output_root: '' });
  assert.deepEqual(pathPrefill(''), {});
  assert.throws(() => normalizePath('smb://user:private@nas/share'), /不得包含凭据/);
  assert.throws(() => normalizePath('smb://nas/share/../other'), /SMB/);
});

test('C rendered source and output inputs edit independently and save only the project defaults', async () => {
  const h = harness({}, '?src=smb%3A%2F%2Fnas%2Fprefill'); await h.form.load();
  assert.equal(find(h.tree(), 'input', 'source_path').props.value, '\\\\nas\\prefill');
  assert.equal(find(h.tree(), 'input', 'output_root').props.value, saved.output_root);
  const edit = find(h.tree(), 'input', 'output_root').props.onChange as (event: { target: { value: string } }) => void;
  edit({ target: { value: 'smb://nas/another-output' } });
  assert.equal(h.state().values.source_path, '\\\\nas\\prefill');
  const submit = find(h.tree(), 'form').props.onSubmit as (event: { preventDefault(): void }) => void;
  submit({ preventDefault() {} }); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(h.calls, [['get', 'default'], ['put', 'default', { source_path: '\\\\nas\\prefill', output_root: '\\\\nas\\another-output' }]]);
  for (const text of ['源目录只读', '输出根当前仅保存、不生效', 'D:', 'ENVI', '第二批验证', '阶段二支持', '保存为该项目默认']) assert.ok(h.render().includes(text));
  assert.doesNotMatch(h.render(), /IrisCube|\.mat/);
});

test('C browse targets only its field, cancel preserves values, and S11 summary displays saved values without editing', async () => {
  const h = harness(); await h.form.load(); await h.form.browse('source_path');
  assert.equal(h.state().values.source_path, '\\\\nas\\browse\\selected'); assert.equal(h.state().values.output_root, saved.output_root);
  const cancel = harness({ chooseDirectory: async () => null }); await cancel.form.load(); await cancel.form.browse('output_root');
  assert.deepEqual(cancel.state().values, saved);
  const html = renderToStaticMarkup(ProjectPathsView({ state: cancel.state(), summary: true, onEdit() {}, onBrowse() {}, onSave() {}, onRetry() {} }));
  assert.ok(html.includes(saved.source_path) && html.includes(saved.output_root) && html.includes(saved.data_root));
  assert.doesNotMatch(html, /<input|<form/);
});

test('C path form failure disables saving; disposal rejects stale GET and double save is suppressed', async () => {
  const failed = harness({ getProjectPaths: async () => { throw { detail: '引擎未就绪' }; } });
  await failed.form.load(); assert.doesNotMatch(failed.render(), /type="submit"/); await failed.form.save();
  assert.match(failed.render(), /引擎未就绪/);
  let release!: (value: ProjectPaths) => void, writes = 0;
  const pending = new Promise<ProjectPaths>(resolve => { release = resolve; });
  const h = harness({ putProjectPaths: async () => { writes++; return pending; } });
  await h.form.load(); const save = h.form.save(); await h.form.save(); assert.equal(writes, 1);
  release(saved); await save; assert.equal(h.state().phase, 'ready');
  const disposed = harness({ getProjectPaths: () => pending }); const load = disposed.form.load(); disposed.form.dispose(); await load;
  assert.equal(disposed.state().phase, 'loading');
});

test('C project path IPC uses fixed ops, strips view extras, normalizes both paths and propagates refusal', async () => {
  const calls: SettingsRequest[] = [];
  const api = settingsClient(async <T>(command: string, args: { request: SettingsRequest }) => {
    assert.equal(command, 'settings_forward'); calls.push(args.request); return saved as T;
  });
  assert.deepEqual(await api.getProjectPaths('project'), saved);
  await api.putProjectPaths('project', { source_path: 'smb://nas/source', output_root: 'smb://nas/output', output_enabled: true, url: '/other' } as never);
  assert.deepEqual(calls, [{ op: 'get_project_paths', project_id: 'project' },
    { op: 'put_project_paths', project_id: 'project', body: { source_path: '\\\\nas\\source', output_root: '\\\\nas\\output' } }]);
  assert.deepEqual(requests.putProjectPaths('project', { source_path: '', output_root: '' }), { op: 'put_project_paths', project_id: 'project', body: { source_path: '', output_root: '' } });
  const refusal = { error: 'DATASET_IDENTITY_MISMATCH' }, bad = settingsClient(async () => { throw refusal; });
  await assert.rejects(bad.getProjectPaths('project'), error => error === refusal);
  const imports: unknown[] = [];
  const datasets = datasetClient(async () => [], async <T>(request: unknown) => { imports.push(request); return {} as T; });
  await datasets.importDirectory('smb://nas/source/batch', false);
  assert.deepEqual(imports, [{ op: 'import', path: '\\\\nas\\source\\batch', raw: false }]);
});
