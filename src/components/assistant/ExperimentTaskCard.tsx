import { useEffect, useState } from 'react';
import { agent, type ExperimentTask } from './api';
import ExperimentResults from './ExperimentResults';
import type { OpenInferenceView } from './InferenceResultsView';

const phases = [['checking','检查输入'],['preparing','准备数据'],['training','预处理与训练'],['testing','测试评价'],['reporting','生成报告与核验']] as const;
const labels = {queued:'等待执行',running:'正在执行',succeeded:'已完成',failed:'执行失败',cancelled:'已取消',interrupted:'已中断'};
const terminal = new Set(['succeeded','failed','cancelled','interrupted']);

export default function ExperimentTaskCard({taskId,sessionId,enabled,onInfer,onHistory,onCommand,onInferenceView}: {
  taskId:string;sessionId:string;enabled:boolean;onInfer?:(id:string)=>void;onHistory:()=>void;onCommand?:(content:string)=>void;onInferenceView?:OpenInferenceView;
}) {
  const [task,setTask] = useState<ExperimentTask|null>(null);
  const [error,setError] = useState('');
  const [canceling,setCanceling] = useState(false);
  const [refresh,setRefresh] = useState(0);
  useEffect(()=>{
    if(!enabled)return;
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>;
    setError('');
    const poll=async()=>{
      try {
        const value=await agent.experimentTask(sessionId,taskId);
        if(disposed)return;
        if(value.task_id!==taskId||value.session_id!==sessionId||!Object.hasOwn(labels,value.status))throw new Error('任务身份不一致');
        setTask(value);
        if(!terminal.has(value.status))timer=setTimeout(()=>void poll(),750);
      } catch { if(!disposed)setError('无法查询任务，当前状态未知。请重试；不会重新提交实验。'); }
    };
    void poll();
    return ()=>{disposed=true;clearTimeout(timer);};
  },[taskId,sessionId,enabled,refresh]);
  return <section className="experiment-task-card" aria-label="实验任务">
    <h3>训练测试实验 · {task?labels[task.status]:'正在查询'}</h3>
    <p>任务 {taskId.slice(0,8)} · 已用时 {Math.floor(task?.elapsed_seconds??0)} 秒 · 已完成 {task?.completed_phases.length??0}/5 个阶段</p>
    <ol>{phases.map(([id,label])=><li key={id}>
      {task?.completed_phases.includes(id)?'✓ ':task?.phase===id&&!terminal.has(task.status)?'● ':'○ '}{label}
      {task?.phase===id&&task.status==='running'?'（进行中）':''}
    </li>)}</ol>
    {task?.status==='running'&&(task.subprogress ? <p role="status">
      {task.subprogress.role==='train'?'训练集':'测试集'} · 第 {task.subprogress.file_index}／{task.subprogress.file_total} 幅
      {task.subprogress.rows_total!=null&&` · 已处理 ${task.subprogress.rows_done}／${task.subprogress.rows_total} 行`}
    </p> : <p>当前阶段正在处理，请稍候。</p>)}
    {task?.cancel_requested&&!terminal.has(task.status)&&<p role="status">已请求取消，等待当前处理块或阶段到达检查点。</p>}
    {task?.status==='succeeded'&&<ExperimentResults sessionId={sessionId} taskId={taskId} enabled={enabled} onInfer={onInfer} onCommand={onCommand} onInferenceView={onInferenceView}/>}
    {task?.status==='failed'&&<p role="alert">失败阶段：{phases.find(([id])=>id===task.failed_phase)?.[1]??'提交检查'}；{task.error}。已完成产物保留。</p>}
    {task?.status==='cancelled'&&<p>实验已取消，已完成产物保留；未宣称完成后续阶段。</p>}
    {task?.status==='interrupted'&&<p>引擎退出时实验已中断。</p>}
    <p>停止对话不会取消此实验。已完成实验自动归档；应用退出时未完成的实验不自动续训。</p>
    {!enabled&&<p>当前引擎不可用，任务状态未核验。</p>}
    {error&&<p role="alert">{error}</p>}
    {error&&<button disabled={!enabled} onClick={()=>setRefresh(x=>x+1)}>重新查询</button>}
    <button disabled={!enabled} onClick={onHistory}>查看历史与模型</button>
    {task&&!terminal.has(task.status)&&<button disabled={!enabled||canceling||task.cancel_requested} onClick={async()=>{
      setCanceling(true);
      try {await agent.experimentTask(sessionId,taskId,'cancel');setRefresh(x=>x+1);}
      catch {setError('取消请求未能确认，请重新查询任务状态。');}
      finally {setCanceling(false);}
    }}>{canceling?'正在请求取消':'取消实验'}</button>}
  </section>;
}
