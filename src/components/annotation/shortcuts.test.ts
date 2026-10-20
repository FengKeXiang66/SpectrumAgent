import assert from 'node:assert/strict';
import test from 'node:test';
import { bindingProblem, changeLabelKey, defaultPreferences, labelKey, resolveShortcut } from './shortcuts.ts';
import type { Label } from './types.ts';

const labels = [
  { id: 'BG', shortcut_key: 0, is_background: 1 },
  { id: 'PE', shortcut_key: 1, is_background: 0 },
  { id: 'PET', shortcut_key: 2, is_background: 0 },
  { id: 'mouse', shortcut_key: null, is_background: 0 },
  { id: 'bad-zero', shortcut_key: 0, is_background: 0 },
  { id: 'bad-ten', shortcut_key: 10, is_background: 0 },
] as Label[];
test('0 is background-only; 1–9 are numeric; unbound or out-of-range labels remain mouse-only', () => {
  const preferences = defaultPreferences();
  assert.deepEqual(resolveShortcut({ key: '0' }, labels, preferences), { labelId: 'BG' });
  assert.deepEqual(resolveShortcut({ key: '1' }, labels, preferences), { labelId: 'PE' });
  for (const label of labels.slice(3)) assert.equal(labelKey(label, preferences), null);
  assert.throws(() => changeLabelKey(labels, preferences, 'PE', 0), /0 仅背景/);
  assert.throws(() => changeLabelKey(labels, preferences, 'mouse', 3), /仅鼠标/);
  assert.throws(() => changeLabelKey(labels, preferences, 'PE', 10), /仅鼠标/);
  assert.equal(resolveShortcut({ key: '9' }, labels, preferences), null);
});
test('Enter / Z / D / E-B-P / arrows / Ctrl+S / space have the specified actions', () => {
  const preferences = defaultPreferences();
  for (const [key, command] of [['Enter', 'confirm'], ['Z', 'undo'], ['D', 'diffuse'], ['E', 'erase'], ['B', 'brush'], ['P', 'polygon'], ['ArrowLeft', 'previous'], ['ArrowRight', 'next'], [' ', 'pan']]) {
    assert.deepEqual(resolveShortcut({ key }, labels, preferences), { command });
  }
  assert.deepEqual(resolveShortcut({ key: 's', ctrlKey: true }, labels, preferences), { command: 'save' });
  assert.deepEqual(resolveShortcut({ key: 's', metaKey: true }, labels, preferences), { command: 'save' });
});
test('typing never changes labels or undo; disabled settings suppress shortcuts; global chat keys pass through', () => {
  const preferences = defaultPreferences();
  for (const key of ['0', '1', 'z', 'Enter', 'ArrowLeft']) assert.equal(resolveShortcut({ key }, labels, preferences, true), null);
  assert.deepEqual(resolveShortcut({ key: 's', ctrlKey: true }, labels, preferences, true), { command: 'save' });
  assert.equal(resolveShortcut({ key: 's', ctrlKey: true }, labels, { ...preferences, enabled: false }), null);
  assert.equal(resolveShortcut({ key: 'k', ctrlKey: true }, labels, preferences), null);
  assert.equal(resolveShortcut({ key: 'Enter', ctrlKey: true }, labels, preferences), null);
});
test('local remapping is deterministic and rejects duplicates/reserved keys without altering server labels', () => {
  const preferences = defaultPreferences();
  const next = changeLabelKey(labels, preferences, 'PE', 3);
  assert.equal(labelKey(labels[1], next), 3);
  assert.equal(labels[1].shortcut_key, 1);
  assert.deepEqual(resolveShortcut({ key: '3' }, labels, next), { labelId: 'PE' });
  assert.throws(() => changeLabelKey(labels, next, 'PET', 3), /已被其他标签/);
  const custom = { ...preferences, bindings: { ...preferences.bindings, undo: 'u' } };
  assert.deepEqual(resolveShortcut({ key: 'u' }, labels, custom), { command: 'undo' });
  assert.equal(resolveShortcut({ key: 'z' }, labels, custom), null);
  assert.equal(bindingProblem(custom.bindings), null);
  assert.match(bindingProblem({ ...custom.bindings, undo: 'Ctrl+k' })!, /常驻对话条/);
  assert.match(bindingProblem({ ...custom.bindings, undo: '1' })!, /数字键/);
  assert.match(bindingProblem({ ...custom.bindings, undo: 'b' })!, /不能重复/);
});
