import { useEffect, useRef, useState } from 'react';
import { agent, type PairingPage, type PairingRole, type PairingSection, type StudyResult, type InferenceResult } from './api';
import StudyLeaderboard from './StudyLeaderboard';
import InferenceViewer from './InferenceResultsView';

type AxisRange = {files:number;axes:number;start:number;stop:number;max_step:number};
export type WavelengthDetails = {sides:Record<PairingRole,AxisRange>;overlap_start:number;overlap_stop:number;max_step:number;
  problem?:string;start?:number;stop?:number;step?:number;bands?:number;window?:number;tolerance?:number};
export type ViewerTarget = {kind:'wavelength';details:WavelengthDetails}
  | {kind:'pairing';previewId?:string;section:PairingSection}
  | {kind:'study';result:StudyResult}
  | {kind:'inference';result:InferenceResult;fileIndex?:number};

const sections = {pairs:'配对明细',unused:'未配对原图',issues:'配对异常'} as const;
const pageSize = 20;
const number = (value:number|undefined) => value?.toLocaleString('zh-CN', {maximumFractionDigits:5});
const basename = (path:string) => path.split(/[\\/]/).at(-1) ?? path;

function WavelengthView({data}:{data:WavelengthDetails}) {
  return <section aria-label="波长详情">
    <h3>训练与测试的波长</h3>
    <div className="experiment-table"><table><thead><tr><th>用途</th><th>原生覆盖范围</th><th>最大相邻间距</th></tr></thead>
      <tbody>{Object.entries(data.sides).map(([role,axis])=><tr key={role}>
        <th>{role} · {axis.files} 幅</th><td>{number(axis.start)}–{number(axis.stop)} nm（{axis.axes} 种波长轴）</td>
        <td>{number(axis.max_step)} nm</td></tr>)}</tbody></table></div>
    {data.overlap_start < data.overlap_stop && <p>全部原图共同覆盖 {number(data.overlap_start)}–{number(data.overlap_stop)} nm。</p>}
    {data.problem ? <p role="alert">{data.problem}</p> : <>
      <p>建议统一为 <strong>{number(data.start)}–{number(data.stop)} nm</strong>，每 {number(data.step)} nm 一个波段，共 {data.bands} 个。已校验全部原图。</p>
      <dl>
        <dt>波长间隔</dt><dd>对齐后每两个相邻波段之间的距离。等间隔也可用于 SG 导数。</dd>
        <dt>映射窗口 {number(data.window)} nm</dt><dd>以目标波长为中心，在这个宽度内对原始通道取平均。</dd>
        <dt>最近通道容差 {number(data.tolerance)} nm</dt><dd>窗口内没有通道时，最近的原始通道最多可以偏离多少。</dd>
      </dl>
    </>}
  </section>;
}

function PairingView({sessionId,target,onLatest}:{sessionId:string;target:Extract<ViewerTarget,{kind:'pairing'}>;
  onLatest:(target:ViewerTarget)=>void}) {
  const [section,setSection] = useState(target.section);
  const [offset,setOffset] = useState(0);
  const [input,setInput] = useState('');
  const [search,setSearch] = useState('');
  const [role,setRole] = useState<PairingRole|''>('');
  const [label,setLabel] = useState('');
  const [page,setPage] = useState<PairingPage|null>(null);
  const [busy,setBusy] = useState(true);
  const [error,setError] = useState('');
  const [file,setFile] = useState<{name:string;text:string}|null>(null);
  const [fileMessage,setFileMessage] = useState('');
  const [copyStatus,setCopyStatus] = useState('');
  const previewId = useRef(target.previewId);
  const fileRequest = useRef(0);
  const fileViewer = useRef<HTMLElement>(null);
  useEffect(()=>{
    let active = true;
    fileRequest.current++;
    setBusy(true);
    setError('');
    setFile(null);
    setFileMessage('');
    void agent.pairingView(sessionId,{preview_id:previewId.current,section,offset,limit:pageSize,search,
      role:section==='pairs'&&role?role:undefined,label:section==='pairs'&&label?label:undefined})
      .then(result=>{
        if(!active)return;
        if(result.status==='ready')previewId.current=result.preview_id;
        setPage(result);
      })
      .catch(()=>{if(active)setError('配对记录读取失败，请重新打开查看器。');})
      .finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;fileRequest.current++;};
  },[sessionId,target.previewId,section,offset,search,role,label]);
  useEffect(()=>{if(file)fileViewer.current?.scrollIntoView({block:'nearest'});},[file]);

  async function copy(path:string) {
    try {await navigator.clipboard.writeText(path);setCopyStatus('已复制路径。');}
    catch {setCopyStatus('无法自动复制，请选中路径后复制。');}
  }

  async function openFile(index:number,kind:'hdr'|'annotation') {
    if(page?.status!=='ready')return;
    const request = ++fileRequest.current;
    setFile(null);
    setFileMessage('正在读取本机文件…');
    try {
      const result = await agent.pairingFile(sessionId,page.preview_id,index,kind);
      if(request===fileRequest.current){setFile(result);setFileMessage('');}
    } catch (failure) {
      const detail = typeof failure==='object'&&failure&&'detail' in failure ? String(failure.detail) : '';
      if(request===fileRequest.current)setFileMessage(detail || '无法读取此文件，请重新核对配对预览。');
    }
  }

  if(error)return <p role="alert">{error}</p>;
  if(!page)return <p role="status">正在读取配对记录…</p>;
  if(page.status==='empty')return <p>当前会话还没有配对预览。</p>;
  if(page.status==='stale')return <section>
    <p role="status">这份配对预览已被新的结果替换。</p>
    <button onClick={()=>onLatest({...target,previewId:page.preview_id??undefined})}>打开最新预览</button>
  </section>;
  if(page.status!=='ready')return null;
  return <section aria-label="配对结果查看器">
    <div className="work-actions">{Object.entries(sections).map(([key,title])=><button key={key}
      aria-pressed={key===section} onClick={()=>{setOffset(0);setSection(key as PairingSection);}}>
      {title}（{page.counts[key as PairingSection]}）</button>)}</div>
    <form className="work-actions" onSubmit={event=>{event.preventDefault();setOffset(0);setSearch(input);}}>
      <input aria-label="按名称或路径搜索" placeholder="按名称或路径搜索" maxLength={200} value={input}
        onChange={event=>setInput(event.target.value)}/>
      <button type="submit">搜索</button>
      {section==='pairs'&&<>
        <select aria-label="筛选用途" value={role} onChange={event=>{setOffset(0);setRole(event.target.value as PairingRole|'');}}>
          <option value="">全部用途</option><option>训练</option><option>测试</option>
        </select>
        <select aria-label="筛选材质" value={label} onChange={event=>{setOffset(0);setLabel(event.target.value);}}>
          <option value="">全部材质</option>{page.labels.map(name=><option key={name}>{name}</option>)}
        </select>
      </>}
    </form>
    {busy ? <p role="status">正在读取…</p> : <>
      <p>{page.total ? '第 '+(offset+1)+'–'+(offset+page.items.length)+' 条，共 '+page.total+' 条' : '没有符合条件的结果。'}</p>
      <ul className="work-pairing-list">{page.items.map(row=><li key={row.index}>
        {'text' in row ? <><span>{row.text}</span>{section==='unused'&&<button onClick={()=>void copy(row.text)}>复制路径</button>}</> :
          <details>
            <summary><strong>{basename(row.hdr)}</strong><small>{row.role} · {row.labels.join('、')} · {row.regions} 个区域</small></summary>
            <p>原图 <code>{row.hdr}</code></p>
            <div className="work-actions"><button onClick={()=>void copy(row.hdr)}>复制原图路径</button>
              <button onClick={()=>void openFile(row.index,'hdr')}>查看 HDR</button></div>
            <p>标注 <code>{row.annotation}</code></p>
            <div className="work-actions"><button onClick={()=>void copy(row.annotation)}>复制标注路径</button>
              <button onClick={()=>void openFile(row.index,'annotation')}>查看 JSON</button></div>
          </details>}
      </li>)}</ul>
      <div className="work-actions"><button disabled={!offset} onClick={()=>setOffset(value=>value-pageSize)}>上一页</button>
        <button disabled={offset+pageSize>=page.total} onClick={()=>setOffset(value=>value+pageSize)}>下一页</button>
        <span role="status">{copyStatus}</span></div>
    </>}
    {fileMessage&&<p role="status">{fileMessage}</p>}
    {file&&<section className="work-file" aria-label="只读文件" ref={fileViewer}><h3>{file.name}</h3>
      <button onClick={()=>setFile(null)}>关闭文件</button><pre>{file.text}</pre></section>}
  </section>;
}

export default function WorkViewer({target,sessionId,onOpen,enabled,send}:{target:ViewerTarget|null;sessionId?:string;
  onOpen:(target:ViewerTarget)=>void;enabled:boolean;send:(text:string)=>void}) {
  if(target?.kind==='study')return <StudyLeaderboard key={target.result.study_id} result={target.result} enabled={enabled} send={send}/>;
  if(target?.kind==='wavelength')return <WavelengthView data={target.details}/>;
  if(!sessionId)return <p>打开会话后可查看其中的结果。</p>;
  if(target?.kind==='inference')return <InferenceViewer key={target.result.run_id+':'+target.fileIndex}
    result={target.result} sessionId={sessionId} fileIndex={target.fileIndex}/>;
  if(!target)return <button onClick={()=>onOpen({kind:'pairing',section:'pairs'})}>查看最近配对预览</button>;
  return <PairingView key={[sessionId,target.previewId,target.section].join(':')} target={target} sessionId={sessionId} onLatest={onOpen}/>;
}
