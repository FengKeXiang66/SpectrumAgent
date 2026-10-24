import { invoke } from '@tauri-apps/api/core';

export type DraftView = { cube_id: string; revision: number; estimated_mat_bytes: number };
export type ConfirmOptions = { revision: number; overwrite?: boolean; note?: string };
export type ConfirmResult = { version_id: string; version_no: number; training_mat_id: string | null;
  mat_error?: string; overlap_conflicts: number; n_spectra: number };
export type DraftRequest = { op: 'get_draft'; cube_id: string } | { op: 'confirm'; cube_id: string; body: ConfirmOptions };
export type InvokeDraft = <T>(command: string, args: { request: DraftRequest }) => Promise<T>;

export const requests = {
  get: (cube_id: string): DraftRequest => ({ op: 'get_draft', cube_id }),
  confirm: (cube_id: string, p: ConfirmOptions): DraftRequest => ({ op: 'confirm', cube_id,
    body: { revision: p.revision, ...(p.overwrite !== undefined ? { overwrite: p.overwrite } : {}),
      ...(p.note !== undefined ? { note: p.note } : {}) } }),
};
export function draftClient(send: InvokeDraft = invoke) {
  const forward = <T>(request: DraftRequest) => send<T>('annotations_draft_forward', { request });
  return { get: (cube: string) => forward<DraftView>(requests.get(cube)),
    confirm: (cube: string, options: ConfirmOptions) => forward<ConfirmResult>(requests.confirm(cube, options)) };
}
export const drafts = draftClient();
