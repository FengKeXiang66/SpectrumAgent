export type Scalars = Record<string, string | number | boolean | null>;
export type PlanEventData = { plan_id: string; steps: { seq: number; tool: string; summary: Scalars; gpu: boolean; estimate_ms: number | null }[]; reason: string };
export type PlanDecision = { action: 'approve' } | { action: 'reject'; reason: string }
  | { action: 'skip' | 'rollback'; step_ref: number; reason: string };
export type AgentEvent =
  | { event: 'step'; data: { seq: number; tool: string; status: string; result_summary: Scalars } }
  | { event: 'clarify'; data: { question: string } }
  | { event: 'human_check'; data: { check_id: string; tool: string; summary: Scalars; reason: string } }
  | { event: 'plan'; data: PlanEventData }
  | { event: 'done'; data: { content: string; step_count: number } }
  | { event: 'error'; data: { code: string; detail: string } };

// Same framing as the Rust collector. No event-count cutoff: rejected calls
// also produce step events; the forwarder's 8MiB body cap is the hard limit.
export function parseSse(text: string): AgentEvent[] {
  const events: AgentEvent[] = [];
  let event = '', data: string[] = [];
  const flush = () => {
    if (data.length) {
      if (!['step', 'clarify', 'human_check', 'plan', 'done', 'error'].includes(event)) throw new Error('SSE 事件类型非法');
      const value: unknown = JSON.parse(data.join('\n'));
      if (value === null || Array.isArray(value) || typeof value !== 'object') throw new Error('SSE 数据必须为对象');
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
  | { type: 'events'; events: AgentEvent[] }
  | { type: 'failed'; detail: string };

export function reduceChat(state: ChatState, action: ChatAction): ChatState {
  if (action.type === 'send') {
    if (state.busy || state.pending) return state;
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
  let next: ChatState = { ...state, pending: null, busy: false, executing: false, error: null };
  for (const event of action.events) {
    next = { ...next, entries: [...next.entries, event] };
    if (event.event === 'human_check') next.pending = event.data;
    if (event.event === 'plan') next.pending = event.data;
    if (event.event === 'done' || event.event === 'error' || event.event === 'clarify') next.pending = null;
    if (event.event === 'error') next.error = `${event.data.code}：${event.data.detail}`;
  }
  return next;
}

export function scalarText(summary: Scalars): string {
  return Object.entries(summary).filter(([, value]) => value === null || ['string', 'number', 'boolean'].includes(typeof value))
    .map(([key, value]) => `${key}: ${String(value)}`).join(' · ');
}
