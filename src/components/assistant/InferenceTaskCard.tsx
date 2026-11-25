import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { InferenceFileTable, InferenceSummary, type OpenInferenceView } from './InferenceResultsView';
import { save } from '@tauri-apps/plugin-dialog';
import { agent, type InferenceStatus, type InferenceResult } from './api';

const labels:Record<string,string>={queued:'等待执行',running:'执行中',succeeded:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
const phases:Record<string,string>={checking:'核对输入与归档模型',preparing:'准备前景与输入预览',predicting:'预处理与分类预测',reporting:'保存结果与来源核验'};
const terminal=new Set(['succeeded','failed','cancelled','interrupted']);
export default function InferenceTaskCard({sessionId,modelId,runId,enabled,onView}:{sessionId:string;modelId:string;runId:string;enabled:boolean;onView?:OpenInferenceView}) {
  const [status,setStatus]=useState<InferenceStatus|null>(null),[result,setResult]=useState<InferenceResult|null>(null);
  const [error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  const [saving,setSaving]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{
    if(!enabled)return;
    let active=true;let timer:ReturnType<typeof setTimeout>;
    setError('');
    const poll=async()=>{
      try {
        const value=await agent.inferenceStatus(sessionId,modelId,runId);
        if(!active)return;
        if(value.run_id!==runId||value.model_id!==modelId)throw new Error('任务身份不一致');
        setStatus(value);
        if(value.status==='succeeded') {
          const saved=await agent.inferenceResult(sessionId,modelId,runId);
          if(active){if(saved.run_id!==runId||saved.model_id!==modelId)throw new Error('结果身份不一致');setResult(saved);}
        } else if(!terminal.has(value.status))timer=setTimeout(()=>void poll(),750);
      } catch {if(active)setError('推理任务或结果读取失败，请重试；不会重复提交。');}
    };
    void poll();return()=>{active=false;clearTimeout(timer);};
  },[sessionId,modelId,runId,enabled,refresh]);
  async function openReport(){
    setSaving(true);setMessage('正在准备对比报告。历史结果首次打开需要复制配套图。');
    try{
      const prepared=await agent.prepareInferenceReport(sessionId,modelId,runId);
      if(!prepared.ready)throw new Error('报告尚未就绪');
      await invoke('open_inference_report',{modelId,runId});
      setMessage('');
    }catch(error){
      setMessage(typeof error==='string'?error:error&&typeof error==='object'&&'detail' in error
        ?String(error.detail):'无法生成或打开对比报告。');
    }finally{setSaving(false);}
  }
  async function exportResults(){
    setSaving(true);setMessage('');
    try{
      const path=await save({title:'保存推理结果包',defaultPath:`inference-${runId.slice(0,8)}.zip`,filters:[{name:'ZIP',extensions:['zip']}]});
      if(!path)return;
      await agent.inferenceExport(sessionId,modelId,runId,path);
      setMessage('已保存推理结果包。');
    }catch(e){setMessage(e&&typeof e==='object'&&'detail' in e?String(e.detail):'导出失败，请选择新的文件名后重试。');}
    finally{setSaving(false);}
  }
  return <section className="experiment-task-card" aria-label="推理任务">
    <h3>分类推理 · {status?labels[status.status]:'正在查询'}</h3>
    <p>模型 {modelId.slice(0,8)} · 任务 {runId.slice(0,8)} · 已用时 {Math.floor(status?.elapsed_seconds??0)} 秒</p>
    {status&&<p>{phases[status.phase]??status.phase}；{status.phase==='checking'?'已核对':'已完成'} {status.phase==='checking'?(status.checked_files??0):status.completed_files}/{status.total_files} 个文件。
      {status.total_rows>0&&`当前文件已处理 ${status.completed_rows}/${status.total_rows} ${status.kind==='envi'?'图像行':'条光谱'}。`}</p>}
    {status?.cancel_requested&&!terminal.has(status.status)&&<p role="status">已请求取消，等待当前数据批次结束。</p>}
    {status?.error&&<p role="alert">{status.error}。已完成产物保留；不将部分结果报告为完整成功。</p>}
    {error&&<p role="alert">{error}<button disabled={!enabled} onClick={()=>setRefresh(x=>x+1)}>重新查询</button></p>}
    {status?.can_cancel&&!terminal.has(status.status)&&<button disabled={!enabled||status.cancel_requested} onClick={async()=>{
      try{setStatus(await agent.cancelInference(sessionId,modelId,runId));}catch{setError('取消请求未确认，请重新查询。');}
    }}>取消推理</button>}
    {result&&<>
      {Boolean(result.excluded_files?.length)&&<details><summary>按范围排除 {result.excluded_files?.length} 幅原图</summary>
        <ul>{result.excluded_files?.map((item,index)=><li key={index}>{item.file} · {item.reason}</li>)}</ul>
      </details>}
      <p>{result.note}</p>
      <p>评价单位：{result.evaluation_unit==='center_pixel'?'中心像元':'光谱样本'}；模型校验值：{result.model_sha256}</p>
      <InferenceSummary result={result}/>
      <InferenceFileTable result={result} rows={result.files.slice(0,10)}
        onSelect={onView&&result.kind==='envi'?row=>onView(result,row.file_index):undefined}/>
      <div className="work-actions">
        {onView&&<button onClick={()=>onView(result)}>查看全部文件（{result.files.length}）</button>}
        {result.kind==='envi'&&<button disabled={!enabled||saving} onClick={()=>void openReport()}>打开对比报告（HTML）</button>}
      </div>
      <button disabled={!enabled||saving} onClick={()=>void exportResults()}>导出推理结果包</button>
      <p>{result.kind==='npz'?'包含逐光谱分类CSV和含原始PLS响应的NPZ。':'包含原分辨率分类 NPZ 和 PNG 预览。已生成的对比报告和配套图也会打包，解压后可双击 report.html 查看。'}</p>
    </>}
    {message&&<p role="status">{message}</p>}
    <p>停止对话不会取消推理。记录与结果跨重启保留；运行中退出后不自动续跑。</p>
  </section>;
}

export function InferenceHistory({sessionId,modelId,enabled,onView}:{sessionId:string;modelId:string;enabled:boolean;onView?:OpenInferenceView}) {
  const [rows,setRows]=useState<InferenceStatus[]>([]),[open,setOpen]=useState(false),[selected,setSelected]=useState(''),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  const [selecting,setSelecting]=useState(false);
  async function focus(runId:string){
    setSelecting(true);setError('');
    try{
      const state=await agent.focusInference(sessionId,modelId,runId);
      if(state.run_id!==runId||state.model_id!==modelId)throw new Error('推理记录身份不一致');
      setSelected(runId);
    }catch{setError('无法选中该次推理，请重试。');}
    finally{setSelecting(false);}
  }
  useEffect(()=>{
    let active=true;
    if(open&&enabled){setError('');void agent.inferenceHistory(sessionId,modelId).then(value=>{if(active)setRows(value.items);}).catch(()=>{if(active)setError('推理历史读取失败，请刷新。');});}
    return()=>{active=false;};
  },[open,sessionId,modelId,enabled,refresh]);
  return <details open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>该模型的推理记录（最近20条）</summary>
    {open&&<><button disabled={!enabled} onClick={()=>setRefresh(x=>x+1)}>刷新推理记录</button>{error&&<p role="alert">{error}</p>}
      {!rows.length&&<p>暂无推理记录。</p>}{rows.map(row=><button key={row.run_id} disabled={!enabled||selecting}
        aria-pressed={selected===row.run_id} onClick={()=>void focus(row.run_id)}>{row.run_id.slice(0,8)} · {labels[row.status]}</button>)}
      {selected&&<InferenceTaskCard key={selected} sessionId={sessionId} modelId={modelId} runId={selected} enabled={enabled} onView={onView}/>}</>}
  </details>;
}
