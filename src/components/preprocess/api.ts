import { invoke } from '@tauri-apps/api/core';
import type { BinaryArtifact, CompareBody, Pipeline, PreprocessApi, PreprocessRequest, RecipeBody, Report, RunBody, RunSummary, VersionBody } from './types.ts';

const pipelineBody = (p: Pipeline): Pipeline => ({ steps: p.steps.map(s => ({ op: s.op, version: s.version, params: { ...s.params } })) });
const versionBody = (p: VersionBody): VersionBody => ({ pipeline: pipelineBody(p.pipeline), ...(p.note !== undefined ? { note: p.note } : {}) });
export const requests = {
  listRecipes: (): PreprocessRequest => ({ op: 'list_recipes' }),
  createRecipe: (p: RecipeBody): PreprocessRequest => ({ op: 'create_recipe', body: { code: p.code, name: p.name,
    ...(p.description !== undefined ? { description: p.description } : {}), ...versionBody(p) } }),
  getRecipe: (id: string): PreprocessRequest => ({ op: 'get_recipe', id }),
  addVersion: (id: string, body: VersionBody): PreprocessRequest => ({ op: 'add_version', id, body: versionBody(body) }),
  selectRecipe: (project_id: string, recipe_id: string): PreprocessRequest => ({ op: 'select_recipe', project_id, recipe_id }),
  deselectRecipe: (project_id: string, recipe_id: string): PreprocessRequest => ({ op: 'deselect_recipe', project_id, recipe_id }),
  listProjectRecipes: (project_id: string): PreprocessRequest => ({ op: 'list_project_recipes', project_id }),
  createRun: (dataset_id: string, p: RunBody): PreprocessRequest => ({ op: 'create_run', dataset_id,
    body: { annotation_version_id: p.annotation_version_id, recipe_version_id: p.recipe_version_id } }),
  listRuns: (dataset_id: string): PreprocessRequest => ({ op: 'list_runs', dataset_id }),
  getRun: (id: string): PreprocessRequest => ({ op: 'get_run', id }),
  compare: (dataset_id: string, p: CompareBody): PreprocessRequest => ({ op: 'compare', dataset_id,
    body: { annotation_version_id: p.annotation_version_id, recipe_version_ids: [...p.recipe_version_ids] } }),
  getArtifact: (run_id: string, kind: 'sample_spectra' | 'report'): PreprocessRequest => ({ op: 'get_artifact', run_id, kind }),
};
export type InvokePreprocess = <T>(command: string, args: { request: PreprocessRequest }) => Promise<T>;
export function preprocessClient(send: InvokePreprocess = invoke): PreprocessApi {
  const forward = <T>(request: PreprocessRequest) => send<T>('preprocess_forward', { request });
  function getArtifact(run: string, kind: 'report'): Promise<Report>;
  function getArtifact(run: string, kind: 'sample_spectra'): Promise<BinaryArtifact>;
  function getArtifact(run: string, kind: 'sample_spectra' | 'report'): Promise<Report | BinaryArtifact> {
    return forward(requests.getArtifact(run, kind));
  }
  return { listRecipes: () => forward(requests.listRecipes()), createRecipe: p => forward(requests.createRecipe(p)),
    getRecipe: id => forward(requests.getRecipe(id)), addVersion: (id, p) => forward(requests.addVersion(id, p)),
    selectRecipe: (project, recipe) => forward(requests.selectRecipe(project, recipe)),
    deselectRecipe: (project, recipe) => forward(requests.deselectRecipe(project, recipe)),
    listProjectRecipes: project => forward(requests.listProjectRecipes(project)),
    createRun: (dataset, p) => forward(requests.createRun(dataset, p)), listRuns: dataset => forward(requests.listRuns(dataset)),
    getRun: id => forward(requests.getRun(id)), compare: (dataset, p) => forward(requests.compare(dataset, p)),
    getArtifact };
}
export const preprocessing = preprocessClient();

export function isTransportError(error: unknown): boolean {
  const code = typeof error === 'object' && error !== null && 'error' in error ? error.error : '';
  if (typeof code === 'string' && code) return code === 'TRANSPORT';
  return /timeout|timed out|超时|network|网络|failed to fetch/i.test(error instanceof Error ? error.message : String(error));
}
// Summaries intentionally have no recipe_version_id: inspect only NEW runs via get_run.
export async function recoverRun(api: PreprocessApi, dataset: string, recipe: string, before: RunSummary[]) {
  const known = new Set(before.map(run => run.id));
  for (const row of await api.listRuns(dataset)) {
    if (known.has(row.id) || row.status !== 'succeeded') continue;
    const run = await api.getRun(row.id);
    if (run.recipe_version_id === recipe && run.status === 'succeeded') return run;
  }
  return null;
}

export async function submitRun(api: PreprocessApi, dataset: string, body: RunBody, before: RunSummary[]) {
  try { return { run: await api.createRun(dataset, body), interrupted: false }; }
  catch (error) {
    if (!isTransportError(error)) throw error;
    // A lost response says nothing about the server transaction's outcome.
    try { return { run: await recoverRun(api, dataset, body.recipe_version_id, before), interrupted: true }; }
    catch { return { run: null, interrupted: true }; }
  }
}
