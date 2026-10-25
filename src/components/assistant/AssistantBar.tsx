import { useReducer, useRef, useState } from 'react';
import { agent, type MessageBody } from './api.ts';
import { initialChat, reduceChat, scalarText, type ChatEntry, type PendingCheck } from './sse.ts';
import './assistant.css';
import ConfirmCard from '../annotation/ConfirmCard.ts';
import PlanCard from './PlanCard.ts';

function entryText(entry: ChatEntry): string {
  switch (entry.event) {
    case 'user': return entry.data.content;
    case 'step': return `${entry.data.seq}. ${entry.data.tool} · ${entry.data.status} · ${scalarText(entry.data.result_summary)}`;
    case 'clarify': return entry.data.question;
    case 'human_check': return `${entry.data.reason} · ${entry.data.tool} · ${scalarText(entry.data.summary)}`;
    case 'plan': return `${entry.data.reason} · ${entry.data.steps.length} 步`;
    case 'done': return entry.data.content;
    case 'error': return `${entry.data.code}：${entry.data.detail}`;
  }
}

export default function AssistantBar({ enabled }: { enabled: boolean }) {
  const [state, dispatch] = useReducer(reduceChat, initialChat);
  const [content, setContent] = useState('');
  const sessionId = useRef<string | null>(null);
  // Ref closes the double-click gap before React commits disabled buttons.
  const inFlight = useRef(false);
  const request = async (body: MessageBody) => {
    if (!enabled || inFlight.current) return;
    if ('content' in body && (!body.content.trim() || state.pending)) return;
    if ('check_id' in body && (!state.pending || !('check_id' in state.pending) || state.pending.check_id !== body.check_id)) return;
    if ('plan_id' in body && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== body.plan_id)) return;
    inFlight.current = true;
    if ('content' in body) dispatch({ type: 'send', content: body.content });
    else if ('check_id' in body) dispatch({ type: 'decision', decision: body.decision });
    else dispatch({ type: 'plan', ...body });
    try {
      sessionId.current ??= (await agent.createSession()).id;
      const result = await agent.sendMessage(sessionId.current, body);
      dispatch({ type: 'events', events: result.events });
      if ('content' in body) setContent('');
    } catch (error) {
      const failure = error as { error?: string; detail?: string } | null;
      dispatch({ type: 'failed', detail: failure && typeof failure.error === 'string'
        ? `${failure.error}：${typeof failure.detail === 'string' ? failure.detail : '请求失败'}` : '助手请求失败，请重试。' });
    } finally { inFlight.current = false; }
  };
  const renderCheck = (state: { pending: PendingCheck; busy: boolean }) => <section aria-label="人工确认">
    <p>{state.pending.reason} · {state.pending.tool} · {scalarText(state.pending.summary)}</p>
    {state.pending.tool === 'annotations.draft_confirm' ? <ConfirmCard key={state.pending.check_id}
      cubeId={String(state.pending.summary.cube_id ?? '')} disabled={!enabled || state.busy} approveLabel="批准" rejectLabel="拒绝"
      onApprove={async () => { await request({ check_id: state.pending!.check_id, decision: 'approve' }); }}
      onReject={() => void request({ check_id: state.pending!.check_id, decision: 'reject' })} /> : <>
      <button disabled={!enabled || state.busy} onClick={() => void request({ check_id: state.pending!.check_id, decision: 'approve' })}>批准</button>
      <button disabled={!enabled || state.busy} onClick={() => void request({ check_id: state.pending!.check_id, decision: 'reject' })}>拒绝</button>
    </>}
  </section>;
  return <section className="assistant-bar" aria-label="S01 助手">
    <h2>编排助手</h2>
    <ol className="assistant-events" aria-label="对话记录" aria-live="polite">
      {state.entries.map((entry, index) => <li key={index} data-event={entry.event}>
        {entry.event === 'plan' && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== entry.data.plan_id)
          ? <PlanCard plan={entry.data} decision={entry.decision} readOnly /> : entryText(entry)}
      </li>)}
    </ol>
    {state.pending && ('plan_id' in state.pending
      ? <PlanCard key={state.pending.plan_id} plan={state.pending} disabled={!enabled || state.busy}
        onAction={async decision => { if (state.pending && 'plan_id' in state.pending) await request({ plan_id: state.pending.plan_id, ...decision }); }} />
      : renderCheck({ pending: state.pending, busy: state.busy }))}
    {state.busy && <p role="status">{state.executing ? '执行中…' : '请求中…'}</p>}
    {state.error && <p role="alert">{state.error}</p>}
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}>
      <label htmlFor="assistant-message">对话</label>
      <input id="assistant-message" value={content} onChange={event => setContent(event.target.value)}
        disabled={!enabled || state.busy || !!state.pending} placeholder="输入需要编排的任务" />
      <button type="submit" disabled={!enabled || state.busy || !!state.pending || !content.trim()}>发送</button>
    </form>
  </section>;
}
