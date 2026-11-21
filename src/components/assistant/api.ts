import { Channel, invoke } from '@tauri-apps/api/core';
import type { AgentEvent, PlanDecision } from './sse.ts';

export type ExperimentTask = {task_id:string;session_id:string;status:'queued'|'running'|'succeeded'|'failed'|'cancelled';
  phase:string|null;completed_phases:string[];elapsed_seconds:number;cancel_requested:boolean;
  experiment_id:string|null;error:string|null;failed_phase:string|null;train_accuracy:number|null;test_accuracy:number|null};
export type ExperimentScore = {n:number;correct:number;accuracy:number;macro_precision:number;macro_recall:number;macro_f1:number;
  kappa?:number|null;weighted_f1?:number|null;balanced_accuracy?:number|null;evaluation_unit:string;purpose:string;
  confusion:number[][];confusion_labels:number[];macro_labels:number[];
  per_class:{label:number;name:string;support:number;precision:number|null;recall:number|null;f1:number|null}[]};
export type ExperimentResult = {experiment_id:string;name:string;classes:Record<string,string>;processed_axis:'component'|'wavelength_nm';
  metrics:Record<'train'|'test',ExperimentScore>;score_definition:string;
  model:{model_id:string;experiment_id:string;stage:string;sha256:string;wavelengths_nm:number[];preprocessing:{op:string;[key:string]:unknown}[];
    parameters:Record<string,number|boolean>;input_stage:string;neighborhood:number;evaluation_unit:string}};
export type ArchivedExperiment = {experiment_id:string;name:string;status:string;created_at:string;model_id:string|null;
  train_accuracy?:number|null;test_accuracy?:number|null;evaluation_unit?:string;test_usage?:string;phase?:string|null;error?:string|null};
export type ExperimentHistory = {items:ArchivedExperiment[];total:number;offset:number;limit:number;selected_experiment_id:string|null};
export type ExperimentComparison = {first:string;second:string;comparable:boolean;checks:Record<string,boolean>;
  metrics:Record<'train'|'test',ExperimentScore>[];note:string};
export type InferenceStatus = {run_id:string;model_id:string;status:'queued'|'running'|'succeeded'|'failed'|'cancelled'|'interrupted';
  kind:'npz'|'envi';phase:string;completed_files:number;total_files:number;completed_rows:number;total_rows:number;elapsed_seconds:number;
  error:string|null;can_cancel:boolean;cancel_requested:boolean};
export type InferenceResult = {run_id:string;model_id:string;model_sha256:string;kind:'npz'|'envi';classes:Record<string,string>;colors:Record<string,string>;
  evaluation_unit:string;note:string;foreground?:{mode:string;[key:string]:unknown}|null;
  files:{file_index:number;name:string;classified:number;excluded:number;total:number;counts:Record<string,number>;
    shape?:number[];edges?:{left:number;right:number};exclusion_counts?:Record<string,number>;preview_wavelengths_nm?:number[]}[]};

export type WorkspaceContext = { cube_id?: string; gesture_ref?: string };
// Local validated batch models only; AgentRequest/MessageBody wire stays unchanged.
export type BatchMember = { cubeId: string; displayName: string; status: 'ready' | 'failed' | 'conflict' | 'not_attempted';
  action: 'generated' | 'reused' | 'restored' | 'retained' | 'none'; superpixelCount: number | null; errorCode: string | null; detail: string | null };
export type BatchResult = { status: 'need_version' | 'need_scope' | 'blocked' | 'ready' | 'partial' | 'failed'; datasetVersionId: string | null;
  batchRef: string | null; retryOf: string | null; authorizationId?:string; memberCount: number; requestedCount: number; readyCount: number;
  failedCount: number; conflictCount: number; notAttemptedCount: number; autoOpen: boolean; openCubeId: string | null;
  members: BatchMember[]; readyMembers: BatchMember[]; detail: string | null; elapsedMs: number;
  admission?: { code: string; constraint: string; actual: number | string | null; limit: number | string | null; checkedAt: string } | null };
export type BatchScope = { result: BatchResult; epoch: number; generation: number; targetCubeIds?: string[]; onDemand?: boolean; authorizationId?:string };
export type AnnotationTask = { task_id: string; task_status: 'queued'|'running'|'completed'|'canceled'|'failed'; phase: 'verifying'|'preparing';
  result_status: 'all_ready'|'partial'|'failed'|null; snapshot_version: number; total: number;
  counts: Record<'pending'|'processing'|'ready'|'failed'|'conflict'|'not_attempted',number>;
  cancel_requested: boolean; cancelable: boolean; current_cube_id: string|null; owner_boot_id: string; session_id: string;
  error: string|null; items?: {cube_id:string;display_name:string;status:BatchMember['status']|'pending'|'processing';action:BatchMember['action'];superpixel_count:number|null;error_code:string|null;detail:string|null}[];
  authorization_id?:string;
  next_after?: number|null };
export type TaskCard = {taskId:string;sessionId:string;generation:number;requestId?:string|null;targetCubeIds?:string[];onDemand?:boolean;authorizationId?:string};
export type TaskAccepted = {status:'accepted';task_id:string;task_status:AnnotationTask['task_status'];member_count:number;flow_id?:string};
export type BatchCard = { result: BatchResult | null; stepStatus: string; epoch: number; generation: number; key: string; sessionId?: string; requestId?: string };
export type MessageBody = ({ content: string; workspace?: WorkspaceContext } | { check_id: string; decision: 'approve' | 'reject' } | ({ plan_id: string } & PlanDecision)) & { request_id?: string };
export type AgentRequest = ({ op: 'create_session' } & CreateSessionInput)
  | {op:'inference_history';id:string;model_id:string}
  | {op:'inference_task';id:string;model_id:string;run_id:string;action:'get'|'cancel'|'result'}
  | {op:'inference_plot';id:string;model_id:string;run_id:string;file_index:number;kind?:'prediction'|'input'}
  | {op:'inference_export';id:string;model_id:string;run_id:string;destination:string}
  | {op:'experiment_history';id:string;offset?:number;limit?:number}
  | {op:'select_experiment';id:string;experiment_id:string}
  | {op:'compare_experiments';id:string;first_id:string;second_id:string}
  | {op:'archived_experiment_result';id:string;experiment_id:string}
  | {op:'archived_experiment_plot';id:string;experiment_id:string;name:string}
  | {op:'archived_experiment_export';id:string;experiment_id:string;kind:'report'|'bundle';destination:string}
  | {op:'cancel_request'|'get_request';id:string;request_id:string}
  | {op:'experiment_task';id:string;task_id:string;action:'get'|'cancel'}
  | {op:'experiment_result';id:string;task_id:string}
  | {op:'experiment_plot';id:string;task_id:string;name:string}
  | {op:'experiment_export';id:string;task_id:string;kind:'report'|'bundle';destination:string}
  | {op:'start_annotation';id:string;request_id:string;cube_ids:string[];mode:'per_image'|'all'}
  | {op:'annotation_task';id:string;task_id:string;action:'get'|'items'|'cancel'|'retry'|'prepare'|'focus'|'blur';after?:number;limit?:number;version?:number;request_id?:string;mode?:'failed'|'remaining';authorization_id?:string}
  | { op: 'check_batch_prepare'; id: string; dataset_version_id?: string }
  | { op: 'get_session'; id: string }
  | { op: 'list_sessions'; query: { kind: 'global'; limit: number } }
  | { op: 'get_history'; id: string; before?: number; after?: number; limit?: number }
  | { op: 'select_cube'; id: string; cube_id: string | null } | { op: 'get_steps'; id: string } | { op: 'get_runtime' } | { op: 'send_message'; id: string; body: MessageBody };
// 2026-11-13 simplification: one global session only. Work sessions, session
// lists, member paging and preflight were removed from the product surface.
export type Scope = { kind: 'global' };
export type CreateSessionInput = { scope?: Scope; request_id?: string };
export type Availability = { available_members: number | null; total_members: number; availability_checked_at: string | null;
  availability_status: 'available' | 'partial' | 'unavailable' | 'unknown' };
export type SessionDetail = Availability & { id: string; title: string; created_at: string; updated_at: string; boot_id: string;
  annotation_flow?: {task_id:string;request_id?:string;cube_ids:string[];mode:'per_image'|'all';authorization_id:string};
  scope: { kind: 'global'; dataset_version_id: null; member_count: number };
  selected_cube_id: string | null; canvas_focus?: WorkspaceContext; selected_ordinal?: number | null; effective_tool_count: number; history_watermark: number;
  pending: ((Extract<AgentEvent, { event: 'human_check' }>['data'] & {kind: 'human_check'}) |
    (Extract<AgentEvent, {event: 'plan'}>['data'] & {kind: 'plan'})) | null;
  request: { request_id: string; status: 'running' | 'completed' | 'failed' | 'interrupted'; events_complete: number; boot_id: string } | null };
export type HistoryEvent = { seq: number; request_id: string | null; kind: AgentEvent['event'] | 'user' | 'decision';
  payload: Record<string, unknown>; origin: string };
export type HistoryPage = { session_id: string; events: HistoryEvent[]; watermark: number; has_more: boolean; next_before: number | null; next_after: number | null };
export type Session = { id: string; title: string; skill_version_id: string; created_at: string;
  skill_name: string; skill_version_no: number; runtime: RuntimeInfo };
export type RuntimeInfo = { skill_name: string | null; skill_version_id: string | null; skill_version_no: number | null;
  assistant_transport?:{protocol:number;progress:boolean;cancel:boolean;context:string};
  desktop_transport?:{protocol:number;stream:boolean};
  tool_catalogue_version: number; tool_count: number; sessions_by_skill: Record<string, number>;
  sessions_upgraded?: number };
export type Steps = { session_id: string; steps: { seq: number; tool: string; status: string; arguments_json: string;
  result_digest: string | null; result_summary: string; latency_ms: number; created_at: string }[] };
export type EventBatch = { events: AgentEvent[] };
export type RequestState = {session_id:string;request_id:string;status:'running'|'completed'|'failed'|'interrupted';cancel_requested:boolean;phase:string;boot_id:string};
export type StreamFrame = AgentEvent | {event:'stream_end';data:null};
export type InvokeAgent = <T>(command: string, args: { request: AgentRequest; onEvent?: Channel<StreamFrame> }) => Promise<T>;

export const requests = {
  checkBatchPrepare: (id: string, datasetVersionId?: string): AgentRequest => ({ op: 'check_batch_prepare', id,
    ...(datasetVersionId !== undefined ? { dataset_version_id: datasetVersionId } : {}) }),
  createSession: (body: CreateSessionInput = {}): AgentRequest => ({ op: 'create_session',
    ...(body.scope ? { scope: { kind: 'global' as const } } : {}),
    ...(body.request_id ? { request_id: body.request_id } : {}) }),
  getSession: (id: string): AgentRequest => ({ op: 'get_session', id }),
  getHistory: (id: string, page: {before?: number; after?: number; limit?: number} = {}): AgentRequest => ({op: 'get_history', id,
    ...(page.before !== undefined ? {before: page.before} : {}), ...(page.after !== undefined ? {after: page.after} : {}),
    ...(page.limit !== undefined ? {limit: page.limit} : {})}),
  selectCube: (id: string, cube_id: string | null): AgentRequest => ({op: 'select_cube', id, cube_id}),
  sendMessage: (id: string, body: MessageBody): AgentRequest => ({ op: 'send_message', id,
    body: { ...(body.request_id ? {request_id: body.request_id} : {}), ...('content' in body ? { content: body.content, ...(body.workspace ? { workspace: workspaceContext(body.workspace) } : {}) } : 'check_id' in body ? { check_id: body.check_id, decision: body.decision }
      : body.action === 'approve' ? { plan_id: body.plan_id, action: 'approve' }
        : body.action === 'reject' ? { plan_id: body.plan_id, action: 'reject', reason: body.reason }
          : { plan_id: body.plan_id, action: body.action, step_ref: body.step_ref, reason: body.reason }) } }),
  getSteps: (id: string): AgentRequest => ({ op: 'get_steps', id }),
  getRuntime: (): AgentRequest => ({ op: 'get_runtime' }),
};

// Names, paths, geometry and component state stay local. Only opaque references
// may accompany a normal message; confirmation continuations retain their IDs.
export function workspaceContext(value: WorkspaceContext): WorkspaceContext {
  return { ...(typeof value.cube_id === 'string' && value.cube_id ? { cube_id: value.cube_id } : {}),
    ...(typeof value.gesture_ref === 'string' && value.gesture_ref ? { gesture_ref: value.gesture_ref } : {}) };
}

export function agentClient(send: InvokeAgent = invoke) {
  const forward = <T>(request: AgentRequest) => send<T>('agent_forward', { request });
  return {
    inferenceHistory:(id:string,model_id:string)=>forward<{items:InferenceStatus[]}>({op:'inference_history',id,model_id}),
    inferenceStatus:(id:string,model_id:string,run_id:string)=>forward<InferenceStatus>({op:'inference_task',id,model_id,run_id,action:'get'}),
    cancelInference:(id:string,model_id:string,run_id:string)=>forward<InferenceStatus>({op:'inference_task',id,model_id,run_id,action:'cancel'}),
    inferenceResult:(id:string,model_id:string,run_id:string)=>forward<InferenceResult>({op:'inference_task',id,model_id,run_id,action:'result'}),
    inferencePlot:(id:string,model_id:string,run_id:string,file_index:number,kind:'prediction'|'input'='prediction')=>forward<{png_base64:string}>({op:'inference_plot',id,model_id,run_id,file_index,kind}),
    inferenceExport:(id:string,model_id:string,run_id:string,destination:string)=>forward<{saved:boolean;bytes:number}>({op:'inference_export',id,model_id,run_id,destination}),
    experimentHistory:(id:string,offset=0)=>forward<ExperimentHistory>({op:'experiment_history',id,offset,limit:20}),
    selectExperiment:(id:string,experiment_id:string)=>forward<{archived_experiment_id:string;status:string}>({op:'select_experiment',id,experiment_id}),
    compareExperiments:(id:string,first_id:string,second_id:string)=>forward<ExperimentComparison>({op:'compare_experiments',id,first_id,second_id}),
    archivedExperimentResult:(id:string,experiment_id:string)=>forward<ExperimentResult>({op:'archived_experiment_result',id,experiment_id}),
    archivedExperimentPlot:(id:string,experiment_id:string,name:string)=>forward<{name:string;png_base64:string}>({op:'archived_experiment_plot',id,experiment_id,name}),
    archivedExperimentExport:(id:string,experiment_id:string,kind:'report'|'bundle',destination:string)=>forward<{saved:boolean;bytes:number}>({op:'archived_experiment_export',id,experiment_id,kind,destination}),
    experimentResult:(id:string,task_id:string)=>forward<ExperimentResult>({op:'experiment_result',id,task_id}),
    experimentPlot:(id:string,task_id:string,name:string)=>forward<{name:string;png_base64:string}>({op:'experiment_plot',id,task_id,name}),
    experimentExport:(id:string,task_id:string,kind:'report'|'bundle',destination:string)=>forward<{saved:boolean;bytes:number}>({op:'experiment_export',id,task_id,kind,destination}),
    experimentTask: (id:string,taskId:string,action:'get'|'cancel'='get') => forward<ExperimentTask>({op:'experiment_task',id,task_id:taskId,action}),
    startAnnotation: (id:string, cubeIds:string[], mode:'per_image'|'all', requestId:string) => forward<TaskAccepted>({op:'start_annotation',id,request_id:requestId,cube_ids:[...cubeIds],mode}),
    annotationTask: (id:string, taskId:string, action:'get'|'cancel' = 'get') => forward<AnnotationTask>({op:'annotation_task',id,task_id:taskId,action}),
    taskItems: (id:string, taskId:string, after:number, version:number) => forward<AnnotationTask>({op:'annotation_task',id,task_id:taskId,action:'items',after,limit:100,version}),
    retryTask: (id:string, taskId:string, mode:'failed'|'remaining', requestId:string) => forward<TaskAccepted>({op:'annotation_task',id,task_id:taskId,action:'retry',mode,request_id:requestId}),
    prepareCube: (id:string,cubeId:string,requestId:string,authorizationId?:string)=>forward<TaskAccepted>({op:'annotation_task',id,task_id:cubeId,action:'prepare',request_id:requestId,...(authorizationId?{authorization_id:authorizationId}:{})}),
    focusCanvas:(id:string,cubeId:string,focused:boolean)=>forward<{cube_id:string;focused:boolean}>({op:'annotation_task',id,task_id:cubeId,action:focused?'focus':'blur'}),
    checkBatchPrepare: async (id: string, version?: string) => parseBatchAssessment(
      await forward<unknown>(requests.checkBatchPrepare(id, version)), id, version),
    createSession: (body: CreateSessionInput = {}) => forward<Session>(requests.createSession(body)),
    getSession: (id: string) => forward<SessionDetail>(requests.getSession(id)),
    latestSession: async () => (await forward<{sessions: {id: string}[]}>({op: 'list_sessions', query: {kind: 'global', limit: 1}})).sessions[0]?.id ?? null,
    getHistory: (id: string, page: {before?: number; after?: number; limit?: number} = {}) => forward<HistoryPage>(requests.getHistory(id, page)),
    selectCube: (id: string, cube: string | null) => forward<SessionDetail>(requests.selectCube(id, cube)),
    sendMessage: async (id: string, body: MessageBody, onEvent?: (event:AgentEvent)=>void, shouldProceed?:()=>boolean) => {
      if (!onEvent) return forward<EventBatch>(requests.sendMessage(id, body));
      let runtime:RuntimeInfo;
      try { runtime=await forward<RuntimeInfo>(requests.getRuntime()); }
      catch {throw {error:'ASSISTANT_RUNTIME_UNAVAILABLE',pre_execution:true};}
      if(runtime.assistant_transport?.protocol!==1||!runtime.assistant_transport.progress||!runtime.assistant_transport.cancel
        ||runtime.desktop_transport?.protocol!==1||!runtime.desktop_transport.stream){
        throw {error:'ASSISTANT_RUNTIME_MISMATCH',pre_execution:true};
      }
      if(shouldProceed&&!shouldProceed())throw {error:'REQUEST_NOT_SENT',pre_execution:true};
      const channel = new Channel<StreamFrame>();
      let end!:()=>void,streamFailure:unknown;
      const finished=new Promise<void>(resolve=>{end=resolve;});
      channel.onmessage = event=>{
        if(event.event==='stream_end'){end();return;}
        try{onEvent(event);}catch(error){streamFailure=error;}
      };
      let result:EventBatch;
      try {result=await send<EventBatch>('agent_stream', {request: requests.sendMessage(id, body), onEvent: channel});}
      catch(error){
        const message=typeof error==='string'?error:error instanceof Error?error.message:'';
        if(/command\s+[`'"]?agent_stream[`'"]?\s+not found|agent_stream.*(?:not allowed|denied)/i.test(message)){
          throw {error:'ASSISTANT_COMMAND_UNAVAILABLE',pre_execution:true};
        }
        throw error;
      }
      // IPC completion may race channel delivery. Drain ordered events before
      // reconciliation so late callbacks cannot overwrite restored history.
      await finished;
      if(streamFailure)throw streamFailure;
      return result;
    },
    cancelRequest: (id:string, requestId:string) => forward<RequestState>({op:'cancel_request',id,request_id:requestId}),
    getRequest: (id:string, requestId:string) => forward<RequestState>({op:'get_request',id,request_id:requestId}),
    getSteps: (id: string) => forward<Steps>(requests.getSteps(id)),
    getRuntime: () => forward<RuntimeInfo>(requests.getRuntime()),
  };
}
export const agent = agentClient();

export type BatchAssessment = {
  schema_version: 1; session_id: string; dataset_version_id: string; binding_source: 'explicit' | 'session_scope';
  profile: 'annotation-default-v1'; member_count: number; checked_at: string;
  assessment: 'blocked' | 'within_profile' | 'unknown'; check_code: string; constraint: string;
  actual: number | string | null; limit: number | string | null; runtime_memory_checked: false;
  execution_guaranteed: false; detail: string;
};
export const admissionConstraints: Record<string, string> = {
  MEMBER_COUNT_LIMIT: 'member_count', SHAPE_LIMIT: 'shape', BANDS_LIMIT: 'bands', DTYPE_LIMIT: 'dtype',
  ITEM_SOURCE_BYTES_LIMIT: 'item_source_bytes', TOTAL_SOURCE_BYTES_LIMIT: 'total_source_bytes',
  TOTAL_PIXELS_LIMIT: 'total_pixels', MEMBERS_UNAVAILABLE: 'members_available',
  METADATA_UNAVAILABLE: 'metadata', WITHIN_PROFILE: 'static_profile',
};
export function parseBatchAssessment(value: unknown, sessionId: string, version?: string): BatchAssessment {
  const s = value as BatchAssessment;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const scalar = (v: unknown) => v === null || typeof v === 'number' && Number.isFinite(v) && v >= 0
    || typeof v === 'string' && v.length <= 64 && /^[A-Za-z0-9_.x-]+$/.test(v);
  if (!s || typeof s !== 'object' || s.schema_version !== 1 || s.session_id !== sessionId
      || !uuid.test(s.dataset_version_id) || version !== undefined && s.dataset_version_id !== version
      || !['explicit', 'session_scope'].includes(s.binding_source) || s.profile !== 'annotation-default-v1'
      || !Number.isSafeInteger(s.member_count) || s.member_count < 1
      || typeof s.checked_at !== 'string' || !Number.isFinite(Date.parse(s.checked_at))
      || !Object.hasOwn(admissionConstraints, s.check_code) || admissionConstraints[s.check_code] !== s.constraint
      || s.assessment !== (s.check_code === 'WITHIN_PROFILE' ? 'within_profile' : s.check_code === 'METADATA_UNAVAILABLE' ? 'unknown' : 'blocked')
      || s.runtime_memory_checked !== false || s.execution_guaranteed !== false
      || !scalar(s.actual) || !scalar(s.limit) || typeof s.detail !== 'string' || s.detail.length > 512
      || /[\\/]|[A-Za-z]:/.test(s.detail)
      || Object.keys(s).some(k => !['schema_version','session_id','dataset_version_id','binding_source','profile','member_count',
        'checked_at','assessment','check_code','constraint','actual','limit','runtime_memory_checked','execution_guaranteed','detail'].includes(k))) {
    throw new Error('批量检查结果无法核验');
  }
  if (s.check_code === 'MEMBER_COUNT_LIMIT' && (s.actual !== s.member_count || s.limit !== 5 || s.member_count <= 5)) throw new Error('数量检查结果无法核验');
  return s;
}
