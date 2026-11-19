import { invoke } from '@tauri-apps/api/core';
import { recipesChanged, draftsChanged } from './recipe-events.ts';
import type { BinaryArtifact, CompareBody, Pipeline, PreprocessApi, PreprocessRequest, RecipeBody, Report, RunBatchBody, RunBody, RunSummary, VersionBody } from './types.ts';

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
  createRunBatch: (p: RunBatchBody): PreprocessRequest => ({ op: 'create_run_batch', items: p.items.map(item => ({
    cube_id: item.cube_id, annotation_version_id: item.annotation_version_id, recipe_version_id: item.recipe_version_id })) }),
  listRuns: (dataset_id: string): PreprocessRequest => ({ op: 'list_runs', dataset_id }),
  getRun: (id: string): PreprocessRequest => ({ op: 'get_run', id }),
  compare: (dataset_id: string, p: CompareBody): PreprocessRequest => ({ op: 'compare', dataset_id,
    body: { annotation_version_id: p.annotation_version_id, recipe_version_ids: [...p.recipe_version_ids] } }),
  getArtifact: (run_id: string, kind: 'sample_spectra' | 'report' | 'processed_cube'): PreprocessRequest => ({ op: 'get_artifact', run_id, kind }),
  exportRun: (run_id: string): PreprocessRequest => ({ op: 'export', run_id }),
};
export type InvokePreprocess = <T>(command: string, args: { request: PreprocessRequest }) => Promise<T>;
export function preprocessClient(send: InvokePreprocess = invoke): PreprocessApi {
  const forward = <T>(request: PreprocessRequest) => send<T>('preprocess_forward', { request });
  const submit = <T>(request:PreprocessRequest, reference:string=crypto.randomUUID()) => forward<T>({op:'submit',submission_ref:reference,request});
  const members = (inputs:import('./types.ts').BatchItem[]) => inputs.map(({cube_id,annotation_version_id,recipe_version_id})=>({cube_id,annotation_version_id,recipe_version_id}));
  function getArtifact(run: string, kind: 'report'): Promise<Report>;
  function getArtifact(run: string, kind: 'sample_spectra'): Promise<BinaryArtifact>;
  function getArtifact(run: string, kind: 'processed_cube'): Promise<BinaryArtifact>;
  function getArtifact(run: string, kind: 'sample_spectra' | 'report' | 'processed_cube'): Promise<Report | BinaryArtifact> {
    return forward(requests.getArtifact(run, kind));
  }
  return { listRecipes: () => forward(requests.listRecipes()), createRecipe: (p, ref) => submit(requests.createRecipe(p),ref),
    getRecipe: id => forward(requests.getRecipe(id)), addVersion: (id, p, ref) => submit(requests.addVersion(id, p),ref),
    getSubmission: (submission_ref,session_id) => forward({op:'get_submission',submission_ref,...(session_id?{session_id}:{})}),
    checkOperation: (operation_id,session_id) => forward({op:'check_operation',operation_id,...(session_id?{session_id}:{})}),
    listOperators: () => forward({op:'list_operators'}),
    currentDraft: session_id => forward({op:'draft_current',session_id}),
    createDraft: (session_id,source,newPlan=false) => forward({op:'draft_create',session_id,body:{...(source?{source_recipe_version_id:source}:{}),new_plan:newPlan}}),
    getDraft: (session_id,draft_id) => forward({op:'draft_get',session_id,draft_id}),
    updateDraft: async(session_id,draft_id,expected_revision,pipeline,metadata) => {
      const row = await forward<import('./types.ts').RecipeDraft>({op:'draft_update',session_id,draft_id,body:{expected_revision,
        ...(pipeline?{pipeline:pipelineBody(pipeline)}:{}),...(metadata?{metadata:{...metadata}}:{})}});
      draftsChanged();return row;
    },
    saveDraft: async(session_id,draft_id,body,ref) => {
      const projected:import('./types.ts').DraftSaveBody={expected_revision:body.expected_revision};
      for(const key of ['recipe_id','code','name','description','note'] as const)if(body[key]!==undefined)Object.assign(projected,{[key]:body[key]});
      const row = await submit<import('./types.ts').DraftSaved>({op:'draft_save',session_id,draft_id,body:projected},ref);
      recipesChanged();draftsChanged();return row;
    },
    confirmDraft: (session_id,draft_id,expected_revision,recipe_version_id,inputs) => forward({op:'draft_confirm',session_id,draft_id,body:{expected_revision,recipe_version_id,inputs:members(inputs)}}),
    executeDraft: (session_id,confirmation_id,inputs,ref) => submit({op:'draft_execute',session_id,body:{confirmation_id,inputs:members(inputs)}},ref),
    retryDraft: (session_id,confirmation_id,inputs,retry_of_submission,ref) => submit({op:'draft_retry',session_id,body:{confirmation_id,retry_of_submission,inputs:members(inputs)}},ref),
    deleteRecipe: async id => {const row=await forward<import('./types.ts').Recipe>({op:'delete_recipe',id});recipesChanged();return row;},
    restoreRecipe: async id => {const row=await forward<import('./types.ts').Recipe>({op:'restore_recipe',id});recipesChanged();return row;},
    selectRecipe: (project, recipe) => forward(requests.selectRecipe(project, recipe)),
    deselectRecipe: (project, recipe) => forward(requests.deselectRecipe(project, recipe)),
    listProjectRecipes: project => forward(requests.listProjectRecipes(project)),
    createRun: (dataset, p, ref) => submit(requests.createRun(dataset, p),ref), listRuns: dataset => forward(requests.listRuns(dataset)),
    createRunBatch: (p,ref) => submit(requests.createRunBatch(p),ref),
    getRun: id => forward(requests.getRun(id)), compare: (dataset, p,ref) => submit(requests.compare(dataset, p),ref),
    getArtifact, exportRun: run => forward(requests.exportRun(run)),
    downloadExport:(run_id,filename,destination)=>forward({op:'download_export',run_id,filename,destination}) };
}
export const preprocessing = preprocessClient();

export function isTransportError(error: unknown): boolean {
  const code = typeof error === 'object' && error !== null && 'error' in error ? error.error : '';
  if (typeof code === 'string' && code) return code === 'TRANSPORT';
  return /timeout|timed out|超时|network|网络|failed to fetch/i.test(error instanceof Error ? error.message : String(error));
}
// Recovery follows the fixed operation/run. Recency never identifies a submission.
export async function recoverRun(api: PreprocessApi, reference:string, dataset:string, annotation:string, recipe:string, ownerSessionId?:string) {
  const submission = await api.getSubmission(reference,ownerSessionId);
  const operations=submission.operations.filter(op=>op.kind==='preprocess.run');
  if (operations.length !== 1) return null;
  const operation = operations[0];
  if (operation.kind !== 'preprocess.run' || !operation.run_id || operation.status==='needs_reconciliation') return null;
  const run = await api.getRun(operation.run_id);
  if (run.cube_id === dataset && run.annotation_version_id === annotation && run.recipe_version_id === recipe) return run;
  return null;
}

export async function submitRun(api: PreprocessApi, dataset: string, body: RunBody, _before: RunSummary[], reference:string=crypto.randomUUID()) {
  try { return { run: await api.createRun(dataset, body, reference), interrupted: false, submissionRef:reference }; }
  catch (error) {
    if (!isTransportError(error)) throw error;
    // A lost response says nothing about the server transaction's outcome.
    try { return { run: await recoverRun(api, reference, dataset, body.annotation_version_id, body.recipe_version_id), interrupted: true, submissionRef:reference }; }
    catch { return { run: null, interrupted: true, submissionRef:reference }; }
  }
}
