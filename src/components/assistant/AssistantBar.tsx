import { scalarText, friendlyError, type ChatEntry, type PendingCheck } from './sse.ts';
import { readableText } from './presentation.ts';
import type { AssistantSession } from './useSession';
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
    case 'error': return friendlyError(entry.data.code, entry.data.detail);
    case 'workspace': return '';
  }
}

// The phase label is derived from the event type, never from invented state.
function agentName(event: ChatEntry['event']): string {
  switch (event) {
    case 'plan': return '智能助手 · 执行计划';
    case 'clarify': return '智能助手 · 需要你确认';
    case 'human_check': return '智能助手 · 人工确认';
    case 'done': return '智能助手 · 已完成';
    default: return '智能助手';
  }
}

export default function AssistantBar({ session }: { session: AssistantSession }) {
  const { enabled, state, content, setContent, request, choices, records } = session;
  const renderCheck = (state: { pending: PendingCheck; busy: boolean }) => <section className="agent-check" aria-label="人工确认">
    <span className="agent-check-icon" aria-hidden="true">!</span>
    <p>{readableText(`${state.pending.reason} · ${state.pending.tool} · ${scalarText(state.pending.summary)}`, choices, records)}</p>
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
    <div className="assistant-content">
    {(() => {
      // TASK-07b R2: step/error events leave the conversation flow. Steps fold
      // into a collapsible "执行日志" panel; errors surface via the alert below.
      const conversation = state.entries.filter(entry => entry.event !== 'step' && entry.event !== 'error' && entry.event !== 'workspace');
      const logs = state.entries.filter(entry => entry.event === 'step');
      return <>
        <ol className="assistant-events" aria-label="对话记录" aria-live="polite">
          {conversation.map((entry, index) => <li key={index} data-event={entry.event}
            className={`agent-msg ${entry.event === 'user' ? 'agent-msg-user' : 'agent-msg-ai'}`}>
            <span className="agent-avatar" aria-hidden="true">{entry.event === 'user' ? '我' : 'AI'}</span>
            <div className="agent-bubble">
              {entry.event !== 'user' && <div className="agent-name">{agentName(entry.event)}</div>}
              <div className="agent-text">
                {entry.event === 'plan' && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== entry.data.plan_id)
                  ? <PlanCard plan={entry.data} decision={entry.decision} readOnly /> : entry.event === 'user' ? entryText(entry)
                    : <>{readableText(entryText(entry), choices, records)}
                      {readableText(entryText(entry), choices, records) !== entryText(entry) && <details className="assistant-references">
                        <summary>查看完整引用</summary><p>{entryText(entry)}</p>
                      </details>}</>}
              </div>
            </div>
          </li>)}
        </ol>
        {logs.length > 0 && <details className="assistant-logs" aria-label="执行日志">
          <summary>执行日志（{logs.length}）</summary>
          <ol>{logs.map((entry, index) => entry.event === 'step' ? <li key={index} className="agent-tool" data-event="step">
            <span className="agent-tool-name">{entry.data.tool}</span>
            <span className="agent-tool-detail">{scalarText(entry.data.result_summary) || '—'}</span>
            <span className={`agent-tool-status ${entry.data.status === 'ok' ? 'is-ok' : 'is-other'}`}>
              {entry.data.status === 'ok' ? '✓ 完成' : entry.data.status}
            </span>
          </li> : null)}</ol>
        </details>}
      </>;
    })()}
    {state.pending && <div className="agent-pending">{'plan_id' in state.pending
      ? <PlanCard key={state.pending.plan_id} plan={state.pending} disabled={!enabled || state.busy}
        onAction={async decision => { if (state.pending && 'plan_id' in state.pending) await request({ plan_id: state.pending.plan_id, ...decision }); }} />
      : renderCheck({ pending: state.pending, busy: state.busy })}</div>}
    {state.pending && <p className="assistant-hint">也可以直接回复“批准执行”“确认保存”或“拒绝”，继续用对话操作。</p>}
    {state.busy && <p role="status" className="agent-busy">{state.executing ? '执行中…' : '请求中…'}</p>}
    {state.error && <p role="alert" className="agent-error">{state.error}</p>}
    </div>
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}>
      <label htmlFor="assistant-message">对话</label>
      <input id="assistant-message" value={content} onChange={event => setContent(event.target.value)}
        disabled={!enabled || state.busy} placeholder={state.pending ? '可输入批准、确认保存或拒绝' : '输入需要编排的任务'} />
      <button type="submit" disabled={!enabled || state.busy || !content.trim()}>发送</button>
    </form>
  </section>;
}
