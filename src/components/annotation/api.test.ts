import assert from 'node:assert/strict';
import test from 'node:test';
import { annotationClient, requests } from './api.ts';
import { describeAnnotationError, type AnnotationApi, type AnnotationRequest, type LabelBody } from './types.ts';

const id = 'ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB', version = '00000000-0000-0000-0000-000000000002';
const cases: [string, (api: AnnotationApi) => Promise<unknown>, AnnotationRequest][] = [
  ['superpixels', api => api.superpixels(id, { n_segments: 800, compactness: .5, pca_components: 3, force: true }), { op: 'superpixels', id, n_segments: 800, compactness: .5, pca_components: 3, force: true }],
  ['diffuse', api => api.diffuse(id, { point: [2, 3] }, { threshold: .92, queue_min_similarity: .8 }), { op: 'diffuse', id, seed: { point: [2, 3] }, threshold: .92, queue_min_similarity: .8 }],
  ['regions', api => api.regions(id, { superpixels: [0, 2] }, 'confirm', 'label-id'), { op: 'regions', id, geometry: { superpixels: [0, 2] }, action: 'confirm', label_id: 'label-id' }],
  ['undo', api => api.undo(id), { op: 'undo', id }],
  ['working', api => api.working(id), { op: 'working', id }],
  ['validate', api => api.validate(id), { op: 'validate', id }],
  ['save', api => api.save(id, { note: '备注', overwrite: true, confirm: true }), { op: 'save', id, note: '备注', overwrite: true, confirm: true }],
  ['versions', api => api.versions(id), { op: 'versions', id }],
  ['version_overlay', api => api.versionOverlay(id, version), { op: 'version_overlay', id, version }],
  ['projects', api => api.projects(), { op: 'projects' }],
  ['labels', api => api.labels(id), { op: 'labels', project_id: id }],
  ['add_label', api => api.addLabel({ project_id: id, from_catalog: 'plastic', codes: ['PS'] }), { op: 'add_label', body: { project_id: id, from_catalog: 'plastic', codes: ['PS'] } }],
  ['catalog', api => api.catalog(), { op: 'catalog' }],
];
for (const [name, call, expected] of cases) test(`IPC ${name}: exact Rust variant, one command, no arbitrary route`, async () => {
  const sent: unknown[] = [];
  const api = annotationClient(async <T>(command: string, args: { request: AnnotationRequest }) => {
    sent.push({ command, args }); return { acknowledged: true } as T;
  });
  assert.deepEqual(await call(api), { acknowledged: true });
  assert.deepEqual(sent, [{ command: 'annotations_forward', args: { request: expected } }]);
});

test('optional defaults are left to Python; all prompt and geometry forms retain [line,sample]', () => {
  assert.deepEqual(requests.superpixels(id), { op: 'superpixels', id });
  assert.deepEqual(requests.save(id), { op: 'save', id });
  assert.deepEqual(requests.diffuse(id, { box: [0, 3, 1, 5] }), { op: 'diffuse', id, seed: { box: [0, 3, 1, 5] } });
  const points: [number, number][] = [[3, 1], [5, 4]];
  assert.deepEqual(requests.diffuse(id, { doodle: points }), { op: 'diffuse', id, seed: { doodle: points } });
  assert.deepEqual(requests.regions(id, { polygon: [[0, 0], [1, 0], [0, 1]] }, 'uncertain'), { op: 'regions', id, geometry: { polygon: [[0, 0], [1, 0], [0, 1]] }, action: 'uncertain' });
  assert.deepEqual(requests.regions(id, { superpixels: [1] }, 'erase'), { op: 'regions', id, geometry: { superpixels: [1] }, action: 'erase' });
});

test('all three structured label bodies match Python and carry the working project id', () => {
  const custom: LabelBody = { project_id: id, code: 'X', name: '自定义', tree_path: '材料/塑料/X', color_hex: '#abcdef', shortcut_key: null, is_background: false };
  const schema: LabelBody = { project_id: id, schema: { name: '温度', tree_path: '温度', field_type: 'continuous', unit: 'K', config: { min: 0, max: 100 } } };
  for (const body of [custom, schema, { project_id: id, from_catalog: 'plastic', codes: ['PS', 'PVC'] } as LabelBody]) {
    assert.deepEqual(requests.addLabel(body), { op: 'add_label', body });
  }
});

test('local estimates and display state cannot enter request projections', () => {
  const extra = { estimated_remaining: 123, label_map: [0, -2], undo_stack: [], queue: [] };
  const requestsWithExtra = [
    requests.superpixels(id, { ...extra, n_segments: 800 }),
    requests.diffuse(id, { point: [0, 0], ...extra }, { ...extra, threshold: .92 }),
    requests.regions(id, { superpixels: [0], ...extra }, 'erase'),
    requests.save(id, { ...extra, note: 'note' }),
    requests.addLabel({ project_id: id, from_catalog: 'plastic', codes: ['PS'], ...extra }),
    requests.addLabel({ project_id: id, code: 'X', name: 'name', tree_path: '材料/塑料/X', color_hex: '#abcdef', ...extra }),
  ];
  for (const value of requestsWithExtra) for (const forbidden of Object.keys(extra)) assert.ok(!JSON.stringify(value).includes(`"${forbidden}"`));
  assert.deepEqual(requests.save(id, { note: '😀'.repeat(2000) }), { op: 'save', id, note: '😀'.repeat(2000) });
});

test('structured errors keep code, field messages and context; client never swallows rejection', async () => {
  const error = { error: 'INVALID_LABEL', detail: '标签登记参数不合法', context: { fields: [{ field: 'color_hex', message: '颜色非法' }] } };
  const api = annotationClient(async () => { throw error; });
  await assert.rejects(api.catalog(), value => value === error);
  const rendered = describeAnnotationError(error);
  for (const text of ['INVALID_LABEL', 'color_hex', '颜色非法']) assert.ok(rendered.includes(text));
  assert.match(describeAnnotationError({ error: 'SEGMENTATION_STALE', detail: '重新生成超像素', context: {} }), /SEGMENTATION_STALE.*重新生成/);
  assert.equal(describeAnnotationError(new Error('离线')), '离线');
  assert.equal(describeAnnotationError('transport'), 'transport');
  assert.match(describeAnnotationError(null), /标注请求失败/);
});
