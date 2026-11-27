import { useRef, useState } from 'react';
import InferenceDraftCard, { inferenceDraft, type InferenceDraft } from './InferenceDraftCard';
import { open } from '@tauri-apps/plugin-dialog';
import { scalarText, friendlyError, type ChatEntry, type PendingCheck, type Scalars } from './sse.ts';
import { readableText, parseBatchSummary, entryBusiness, batchExplanation, preprocessingBusiness } from './presentation.ts';
import type { AssistantSession } from './useSession';
import './assistant.css';
import PlanCard from './PlanCard.ts';
import BatchPrepareCard, { batchBusinessLabel } from './BatchPrepareCard.tsx';
import AsyncPrepareCard from './AsyncPrepareCard.tsx';
import { annotationChoices, choiceScope, taskPositions, replyPosition } from './annotation-timeline.ts';
import RequestStatus from './RequestStatus';
import MessageInput from './MessageInput';
import ResultCard from './ResultCard';
import ExperimentTaskCard from './ExperimentTaskCard';
import type { ViewerTarget, WavelengthDetails } from './WorkViewer';
import ExperimentResults from './ExperimentResults';
import InferenceTaskCard from './InferenceTaskCard';
import type { OpenInferenceView } from './InferenceResultsView';
import StudyCard from './StudyCard';
import ForegroundProbeCard from './ForegroundProbeCard';
import DataIntakeCard from './DataIntakeCard';
import { labelCommandText } from './label-names.ts';
import { formInputLabel, type EditorKind } from './preprocessing-form';
import PreprocessingEditorCard from './PreprocessingEditorCard';

function entryText(entry: ChatEntry): string {
  switch (entry.event) {
    case 'user': return entry.data.content.startsWith('应用推理参数 ') ? '应用推理参数微调' : formInputLabel(labelCommandText(entry.data.content));
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

function DraftCard({card,details,active,canAct,send,onViewer,onEdit,onPreprocess}:{
  card:Scalars;details:string;active:boolean;canAct:boolean;send:(text:string)=>void;
  onViewer:(target:ViewerTarget)=>void;onEdit:()=>void;onPreprocess:()=>void;
}) {
  let spectrum:WavelengthDetails|null = null;
  if(typeof card.wavelength_details==='string'){
    try {spectrum=JSON.parse(card.wavelength_details) as WavelengthDetails;} catch { /* Older cards still show full configuration. */ }
  }
  const revision = card.draft_revision;
  const changes = typeof card.draft_changes==='string' ? card.draft_changes.split('\n').filter(Boolean) : [];
  return <section className="draft-review" aria-label="当前实验方案">
    {typeof card.draft_todo==='string'&&<p className="draft-todo">{card.draft_todo}</p>}
    {changes.length>0&&<section className="draft-changes" aria-label="本轮变更"><strong>本轮变更</strong>
      <ul>{changes.map((change,index)=><li key={index}>{change}</li>)}</ul>
    </section>}
    {card.draft_summary&&<p className="draft-summary">{String(card.draft_summary)}</p>}
    {typeof card.draft_notes==='string'&&<p className="draft-notes">{card.draft_notes}</p>}
    <div className="work-actions">
      {active&&typeof card.wavelength_label==='string'&&<button className="draft-primary" disabled={!canAct}
        onClick={()=>send('采用波长建议 '+revision)}>
        <strong>采用建议并更新方案</strong><small>{card.wavelength_label}</small></button>}
      {spectrum&&<button onClick={()=>onViewer({kind:'wavelength',details:spectrum})}>查看波长详情</button>}
      {active&&typeof card.study_label==='string'&&<button className="draft-primary" disabled={!canAct}
        onClick={()=>send('训练集内自动寻优 '+revision+' 折数 '+card.study_folds)}>
        <strong>训练集内自动寻优</strong><small>{card.study_label}</small></button>}
    </div>
    {active&&<div className="work-actions">
      <button disabled={!canAct} onClick={onPreprocess}>编辑预处理参数</button>
      <button disabled={!canAct} onClick={onEdit}>手动改参</button>
      {card.draft_ready===true&&<button disabled={!canAct} onClick={()=>send('确认执行')}>
        {card.study_folds?'直接运行当前方案':'确认执行'}</button>}
    </div>}
    <details className="draft-details"><summary>完整配置 · 修订 {String(revision)}</summary>
      <p>{changes.length ? details.replace(/\n本轮变更\n(?:• [^\n]*\n?)*/, '\n') : details}</p>
    </details>
  </section>;
}

const pairingSections = {pairs:'配对明细', unused:'未配对原图', issues:'配对异常'} as const;

export default function AssistantBar({session,onHistory,onViewer}:{
  session:AssistantSession;onHistory:()=>void;onViewer:(target:ViewerTarget)=>void;
}) {
  const { enabled, state, content, setContent, request, choices, records } = session;
  const showInference:OpenInferenceView=(result,fileIndex)=>onViewer({kind:'inference',result,fileIndex});
  const [pickerError,setPickerError] = useState('');
  const [editorKind, setEditorKind] = useState<EditorKind | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const editDraft=(prompt:string)=>{setContent(prompt);input.current?.focus();};
  const prepareInference=(modelId:string)=>setContent('使用模型 '+modelId+' 进行推理，数据目录为');
  const sendCommand=(text:string)=>{if(!state.busy)void request({content:text});};
  async function pickPath(directory:boolean){
    setPickerError('');
    try{
      const selected=await open({title:directory?'选择数据目录':'选择数据文件',directory,multiple:false});
      if(typeof selected==='string')setContent((content.trimEnd()+' "'+selected+'"').trimStart());
    }catch{setPickerError('无法打开文件选择器，请重试。');}
  }
  const renderCheck = (state: { pending: PendingCheck; busy: boolean }) => <section className="agent-check" aria-label="人工确认">
    <span className="agent-check-icon" aria-hidden="true">!</span>
    <p>{readableText(`${state.pending.reason} · ${state.pending.tool} · ${scalarText(state.pending.summary)}`, choices, records)}</p>
      <button disabled={!enabled || state.busy} onClick={() => void request({ check_id: state.pending!.check_id, decision: 'approve' })}>批准</button>
      <button disabled={!enabled || state.busy} onClick={() => void request({ check_id: state.pending!.check_id, decision: 'reject' })}>拒绝</button>
  </section>;
  return <section className="assistant-bar" aria-label="S01 助手">
    <header className="assistant-heading"><h2>编排助手</h2>
      <button disabled={!enabled||session.loading} onClick={onHistory}>历史与模型</button>
    </header>
    <div className="assistant-content">
    <div className="work-actions" aria-label="对话预处理配置">
      <button disabled={!session.canSend || !!state.pending} onClick={() => setEditorKind('classification')}>分类预处理参数</button>
      <button disabled={!session.canSend || !!state.pending} onClick={() => setEditorKind('recipe')}>回归／高级配方参数</button>
    </div>
    {editorKind && <PreprocessingEditorCard key={`${session.active?.id ?? 'new'}:${editorKind}`} session={session} kind={editorKind} onClose={() => setEditorKind(null)} />}
    {session.historyBefore!==null && <button disabled={!enabled} onClick={()=>void session.loadOlder()}>加载更早历史</button>}
    {(() => {
      // TASK-07b R2: step/error events leave the conversation flow. Steps fold
      // into a collapsible "执行日志" panel; errors surface via the alert below.
      const requestStart=state.entries.reduce((last,entry,index)=>entry.event==='user'?index:last,0);
      const logs = state.entries.slice(Math.max(0,requestStart)).filter(entry => entry.event === 'step');
      const centerStep = logs.find(entry => entry.event === 'step' && entry.data.status === 'ok' && entry.data.result_summary.center_action);
      const splitReady = logs.some(entry => entry.event === 'step' && entry.data.tool === 'experiments.group_split'
        && entry.data.status === 'ok' && entry.data.result_summary.split_ready === true);
      const splitAction = logs.find(entry => entry.event === 'step' && entry.data.tool === 'experiments.group_split'
        && entry.data.status === 'ok' && (entry.data.result_summary.split_saved || entry.data.result_summary.split_baseline_ready));
      const splitCommand = splitAction?.event === 'step' && (splitAction.data.result_summary.split_saved
        ? '用已保存划分新建基线训练方案' : '确认执行');
      const centerAction = centerStep?.event === 'step' ? centerStep.data.result_summary.center_action : null;
      const pairedTraining = logs.some(entry => entry.event === 'step' && entry.data.result_summary.paired_training_available === true);
      const pairingReady = logs.some(entry => entry.event === 'step' && entry.data.result_summary.pairing_ready === true);
      const centerCommand = centerAction === 'verify_centers' ? '核验中心取谱'
        : centerAction === 'prepare_training' ? '用本次取谱结果新建训练方案' : null;
      const modeChoices=annotationChoices(state.entries);
      const tasks=taskPositions(state.entries,session.taskCards??[]);
      const legacy=(session.batchCards??[]).map(card=>({card,start:state.entries.findIndex(entry=>!!card.requestId&&entry.requestId===card.requestId)}))
        .filter(item=>item.start>=0).map(item=>({...item,anchor:replyPosition(state.entries,item.start)}));
      const latestDraft = state.entries.reduce((last,entry,index)=>entry.event==='step'&&entry.data.status==='ok'
        && ['experiments.draft_presentation','experiments.inference_presentation'].includes(entry.data.tool) ? index : last,-1);
      const latestIntake = state.entries.reduce((last, entry, index) => entry.event === 'done' && entry.data.data_intake ? index : last, -1);
      let draftCard: Scalars|undefined;
      let inferCard: InferenceDraft|undefined;
      let draftIndex = -1;
      const retainedStudy = logs.find(entry=>entry.event==='step' && entry.data.status==='ok'
        && entry.data.tool==='experiments.study_preview_retained');
      const retainedStudyId = retainedStudy?.event==='step' ? retainedStudy.data.result_summary.retained_study_preview_id : undefined;
      const latestStudyPreview = state.entries.reduce((last,entry,index)=>entry.event==='step'&&entry.data.status==='ok'
        && entry.data.tool==='experiments.study_preview' ? index : last,-1);
      let studyPreview: Scalars|undefined;
      let studyIndex = -1;
      let pairedPreview: string|undefined;
      return <>
        <ol className="assistant-events" aria-label="对话记录" aria-live="polite">
          {state.entries.map((entry, index) => {
            if(entry.event==='user'){draftCard=undefined;inferCard=undefined;draftIndex=-1;studyPreview=undefined;studyIndex=-1;pairedPreview=undefined;}
            if(entry.event==='step'&&entry.data.status==='ok'){
              const summary = entry.data.result_summary;
              if(entry.data.tool==='experiments.draft_presentation'){
                draftCard=summary;inferCard=undefined;draftIndex=index;
              }
              if(entry.data.tool==='experiments.inference_presentation'){
                inferCard=inferenceDraft(summary);draftCard=undefined;draftIndex=index;
              }
              if(entry.data.tool==='experiments.study_preview'){studyPreview=summary;studyIndex=index;}
              if(typeof summary.pairing_preview_id==='string')pairedPreview=summary.pairing_preview_id;
            }
            const reply = entry.event==='clarify'||entry.event==='done';
            const card = reply?draftCard:undefined;
            const inference = reply?inferCard:undefined;
            const currentDraft = draftIndex===latestDraft && index>=requestStart;
            const draftTitle = inference ? '推理方案' : '训练方案';
            const ready = inference?.ready ?? card?.draft_ready===true;
            const revision = inference?.revision ?? card?.draft_revision;
            const preview = reply?pairedPreview:undefined;
            const study = reply?studyPreview:undefined;
            const retained = study && studyIndex===latestStudyPreview && typeof retainedStudyId==='string'
              && (study.study_preview_id===undefined || study.study_preview_id===retainedStudyId);
            if(reply){draftCard=undefined;inferCard=undefined;draftIndex=-1;studyPreview=undefined;studyIndex=-1;pairedPreview=undefined;}
            const current = index>=requestStart;
            const actionsEnabled = enabled&&!state.busy&&!state.pending&&!session.loading;
            const canAct = current&&actionsEnabled;
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
            const draftContent = inference
              ? <InferenceDraftCard card={inference} active={currentDraft} canAct={canAct} send={sendCommand}/>
              : card ? <DraftCard card={card} details={readableText(actualText, choices, records)} active={currentDraft}
                    canAct={canAct} send={sendCommand} onViewer={onViewer} onEdit={()=>editDraft('把实验方案改为')}
                    onPreprocess={() => setEditorKind('classification')}/> : null;
            return [visible&&<li key={`message:${index}`} data-event={entry.event}
              data-draft={draftContent?(currentDraft?(ready?'ready':'incomplete'):'history'):undefined}
            className={`agent-msg ${entry.event === 'user' ? 'agent-msg-user' : 'agent-msg-ai'}`}>
            <span className="agent-avatar" aria-hidden="true">{entry.event === 'user' ? '我' : 'AI'}</span>
            <div className="agent-bubble">
              {entry.event !== 'user' && (!draftContent||currentDraft) && <div className="agent-name">{draftContent
                ? draftTitle+(ready?' · 待确认':' · 待补充')
                :study?'寻优方案 · 待确认':agentName(entry.event,outcome.label)}</div>}
              <div className="agent-text">
                {entry.event === 'plan' && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== entry.data.plan_id)
                  ? <PlanCard plan={entry.data} decision={entry.decision} readOnly /> : entry.event === 'user' ? entryText(entry)
                    : study ? <section className="draft-review">
                      <p className="draft-todo">{String(study.study_overview)}</p>
                      {study.study_fold_note&&<p>{String(study.study_fold_note)}</p>}
                      {study.study_sampling&&<p>{String(study.study_sampling)}</p>}
                      <details className="draft-details"><summary>查看寻优配置与评价口径</summary>
                        <p>{readableText(actualText,choices,records)}</p></details>
                      {(current||retained)&&<div className="work-actions"><button className="draft-primary" disabled={!actionsEnabled}
                        onClick={()=>sendCommand(String(study.study_confirm))}>{String(study.study_confirm)}</button></div>}
                    </section>
                    : draftContent ? currentDraft ? draftContent : <details className="draft-history">
                      <summary>{draftTitle} · 修订 {String(revision)}</summary>{draftContent}</details>
                    : <>{readableText(actualText, choices, records)}
                      {readableText(actualText, choices, records) !== actualText && <details className="assistant-references">
                        <summary>查看完整引用</summary><p>{actualText}</p>
                      </details>}</>}
              </div>
              {entry.event === 'done' && entry.data.data_intake && <DataIntakeCard card={entry.data.data_intake}
                active={index === latestIntake} enabled={enabled && !state.busy && !session.loading}
                send={sendCommand} edit={editDraft} />}
              {preview&&<div className="work-actions">{Object.entries(pairingSections).map(([key,title])=>
                <button key={key} onClick={()=>onViewer({kind:'pairing',previewId:preview,section:key as keyof typeof pairingSections})}>{title}</button>)}</div>}
            </div>
          </li>,entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.view_kind==='string'&&
            <li key={`result:${index}`} className="agent-msg agent-msg-ai" data-event="local-result"><ResultCard summary={entry.data.result_summary}/></li>,
            entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.experiment_task_id==='string'&&session.active&&
              !state.entries.slice(0,index).some(old=>old.event==='step'&&old.data.result_summary.experiment_task_id===entry.data.result_summary.experiment_task_id)&&
              <li key={`experiment:${entry.data.result_summary.experiment_task_id}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <ExperimentTaskCard taskId={entry.data.result_summary.experiment_task_id} sessionId={session.active.id} enabled={enabled} onInfer={prepareInference} onCommand={sendCommand} onHistory={onHistory} onInferenceView={showInference}/>
              </div></li>,
            entry.event==='step'&&entry.data.status==='ok'&&entry.data.result_summary.status==='succeeded'&&
              typeof entry.data.result_summary.archived_experiment_id==='string'&&session.active&&
              <li key={`archived-experiment:${index}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <ExperimentResults sessionId={session.active.id} experimentId={entry.data.result_summary.archived_experiment_id} enabled={enabled} onInfer={prepareInference} onCommand={sendCommand} onInferenceView={showInference}/>
              </div></li>,
            entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.study_id==='string'&&session.active&&
              !state.entries.slice(0,index).some(old=>old.event==='step'&&old.data.result_summary.study_id===entry.data.result_summary.study_id)&&
              <li key={`study:${entry.data.result_summary.study_id}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <StudyCard sessionId={session.active.id} id={entry.data.result_summary.study_id} enabled={enabled&&!state.busy&&!state.pending} send={sendCommand} onView={result=>onViewer({kind:'study',result})}/>
              </div></li>,
            entry.event==='step'&&entry.data.result_summary.foreground_probe===true&&session.active&&
              !state.entries.slice(index+1).some(next=>next.event==='step'&&next.data.result_summary.foreground_probe===true)&&
              <li key={`probe:${index}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <ForegroundProbeCard key={`${index}:${requestStart}`} sessionId={session.active.id} enabled={enabled} canAct={canAct} send={sendCommand}/>
              </div></li>,
            entry.event==='step'&&entry.data.status==='ok'&&typeof entry.data.result_summary.inference_run_id==='string'&&
              typeof entry.data.result_summary.model_id==='string'&&session.active&&
              !state.entries.slice(0,index).some(old=>old.event==='step'&&old.data.result_summary.inference_run_id===entry.data.result_summary.inference_run_id)&&
              <li key={`inference:${entry.data.result_summary.inference_run_id}`} className="agent-msg agent-msg-ai"><div className="agent-bubble">
                <InferenceTaskCard sessionId={session.active.id} modelId={entry.data.result_summary.model_id} runId={entry.data.result_summary.inference_run_id} enabled={enabled} onView={showInference}/>
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
        {splitCommand && !state.busy && !state.pending && <button type="button" disabled={!enabled || session.loading}
          onClick={() => void request({ content: splitCommand })}>{splitCommand}</button>}
        {pairingReady && !state.busy && !state.pending && <div className="assistant-input-paths">
          {['按这个关系检查','调整目录用途'].map(command => <button type="button" key={command}
            disabled={!enabled || session.loading} onClick={() => sendCommand(command)}>{command}</button>)}
        </div>}
        {pairedTraining && !state.busy && !state.pending && <button type="button" disabled={!enabled || session.loading}
          onClick={() => sendCommand('用本次配对结果新建训练方案')}>用本次配对结果新建训练方案</button>}
        {centerCommand && !state.busy && !state.pending && <button type="button" disabled={!enabled || session.loading}
          onClick={() => void request({ content: centerCommand })}>{centerCommand}</button>}
        {logs.length > 0 && <details className="assistant-logs" aria-label="执行日志">
          <summary>执行日志（{logs.length}）</summary>
          <ol>{logs.map((entry, index) => {
            if (entry.event !== 'step') return null;
            const {tool, result_summary: summary} = entry.data;
            const inspection = entry.data.status === 'ok' && tool === 'experiments.input_inspect' && summary.available === false
              ? '输入未识别' : entry.data.status === 'ok' && tool === 'experiments.draft_get' && summary.status === 'needs_input'
              ? '草稿待补充' : null;
            return <li key={index} className="agent-tool" data-event="step">
            <span className="agent-tool-name">{entry.data.tool}</span>
            <span className="agent-tool-detail">{scalarText(entry.data.result_summary) || '—'}</span>
            <span className={`agent-tool-status ${(!inspection && (entry.data.tool === 'annotations.prepare_batch'
              ? entry.data.status === 'ok' && parseBatchSummary(entry.data.result_summary)?.status === 'ready'
              : entry.data.status === 'ok' && (!['preprocess.run_batch','preprocess.draft_execute'].includes(entry.data.tool) || preprocessingBusiness(entry.data.result_summary).complete))) ? 'is-ok' : 'is-other'}`}>
              {inspection ?? (entry.data.tool === 'annotations.prepare_batch'
                ? entry.data.status === 'ok' && entry.data.result_summary.status === 'accepted' ? '已受理' : batchBusinessLabel(entry.data.status === 'ok' ? parseBatchSummary(entry.data.result_summary) : null)
                : entry.data.status === 'ok' ? ['preprocess.run_batch','preprocess.draft_execute'].includes(entry.data.tool)?preprocessingBusiness(entry.data.result_summary).label:'✓ 完成' : entry.data.status)}
            </span>
          </li>})}</ol>
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
    {pickerError && <p role="alert" className="agent-error">{pickerError}</p>}
    </div>
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}>
      <label htmlFor="assistant-message">对话</label>
      <MessageInput id="assistant-message" session={session} inputRef={input}/>
      <div className="assistant-compose-actions">
      <button type="button" disabled={!enabled} onClick={()=>void pickPath(true)}>选择目录</button>
      <button type="button" disabled={!enabled} onClick={()=>void pickPath(false)}>选择文件</button>
      {state.busy?<button type="button" className="agent-stop" disabled={!enabled||session.stopping} onClick={()=>void session.stop()}>{session.stopping?'正在停止…':'停止'}</button>
        :<button type="submit" disabled={!session.canSend || !content.trim()}>发送</button>}
      </div>
    </form>
  </section>;
}
