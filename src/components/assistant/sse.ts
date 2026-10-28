export type Scalars = Record<string, string | number | boolean | null>;
export type PlanEventData = { plan_id: string; steps: { seq: number; tool: string; summary: Scalars; gpu: boolean; estimate_ms: number | null }[]; reason: string };
export type PlanDecision = { action: 'approve' } | { action: 'reject'; reason: string }
  | { action: 'skip' | 'rollback'; step_ref: number; reason: string };
export type WorkspaceEventData = { cube_id: string; gesture_ref?: string; display_name?: string; stage?: 'annotation' | 'preprocess'; revision?: number };
export type AgentEvent =
  | { event: 'step'; data: { seq: number; tool: string; status: string; result_summary: Scalars } }
  | { event: 'clarify'; data: { question: string; keep_pending?: boolean } }
  | { event: 'human_check'; data: { check_id: string; tool: string; summary: Scalars; reason: string } }
  | { event: 'plan'; data: PlanEventData }
  | { event: 'workspace'; data: WorkspaceEventData }
  | { event: 'done'; data: { content: string; step_count: number } }
  | { event: 'error'; data: { code: string; detail: string } };

// Same framing as the Rust collector. No event-count cutoff: rejected calls
// also produce step events; the forwarder's 8MiB body cap is the hard limit.
export function parseSse(text: string): AgentEvent[] {
  const events: AgentEvent[] = [];
  let event = '', data: string[] = [];
  const flush = () => {
    if (data.length) {
      if (!['step', 'clarify', 'human_check', 'plan', 'workspace', 'done', 'error'].includes(event)) throw new Error('SSE 事件类型非法');
      const value: unknown = JSON.parse(data.join('\n'));
      if (value === null || Array.isArray(value) || typeof value !== 'object') throw new Error('SSE 数据必须为对象');
      if (event === 'workspace') validateWorkspaceEvent(value);
      if (event === 'clarify' && 'keep_pending' in value && typeof value.keep_pending !== 'boolean') throw new Error('SSE 确认保留标志非法');
      events.push({ event, data: value } as AgentEvent);
    }
    event = ''; data = [];
  };
  for (const raw of text.split('\n')) {
    const line = raw.replace(/\r$/, '');
    if (!line) { flush(); continue; }
    const colon = line.indexOf(':');
    if (colon < 0) continue;
    const field = line.slice(0, colon), value = line.slice(colon + 1).replace(/^ /, '');
    if (field === 'event') event = value;
    if (field === 'data') data.push(value);
  }
  flush();
  return events;
}

export function validateWorkspaceEvent(value: object): asserts value is WorkspaceEventData {
  const data = value as Record<string, unknown>;
  const valid = Object.keys(data).every(key => ['cube_id', 'gesture_ref', 'display_name', 'stage', 'revision'].includes(key))
    && typeof data.cube_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(data.cube_id)
    && (data.gesture_ref === undefined || typeof data.gesture_ref === 'string' && /^g-[0-9a-f]{32}$/.test(data.gesture_ref))
    && (data.display_name === undefined || typeof data.display_name === 'string')
    && (data.stage === undefined || data.stage === 'annotation' || data.stage === 'preprocess')
    && (data.revision === undefined || typeof data.revision === 'number' && Number.isInteger(data.revision) && data.revision >= 0);
  if (!valid) throw new Error('SSE 工作区引用非法');
}

export type ChatEntry = Exclude<AgentEvent, { event: 'plan' }> | { event: 'plan'; data: PlanEventData; decision?: PlanDecision }
  | { event: 'user'; data: { content: string } };
export type PendingCheck = Extract<AgentEvent, { event: 'human_check' }>['data'];
export type PendingPlan = PlanEventData;
export type ChatState = { entries: ChatEntry[]; pending: PendingCheck | PendingPlan | null; busy: boolean; executing: boolean; error: string | null };
export const initialChat: ChatState = { entries: [], pending: null, busy: false, executing: false, error: null };
export type ChatAction =
  | { type: 'send'; content: string }
  | { type: 'decision'; decision: 'approve' | 'reject' }
  | ({ type: 'plan' } & PlanDecision)
  | { type: 'reset' }
  | { type: 'events'; events: AgentEvent[] }
  | { type: 'failed'; detail: string };

export function reduceChat(state: ChatState, action: ChatAction): ChatState {
  if (action.type === 'reset') return initialChat;
  if (action.type === 'send') {
    if (state.busy) return state;
    return { ...state, busy: true, error: null, entries: [...state.entries, { event: 'user', data: { content: action.content } }] };
  }
  if (action.type === 'decision') {
    if (state.busy || !state.pending || !('check_id' in state.pending)) return state;
    return { ...state, pending: action.decision === 'reject' ? null : state.pending,
      busy: true, executing: action.decision === 'approve', error: null };
  }
  if (action.type === 'plan') {
    if (state.busy || !state.pending || !('plan_id' in state.pending)) return state;
    const planId = state.pending.plan_id;
    const { type: _type, ...decision } = action;
    return { ...state, pending: action.action === 'reject' ? null : state.pending,
      busy: true, executing: action.action !== 'reject', error: null,
      entries: state.entries.map(entry => entry.event === 'plan' && entry.data.plan_id === planId ? { ...entry, decision } : entry) };
  }
  if (action.type === 'failed') return { ...state, busy: false, executing: false, error: action.detail };
  let next: ChatState = { ...state, busy: false, executing: false, error: null };
  for (const event of action.events) {
    next = { ...next, entries: [...next.entries, event] };
    if (event.event === 'human_check') next.pending = event.data;
    if (event.event === 'plan') next.pending = event.data;
    if (event.event === 'done' || event.event === 'error' || event.event === 'clarify' && !event.data.keep_pending) next.pending = null;
    if (event.event === 'error') next.error = friendlyError(event.data.code, event.data.detail);
  }
  return next;
}

export function scalarText(summary: Scalars): string {
  const truncate = (value: string) => value.length > 50 ? value.slice(0, 47) + '…' : value;
  return Object.entries(summary).filter(([, value]) => value === null || ['string', 'number', 'boolean'].includes(typeof value))
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? truncate(value) : String(value)}`).join(' · ');
}

// TASK-07b R4: map internal error codes to user-facing Chinese; unknown codes fall back.
const ERROR_MESSAGES: Record<string, string> = {
  LLM_HTTP: '模型服务返回异常，请稍后重试',
  LLM_TRANSPORT: '无法连接模型服务，请检查网络或网关设置',
  http_error: '模型服务返回异常，请稍后重试',
  transport_error: '无法连接模型服务，请检查网络或网关设置',
  TOOL_FAILED: '工具执行失败',
  AGENT_FAILED: '编排执行失败',
  AGENT_STORAGE: '编排留痕存储失败',
  SESSION_NOT_FOUND: '会话不存在',
  INVALID_REQUEST: '请求不合法',
  LLM_AUTH: '模型服务鉴权失败，请检查设置中的 API 密钥',
  LLM_RATE_LIMIT: '模型服务请求过于频繁，请稍后重试',
  LLM_UNAVAILABLE: '模型服务暂时不可用，请稍后重试',
  LLM_PROTOCOL: '模型服务的工具调用格式不兼容，请检查模型与网关配置',
  LLM_PROTOCOL_ERROR: '模型服务的工具调用格式不兼容，请检查模型与网关配置',
  LLM_TOOL_PROTOCOL: '模型服务未返回有效工具调用，请检查模型与网关的兼容性',
  LLM_TRUNCATED: '模型回复不完整，请重试或调整回复长度限制',
  LLM_OUTPUT_TRUNCATED: '模型回复达到长度上限，请提高回复长度上限后重试',
  LLM_NOT_CONFIGURED: '请先在设置中配置模型服务',
  LLM_EGRESS_DISABLED: '模型联网已关闭，可在设置中开启',
  EGRESS_BLOCKED: '消息包含不能发送给模型的数据，请使用平台内的数据引用',
  ENGINE_NOT_READY: '引擎尚未就绪，请稍后重试',
  TRANSPORT: '无法连接本机引擎，请检查引擎状态后重试',
  AGENT_NO_PROGRESS: '助手重复了相同操作，已停止并保留进度。请查看执行日志后继续。',
  AGENT_BUDGET_EXCEEDED: '本轮已达到连续执行上限，进度已保留，请查看执行日志后继续。',
};

// These details are curated by the local backend, not provider response bodies.
// Preserve their actionable distinction (e.g. HTTP 401 versus a bad response).
const DETAILED_ERRORS = new Set(['LLM_HTTP', 'http_error', 'LLM_TOOL_PROTOCOL', 'LLM_OUTPUT_TRUNCATED',
  'AGENT_NO_PROGRESS', 'AGENT_BUDGET_EXCEEDED']);

export function friendlyError(code: string, detail: string): string {
  if (DETAILED_ERRORS.has(code) && detail && detail !== code && !/^[A-Z][A-Z0-9_]+$/.test(detail)) return detail;
  if (ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  return detail && detail !== code && !/^[A-Z][A-Z0-9_]+$/.test(detail)
    ? detail : '请求未完成，已保留当前结果。请重试或查看执行日志。';
}

export function requestError(error: unknown): string {
  if (error && typeof error === 'object') {
    const failure = error as { error?: unknown; code?: unknown; detail?: unknown };
    const code = typeof failure.error === 'string' ? failure.error : typeof failure.code === 'string' ? failure.code : '';
    return friendlyError(code, typeof failure.detail === 'string' ? failure.detail : '');
  }
  return friendlyError(typeof error === 'string' ? error : '', '');
}
