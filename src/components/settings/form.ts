import { configFields, type LLMConfig, type SettingsApi } from './settings-forward.ts';

export type FormState = { values: LLMConfig; keyInput: string; hasKey: boolean | null;
  phase: 'loading' | 'ready' | 'saving' | 'load_error'; error: string; message: string };
export const emptyForm = (): FormState => ({ values: { base_url: '', model: '', temperature: '', max_tokens: '', timeout_ms: '', egress_enabled: true },
  keyInput: '', hasKey: null, phase: 'loading', error: '', message: '' });

export function validateConfig(value: LLMConfig): string {
  if (value.base_url) {
    try {
      const url = new URL(value.base_url);
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) {
        return 'base_url 须为无凭据、查询或片段的 HTTP(S) 地址。';
      }
    } catch { return 'base_url 须为有效的 HTTP(S) 地址。'; }
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
      if (state.phase === 'ready') update({ values: { ...state.values, [field]: value }, error: '', message: '' });
    },
    editSwitch(checked: boolean) {
      if (state.phase === 'ready') update({ values: { ...state.values, egress_enabled: checked }, error: '', message: '' });
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
        update({ message: key ? '配置与 key 已保存。' : '配置已保存。' });
      } catch (failure) {
        update({ error: `${configSaved ? '配置已保存，key 未保存。' : ''}${errorText(failure, key)}` });
      } finally {
        // A submitted credential is write-only, including failed attempts. Never persist form state.
        update({ phase: 'ready', ...(keyAttempted ? { keyInput: '' } : {}) });
      }
    },
    dispose() { disposed = true; state = { ...state, keyInput: '' }; },
  };
}
