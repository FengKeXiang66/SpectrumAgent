import { invoke } from '@tauri-apps/api/core';
import type { BinaryArtifact, PreprocessRun, Recipe, RecipeBody, Report, RunSummary } from './types';

type Request = { op: 'create_recipe'; body: RecipeBody } | { op: 'submit'; submission_ref: string; request: Request }
  | { op: 'get_run'; id: string } | { op: 'list_runs'; dataset_id: string }
  | { op: 'get_artifact'; run_id: string; kind: 'report' | 'sample_spectra' | 'processed_cube' }
  | { op: 'download_export'; run_id: string; filename: 'processed_cube.img' | 'processed_cube.hdr' | 'export_manifest.json'; destination: string };
export function preprocessClient(send: <T>(command: string, args: {request: Request}) => Promise<T> = invoke) {
  const forward = <T>(request: Request) => send<T>('preprocess_forward', {request});
  function getArtifact(run: string, kind: 'report'): Promise<Report>;
  function getArtifact(run: string, kind: 'sample_spectra' | 'processed_cube'): Promise<BinaryArtifact>;
  function getArtifact(run: string, kind: 'report' | 'sample_spectra' | 'processed_cube'): Promise<Report | BinaryArtifact> {
    return forward({op:'get_artifact',run_id:run,kind});
  }
  return {
    createRecipe: (body: RecipeBody) => forward<Recipe>({op:'submit',submission_ref:crypto.randomUUID(),request:{op:'create_recipe',body}}),
    listRuns: (dataset_id: string) => forward<RunSummary[]>({op:'list_runs',dataset_id}),
    getRun: (id: string) => forward<PreprocessRun>({op:'get_run',id}),
    getArtifact,
    downloadExport: (run_id: string, filename: 'processed_cube.img' | 'processed_cube.hdr' | 'export_manifest.json', destination: string) =>
      forward<{saved:boolean;bytes:number}>({op:'download_export',run_id,filename,destination}),
  };
}
export const preprocessing = preprocessClient();
