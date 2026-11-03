import { useEffect, useReducer, useRef, useState } from 'react';
import { agent, type MessageBody, type RuntimeInfo, type WorkspaceContext } from './api.ts';
import { initialChat, reduceChat, scalarText, friendlyError, requestError, validateWorkspaceEvent, type ChatEntry, type PendingCheck, type WorkspaceEventData } from './sse.ts';
import { changedCubes, datasetChoices, proposedCandidates, readableText } from './presentation.ts';
import type { DatasetRecord } from '../datasets/types.ts';
import { displayName as datasetDisplayName } from '../datasets/types.ts';
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

export default function AssistantBar({ enabled, workspace = {}, displayName, records = [], onWorkspaceChange, onWorkspaceNavigate, onDataChanged, onPreviewCandidate }: {
  enabled: boolean; workspace?: WorkspaceContext; records?: DatasetRecord[];
  displayName?: string; onWorkspaceChange?(workspace: WorkspaceContext): void;
  onWorkspaceNavigate?(selection: WorkspaceEventData): void; onDataChanged?(cubeIds: string[]): void;
  onPreviewCandidate?(cubeId: string, candidateRef: string): void;
}) {
  const [state, dispatch] = useReducer(reduceChat, initialChat);
  const [content, setContent] = useState('');
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const sessionId = useRef<string | null>(null);
  // Ref closes the double-click gap before React commits disabled buttons.
  const inFlight = useRef(false);
  // The running orchestration version is read from the engine, never guessed from
  // file timestamps, so the badge always states what is really executing.
  useEffect(() => {
    let cancelled = false;
    void agent.getRuntime().then(value => { if (!cancelled) setRuntime(value); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);
  const choices = datasetChoices(state.entries, records);
  const selected = records.find(record => record.id === workspace.cube_id);
  const selectedChoice = choices.find(choice => choice.id === workspace.cube_id);
  const request = async (body: MessageBody) => {
    if (!enabled || inFlight.current) return;
    if ('content' in body && !body.content.trim()) return;
    if ('check_id' in body && (!state.pending || !('check_id' in state.pending) || state.pending.check_id !== body.check_id)) return;
    if ('plan_id' in body && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== body.plan_id)) return;
    const requestWorkspace = 'content' in body ? body.workspace ?? workspace : workspace;
    inFlight.current = true;
    if ('content' in body) dispatch({ type: 'send', content: body.content });
    else if ('check_id' in body) dispatch({ type: 'decision', decision: body.decision });
    else dispatch({ type: 'plan', ...body });
    try {
      sessionId.current ??= (await agent.createSession()).id;
      const result = await agent.sendMessage(sessionId.current, 'content' in body
        ? { content: body.content, ...(requestWorkspace.cube_id ? { workspace: requestWorkspace } : {}) } : body);
      for (const event of result.events) if (event.event === 'workspace') validateWorkspaceEvent(event.data);
      dispatch({ type: 'events', events: result.events });
      for (const event of result.events) if (event.event === 'workspace') {
        onWorkspaceChange?.({ cube_id: event.data.cube_id, ...(event.data.gesture_ref ? { gesture_ref: event.data.gesture_ref } : {}) });
        onWorkspaceNavigate?.(event.data);
      }
      for (const preview of proposedCandidates(result.events)) onPreviewCandidate?.(preview.cube_id, preview.candidate_ref);
      const changed = changedCubes(result.events, requestWorkspace);
      if (changed.length) onDataChanged?.(changed);
      if ('content' in body) setContent('');
    } catch (error) {
      dispatch({ type: 'failed', detail: requestError(error) });
    } finally { inFlight.current = false; }
  };
  const renderCheck = (state: { pending: PendingCheck; busy: boolean }) => <section aria-label="人工确认">
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
    <button disabled={!enabled || state.busy || !!state.pending} onClick={() => { sessionId.current = null; dispatch({ type: 'reset' }); setContent(''); }}>
      开始新对话
    </button>
    <small>新对话使用当前编排能力，保留当前数据选择。</small>
    <p className="assistant-runtime" aria-label="当前编排版本">{runtime?.skill_name
      ? `当前编排：${runtime.skill_name} · 工具目录 v${runtime.tool_catalogue_version} · ${runtime.tool_count} 个工具`
      : '当前编排版本读取中…'}</p>
    <p className="assistant-context" aria-label="当前对话对象">{workspace.cube_id
      ? `当前数据：${(selected && datasetDisplayName(selected)) || selectedChoice?.label || displayName || workspace.cube_id.slice(0, 8)}${workspace.gesture_ref ? ' · 已带入最近的画布提示' : ''}`
      : '可在工作台选择数据，或直接告诉助手要处理哪份数据。'}</p>
    {(() => {
      // TASK-07b R2: step/error events leave the conversation flow. Steps fold
      // into a collapsible "执行日志" panel; errors surface via the alert below.
      const conversation = state.entries.filter(entry => entry.event !== 'step' && entry.event !== 'error' && entry.event !== 'workspace');
      const logs = state.entries.filter(entry => entry.event === 'step');
      return <>
        <ol className="assistant-events" aria-label="对话记录" aria-live="polite">
          {conversation.map((entry, index) => <li key={index} data-event={entry.event}>
            {entry.event === 'plan' && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== entry.data.plan_id)
              ? <PlanCard plan={entry.data} decision={entry.decision} readOnly /> : entry.event === 'user' ? entryText(entry)
                : <>{readableText(entryText(entry), choices, records)}
                  {readableText(entryText(entry), choices, records) !== entryText(entry) && <details className="assistant-references">
                    <summary>查看完整引用</summary><p>{entryText(entry)}</p>
                  </details>}</>}
          </li>)}
        </ol>
        {logs.length > 0 && <details className="assistant-logs" aria-label="执行日志">
          <summary>执行日志（{logs.length}）</summary>
          <ol>{logs.map((entry, index) => <li key={index} data-event={entry.event}>{entryText(entry)}</li>)}</ol>
        </details>}
      </>;
    })()}
    {choices.length > 0 && <section className="assistant-datasets" aria-label="对话中的数据集选择">
      <p>可按序号选择，也可以继续说“第一个”或数据名称。</p>
      <ol>{choices.map(choice => <li key={choice.id}>
        <button disabled={!enabled || state.busy || !!state.pending} aria-pressed={workspace.cube_id === choice.id}
          onClick={() => { onWorkspaceChange?.({ cube_id: choice.id }); void request({ content: `选择第${choice.index}个数据集`, workspace: { cube_id: choice.id } }); }}>
          {choice.index}号 · {choice.label} · {choice.id.slice(0, 8)}
        </button>
        <details><summary>数据引用</summary><code>{choice.id}</code></details>
      </li>)}</ol>
    </section>}
    {state.pending && ('plan_id' in state.pending
      ? <PlanCard key={state.pending.plan_id} plan={state.pending} disabled={!enabled || state.busy}
        onAction={async decision => { if (state.pending && 'plan_id' in state.pending) await request({ plan_id: state.pending.plan_id, ...decision }); }} />
      : renderCheck({ pending: state.pending, busy: state.busy }))}
    {state.pending && <p className="assistant-hint">也可以直接回复“批准执行”“确认保存”或“拒绝”，继续用对话操作。</p>}
    {state.busy && <p role="status">{state.executing ? '执行中…' : '请求中…'}</p>}
    {state.error && <p role="alert">{state.error}</p>}
    </div>
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}>
      <label htmlFor="assistant-message">对话</label>
      <input id="assistant-message" value={content} onChange={event => setContent(event.target.value)}
        disabled={!enabled || state.busy} placeholder={state.pending ? '可输入批准、确认保存或拒绝' : '输入需要编排的任务'} />
      <button type="submit" disabled={!enabled || state.busy || !content.trim()}>发送</button>
    </form>
  </section>;
}
