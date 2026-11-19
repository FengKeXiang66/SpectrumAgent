import type { DraftView } from './draft-api.ts';

// TASK-07 §10-2: a UX confirmation, shared by REST and agent HUMAN_CHECK.
export const LARGE_MAT_BYTES = 2 * 1024 ** 3;
export function needsAdditionalConfirmation(bytes: number): boolean { return bytes > LARGE_MAT_BYTES; }
export function mayConfirm(bytes: number, additional: boolean): boolean {
  return Number.isSafeInteger(bytes) && bytes >= 0 && (!needsAdditionalConfirmation(bytes) || additional);
}
export async function loadConfirmation(api: { get(cube: string): Promise<DraftView> }, cube: string): Promise<DraftView> {
  const view = await api.get(cube);
  if (view.cube_id !== cube || !Number.isSafeInteger(view.revision) || view.revision < 0
      || !Number.isSafeInteger(view.estimated_mat_bytes) || view.estimated_mat_bytes < 0) {
    throw { error: 'INVALID_DRAFT_SUMMARY', detail: '草稿体积或版本信息不合法' };
  }
  // The REST document is not retained by the confirmation UI.
  return { cube_id: cube, revision: view.revision, estimated_mat_bytes: view.estimated_mat_bytes };
}
