import { useEffect, useRef, useState } from 'react';
import { agent, type AnnotationTask, type BatchMember, type BatchResult, type TaskCard } from './api.ts';
import { requestError } from './sse.ts';

export function checkedTask(view: AnnotationTask, card: TaskCard, bootId?: string|null): AnnotationTask {
  const counts = view.counts;
  const keys = ['pending','processing','ready','failed','conflict','not_attempted'] as const;
  if (view.task_id !== card.taskId || view.session_id !== card.sessionId || bootId && view.owner_boot_id !== bootId
      || !['queued','running','completed','canceled','failed'].includes(view.task_status)
      || !Number.isInteger(view.snapshot_version) || view.snapshot_version < 1
      || !Number.isInteger(view.total) || view.total < 1 || !counts
      || keys.some(k => !Number.isInteger(counts[k]) || counts[k] < 0)
      || keys.reduce((n,k)=>n+counts[k],0) !== view.total) throw new Error('任务状态或归属无法核验');
  return view;
}

function batchResult(view:AnnotationTask, items:NonNullable<AnnotationTask['items']>):BatchResult {
  const members:BatchMember[] = items.map(item=>({cubeId:item.cube_id,displayName:item.display_name,
    status:item.status==='pending'||item.status==='processing'?'not_attempted':item.status,action:item.action,
    superpixelCount:item.superpixel_count,errorCode:item.error_code,detail:item.detail}));
  const readyMembers=members.filter(item=>item.status==='ready');
  return {status:readyMembers.length===view.total?'ready':readyMembers.length?'partial':'failed',datasetVersionId:null,
    authorizationId:view.authorization_id,
    batchRef:null,retryOf:null,memberCount:view.total,requestedCount:view.total,readyCount:readyMembers.length,
    failedCount:view.counts.failed,conflictCount:view.counts.conflict,
    notAttemptedCount:view.counts.not_attempted+view.counts.pending+view.counts.processing,
    autoOpen:false,openCubeId:readyMembers[0]?.cubeId??null,members,readyMembers,detail:null,elapsedMs:0};
}

export default function AsyncPrepareCard({card,bootId,disabled,actionsDisabled=false,onOpen,onRetry}: {
  card:TaskCard;bootId?:string|null;disabled:boolean;actionsDisabled?:boolean;
  onOpen(result:BatchResult):void;onRetry(taskId:string,requestId:string,mode:'failed'|'remaining'):void;
}) {
  const [view,setView]=useState<AnnotationTask|null>(null), [error,setError]=useState('');
  const [acting,setActing]=useState(false);
  const latest=useRef({onOpen,onRetry});latest.current={onOpen,onRetry};
  const alive=useRef(true);
  const actionEpoch=useRef(0);
  useEffect(()=>{
    alive.current=!disabled;actionEpoch.current++;setActing(false);let canceled=false;let timer:ReturnType<typeof setTimeout>|undefined;
    const poll=async()=>{
      try {
        const next=checkedTask(await agent.annotationTask(card.sessionId,card.taskId),card,bootId);
        if(canceled)return;
        setView(old=>old&&old.snapshot_version>next.snapshot_version?old:next);setError('');
        if(['queued','running'].includes(next.task_status))timer=setTimeout(()=>void poll(),1000);
      } catch(e) {if(!canceled){
        setError(requestError(e));
        const code=e&&typeof e==='object'?String((e as {error?:unknown;code?:unknown}).error??(e as {code?:unknown}).code??''):'';
        if(!['TASK_EXPIRED','TASK_NOT_FOUND','SESSION_ARCHIVED'].includes(code)
            && !(e instanceof Error&&e.message==='任务状态或归属无法核验'))timer=setTimeout(()=>void poll(),3000);
      }}
    };
    if(!disabled)void poll();
    return()=>{canceled=true;alive.current=false;actionEpoch.current++;if(timer)clearTimeout(timer);};
  },[card.taskId,card.sessionId,card.generation,bootId,disabled]);
  const act=async(action:'open'|'cancel'|'failed'|'remaining')=>{
    if(disabled||actionsDisabled||acting||!view)return;
    const ticket=actionEpoch.current;
    const current=()=>alive.current&&ticket===actionEpoch.current;
    setActing(true);setError('');
    try {
      if(action==='cancel'){
        const next=checkedTask(await agent.annotationTask(card.sessionId,card.taskId,'cancel'),card,bootId);
        if(current())setView(old=>old&&old.snapshot_version>next.snapshot_version?old:next);
      }
      else if(action==='failed'||action==='remaining') {
        const requestId=crypto.randomUUID();
        const result=await agent.retryTask(card.sessionId,card.taskId,action,requestId);
        if(current())latest.current.onRetry(result.task_id,requestId,action);
      } else {
        const snapshot=checkedTask(await agent.annotationTask(card.sessionId,card.taskId),card,bootId);
        const items:NonNullable<AnnotationTask['items']>=[];let after:number|null=0;
        while(after!==null) {
          const page=checkedTask(await agent.taskItems(card.sessionId,card.taskId,after,snapshot.snapshot_version),card,bootId);
          if(!current())return;
          if(!page.items||page.items.some(i=>!['pending','processing','ready','failed','conflict','not_attempted'].includes(i.status)))throw new Error('任务明细无法核验');
          items.push(...page.items);after=page.next_after??null;
        }
        if(items.length!==snapshot.total||new Set(items.map(i=>i.cube_id)).size!==items.length)throw new Error('任务成员不完整');
        const result=batchResult(snapshot,items);
        if(!result.readyMembers.length)throw new Error('当前没有可用分割');
        if(current())latest.current.onOpen(result);
      }
    } catch(e){if(current())setError(requestError(e));}
    finally {if(current())setActing(false);}
  };
  const terminal=view&&['completed','canceled','failed'].includes(view.task_status);
  const labels={queued:'排队中',running:view?.phase==='verifying'?'正在核验数据':'正在生成超像素',completed:'处理结束',canceled:'已取消',failed:'处理失败'};
  return <section className="batch-prepare-card" aria-label="超像素后台任务">
    <strong>{view?.cancel_requested&&!terminal?'正在取消（当前项完成后停止）':view?labels[view.task_status]:'正在查询任务'}</strong>
    {view&&<><p>分割就绪 {view.counts.ready}/{view.total} · 处理中 {view.counts.processing} · 失败 {view.counts.failed} · 冲突 {view.counts.conflict} · 未执行 {view.counts.not_attempted}</p>
      <progress max={view.total} value={view.counts.ready+view.counts.failed+view.counts.conflict+view.counts.not_attempted}/>
      <p>分割就绪后由人工点选赋类，尚未保存标注。</p>
      <button disabled={disabled||actionsDisabled||acting||!view.counts.ready} onClick={()=>void act('open')}>进入标注</button>
      <button disabled={disabled||actionsDisabled||acting||!view.cancelable||view.cancel_requested} onClick={()=>void act('cancel')}>取消剩余任务</button>
      <button disabled={disabled||actionsDisabled||acting||!terminal||!view.counts.failed} onClick={()=>void act('failed')}>重试失败项</button>
      <button disabled={disabled||actionsDisabled||acting||!terminal||!view.counts.not_attempted} onClick={()=>void act('remaining')}>继续未完成</button>
      {view.error&&<p role="alert">{view.error}</p>}</>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
