import { useEffect, useState } from 'react';
import { agent, type ExperimentTask } from './api';
import ExperimentResults from './ExperimentResults';

const phases = [['checking','检查输入'],['preparing','准备数据'],['training','预处理与训练'],['testing','测试评价'],['reporting','生成报告与核验']] as const;
const labels = {queued:'等待执行',running:'正在执行',succeeded:'已完成',failed:'执行失败',cancelled:'已取消'};
const terminal = new Set(['succeeded','failed','cancelled']);

export default function ExperimentTaskCard({taskId,sessionId,enabled,onInfer}: {taskId:string;sessionId:string;enabled:boolean;onInfer?:(id:string)=>void}) {
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
    {task?.status==='running'&&<p>当前阶段尚未结束，未提供内部百分比。</p>}
    {task?.cancel_requested&&task.status!=='cancelled'&&!terminal.has(task.status)&&<p role="status">已请求取消，等待下一个安全阶段边界；当前算子可能仍在运行。</p>}
    {task?.status==='succeeded'&&<ExperimentResults sessionId={sessionId} taskId={taskId} enabled={enabled} onInfer={onInfer}/>}
    {task?.status==='failed'&&<p role="alert">失败阶段：{phases.find(([id])=>id===task.failed_phase)?.[1]??'提交检查'}；{task.error}。已完成产物保留。</p>}
    {task?.status==='cancelled'&&<p>实验已取消，已完成产物保留；未宣称完成后续阶段。</p>}
    <p>停止对话不会取消此实验。已完成实验自动归档；应用退出时未完成的实验不自动续训。</p>
    {!enabled&&<p>当前引擎不可用，任务状态未核验。</p>}
    {error&&<p role="alert">{error}</p>}
    {error&&<button disabled={!enabled} onClick={()=>setRefresh(x=>x+1)}>重新查询</button>}
    {task&&!terminal.has(task.status)&&<button disabled={!enabled||canceling||task.cancel_requested} onClick={async()=>{
      setCanceling(true);
      try {await agent.experimentTask(sessionId,taskId,'cancel');setRefresh(x=>x+1);}
      catch {setError('取消请求未能确认，请重新查询任务状态。');}
      finally {setCanceling(false);}
    }}>{canceling?'正在请求取消':'取消实验'}</button>}
  </section>;
}
