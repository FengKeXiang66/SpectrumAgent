import assert from 'node:assert/strict';
import test from 'node:test';
import { catalogCode, folderName, matchLabel } from './folder-label.ts';
import type { CatalogItem, Label } from './types.ts';

const label = (code: string, is_background = 0, id = code): Label => ({ id, code, is_background,
  name: code, color_hex: '#123456', project_id: 'project', schema_id: 'material', tree_path: `材料/塑料/${code}`,
  shortcut_key: null, sort_order: 0, created_at: '' });
const labels = [label('PE'), label('PET'), label('PP')];
const catalog: CatalogItem[] = [{ code: 'ABS', name: '丙烯腈-丁二烯-苯乙烯', color_hex: '#abcdef' }];

test('B1/B6 parent folder supports Windows, slash and mixed paths', () => {
  for (const path of ['E:\\a\\pet\\x.hdr', 'E:/a/pet/x.hdr', 'E:\\a/pet\\x.hdr',
    'E:\\高光谱数据集\\plastic\\pet\\x.hdr', 'plastic/pet/x.hdr']) {
    assert.equal(folderName(path), 'pet');
    assert.equal(matchLabel(labels, folderName(path)!)?.id, 'PET');
  }
});

test('B1 matching is exact, case insensitive and trims only', () => {
  for (const folder of ['pe', 'Pe', 'PE', ' pe ']) assert.equal(matchLabel(labels, folder)?.id, 'PE');
  for (const folder of ['pe_0602', 'PE_W0', 'pe0602', 'p', 'P E', '']) assert.equal(matchLabel(labels, folder), null);
  assert.equal(folderName('E:/a/ pe_0602 /x.hdr'), 'pe_0602');
});

test('B1 background number 1 is excluded; first ordered foreground match wins', () => {
  const first = label('PE', 0, 'first');
  assert.equal(matchLabel([label('PE', 1), first, label('pe', 0, 'second')], 'Pe'), first);
  assert.equal(matchLabel([label('PE', 1)], 'pe'), null);
});

test('B2 catalog returns the canonical code without constructing label fields', () => {
  for (const folder of ['abs', 'AbS', ' ABS ']) assert.equal(catalogCode(catalog, folder), 'ABS');
  for (const folder of ['2026-10-01', 'abs_0602', 'ABS_W0', 'ab']) assert.equal(catalogCode(catalog, folder), null);
  assert.equal(catalogCode([], 'abs'), null);
});

test('B2 an absent folder matches after the refreshed label list includes the catalog label', () => {
  assert.equal(matchLabel(labels, 'abs'), null);
  const added = label(catalogCode(catalog, 'abs')!);
  assert.equal(matchLabel([...labels, added], 'abs'), added);
});

test('B3 matching leaves the input list and labels unchanged', () => {
  const frozen = Object.freeze(labels.map(item => Object.freeze({ ...item })));
  const before = JSON.stringify(frozen);
  assert.equal(matchLabel(frozen, 'pet'), frozen[1]);
  assert.equal(JSON.stringify(frozen), before);
});

test('B4 folders are derived separately for each cube', () => {
  assert.equal(matchLabel(labels, folderName('E:\\a\\pp\\a.hdr')!)?.id, 'PP');
  assert.equal(matchLabel(labels, folderName('E:/a/pet/b.hdr')!)?.id, 'PET');
});

test('B5 single-file import with an arbitrary parent has no fallback label or catalog code', () => {
  const folder = folderName('E:\\临时\\x.hdr');
  assert.equal(folder, '临时');
  assert.equal(matchLabel(labels, folder!), null);
  assert.equal(catalogCode(catalog, folder!), null);
  for (const path of ['x.hdr', '', '/x.hdr', 'E:\\x.hdr']) assert.equal(folderName(path), null);
});
