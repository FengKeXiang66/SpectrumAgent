import { configFields, type LLMConfig, type LLMVerify, type SettingsApi } from './settings-forward.ts';

export type FormState = { values: LLMConfig; keyInput: string; hasKey: boolean | null;
  phase: 'loading' | 'ready' | 'saving' | 'load_error'; error: string; message: string;
  modelStatus: LLMVerify | null };
export const emptyForm = (): FormState => ({ values: { base_url: '', model: '', temperature: '', max_tokens: '', timeout_ms: '', egress_enabled: true },
  keyInput: '', hasKey: null, phase: 'loading', error: '', message: '', modelStatus: null });

export function validateConfig(value: LLMConfig): string {
  if (value.base_url) {
    try {
      const url = new URL(value.base_url);
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) {
        return 'base_url 须为无凭据、查询或片段的 HTTP(S) 地址。';
      }
    } catch { return 'base_url 须为有效的 HTTP(S) 地址。'; }
    if (/\/chat\/completions\/?$/i.test(value.base_url)) {
      return 'base_url 请填写 API 基地址（例如 https://api.siliconflow.cn/v1，以 /v1 结尾），不要带 /chat/completions；程序会自动拼接。';
    }
  }
  // Mirrors LLMSettings: blanks mean unconfigured, temperature has no provider-specific range.
  if (value.temperature !== '' && (!value.temperature.trim() || !Number.isFinite(Number(value.temperature)))) {
    return 'temperature 须为有限数或留空。';
  }
  for (const field of ['max_tokens', 'timeout_ms'] as const) {
    if (value[field] !== '' && (!/^\+?\d+$/.test(value[field].trim()) || BigInt(value[field].trim()) <= 0n)) {
      return `${field} 须为正整数或留空。`;
    }
  }
  return '';
}

function errorText(failure: unknown, key: string): string {
  const e = failure as { error?: unknown; detail?: unknown; status_code?: unknown } | null;
  const code = typeof e?.error === 'string' ? e.error : 'SETTINGS_FAILED';
  const detail = typeof e?.detail === 'string' ? e.detail : '设置请求失败，请重试。';
  const text = `${e?.status_code === 400 ? '400 · ' : ''}${code}：${detail}`;
  // Keep the backend envelope's code/detail while preventing a credential from appearing in an error.
  return key ? text.split(key).join('[已隐藏]') : text;
}

export function createSettingsForm(api: SettingsApi, changed: (state: FormState) => void) {
  let state = emptyForm(), disposed = false;
  const update = (patch: Partial<FormState>) => {
    if (!disposed) { state = { ...state, ...patch }; changed(state); }
  };
  return {
    async load() {
      try {
        const value = await api.getLLM();
        update({ values: configFields(value), hasKey: value.has_key, phase: 'ready' });
      } catch (failure) { update({ phase: 'load_error', error: errorText(failure, '') }); }
    },
    edit(field: Exclude<keyof LLMConfig, 'egress_enabled'>, value: string) {
      if (state.phase === 'ready') update({ values: { ...state.values, [field]: value }, error: '', message: '', modelStatus: null });
    },
    editSwitch(checked: boolean) {
      if (state.phase === 'ready') update({ values: { ...state.values, egress_enabled: checked }, error: '', message: '', modelStatus: null });
    },
    editKey(keyInput: string) {
      if (state.phase === 'ready') update({ keyInput, error: '', message: '' });
    },
    async save() {
      if (disposed || state.phase !== 'ready') return;
      const invalid = validateConfig(state.values);
      if (invalid) { update({ error: invalid, message: '' }); return; }
      const key = state.keyInput;
      let configSaved = false, keyAttempted = false;
      update({ phase: 'saving', error: '', message: '' });
      try {
        const value = await api.putLLM(state.values);
        if (disposed) return;
        configSaved = true;
        update({ values: configFields(value), hasKey: value.has_key });
        if (key !== '') {
          keyAttempted = true;
          const status = await api.putKey(key);
          update({ hasKey: status.has_key });
        }
        // A saved but unused configuration is not a working model: probe once
        // after the key has been written so a new credential is actually used.
        let modelStatus: LLMVerify;
        if (!state.values.egress_enabled) {
          modelStatus = { status: 'disabled', detail: '允许 LLM 外发已关闭，未发起验证请求。' };
        } else if (!state.values.base_url || !state.values.model) {
          modelStatus = { status: 'unconfigured', detail: '请填写 base_url、model 并配置 API KEY。' };
        } else {
          try { modelStatus = await api.verifyLLM(); }
          catch { modelStatus = { status: 'unknown', detail: '验证请求未完成，请稍后重试。' }; }
        }
        const probe = modelStatus.status === 'available' ? '模型可以正常使用。'
          : modelStatus.status === 'disabled' ? '外发已关闭，未验证模型。'
          : modelStatus.status === 'unconfigured' ? '模型配置不完整，未验证。'
          : modelStatus.status === 'unknown' ? '模型验证未完成。'
          : '模型暂不可用，请按下方状态提示修正。';
        update({ message: `${key ? '配置与 API KEY 已保存。' : '配置已保存。'}${probe}`, modelStatus });
      } catch (failure) {
        update({ error: `${configSaved ? '配置已保存，API KEY 未保存。' : ''}${errorText(failure, key)}`, modelStatus: null });
      } finally {
        // A submitted credential is write-only, including failed attempts. Never persist form state.
        update({ phase: 'ready', ...(keyAttempted ? { keyInput: '' } : {}) });
      }
    },
    dispose() { disposed = true; state = { ...state, keyInput: '' }; },
  };
}
