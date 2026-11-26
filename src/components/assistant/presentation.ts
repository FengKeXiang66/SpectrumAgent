import type { DatasetReference } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import type { AgentEvent, ChatEntry } from './sse.ts';
import type { WorkspaceContext, BatchMember, BatchResult } from './api.ts';
import type { Scalars } from './sse.ts';
import type { Working } from '../annotation/types.ts';
import { candidateKey } from '../annotation/working.ts';
import { admissionConstraints } from './api.ts';

export type DatasetChoice = { id: string; label: string; index: number };
export type WorkspaceDisplay = { cube_id?: string; display_name?: string };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const uuidInText = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

// UI-only identity: never part of the model workspace request.
export function workspaceDisplay(current: WorkspaceDisplay, next: WorkspaceDisplay, records: DatasetReference[]): WorkspaceDisplay {
  if (!next.cube_id) return {};
  const valid = (value: unknown): value is string => typeof value === 'string'
    && value.trim().length > 0 && !/[\\/:\x00-\x1f\x7f]/.test(value);
  const row = records.find(record => record.id === next.cube_id);
  const catalogName = row && displayName(row);
  const name = valid(catalogName) ? catalogName : valid(next.display_name) ? next.display_name
    : current.cube_id === next.cube_id && valid(current.display_name) ? current.display_name : undefined;
  return { cube_id: next.cube_id, ...(name ? { display_name: name } : {}) };
}

export function datasetChoices(entries: ChatEntry[], records: DatasetReference[]): DatasetChoice[] {
  const listing = [...entries].reverse().find(entry => entry.event === 'step' && entry.data.tool === 'datasets.list' && entry.data.status === 'ok');
  if (!listing || listing.event !== 'step') return [];
  const summary = listing.data.result_summary;
  const indexed = Object.keys(summary).flatMap(key => {
    const match = /^dataset_(\d+)_id$/.exec(key);
    const id = summary[key];
    return match && typeof id === 'string' && uuid.test(id) ? [{ id, index: Number(match[1]) }] : [];
  }).sort((left, right) => left.index - right.index);
  if (indexed.length) return indexed.map(({ id, index }) => ({ id, index,
    label: records.filter(record => record.id === id).map(displayName)[0]
      || (typeof summary[`dataset_${index}_name`] === 'string' ? String(summary[`dataset_${index}_name`]) : `数据集 ${index}`) }));
  const ids = typeof summary.dataset_ids === 'string' ? summary.dataset_ids.split(',').map(value => value.trim()).filter(value => uuid.test(value)) : [];
  return [...new Set(ids)].map((id, index) => ({ id, index: index + 1,
    label: records.filter(record => record.id === id).map(displayName)[0] || `数据集 ${index + 1}` }));
}

export function readableText(text: string, choices: DatasetChoice[], records: DatasetReference[]): string {
  // Keep references accurate while avoiding UUID tables in ordinary replies.
  return text.replace(uuidInText, id => {
    const choice = choices.find(item => item.id.toLowerCase() === id.toLowerCase());
    const record = records.find(item => item.id.toLowerCase() === id.toLowerCase());
    return choice ? `${choice.index}号 ${choice.label}（${id.slice(0, 8)}）`
      : record ? `${displayName(record)}（${id.slice(0, 8)}）` : `引用 ${id.slice(0, 8)}`;
  });
}

export function changedCubes(events: AgentEvent[], workspace: WorkspaceContext = {}): string[] {
  const cubes = events.flatMap(event => {
    if (event.event !== 'step' || event.data.status !== 'ok' || !/^(annotations\.|preprocess\.|workspace\.)/.test(event.data.tool)) return [];
    if (event.data.tool === 'workspace.preprocess') {
      return Object.entries(event.data.result_summary).flatMap(([key,value]) => /^item_\d+_cube_id$/.test(key) && typeof value === 'string' && uuid.test(value) ? [value] : []);
    }
    if (event.data.tool === 'annotations.prepare_batch') {
      return parseBatchSummary(event.data.result_summary)?.readyMembers.map(item => item.cubeId) ?? [];
    }
    const cube = event.data.result_summary.cube_id ?? workspace.cube_id;
    return typeof cube === 'string' && uuid.test(cube) ? [cube] : [];
  });
  return [...new Set(cubes)];
}

export function catalogChanged(events: AgentEvent[]): boolean {
  return events.some(event => event.event === 'step' && event.data.status === 'ok'
    && (event.data.tool === 'datasets.import' && event.data.result_summary.status === 'imported'
      || event.data.tool === 'datasets.delete' && event.data.result_summary.status === 'deleted'
      || event.data.tool === 'annotations.external_import' && event.data.result_summary.status === 'saved'));
}

export function parseBatchSummary(s: Scalars): BatchResult | null {
  const integer = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
  const nullable = (value: unknown): value is string | null => value === null || typeof value === 'string';
  const reference = (value: unknown) => typeof value === 'string' && /^b-[0-9a-f]{32}$/.test(value);
  const statuses = ['need_version', 'need_scope', 'blocked', 'ready', 'partial', 'failed'] as const;
  if (!statuses.includes(s.status as BatchResult['status']) || s.truncated !== false
      || s.profile !== 'annotation-default-v1' || s.n_segments !== 200 || s.compactness !== .5 || s.pca_components !== 5
      || s.k !== 3 || s.block_size !== 32 || s.feature_version !== 'pca-global-zscore-clip3-unit-v1'
      || typeof s.algorithm_version !== 'string' || !s.algorithm_version
      || !integer(s.elapsed_ms) || typeof s.auto_open !== 'boolean'
      || !nullable(s.batch_ref) || !nullable(s.retry_of) || !nullable(s.dataset_version_id) || !nullable(s.open_cube_id)
      || (s.retry_of !== null && !reference(s.retry_of))) return null;
  const keys = ['member_count', 'requested_count', 'ready_count', 'failed_count', 'conflict_count', 'not_attempted_count'] as const;
  if (!keys.every(key => integer(s[key]))) return null;
  const n = s.member_count as number, requested = s.requested_count as number;
  const ready = s.ready_count as number, failed = s.failed_count as number, conflict = s.conflict_count as number, pending = s.not_attempted_count as number;
  if (ready + failed + conflict + pending !== n || requested > n) return null;
  const blocked = s.status === 'need_version' || s.status === 'need_scope' || s.status === 'blocked';
  const versionOk = typeof s.dataset_version_id === 'string' && uuid.test(s.dataset_version_id);
  const scopeOk = typeof s.scope_key === 'string' && /^[0-9a-f]{64}$/.test(s.scope_key);
  const members: BatchMember[] = [];
  if (blocked) {
    if (s.batch_ref !== null || s.auto_open || s.open_cube_id !== null || ready || failed || conflict || pending !== n
        || Object.keys(s).some(key => /^item_\d+_/.test(key))) return null;
    if (s.status === 'need_version' && (n !== 0 || s.dataset_version_id !== null || s.missing !== 'dataset_version_id')) return null;
    if (s.status === 'need_scope' && (n !== 0 || s.dataset_version_id !== null || s.missing !== 'cube_ids')) return null;
    if (s.status === 'blocked' && !versionOk && !scopeOk) return null;
  } else {
    // 2026-11-13: no member ceiling. A scope batch has no dataset_version_id;
    // its identity is the server-side scope_key instead.
    if (!n || (!versionOk && !scopeOk) || !reference(s.batch_ref)) return null;
    if (Object.keys(s).some(key => { const match = /^item_(\d+)_/.exec(key); return match && (Number(match[1]) < 1 || Number(match[1]) > n); })) return null;
    for (let i = 1; i <= n; i++) {
      const get = (key: string) => s[`item_${i}_${key}`];
      const cube = get('cube_id'), name = get('display_name'), status = get('status'), action = get('action');
      const count = get('superpixel_count'), code = get('error_code'), detail = get('detail');
      if (typeof cube !== 'string' || !uuid.test(cube) || typeof name !== 'string' || !name.trim()
          || !['ready', 'failed', 'conflict', 'not_attempted'].includes(String(status))
          || !['generated', 'reused', 'restored', 'retained', 'none'].includes(String(action)) || !nullable(code) || !nullable(detail)) return null;
      if (status === 'ready' ? !integer(count) || count === 0 || action === 'none' || code !== null || detail !== null
        : count !== null || action !== 'none' || typeof code !== 'string' || !code || typeof detail !== 'string' || !detail) return null;
      members.push({ cubeId: cube, displayName: name, status: status as BatchMember['status'], action: action as BatchMember['action'],
        superpixelCount: count as number | null, errorCode: code, detail });
    }
    if (new Set(members.map(item => item.cubeId.toLowerCase())).size !== n) return null;
    for (const [status, count] of [['ready', ready], ['failed', failed], ['conflict', conflict], ['not_attempted', pending]] as const) {
      if (members.filter(item => item.status === status).length !== count) return null;
    }
    const first = members.find(item => item.status === 'ready')?.cubeId ?? null;
    if (s.open_cube_id !== first || s.auto_open !== (s.status === 'ready')
        || (s.status === 'ready' ? ready !== n : s.status === 'partial' ? ready === 0 || ready === n : ready !== 0)) return null;
  }
  return { status: s.status as BatchResult['status'], datasetVersionId: s.dataset_version_id, batchRef: s.batch_ref,
    retryOf: s.retry_of, memberCount: n, requestedCount: requested, readyCount: ready, failedCount: failed,
    conflictCount: conflict, notAttemptedCount: pending, autoOpen: s.auto_open, openCubeId: s.open_cube_id,
    members, readyMembers: members.filter(item => item.status === 'ready'),
    detail: typeof s.detail === 'string' ? s.detail : null, elapsedMs: s.elapsed_ms, admission: parseAdmission(s) };
}

function parseAdmission(s: Scalars): BatchResult['admission'] {
  const code = s.admission_reason, constraint = s.admission_constraint;
  const safe = (v: unknown) => v === null || typeof v === 'number' && Number.isFinite(v) && v >= 0
    || typeof v === 'string' && v.length <= 64 && /^[A-Za-z0-9_.x-]+$/.test(v);
  if (typeof code !== 'string' || typeof constraint !== 'string'
      || (code === 'RUNTIME_MEMORY_LIMIT' ? constraint !== 'runtime_memory_budget' : !Object.hasOwn(admissionConstraints, code) || admissionConstraints[code] !== constraint)
      || !safe(s.admission_actual) || !safe(s.admission_limit) || typeof s.admission_checked_at !== 'string'
      || !Number.isFinite(Date.parse(s.admission_checked_at))) return null;
  if (code === 'MEMBER_COUNT_LIMIT' && (s.admission_actual !== s.member_count || s.admission_limit !== 5 || Number(s.member_count) <= 5)) return null;
  return { code, constraint, actual: s.admission_actual as number | string | null, limit: s.admission_limit as number | string | null, checkedAt: s.admission_checked_at };
}


export function sameMembers(left: readonly string[], right: readonly string[]): boolean {
  return left.length === new Set(left).size && right.length === new Set(right).size && left.length === right.length
    && left.every(id => right.includes(id));
}

export function batchExplanation(result: BatchResult): string {
  if (result.status === 'ready') return '分割准备完成，等待人工点选；尚未识别材质或保存标注。';
  if (result.status === 'need_version' || result.status === 'need_scope') return '本次未执行，需要明确要处理的样品范围。';
  const a = result.admission;
  if (!a) return result.status === 'blocked' ? '本次未执行；具体准入条件未提供。' : result.detail ?? '请核查逐项结果。';
  if (a.code === 'MEMBER_COUNT_LIMIT') return `范围包含${a.actual}个样品，当前同步批量上限为${a.limit}个，本次未开始处理。`;
  if (a.code === 'RUNTIME_MEMORY_LIMIT') return '实际执行的内存准入未通过，本次未开始处理。';
  const labels: Record<string,string> = { shape:'尺寸', bands:'波段', dtype:'数据类型', item_source_bytes:'单项源字节', total_source_bytes:'总源字节', total_pixels:'总像素', members_available:'可用成员' };
  return `${labels[a.constraint] ?? '静态准入'}检查阻断：实际 ${a.actual ?? '未知'}，限制 ${a.limit ?? '未知'}；本次未执行。`;
}

// A done event is a transport boundary. Only the current request/round's
// validated summary may supply a batch label, never a previous request's ready.
export function entryBusiness(entries: ChatEntry[], index: number): { label: string; batch: BatchResult | null; hasBatch?: boolean; hasTask?:boolean } {
  const entry = entries[index];
  if (entry.event === 'done' && entry.data.reply_status) return {batch:null,label:
    entry.data.reply_status === 'needs_input' ? '需要补充信息' : entry.data.reply_status === 'needs_confirmation' ? '需要你确认' : '已回复'};
  let start = index;
  while (start > 0 && entries[start].event !== 'user' && entries[start-1].event !== 'done') start--;
  const round = entries.slice(start,index+1).filter(e => !entry.requestId || e.requestId === entry.requestId);
  const associated = !!entry.requestId || round.some(e=>e.event==='user') || start>0 && entries[start-1].event==='done';
  const step = associated ? [...round].reverse().find(e => e.event === 'step' && e.data.tool === 'annotations.prepare_batch') : undefined;
  const batch = step?.event === 'step' && step.data.status === 'ok' ? parseBatchSummary(step.data.result_summary) : null;
  if(step?.event==='step'&&step.data.status==='ok'&&step.data.result_summary.status==='accepted')return {batch:null,hasTask:true,label:'后台任务已受理'};
  if (batch) return { batch, hasBatch:true, label: ({blocked:'未执行',need_version:'需要补充信息',need_scope:'需要补充信息',partial:'部分就绪',failed:'未就绪',ready:'分割准备完成，等待人工点选'} as const)[batch.status] };
  if (step) return {batch:null,hasBatch:true,label:'未就绪'};
  const result = entry.event === 'done' ? entry.data.task_result : undefined;
  return {batch:null,label: result === 'needs_input' ? '需要补充信息' : result === 'needs_review' ? '等待人工核查'
    : result === 'failed' ? '未就绪' : result === 'cancelled' ? '已取消' : result === 'working' ? '处理中' : '已回复'};
}

export function selectWorkspace(current: WorkspaceContext, next: WorkspaceContext): WorkspaceContext {
  // A gesture belongs to one cube. Switching selection never carries it over.
  if (next.cube_id !== current.cube_id) return { ...(next.cube_id ? { cube_id: next.cube_id } : {}),
    ...(next.gesture_ref ? { gesture_ref: next.gesture_ref } : {}) };
  return { ...current, ...next };
}

export function proposedCandidates(events: AgentEvent[]): { cube_id: string; candidate_ref: string }[] {
  return events.flatMap(event => {
    if (event.event !== 'step' || event.data.tool !== 'annotations.propose' || event.data.status !== 'ok') return [];
    const { cube_id, candidate_ref, status } = event.data.result_summary;
    return status === 'preview' && typeof cube_id === 'string' && uuid.test(cube_id)
      && typeof candidate_ref === 'string' && /^c-[0-9a-f]{32}$/.test(candidate_ref) ? [{ cube_id, candidate_ref }] : [];
  });
}

export function candidatePreviewKey(working: Working | null, reference: string): string | null {
  const candidate = working?.queue.find(item => item.candidate_ref === reference);
  return candidate ? candidateKey(candidate) : null;
}

export function preprocessingBusiness(summary: Scalars): {label:string;complete:boolean} {
  if(summary.status==='need_version')return {label:'需要核对当前输入 · 尚未执行',complete:false};
  const succeeded=Number(summary.succeeded??0),failed=Number(summary.failed??0),remaining=Number(summary.remaining_failed??0);
  if(failed||remaining)return {label:`${succeeded||Number(summary.retained_succeeded??0)?'部分完成':'执行失败'}（${succeeded} 成功，${failed} 失败${remaining?`，${remaining} 待处理`:''}）`,complete:false};
  return {label:'✓ 完成',complete:true};
}
