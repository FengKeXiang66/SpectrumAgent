import type { Label } from './types.ts';
export type Tool = 'diffuse' | 'brush' | 'polygon' | 'erase';
export type Command = 'confirm' | 'undo' | 'previous' | 'next' | 'save' | 'pan' | Tool;
export type Preferences = { enabled: boolean; bindings: Record<Command, string>; labelKeys: Record<string, number | null> };
// TASK-04 §5.8 / S05: local, editable, switchable. No DB label mutations.
export function defaultPreferences(): Preferences {
  return { enabled: true, bindings: { confirm: 'Enter', undo: 'z', diffuse: 'd', brush: 'b', polygon: 'p', erase: 'e',
    previous: 'ArrowLeft', next: 'ArrowRight', save: 'Ctrl+s', pan: ' ' }, labelKeys: {} };
}
export function labelKey(label: Label, preferences: Preferences): number | null {
  // Labels without a registered numeric shortcut remain mouse-only, including >9.
  if (label.shortcut_key === null) return null;
  const key = Object.hasOwn(preferences.labelKeys, label.id) ? preferences.labelKeys[label.id] : label.shortcut_key;
  return key !== null && Number.isInteger(key) && key >= 0 && key <= 9 && (key !== 0 || !!label.is_background) ? key : null;
}
export type KeyInput = { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; shiftKey?: boolean };
export function chord(event: KeyInput): string {
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  return `${event.ctrlKey || event.metaKey ? 'Ctrl+' : ''}${event.altKey ? 'Alt+' : ''}${event.shiftKey ? 'Shift+' : ''}${key}`;
}
export function bindingProblem(bindings: Record<Command, string>): string | null {
  const seen = new Set<string>();
  for (const value of Object.values(bindings)) {
    if (!value || /^\d$/.test(value) || value === 'Ctrl+k' || value === 'Ctrl+Enter') return '数字键留给标签；Ctrl+K / Ctrl+Enter 留给常驻对话条。';
    if (seen.has(value)) return '快捷键不能重复。';
    seen.add(value);
  }
  return null;
}
export function changeLabelKey(labels: Label[], preferences: Preferences, id: string, key: number | null): Preferences {
  const label = labels.find(item => item.id === id);
  if (!label || label.shortcut_key === null || (key !== null && (!Number.isInteger(key) || key < 0 || key > 9 || (key === 0 && !label.is_background)))) throw new Error('0 仅背景；1–9 为登记标签；未绑定的标签仅鼠标点选。');
  const next = { ...preferences, labelKeys: { ...preferences.labelKeys, [id]: key } };
  if (key !== null && labels.some(item => item.id !== id && labelKey(item, next) === key)) throw new Error('该数字键已被其他标签占用。');
  return next;
}
export function resolveShortcut(event: KeyInput, labels: Label[], preferences: Preferences, editingText = false): { labelId: string } | { command: Command } | null {
  if (!preferences.enabled) return null;
  const key = chord(event);
  // Ctrl+S still saves while editing the version note. Typing never assigns labels.
  if (editingText && key !== preferences.bindings.save) return null;
  if (/^\d$/.test(key)) {
    const label = labels.find(item => labelKey(item, preferences) === Number(key));
    return label ? { labelId: label.id } : null;
  }
  const entry = Object.entries(preferences.bindings).find(([, value]) => value === key);
  return entry ? { command: entry[0] as Command } : null;
}
