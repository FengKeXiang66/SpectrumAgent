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
    h('label', { key: field, className: 'settings-field' }, field,
      h('input', { name: field, value: p.state.values[field], disabled,
        type: field === 'base_url' ? 'url' : field === 'model' ? 'text' : 'number',
        ...(field === 'base_url' ? { placeholder: '例如：https://api.siliconflow.cn/v1' } : {}),
        ...(field === 'model' ? { placeholder: '例如：deepseek-ai/DeepSeek-V4-Flash' } : {}),
        ...(field === 'temperature' ? { step: 'any' } : {}),
        ...(field === 'max_tokens' || field === 'timeout_ms' ? { min: 1, step: 1 } : {}),
        autoComplete: 'off', onChange: (event: { target: { value: string } }) => p.onField(field, event.target.value) })));
  const probe = p.state.modelStatus;
  const statusText = !probe ? '模型状态：尚未验证。点击「保存」后会发起一次真实调用，检查模型是否可以正常使用。'
    : probe.status === 'available' ? `模型状态：模型可以正常使用。${probe.detail}`
    : probe.status === 'unavailable' ? `模型状态：暂不可用 — ${probe.detail}`
    : probe.status === 'disabled' ? `模型状态：外发已关闭 — ${probe.detail}`
    : probe.status === 'unconfigured' ? `模型状态：配置不完整 — ${probe.detail}`
    : `模型状态：验证未完成 — ${probe.detail}`;
  return h('section', { 'aria-labelledby': 'llm-settings-title' },
    h('h2', { id: 'llm-settings-title' }, 'LLM 设置'),
    h('p', null, '空值表示未配置。模型参数与外发开关保存在本机，重启后自动恢复，无需重新输入。API KEY 由系统加密保存在本机，同样无需重复配置。'),
    h('p', { className: 'settings-hint' },
      'base_url 填写服务商的 API 基地址，例如 https://api.siliconflow.cn/v1（以 /v1 结尾）。不要带 /chat/completions、查询参数或密钥：程序会自动在基地址后拼接 /chat/completions，多写一次会导致 404。',
      h('br'),
      'model 填写服务商给出的模型 ID，例如 deepseek-ai/DeepSeek-V4-Flash。temperature、max_tokens、timeout_ms 可留空，留空表示由服务商决定；timeout_ms 为毫秒数。'),
    h('p', { className: `key-status${p.state.hasKey ? ' configured' : ''}`,
      role: 'status', 'aria-label': 'API KEY 配置状态' },
      p.state.hasKey === null ? '正在读取 API KEY 配置状态…' : p.state.hasKey ? 'API KEY 已配置' : 'API KEY 未配置'),
    h('p', { className: `model-status ${probe?.status ?? 'unverified'}`,
      role: 'status', 'aria-label': '模型可用状态' }, statusText),
    h('form', { className: 'settings-form', onSubmit: event => { event.preventDefault(); return p.onSave(); } },
      ...fields,
      h('label', null,
        h('input', { name: 'egress_enabled', type: 'checkbox', checked: p.state.values.egress_enabled, disabled,
          onChange: (event: { target: { checked: boolean } }) => p.onSwitch(event.target.checked) }),
        '允许 LLM 外发（关闭后对话与结果解读不可用，核心分析不受影响）'),
      h('label', { className: 'settings-field' }, 'API KEY（留空保留已配置密钥）',
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
  const form = useRef<ReturnType<typeof createSettingsForm> | null>(null);
  useEffect(() => {
    // Create per effect so StrictMode's cleanup/replay and engine restarts cannot retain a password.
    const current = createSettingsForm(api, setState);
    form.current = current;
    void current.load();
    return () => { current.dispose(); form.current = null; };
  }, [api]);
  return h(SettingsPanelView, { state, onClose,
    onField: (field, value) => form.current?.edit(field, value), onSwitch: checked => form.current?.editSwitch(checked),
    onKey: value => form.current?.editKey(value),
    onSave: () => form.current?.save() });
}
