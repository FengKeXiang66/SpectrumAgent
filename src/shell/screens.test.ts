import assert from 'node:assert/strict';
import test from 'node:test';
import { NAV, SCREEN_TITLE, navHighlight, type Screen } from './screens.ts';

test('A1 navigation retains five ordered groups and exactly ten unique screen entries', () => {
  assert.deepEqual(NAV.map(group => group.group), ['主入口', '我的工作', '分析流程', '沉淀与复用', '本机']);
  assert.deepEqual(NAV.map(group => group.items.length), [1, 1, 5, 2, 1]);
  const screens = NAV.flatMap(group => group.items.map(item => item.screen));
  assert.deepEqual(screens, ['s01', 's02', 's03', 's05', 's06', 's07', 's08', 's09', 's10', 's11']);
  assert.equal(screens.length, 10);
  assert.equal(new Set(screens).size, 10);
  assert.ok(!screens.includes('s04'));
  for (const { items } of NAV) for (const item of items) {
    assert.equal(item.label, SCREEN_TITLE[item.screen]);
    assert.ok(item.icon.length > 0);
  }
});

test('A1 titles cover all eleven Screen values including the viewer below data', () => {
  const screens = ['s01', 's02', 's03', 's04', 's05', 's06', 's07', 's08', 's09', 's10', 's11'] satisfies Screen[];
  assert.deepEqual(Object.keys(SCREEN_TITLE), screens);
  assert.deepEqual(Object.values(SCREEN_TITLE), ['智能助手', '工作台', '数据', '数据查看器', '标注', '预处理', '建模', '结果', '实验台账', '检索', '设置与出域记录']);
});

test('A1 only s04 redirects its navigation highlight to s03', () => {
  assert.equal(navHighlight('s04'), 's03');
  for (const { items } of NAV) for (const { screen } of items) assert.equal(navHighlight(screen), screen);
});
