import { invoke } from '@tauri-apps/api/core';
import type { Seed } from './types.ts';

export type DraftView = { cube_id: string; revision: number; estimated_mat_bytes: number };
export type GestureResult = { gesture_ref: string; kind: string };
export type DraftRequest = { op: 'get_draft'; cube_id: string }
  | { op: 'store_gesture'; cube_id: string; body: { seed: Seed } };
export type InvokeDraft = <T>(command: string, args: { request: DraftRequest }) => Promise<T>;

export const requests = {
  storeGesture: (cube_id: string, seed: Seed): DraftRequest => ({ op: 'store_gesture', cube_id, body: { seed: gestureSeed(seed) } }),
  get: (cube_id: string): DraftRequest => ({ op: 'get_draft', cube_id }),

};

function gestureSeed(seed: Seed): Seed {
  if ('point' in seed) return { point: [seed.point[0], seed.point[1]] };
  if ('box' in seed) return { box: [seed.box[0], seed.box[1], seed.box[2], seed.box[3]] };
  return { doodle: seed.doodle.map(([line, sample]) => [line, sample]) };
}
export function draftClient(send: InvokeDraft = invoke) {
  const forward = <T>(request: DraftRequest) => send<T>('annotations_draft_forward', { request });
  return { get: (cube: string) => forward<DraftView>(requests.get(cube)),
    storeGesture: (cube: string, seed: Seed) => forward<GestureResult>(requests.storeGesture(cube, seed)),
  };
}
export const drafts = draftClient();
