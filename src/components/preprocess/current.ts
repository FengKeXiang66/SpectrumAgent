import { invoke } from '@tauri-apps/api/core';
import type { Pipeline, PreprocessRun } from './types';

export type CurrentMember = { cube_id: string; annotation_id: string | null; run_id: string | null;
  recipe_id: string | null; recipe_input_id?: string; status: 'ready' | 'need_annotation' | 'need_preprocess' };
export type CurrentRecipe = { id: string; code: string; name: string; description: string | null; builtin: number; pipeline: Pipeline };
export type CurrentState = { members: CurrentMember[]; recipes: CurrentRecipe[] };
export const currentWorkspace = {
  state: () => invoke<CurrentState>('preprocess_forward', { request: { op: 'current_state' } }),
  saveRecipe: (id: string, pipeline: Pipeline) => invoke<CurrentState>('preprocess_forward', {
    request: { op: 'save_current_recipe', id, body: { pipeline } } }),
  process: (dataset_id: string, recipe_id: string) => invoke<PreprocessRun>('preprocess_forward', {
    request: { op: 'run_current', dataset_id, recipe_id } }),
};
