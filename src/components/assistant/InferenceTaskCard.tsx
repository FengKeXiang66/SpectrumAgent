import { useEffect, useState } from 'react';
import { save } from '@tauri-apps/plugin-dialog';
import { agent, type InferenceStatus, type InferenceResult } from './api';

const labels:Record<string,string>={queued:'等待执行',running:'执行中',succeeded:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
const phases:Record<string,string>={checking:'核对输入与归档模型',preparing:'准备前景与输入预览',predicting:'预处理与分类预测',reporting:'保存结果与来源核验'};
const terminal=new Set(['succeeded','failed','cancelled','interrupted']);
export default function InferenceTaskCard({sessionId,modelId,runId,enabled}:{sessionId:string;modelId:string;runId:string;enabled:boolean}) {
  const [status,setStatus]=useState<InferenceStatus|null>(null),[result,setResult]=useState<InferenceResult|null>(null);
  const [error,setError]=useState(''),[refresh,setRefresh]=useState(0),[file,setFile]=useState(0),[image,setImage]=useState(''),[inputImage,setInputImage]=useState('');
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
  useEffect(()=>{
    let active=true;setImage('');setInputImage('');
    if(enabled&&result?.kind==='envi')void agent.inferencePlot(sessionId,modelId,runId,file)
      .then(value=>{if(active)setImage('data:image/png;base64,'+value.png_base64);})
      .catch(()=>{if(active)setError('分类预览读取失败或校验未通过，请重新查询。');});
    if(enabled&&result?.kind==='envi'&&result.files.find(row=>row.file_index===file)?.preview_wavelengths_nm)void agent.inferencePlot(sessionId,modelId,runId,file,'input')
      .then(value=>{if(active)setInputImage('data:image/png;base64,'+value.png_base64);})
      .catch(()=>{if(active)setError('输入预览读取失败或校验未通过，请重新查询。');});
    return()=>{active=false;};
  },[sessionId,modelId,runId,enabled,result,file]);
  async function exportResults(){
    setSaving(true);setMessage('');
    try{
      const path=await save({title:'保存推理结果包',defaultPath:`inference-${runId.slice(0,8)}.zip`,filters:[{name:'ZIP',extensions:['zip']}]});
      if(!path)return;
      await agent.inferenceExport(sessionId,modelId,runId,path);
      setMessage('已保存推理结果、配置和来源记录；不包含模型或原始输入文件。');
    }catch(e){setMessage(e&&typeof e==='object'&&'detail' in e?String(e.detail):'导出失败，请选择新的文件名后重试。');}
    finally{setSaving(false);}
  }
  const classes=result?Object.entries(result.classes).sort((a,b)=>Number(a[0])-Number(b[0])):[];
  const selected=result?.files.find(row=>row.file_index===file);
  const exclusions:Record<string,string>={brightness:'亮度阈值排除',side_edges:'左右边缘屏蔽',quality_or_neighborhood:'质量或邻域无效',image_boundary:'图像外边界'};
  return <section className="experiment-task-card" aria-label="推理任务">
    <h3>分类推理 · {status?labels[status.status]:'正在查询'}</h3>
    <p>模型 {modelId.slice(0,8)} · 任务 {runId.slice(0,8)} · 已用时 {Math.floor(status?.elapsed_seconds??0)} 秒</p>
    {status&&<p>{phases[status.phase]??status.phase}；已完成 {status.completed_files}/{status.total_files} 个文件。
      {status.total_rows>0&&`当前文件已处理 ${status.completed_rows}/${status.total_rows} ${status.kind==='envi'?'图像行':'条光谱'}。`}</p>}
    {status?.cancel_requested&&!terminal.has(status.status)&&<p role="status">已请求取消，等待当前数据批次结束。</p>}
    {status?.error&&<p role="alert">{status.error}。已完成产物保留；不将部分结果报告为完整成功。</p>}
    {error&&<p role="alert">{error}<button disabled={!enabled} onClick={()=>setRefresh(x=>x+1)}>重新查询</button></p>}
    {status?.can_cancel&&!terminal.has(status.status)&&<button disabled={!enabled||status.cancel_requested} onClick={async()=>{
      try{setStatus(await agent.cancelInference(sessionId,modelId,runId));}catch{setError('取消请求未确认，请重新查询。');}
    }}>取消推理</button>}
    {result&&<>
      <p>{result.note}</p>
      <p>评价单位：{result.evaluation_unit==='center_pixel'?'中心像元':'光谱样本'}；模型校验值：{result.model_sha256}</p>
      <div className="experiment-table"><table><caption>按文件统计的分类数量</caption><thead><tr><th>输入文件</th><th>总数</th><th>已分类</th><th>未分类</th>{classes.map(([id,name])=><th key={id}>{name}</th>)}</tr></thead><tbody>
        {result.files.map(row=><tr key={row.file_index}><th>{row.name}</th><td>{row.total}</td><td>{row.classified}</td><td>{row.excluded}</td>{classes.map(([id])=><td key={id}>{row.counts[id]??0}</td>)}</tr>)}
      </tbody></table></div>
      {result.kind==='envi'&&<>
        <label>分类图：<select value={file} onChange={e=>setFile(Number(e.target.value))}>{result.files.map(row=><option key={row.file_index} value={row.file_index}>{row.name}</option>)}</select></label>
        <div className="inference-image-pair">
          {inputImage&&<figure><figcaption>输入伪彩（非真值标注）</figcaption><img className="experiment-plot" src={inputImage} alt="输入原图的伪彩预览"/></figure>}
          <figure><figcaption>分类结果</figcaption>{image?<img className="experiment-plot" src={image} alt="推理分类预览图"/>:<p>正在读取分类预览…</p>}</figure>
        </div>
        {selected?.preview_wavelengths_nm&&<p>伪彩R/G/B实际通道：{selected.preview_wavelengths_nm.map(value=>value.toFixed(2)).join('／')} nm；显示拉伸不参与分类。</p>}
        {selected?.edges&&<p>原图尺寸：{selected.shape?.join(' × ')}；实际左／右屏蔽：{selected.edges.left}／{selected.edges.right} 列。</p>}
        {selected?.exclusion_counts&&<div className="experiment-table"><table><caption>未分类像元原因（互斥计数，合计等于未分类数）</caption><tbody>{Object.entries(selected.exclusion_counts).map(([key,count])=><tr key={key}><th>{exclusions[key]??key}</th><td>{count}</td></tr>)}</tbody></table></div>}
        <p>亮度与边缘前景规则：{result.foreground?.mode==='brightness_edges'?'已按确认方案启用':'未启用，按质量条件处理'}。</p>
        <p>{classes.map(([id,name])=><span key={id} className="inference-legend"><span style={{backgroundColor:result.colors[id]}}/> {id}={name} </span>)}<span className="inference-legend"><span style={{backgroundColor:'#e0e0e0'}}/> 未分类</span></p>
        <p>预览最长边不超过1200像素；NPZ保存原分辨率的prediction_map、valid_mask及exclusion_reason（0已分类、1亮度、2侧边、3质量或邻域、4图像边界）。请结合掩膜读取类别。</p>
      </>}
      <button disabled={!enabled||saving} onClick={()=>void exportResults()}>导出推理结果包</button>
      <p>{result.kind==='npz'?'包含逐光谱分类CSV和含原始PLS响应的NPZ。':'包含原分辨率分类NPZ、有效像元掩膜和PNG预览。'}单次导出上限64MiB。</p>
    </>}
    {message&&<p role="status">{message}</p>}
    <p>停止对话不会取消推理。记录与结果跨重启保留；运行中退出后不自动续跑。</p>
  </section>;
}

export function InferenceHistory({sessionId,modelId,enabled}:{sessionId:string;modelId:string;enabled:boolean}) {
  const [rows,setRows]=useState<InferenceStatus[]>([]),[open,setOpen]=useState(false),[selected,setSelected]=useState(''),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  useEffect(()=>{
    let active=true;
    if(open&&enabled){setError('');void agent.inferenceHistory(sessionId,modelId).then(value=>{if(active)setRows(value.items);}).catch(()=>{if(active)setError('推理历史读取失败，请刷新。');});}
    return()=>{active=false;};
  },[open,sessionId,modelId,enabled,refresh]);
  return <details open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>该模型的推理记录（最近20条）</summary>
    {open&&<><button disabled={!enabled} onClick={()=>setRefresh(x=>x+1)}>刷新推理记录</button>{error&&<p role="alert">{error}</p>}
      {!rows.length&&<p>暂无推理记录。</p>}{rows.map(row=><button key={row.run_id} disabled={!enabled} onClick={()=>setSelected(row.run_id)}>{row.run_id.slice(0,8)} · {labels[row.status]}</button>)}
      {selected&&<InferenceTaskCard key={selected} sessionId={sessionId} modelId={modelId} runId={selected} enabled={enabled}/>}</>}
  </details>;
}
