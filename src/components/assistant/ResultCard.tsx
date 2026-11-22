import { useEffect, useState, useRef, type ReactNode } from 'react';
import { preprocessing } from '../preprocess/api';
import type { BinaryArtifact } from '../preprocess/types';
import type { Preview } from '../datasets/types';
import { applyLut, makeLut, type LutParameters } from '../annotation/display/display';
import CompareChart from '../preprocess/CompareChart';
import { datasets } from '../datasets/api';
import { annotations } from '../annotation/api';
import { SpectrumReadout } from '../annotation/display/DisplayToolbar';
import SpectrumReview from '../annotation/SpectrumReview.tsx';
import { modeling, mapSource } from '../modeling/api';
import CoefficientChart from '../modeling/CoefficientChart';
import S08 from '../../screens/S08';
import SettingsPanel from '../settings/SettingsPanel';
import ProjectPathsPanel from '../settings/ProjectPathsPanel';
import SmokePanel from '../settings/SmokePanel';
import type { Scalars } from './sse';

// Values are obtained through existing local IPC clients. None of these
// artifacts or arrays are appended to the model's conversation history.
function ReadLocal({ identity, read }: { identity:string; read:()=>Promise<ReactNode> }) {
  const [content,setContent]=useState<ReactNode>(null),[error,setError]=useState('');
  useEffect(()=>{
    let active=true;setContent(null);setError('');
    void read().then(value=>{if(active)setContent(value);}).catch(e=>{
      if(active)setError(e instanceof Error?e.message:typeof e==='object'&&e!==null&&'detail' in e?String(e.detail):'本地产物读取失败');
    });
    return()=>{active=false;};
  },[identity]);
  return error?<p role="alert">{error}</p>:content??<p role="status">正在读取本地结果…</p>;
}

function download(item:BinaryArtifact) {
  const bytes=Uint8Array.from(atob(item.body_base64),c=>c.charCodeAt(0));
  const href=URL.createObjectURL(new Blob([bytes],{type:item.content_type}));
  const a=document.createElement('a');a.href=href;a.download=item.filename;a.click();
  setTimeout(()=>URL.revokeObjectURL(href),1000);
}

function ImageView({preview,zoom,lut}:{preview:Preview;zoom:number;lut?:LutParameters}) {
  const canvas=useRef<HTMLCanvasElement>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    let active=true;
    const bytes=Uint8Array.from(atob(preview.png_base64),c=>c.charCodeAt(0));
    void createImageBitmap(new Blob([bytes],{type:'image/png'})).then(bitmap=>{
      const ctx=canvas.current?.getContext('2d');
      if(active&&ctx){ctx.drawImage(bitmap,0,0);if(lut){const data=ctx.getImageData(0,0,preview.width,preview.height);
        data.data.set(applyLut(data.data,makeLut(lut)));ctx.putImageData(data,0,0);}}
      bitmap.close();
    }).catch(()=>{if(active)setError('本地图像加载失败');});
    return()=>{active=false;};
  },[preview,lut?.black,lut?.white,lut?.gamma]);
  return <>{error&&<p role="alert">{error}</p>}<canvas ref={canvas} width={preview.width} height={preview.height}
    style={{width:preview.width*zoom,maxWidth:'none'}} aria-label="本地数据图像"/></>;
}

function RunReport({ runId }: {runId:string}) {
  return <ReadLocal identity={runId} read={async()=>{
    const run=await preprocessing.getRun(runId);
    if(run.status!=='succeeded')return <p>运行 {runId.slice(0,8)}：{run.status} · {run.error?.detail}</p>;
    const [report,record]=await Promise.all([preprocessing.getArtifact(runId,'report'),datasets.get(run.cube_id)]);
    const projects=await annotations.projects();
    const trees=await Promise.all(projects.map(project=>annotations.labels(project.id)));
    const labels=trees.flatMap(tree=>tree.flatMap(schema=>schema.labels));
    return <section aria-label="预处理本地结果">
      <p>{record.display_name??record.dataset.name} · 运行 {runId.slice(0,8)} · {run.status}</p>
      <p>Fisher：{run.metrics?.fisher??'不适用'}；SNR 中位数：{run.metrics?.snr.median??'不适用'}</p>
      <CompareChart report={report} labels={labels} inputBands={record.dataset.shape[2]}/>
      <details><summary>指标与比较边界</summary><pre>{JSON.stringify(report.metrics,null,2)}</pre></details>
      <button onClick={()=>download({content_type:'application/octet-stream',filename:`report-${runId.slice(0,8)}.json`,body_base64:btoa(unescape(encodeURIComponent(JSON.stringify(report,null,2))))})}>下载报告</button>
    </section>;
  }}/>;
}

function ExportFiles({runId}:{runId:string}) {
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  async function saveFile(filename:'processed_cube.img'|'processed_cube.hdr'|'export_manifest.json') {
    setBusy(true);setMessage('');
    try {
      const {save}=await import('@tauri-apps/plugin-dialog');
      const path=await save({defaultPath:filename,title:'保存预处理导出文件'});
      if(!path)return;
      if(!preprocessing.downloadExport)throw new Error('当前客户端尚未支持导出下载');
      const result=await preprocessing.downloadExport(runId,filename,path);
      setMessage(result.saved?`已保存 ${filename}，${result.bytes} 字节。`:'文件未保存');
    } catch(error){setMessage(error instanceof Error?error.message:'导出下载失败，服务器产物保留。');}
    finally{setBusy(false);}
  }
  return <section aria-label="导出下载"><p>ENVI 图像与头文件需保存在同一目录。</p>
    {(['processed_cube.img','processed_cube.hdr','export_manifest.json'] as const).map(name=><button key={name} disabled={busy} onClick={()=>void saveFile(name)}>保存 {name}</button>)}
    {message&&<p role="status">{message}</p>}</section>;
}

function AnnotationReview({cubeId}:{cubeId:string}) {
  const [revision,setRevision]=useState(0),[error,setError]=useState('');
  return <>{error&&<p role="alert">{error}</p>}<ReadLocal identity={cubeId+':'+revision} read={async()=>{
    const [record,working,quality]=await Promise.all([datasets.get(cubeId),annotations.working(cubeId),annotations.validate(cubeId)]);
    const tree=await annotations.labels(working.project_id);
    return <SpectrumReview quality={quality} labels={tree.flatMap(row=>row.labels)} bands={record.dataset.shape[2]}
      wavelengths={record.dataset.wavelengths} disabled={false} onRefresh={()=>setRevision(v=>v+1)}
      onBlockErase={block=>{void annotations.regions(cubeId,{superpixels:[block]},'erase').then(()=>setRevision(v=>v+1)).catch(()=>setError('剔除失败，请核对当前标注状态。'));}}/>;
  }}/></>;
}

export function hasLocalResult(summary:Scalars):boolean {
  return typeof summary.view_kind==='string';
}

export default function ResultCard({ summary }: {summary:Scalars}) {
  const kind=String(summary.view_kind),runId=String(summary.run_id??''),cubeId=String(summary.cube_id??'');
  const [hidden,setHidden]=useState(false);
  if(hidden)return null;
  const identity=JSON.stringify(summary);
  let content:ReactNode;
  if(kind==='preprocess_batch') {
    const rows=Array.from({length:Number(summary.count??0)},(_,i)=>({
      id:String(summary[`item_${i+1}_run_id`]??''),status:String(summary[`item_${i+1}_status`]??'unknown'),
      name:String(summary[`item_${i+1}_display_name`]??summary[`item_${i+1}_cube_id`]??`成员 ${i+1}`),
      error:String(summary[`item_${i+1}_error_code`]??'')}));
    content=<><p>本页 {rows.length} 项，共 {String(summary.total)} 项{summary.truncated?'；仍有下一页':''}</p>
      {rows.map((row,i)=><details key={row.id||row.name+':'+i}><summary>{row.name} · {row.id.slice(0,8)} · {row.status}</summary>
        {row.id&&row.status==='succeeded'?<RunReport runId={row.id}/>:<p>{row.error==='VERSION_NOT_FOUND'?'当前标注引用无效，尚未生成预处理运行。':row.status==='failed'?`该成员执行失败：${row.error||'请核对执行记录'}。`:'当前结果待核对。'}</p>}</details>)}</>;
  } else if(kind==='preprocess'||kind==='compare') {
    content=<><RunReport runId={runId}/>{typeof summary.comparison_run_id==='string'&&<RunReport runId={summary.comparison_run_id}/>}</>;
  } else if(kind==='classification'||kind==='regression') {
    content=<S08 runId={runId} onOpen={()=>{}} onBackToList={()=>setHidden(true)} onClose={()=>setHidden(true)}/>;
  } else if(kind==='settings') {
    content=<><SettingsPanel onClose={()=>setHidden(true)}/><ProjectPathsPanel/></>;
  } else if(kind==='diagnostics') {
    content=<SmokePanel/>;
  } else if(kind==='exports') {
    content=<ExportFiles runId={runId}/>;
  } else if(kind==='annotation_review') {
    content=<AnnotationReview cubeId={cubeId}/>;
  } else {
    content=<ReadLocal identity={identity} read={async()=>{
      if(kind==='coefficients')return <CoefficientChart input={{result:await modeling.coefficients(String(summary.model_id))}}/>;
      if(kind==='inference') {
        const map=await modeling.inferenceMap(runId);
        return <><img src={mapSource(map)} alt="预测空间分布图"/><img src={mapSource(map,true)} alt="模型适用域图"/>
          <p>{map.stats.warning}</p><pre>{JSON.stringify(map.stats,null,2)}</pre></>;
      }
      if(kind==='annotation_history') {
        const result=await annotations.current(cubeId);
        return <><p>{result.current ? `当前已保存标注：${result.current.labeled_pixels} 像素` : '尚未保存标注'}</p>
          <p>{result.json_projection?.exists?'已生成标注 JSON。':'尚无标注 JSON。'}</p></>;
      }
      const record=await datasets.get(cubeId);
      if(kind==='spectrum') {
        const spectrum=await datasets.spectraMean(cubeId,{l0:Number(summary.l0??0),l1:Number(summary.l1??record.dataset.shape[0]),
          s0:Number(summary.s0??0),s1:Number(summary.s1??record.dataset.shape[1])});
        return <SpectrumReadout spectrum={spectrum} wavelengths={record.dataset.wavelengths??[]}/>;
      }
      const rgb=['red','green','blue'].every(k=>typeof summary[k]==='number');
      const preview=await datasets.preview(cubeId,{...(rgb?{bands:[summary.red,summary.green,summary.blue].join(',')}:{band:Number(summary.band??0)}),
        stretch:summary.stretch==='manual'?'none':'auto',size:'full'});
      return <figure><figcaption>{record.display_name??record.dataset.name}</figcaption>
        <ImageView preview={preview} zoom={Number(summary.zoom??1)} lut={summary.stretch==='manual'?{
          black:Number(summary.black),white:Number(summary.white),gamma:Number(summary.gamma)}:undefined}/></figure>;
    }}/>;
  }
  return <section className="assistant-local-result" aria-label="本地结果展示"><button onClick={()=>setHidden(true)}>收起结果</button>{content}</section>;
}
