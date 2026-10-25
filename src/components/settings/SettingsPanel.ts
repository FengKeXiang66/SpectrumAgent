import { createElement as h, useEffect, useRef, useState, type RefObject } from 'react';
import { createSettingsForm, emptyForm, type FormState } from './form.ts';
import { settings, type LLMConfig, type SettingsApi } from './settings-forward.ts';

export type SettingsPanelViewProps = { state: FormState; dialogRef?: RefObject<HTMLDialogElement | null>;
  onField(field: Exclude<keyof LLMConfig, 'egress_enabled'>, value: string): void;
  onSwitch(checked: boolean): void; onKey(value: string): void;
  onSave(): void | Promise<void>; onClose(): void };

export function SettingsPanelView(p: SettingsPanelViewProps) {
  const disabled = p.state.phase !== 'ready';
  const fields = (['base_url', 'model', 'temperature', 'max_tokens', 'timeout_ms'] as const).map(field =>
    h('label', { key: field, style: { display: 'grid', gap: 4 } }, field,
      h('input', { name: field, value: p.state.values[field], disabled,
        type: field === 'base_url' ? 'url' : field === 'model' ? 'text' : 'number',
        ...(field === 'temperature' ? { step: 'any' } : {}),
        ...(field === 'max_tokens' || field === 'timeout_ms' ? { min: 1, step: 1 } : {}),
        autoComplete: 'off', onChange: (event: { target: { value: string } }) => p.onField(field, event.target.value) })));
  return h('dialog', { ref: p.dialogRef, 'aria-labelledby': 'llm-settings-title',
    style: { width: 'min(520px, calc(100vw - 48px))', maxHeight: 'calc(100vh - 48px)', overflowY: 'auto', padding: 24 },
    onKeyDown: event => event.stopPropagation(),
    onCancel: (event: { preventDefault(): void }) => { event.preventDefault(); if (p.state.phase !== 'saving') p.onClose(); } },
    h('h2', { id: 'llm-settings-title' }, 'LLM 设置'),
    h('p', null, '空值表示未配置。API key 仅由引擎内存持有，重启后需重新输入。'),
    h('p', { role: 'status', 'aria-label': 'key 配置状态' },
      p.state.hasKey === null ? '正在读取 key 配置状态…' : p.state.hasKey ? 'key 已配置' : 'key 未配置'),
    h('form', { style: { display: 'grid', gap: 12 }, onSubmit: event => { event.preventDefault(); return p.onSave(); } },
      ...fields,
      h('label', null,
        h('input', { name: 'egress_enabled', type: 'checkbox', checked: p.state.values.egress_enabled, disabled,
          onChange: (event: { target: { checked: boolean } }) => p.onSwitch(event.target.checked) }),
        '允许 LLM 外发（关闭后对话与结果解读不可用，核心分析不受影响）'),
      h('label', { style: { display: 'grid', gap: 4 } }, 'API key（留空保留已配置 key）',
        h('input', { name: 'key', type: 'password', autoComplete: 'new-password', value: p.state.keyInput, disabled,
          onChange: (event: { target: { value: string } }) => p.onKey(event.target.value) })),
      p.state.phase === 'loading' && h('p', null, '正在读取设置…'),
      p.state.error && h('p', { role: 'alert' }, p.state.error),
      p.state.message && h('p', { role: 'status' }, p.state.message),
      h('div', null,
        h('button', { type: 'submit', disabled }, p.state.phase === 'saving' ? '保存中…' : '保存'),
        h('button', { type: 'button', disabled: p.state.phase === 'saving', onClick: p.onClose }, '取消'))));
}

export default function SettingsPanel({ onClose, api = settings }: { onClose(): void; api?: SettingsApi }) {
  const [state, setState] = useState(emptyForm);
  const dialog = useRef<HTMLDialogElement>(null);
  const form = useRef<ReturnType<typeof createSettingsForm> | null>(null);
  useEffect(() => {
    // Create per effect so StrictMode's cleanup/replay and engine restarts cannot retain a password.
    const current = createSettingsForm(api, setState);
    form.current = current;
    void current.load();
    return () => { current.dispose(); form.current = null; };
  }, [api]);
  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal(); }, []);
  return h(SettingsPanelView, { state, dialogRef: dialog, onClose,
    onField: (field, value) => form.current?.edit(field, value), onSwitch: checked => form.current?.editSwitch(checked),
    onKey: value => form.current?.editKey(value),
    onSave: () => form.current?.save() });
}
