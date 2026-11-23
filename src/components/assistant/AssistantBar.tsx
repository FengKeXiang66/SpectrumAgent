import { useState } from 'react';
import { scalarText, friendlyError, type ChatEntry, type PendingCheck } from './sse.ts';
import { readableText, parseBatchSummary, entryBusiness, batchExplanation, preprocessingBusiness } from './presentation.ts';
import type { AssistantSession } from './useSession';
import './assistant.css';
import PlanCard from './PlanCard.ts';
import BatchPrepareCard, { batchBusinessLabel } from './BatchPrepareCard.tsx';
import AsyncPrepareCard from './AsyncPrepareCard.tsx';
import { annotationChoices, choiceScope, taskPositions, replyPosition } from './annotation-timeline.ts';
import RequestStatus from './RequestStatus';
import ResultCard from './ResultCard';
import ExperimentTaskCard from './ExperimentTaskCard';
import ExperimentHistory from './ExperimentHistory';
import ExperimentResults from './ExperimentResults';
import InferenceTaskCard from './InferenceTaskCard';

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
    case 'progress': return '';
  }
}

// The phase label is derived from the event type, never from invented state.
function agentName(event: ChatEntry['event'], business = '已回复'): string {
  switch (event) {
    case 'plan': return '智能助手 · 执行计划';
    case 'clarify': return '智能助手 · 需要补充信息';
    case 'human_check': return '智能助手 · 人工确认';
    case 'done': return `智能助手 · ${business}`;
    default: return '智能助手';
  }
}

export default function AssistantBar({ session }: { session: AssistantSession }) {
  const { enabled, state, content, setContent, request, choices, records } = session;
  const [historyOpen,setHistoryOpen] = useState(false);
  const prepareInference=(modelId:string)=>setContent('使用模型 '+modelId+' 进行推理，数据目录为');
  const renderCheck = (state: { pending: PendingCheck; busy: boolean }) => <section className="agent-check" aria-label="人工确认">
    <span className="agent-check-icon" aria-hidden="true">!</span>
    <p>{readableText(`${state.pending.reason} · ${state.pending.tool} · ${scalarText(state.pending.summary)}`, choices, records)}</p>
      <button disabled={!enabled || state.busy} onClick={() => void request({ check_id: state.pending!.check_id, decision: 'approve' })}>批准</button>
      <button disabled={!enabled || state.busy} onClick={() => void request({ check_id: state.pending!.check_id, decision: 'reject' })}>拒绝</button>
  </section>;
  return <section className="assistant-bar" aria-label="S01 助手">
    <h2>编排助手</h2>
    <div className="experiment-history-dock">
      <button className="experiment-history-toggle" aria-expanded={historyOpen} aria-controls="experiment-history-panel"
        disabled={!enabled||session.loading} onClick={()=>{
          const next=!historyOpen;
          setHistoryOpen(next);
          if(next&&!session.active)session.startNew();
        }}>{historyOpen?'收起':'查看'}历史实验与归档模型</button>
      {historyOpen&&(session.active
        ?<ExperimentHistory sessionId={session.active.id} enabled={enabled} onInfer={prepareInference}/>
        :<div id="experiment-history-panel" className="experiment-history"><p role="status">{session.loading?'正在打开历史实验…':'尚未打开历史实验，请重试。'}</p>
          {!session.loading&&<button disabled={!enabled} onClick={session.startNew}>重新打开历史实验</button>}</div>)}
    </div>
    <div className="assistant-content">
    {session.historyBefore!==null && <button disabled={!enabled} onClick={()=>void session.loadOlder()}>加载更早历史</button>}
    {(() => {
      // TASK-07b R2: step/error events leave the conversation flow. Steps fold
      // into a collapsible "执行日志" panel; errors surface via the alert below.
      const requestStart=state.entries.reduce((last,entry,index)=>entry.event==='user'?index:last,0);
      const logs = state.entries.slice(Math.max(0,requestStart)).filter(entry => entry.event === 'step');
      const centerStep = logs.find(entry => entry.event === 'step' && entry.data.status === 'ok' && entry.data.result_summary.center_action);
      const splitReady = logs.some(entry => entry.event === 'step' && entry.data.tool === 'experiments.group_split'
        && entry.data.status === 'ok' && entry.data.result_summary.split_ready === true);
      const centerAction = centerStep?.event === 'step' ? centerStep.data.result_summary.center_action : null;
      const centerCommand = centerAction === 'verify_centers' ? '核验中心取谱'
        : centerAction === 'prepare_training' ? '用本次取谱结果新建训练方案' : null;
      const modeChoices=annotationChoices(state.entries);
      const tasks=taskPositions(state.entries,session.taskCards??[]);
      const legacy=(session.batchCards??[]).map(card=>({card,start:state.entries.findIndex(entry=>!!card.requestId&&entry.requestId===card.requestId)}))
        .filter(item=>item.start>=0).map(item=>({...item,anchor:replyPosition(state.entries,item.start)}));
      return <>
        <ol className="assistant-events" aria-label="对话记录" aria-live="polite">
          {state.entries.map((entry, index) => {
            const visible=!['step','error','workspace','progress'].includes(entry.event);
            const choice=modeChoices.get(index);
            const resolvedScope=choice&&!choice.selected&&(choice.cubeIds
              ?{cubeIds:choice.cubeIds,label:'本次已确定的数据'}
              :choiceScope(choice.text,records,choices,session.workspace?.cube_id));
            const scope=choice?.selected?{label:'该次选择范围',cubeIds:[],memberCount:choice.memberCount}
              :resolvedScope?{...resolvedScope,memberCount:resolvedScope.cubeIds.length||undefined}
                :{label:'尚未选择',cubeIds:[],memberCount:undefined};
            const outcome = entryBusiness(state.entries,state.entries.indexOf(entry));
            const actualText = entry.event==='done'&&outcome.hasTask?'超像素任务已受理，请查看任务卡片中的实时状态。':entry.event === 'done' && outcome.hasBatch
              ? outcome.batch ? batchExplanation(outcome.batch) : '本轮批量结果无法核验，未开启批量操作。' : entryText(entry);
            return [visible&&<li key={`message:${index}`} data-event={entry.event}
            className={`agent-msg ${entry.event === 'user' ? 'agent-msg-user' : 'agent-msg-ai'}`}>
            <span className="agent-avatar" aria-hidden="true">{entry.event === 'user' ? '我' : 'AI'}</span>
            <div className="agent-bubble">
              {entry.event !== 'user' && <div className="agent-name">{agentName(entry.event,outcome.label)}</div>}
              <div className="agent-text">
                {entry.event === 'plan' && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== entry.data.plan_id)
                  ? <PlanCard plan={entry.data} decision={entry.decision} readOnly /> : entry.event === 'user' ? entryText(entry)
                    : <>{readableText(actualText, choices, records)}
                      {readableText(actualText, choices, records) !== actualText && <details className="assistant-references">
                        <summary>查看完整引用</summary><p>{actualText}</p>
                      </details>}</>}
              </div>
            </div>
          </li>,entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.view_kind==='string'&&
            <li key={`result:${index}`} className="agent-msg agent-msg-ai" data-event="local-result"><ResultCard summary={entry.data.result_summary}/></li>,
            entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.experiment_task_id==='string'&&session.active&&
              !state.entries.slice(0,index).some(old=>old.event==='step'&&old.data.result_summary.experiment_task_id===entry.data.result_summary.experiment_task_id)&&
              <li key={`experiment:${entry.data.result_summary.experiment_task_id}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <ExperimentTaskCard taskId={entry.data.result_summary.experiment_task_id} sessionId={session.active.id} enabled={enabled} onInfer={prepareInference}/>
              </div></li>,
            entry.event==='step'&&entry.data.status==='ok'&&entry.data.result_summary.status==='succeeded'&&
              typeof entry.data.result_summary.archived_experiment_id==='string'&&session.active&&
              <li key={`archived-experiment:${index}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <ExperimentResults sessionId={session.active.id} experimentId={entry.data.result_summary.archived_experiment_id} enabled={enabled} onInfer={prepareInference}/>
              </div></li>,
            entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.inference_run_id==='string'&&
              typeof entry.data.result_summary.model_id==='string'&&session.active&&
              !state.entries.slice(0,index).some(old=>old.event==='step'&&old.data.result_summary.inference_run_id===entry.data.result_summary.inference_run_id)&&
              <li key={`inference:${entry.data.result_summary.inference_run_id}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <InferenceTaskCard sessionId={session.active.id} modelId={entry.data.result_summary.model_id} runId={entry.data.result_summary.inference_run_id} enabled={enabled}/>
              </div></li>,
            choice&&<li key={`choice:${index}`} className="agent-msg agent-msg-ai" data-event="annotation-choice">
            <span className="agent-avatar" aria-hidden="true">AI</span>
            <div className="agent-bubble"><section aria-label="开始人工点选标注" className="batch-prepare-card">
              <p>使用超像素人工点选标注。范围：{scope.cubeIds.length||choice.selected?scope.label:'尚未选择'}{scope.memberCount!==undefined&&`，共 ${scope.memberCount} 张`}。</p>
              {choice.selected?<p>已选择{choice.selected==='per_image'?'逐张生成':'提前生成全部'}。</p>:!scope.cubeIds.length?
                choice.active?<form className="annotation-range-choice" onSubmit={event=>{
                  event.preventDefault();
                  const input=event.currentTarget.elements.namedItem('annotation-range') as HTMLInputElement;
                  const mode=((event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement|null)?.value;
                  const range=choiceScope(input.value,records,choices,session.workspace?.cube_id,true);
                  if(!range?.cubeIds.length){input.setCustomValidity('请选择全部已导入数据，或填写有效范围，例如 D1–D5');input.reportValidity();return;}
                  if(mode==='per_image'||mode==='all')void session.startAnnotation(mode,range.cubeIds);
                }}>
                  <p>先选择标注范围，再点击生成方式：</p>
                  <label>数据范围<input name="annotation-range" aria-label="标注数据范围" required placeholder="全部已导入数据或 D1–D5"
                    disabled={!enabled||state.busy||!!state.pending} onInput={event=>event.currentTarget.setCustomValidity('')}/></label>
                  <button type="button" disabled={!enabled||state.busy||!!state.pending||!records.length} onClick={event=>{
                    const input=event.currentTarget.form?.elements.namedItem('annotation-range') as HTMLInputElement|null;
                    if(input){input.value='全部已导入数据';input.setCustomValidity('');input.focus();}
                  }}>全部已导入数据（{records.length} 张）</button>
                  <button type="submit" name="annotation-mode" value="per_image" disabled={!enabled||state.busy||!!state.pending||!records.length}>逐张生成（推荐）</button>
                  <button type="submit" name="annotation-mode" value="all" disabled={!enabled||state.busy||!!state.pending||!records.length}>提前生成全部</button>
                </form>:<p>本轮未选择范围，可在后续对话中继续。</p>:<>
                <p>请选择生成方式：</p>
                <button disabled={!choice.active||!enabled||state.busy||!!state.pending||!scope.cubeIds.length}
                  onClick={()=>void session.startAnnotation('per_image',scope.cubeIds)}>逐张生成（推荐）</button>
                <button disabled={!choice.active||!enabled||state.busy||!!state.pending||!scope.cubeIds.length}
                  onClick={()=>void session.startAnnotation('all',scope.cubeIds)}>提前生成全部</button>
              </>}
            </section></div>
          </li>,...(tasks.get(index)??[]).map(card=><li key={`task:${card.taskId}`} className="agent-msg agent-msg-ai" data-event="annotation-task">
            <span className="agent-avatar" aria-hidden="true">AI</span>
            <div className="agent-bubble"><AsyncPrepareCard card={card} bootId={session.bootId}
              actionsDisabled={state.busy||!!state.pending||session.loading}
              disabled={!enabled||!session.taskActive(card)} onOpen={result=>session.openTask(card,result)}
              onRetry={(id,requestId,mode)=>session.retriedTask(card,id,requestId,mode)}/></div>
          </li>),...legacy.filter(item=>item.anchor===index).map(({card})=><li key={card.key} className="agent-msg agent-msg-ai" data-event="annotation-batch">
            <span className="agent-avatar" aria-hidden="true">AI</span><div className="agent-bubble">
              <BatchPrepareCard result={card.result}
                disabled={!enabled || state.busy || !session.isBatchActive(card)}
                onOpen={() => session.openBatch(card)} onRetry={() => session.retryBatch(card)} />

            </div>
          </li>)];})}
        </ol>
        {splitReady && !state.busy && !state.pending && <div>
          <button type="button" disabled={!enabled || session.loading} onClick={() => void request({ content:'划分明细 第1页' })}>查看逐图明细</button>
          <button type="button" disabled={!enabled || session.loading} onClick={() => void request({ content:'确认保存划分' })}>确认保存划分</button>
        </div>}
        {centerCommand && !state.busy && !state.pending && <button type="button" disabled={!enabled || session.loading}
          onClick={() => void request({ content: centerCommand })}>{centerCommand}</button>}
        {logs.length > 0 && <details className="assistant-logs" aria-label="执行日志">
          <summary>执行日志（{logs.length}）</summary>
          <ol>{logs.map((entry, index) => entry.event === 'step' ? <li key={index} className="agent-tool" data-event="step">
            <span className="agent-tool-name">{entry.data.tool}</span>
            <span className="agent-tool-detail">{scalarText(entry.data.result_summary) || '—'}</span>
            <span className={`agent-tool-status ${(entry.data.tool === 'annotations.prepare_batch'
              ? entry.data.status === 'ok' && parseBatchSummary(entry.data.result_summary)?.status === 'ready'
              : entry.data.status === 'ok' && (!['preprocess.run_batch','preprocess.draft_execute'].includes(entry.data.tool) || preprocessingBusiness(entry.data.result_summary).complete)) ? 'is-ok' : 'is-other'}`}>
              {entry.data.tool === 'annotations.prepare_batch'
                ? entry.data.status === 'ok' && entry.data.result_summary.status === 'accepted' ? '已受理' : batchBusinessLabel(entry.data.status === 'ok' ? parseBatchSummary(entry.data.result_summary) : null)
                : entry.data.status === 'ok' ? ['preprocess.run_batch','preprocess.draft_execute'].includes(entry.data.tool)?preprocessingBusiness(entry.data.result_summary).label:'✓ 完成' : entry.data.status}
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
    <RequestStatus session={session}/>
    {state.error && <p role="alert" className="agent-error">{state.error}</p>}
    </div>
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}>
      <label htmlFor="assistant-message">对话</label>
      <input id="assistant-message" value={content} onChange={event => setContent(event.target.value)}
        disabled={!enabled} placeholder={state.busy?'可先编辑下一条消息，停止后发送':state.pending ? '可输入批准、确认保存或拒绝' : '输入需要编排的任务'} />
      {state.busy?<button type="button" className="agent-stop" disabled={!enabled||session.stopping} onClick={()=>void session.stop()}>{session.stopping?'正在停止…':'停止'}</button>
        :<button type="submit" disabled={!session.canSend || !content.trim()}>发送</button>}
    </form>
  </section>;
}
