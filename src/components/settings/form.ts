import { configFields, type LLMConfig, type LLMVerify, type SettingsApi } from './settings-forward.ts';

export type FormState = { values: LLMConfig; keyInput: string; hasKey: boolean | null;
  routerKeyInput: string; hasRouterKey: boolean | null;
  phase: 'loading' | 'ready' | 'saving' | 'load_error'; error: string; message: string;
  modelStatus: LLMVerify | null; routerStatus: LLMVerify | null };
export const emptyForm = (): FormState => ({ values: { base_url: '', model: '', router_model: '', router_base_url: '', temperature: '', max_tokens: '', timeout_ms: '', egress_enabled: true },
  keyInput: '', hasKey: null, routerKeyInput: '', hasRouterKey: null, phase: 'loading', error: '', message: '',
  modelStatus: null, routerStatus: null });

export function validateConfig(value: LLMConfig): string {
  for (const field of ['base_url', 'router_base_url'] as const) {
    const address = value[field];
    if (!address) continue;
    try {
      const url = new URL(address);
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || /[?#]/.test(address)) {
        return `${field} 须为无凭据、查询或片段的 HTTP(S) 地址。`;
      }
      if (/\/chat\/completions\/*$/i.test(url.pathname)) {
        return `${field} 请填写 API 基地址，程序会自动拼接 /chat/completions。`;
      }
    } catch {
      return `${field} 须为有效的 HTTP(S) 地址。`;
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

function errorText(failure: unknown, ...keys: string[]): string {
  const e = failure as { error?: unknown; detail?: unknown; status_code?: unknown } | null;
  const code = typeof e?.error === 'string' ? e.error : 'SETTINGS_FAILED';
  const detail = typeof e?.detail === 'string' ? e.detail : '设置请求失败，请重试。';
  const text = `${e?.status_code === 400 ? '400 · ' : ''}${code}：${detail}`;
  // Keep the backend envelope's code/detail while preventing a credential from appearing in an error.
  return keys.filter(Boolean).sort((a, b) => b.length - a.length)
    .reduce((safe, key) => safe.split(key).join('[已隐藏]'), text);
}

async function verify(check: () => Promise<LLMVerify>): Promise<LLMVerify> {
  try { return await check(); }
  catch { return { status: 'unknown', detail: '验证请求未完成，请稍后重试。' }; }
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
        update({ values: configFields(value), hasKey: value.has_key, hasRouterKey: value.has_router_key, phase: 'ready' });
      } catch (failure) { update({ phase: 'load_error', error: errorText(failure) }); }
    },
    edit(field: Exclude<keyof LLMConfig, 'egress_enabled'>, value: string) {
      if (state.phase === 'ready') update({ values: { ...state.values, [field]: value }, error: '', message: '', modelStatus: null, routerStatus: null });
    },
    editSwitch(checked: boolean) {
      if (state.phase === 'ready') update({ values: { ...state.values, egress_enabled: checked }, error: '', message: '', modelStatus: null, routerStatus: null });
    },
    editKey(keyInput: string) {
      if (state.phase === 'ready') update({ keyInput, error: '', message: '', modelStatus: null, routerStatus: null });
    },
    editRouterKey(routerKeyInput: string) {
      if (state.phase === 'ready') update({ routerKeyInput, error: '', message: '', routerStatus: null });
    },
    async clearRouterKey() {
      if (disposed || state.phase !== 'ready' || !state.hasRouterKey) return;
      const key = state.routerKeyInput;
      update({ phase: 'saving', error: '', message: '', routerKeyInput: '', routerStatus: null });
      try {
        const status = await api.putRouterKey('');
        update({ hasRouterKey: status.has_router_key, message: '已清除路由 API KEY。' });
      } catch (failure) {
        update({ error: errorText(failure, key, state.keyInput) });
      } finally {
        update({ phase: 'ready' });
      }
    },
    async save() {
      if (disposed || state.phase !== 'ready') return;
      const invalid = validateConfig(state.values);
      if (invalid) { update({ error: invalid, message: '' }); return; }
      const { keyInput: key, routerKeyInput: routerKey } = state;
      let keyAttempted = false, routerKeyAttempted = false;
      let partialError = '';
      update({ phase: 'saving', error: '', message: '' });
      try {
        const value = await api.putLLM(state.values);
        if (disposed) return;
        update({ values: configFields(value), hasKey: value.has_key, hasRouterKey: value.has_router_key });
        if (key !== '') {
          keyAttempted = true;
          partialError = '配置已保存，主 API KEY 未保存。';
          const status = await api.putKey(key);
          update({ hasKey: status.has_key });
        }
        if (disposed) return;
        if (routerKey !== '') {
          routerKeyAttempted = true;
          partialError = '配置已保存，路由 API KEY 未保存。';
          const status = await api.putRouterKey(routerKey);
          update({ hasRouterKey: status.has_router_key });
        }
        if (disposed) return;
        const independent = Boolean(state.values.router_base_url || state.values.router_model);
        const [modelStatus, routerStatus] = await Promise.all([
          verify(() => api.verifyLLM()),
          independent ? verify(() => api.verifyRouterLLM()) : null,
        ]);
        update({ message: key || routerKey ? '配置与 API KEY 已保存。' : '配置已保存。', modelStatus, routerStatus });
      } catch (failure) {
        update({ error: partialError + errorText(failure, key, routerKey), modelStatus: null, routerStatus: null });
      } finally {
        // A submitted credential is write-only, including failed attempts. Never persist form state.
        update({ phase: 'ready', ...(keyAttempted ? { keyInput: '' } : {}),
          ...(routerKeyAttempted ? { routerKeyInput: '' } : {}) });
      }
    },
    dispose() { disposed = true; state = { ...state, keyInput: '', routerKeyInput: '' }; },
  };
}
