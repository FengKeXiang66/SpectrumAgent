import { useEffect, useMemo, useState } from 'react';
import { agent, type InferenceResult } from './api';

type Row = InferenceResult['files'][number];
export type OpenInferenceView = (result:InferenceResult,fileIndex?:number)=>void;
const reasons:Record<string,string>={brightness:'亮度阈值排除',side_edges:'左右边缘屏蔽',
  quality_or_neighborhood:'质量或邻域无效',image_boundary:'图像外边界'};
const labels = (result:InferenceResult) => Object.keys(result.classes).sort((a,b)=>Number(a)-Number(b));
const path = (row:Row) => row.relative_path || row.name;
const num = (value:number) => value.toLocaleString();
const none = '无已分类样本';

function majority(row:Row, ids:string[]) {
  let best: string|null = null;
  let count = 0;
  for(const id of ids){
    const value = row.counts[id]??0;
    if(value>count){ best=id; count=value; }
  }
  return best;
}

export function InferenceSummary({result}:{result:InferenceResult}) {
  const ids = labels(result);
  const count:Record<string,number> = {}, votes:Record<string,number> = {}, excludedByReason:Record<string,number> = {};
  let classified = 0, excluded = 0, unvoted = 0;
  for(const row of result.files){
    classified += row.classified;
    excluded += row.excluded;
    const winner = majority(row,ids);
    if(winner===null)unvoted++;
    else votes[winner]=(votes[winner]??0)+1;
    for(const id of ids)count[id]=(count[id]??0)+(row.counts[id]??0);
    for(const [reason,value] of Object.entries(row.exclusion_counts??{})){
      excludedByReason[reason]=(excludedByReason[reason]??0)+value;
    }
  }
  const unit = result.kind==='envi'?'像元':'条光谱';
  const noVote = result.kind==='envi'?'无已分类像元':none;
  return <section aria-label="推理批次汇总">
    <p><strong>{num(result.files.length)} 个文件</strong> · 已分类 {num(classified)} · 未分类 {num(excluded)}{unit}</p>
    {Object.keys(excludedByReason).length>0&&<p>未分类原因 · {Object.entries(excludedByReason)
      .map(([key,value])=>(reasons[key]??key)+' '+num(value)).join('，')}</p>}
    <div className="experiment-table"><table>
      <thead><tr><th>类别</th><th>已分类数量</th><th>占已分类比例</th><th>多数票文件数</th></tr></thead>
      <tbody>{ids.map(id=><tr key={id}><th>{result.classes[id]}</th><td>{num(count[id]??0)}</td>
        <td>{classified?((count[id]??0)/classified*100).toFixed(2)+'%':'—'}</td><td>{num(votes[id]??0)}</td></tr>)}
        {unvoted>0&&<tr><th>{noVote}</th><td>—</td><td>—</td><td>{num(unvoted)}</td></tr>}</tbody>
    </table></div>
  </section>;
}

export function InferenceFileTable({result,rows,onSelect,selected}:{result:InferenceResult;rows:Row[];
  onSelect?:(row:Row)=>void;selected?:number}) {
  const ids = labels(result);
  return <div className="experiment-table"><table><caption>按文件统计的分类数量</caption>
    <thead><tr><th>文件</th><th>多数票</th><th>总数</th><th>已分类</th><th>未分类</th>{ids.map(id=><th key={id}>{result.classes[id]}</th>)}</tr></thead>
    <tbody>{rows.map(row=>{
      const winner = majority(row,ids);
      return <tr key={row.file_index}><th>{onSelect
        ?<button type="button" onClick={()=>onSelect(row)} aria-pressed={selected===row.file_index}>{path(row)}</button>
        :path(row)}</th><td> {winner===null?(result.kind==='envi'?'无已分类像元':none):result.classes[winner]}</td><td>{num(row.total)}</td>
        <td>{num(row.classified)}</td><td>{num(row.excluded)}</td>{ids.map(id=><td key={id}>{num(row.counts[id]??0)}</td>)}</tr>;
    })}</tbody>
  </table></div>;
}

function FileImages({sessionId,result,row}:{sessionId:string;result:InferenceResult;row:Row}) {
  const [images,setImages] = useState<{input?:string;prediction?:string}>({});
  const [failed,setFailed] = useState<string[]>([]);
  const {model_id,run_id} = result;
  const index = row.file_index;
  const hasInput = !!row.preview_wavelengths_nm;
  useEffect(()=>{
    let active = true;
    for(const kind of (hasInput?['input','prediction']:['prediction']) as ('input'|'prediction')[]){
      void agent.inferencePlot(sessionId,model_id,run_id,index,kind)
        .then(value=>{if(active)setImages(previous=>({...previous,[kind]:'data:image/png;base64,'+value.png_base64}));})
        .catch(()=>{if(active)setFailed(previous=>[...previous,kind]);});
    }
    return ()=>{active=false;};
  },[sessionId,model_id,run_id,index,hasInput]);
  const image = (kind:'input'|'prediction',title:string) => <figure><figcaption>{title}</figcaption>
    {images[kind]?<img className="experiment-plot" src={images[kind]} alt={title}/>
      :<p>{failed.includes(kind)?'读取失败或校验未通过。':'正在读取预览…'}</p>}
  </figure>;
  return <section aria-label="当前图像详情">
    <h3>{path(row)}</h3>
    <div aria-label="分类图图例">
      {result.background_colors&&result.foreground?.mode==='brightness_edges'&&<span className="inference-legend">
        <span style={{backgroundColor:result.background_colors.brightness}}/>低亮度筛除</span>}
      {labels(result).map(id=><span key={id} className="inference-legend"><span style={{backgroundColor:result.colors[id]}}/>{result.classes[id]}</span>)}
      <span className="inference-legend"><span style={{backgroundColor:result.background_colors?.other??'#e0e0e0'}}/>边缘或无效像元</span>
    </div>
    <div className="inference-image-pair">{hasInput?image('input','输入伪彩'):<p>此归档没有输入伪彩。</p>}
      {image('prediction','逐像元分类')}</div>
    {row.preview_wavelengths_nm&&<p>伪彩通道 {row.preview_wavelengths_nm.map(value=>value.toFixed(2)).join('／')} nm</p>}
    {row.edges&&<p>尺寸 {row.shape?.join(' × ')} · 左／右屏蔽 {row.edges.left}／{row.edges.right} 列</p>}
    {row.exclusion_counts&&<div className="experiment-table"><table><caption>未分类像元原因</caption><tbody>
      {Object.entries(row.exclusion_counts).map(([key,value])=><tr key={key}><th>{reasons[key]??key}</th><td>{num(value)}</td></tr>)}
    </tbody></table></div>}
  </section>;
}

export default function InferenceViewer({sessionId,result,fileIndex}:{sessionId:string;result:InferenceResult;fileIndex?:number}) {
  const [search,setSearch] = useState('');
  const [vote,setVote] = useState('');
  const [page,setPage] = useState(()=>Math.max(0,Math.floor(result.files.findIndex(row=>row.file_index===fileIndex)/20)));
  const [selected,setSelected] = useState<number|undefined>(fileIndex??result.files[0]?.file_index);
  const ids = useMemo(()=>labels(result),[result]);
  const rows = useMemo(()=>{
    const query = search.trim().toLowerCase();
    return result.files.filter(row=>path(row).toLowerCase().includes(query)
      && (!vote||(majority(row,ids)??'none')===vote));
  },[result,search,vote,ids]);
  const row = rows.find(item=>item.file_index===selected) ?? rows[page*20];
  return <section aria-label="推理文件查看器">
    <div className="work-actions">
      <input placeholder="搜索目录或文件名" aria-label="搜索目录或文件名" value={search}
        onChange={event=>{setSearch(event.target.value);setPage(0);setSelected(undefined);}}/>
      <select aria-label="筛选多数票类别" value={vote} onChange={event=>{setVote(event.target.value);setPage(0);setSelected(undefined);}}>
        <option value="">全部多数票</option>{ids.map(id=><option key={id} value={id}>{result.classes[id]}</option>)}
        <option value="none">{result.kind==='envi'?'无已分类像元':none}</option>
      </select>
    </div>
    {rows.length>0?<InferenceFileTable result={result} rows={rows.slice(page*20,page*20+20)}
      selected={row?.file_index} onSelect={result.kind==='envi'?item=>setSelected(item.file_index):undefined}/>:<p>没有符合条件的文件。</p>}
    <div className="work-actions">
      <button disabled={page===0} onClick={()=>{setPage(page-1);setSelected(undefined);}}>上一页</button>
      <span>{rows.length?('第 '+(page+1)+' / '+Math.ceil(rows.length/20)+' 页 · '+rows.length+' 个文件'):'0 个文件'}</span>
      <button disabled={(page+1)*20>=rows.length} onClick={()=>{setPage(page+1);setSelected(undefined);}}>下一页</button>
    </div>
    {result.kind==='envi'&&row&&<FileImages key={row.file_index} sessionId={sessionId} result={result} row={row}/>}
  </section>;
}
