import { invoke } from '@tauri-apps/api/core';
import { normalizePath } from '../datasets/paths.ts';

export type LLMConfig = { base_url: string; model: string; temperature: string; max_tokens: string; timeout_ms: string; egress_enabled: boolean };
export type LLMSettings = LLMConfig & { has_key: boolean };
export type ProjectPaths = { source_path: string; output_root: string; data_root: string; output_enabled: boolean };
export type PathValues = Pick<ProjectPaths, 'source_path' | 'output_root'>;
export type SettingsRequest = { op: 'get_llm' } | { op: 'put_llm'; body: LLMConfig } | { op: 'put_key'; key: string }
  | { op: 'get_project_paths'; project_id: string }
  | { op: 'put_project_paths'; project_id: string; body: PathValues };
export type InvokeSettings = <T>(command: string, args: { request: SettingsRequest }) => Promise<T>;

export function configFields(value: LLMConfig): LLMConfig {
  return { base_url: value.base_url, model: value.model, temperature: value.temperature,
    max_tokens: value.max_tokens, timeout_ms: value.timeout_ms, egress_enabled: value.egress_enabled };
}
export const requests = {
  getLLM: (): SettingsRequest => ({ op: 'get_llm' }),
  putLLM: (body: LLMConfig): SettingsRequest => ({ op: 'put_llm', body: configFields(body) }),
  putKey: (key: string): SettingsRequest => ({ op: 'put_key', key }),
  getProjectPaths: (projectId: string): SettingsRequest => ({ op: 'get_project_paths', project_id: projectId }),
  putProjectPaths: (projectId: string, body: PathValues): SettingsRequest => ({ op: 'put_project_paths', project_id: projectId,
    body: { source_path: normalizePath(body.source_path), output_root: normalizePath(body.output_root) } }),
};

export function settingsClient(send: InvokeSettings = invoke) {
  // The only settings IPC exit. Neither credentials nor view state enter the six-key body.
  const forward = <T>(request: SettingsRequest) => send<T>('settings_forward', { request });
  const settings = (value: LLMSettings): LLMSettings => ({ ...configFields(value), has_key: value.has_key });
  return {
    getLLM: async () => settings(await forward<LLMSettings>(requests.getLLM())),
    putLLM: async (body: LLMConfig) => settings(await forward<LLMSettings>(requests.putLLM(body))),
    putKey: async (key: string) => {
      const value = await forward<{ has_key: boolean }>(requests.putKey(key));
      return { has_key: value.has_key };
    },
    getProjectPaths: (id: string) => forward<ProjectPaths>(requests.getProjectPaths(id)),
    putProjectPaths: (id: string, body: PathValues) => forward<ProjectPaths>(requests.putProjectPaths(id, body)),
  };
}
export type SettingsApi = ReturnType<typeof settingsClient>;
export const settings = settingsClient();
