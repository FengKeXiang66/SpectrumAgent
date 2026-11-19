import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { datasets } from '../datasets/api.ts';
import type { CatalogRecord, DatasetRecord } from '../datasets/types.ts';
import { annotations } from '../annotation/api.ts';
import type { Version } from '../annotation/types.ts';
import PreprocessPanel, {MetricsView,type PreprocessDesignState} from './PreprocessPanel';
import RecipeMatrix from './RecipeMatrix.tsx';
import { preprocessing } from './api.ts';
import { describePreprocessError, type PreprocessRun, type Report } from './types.ts';
import { planMembers, type BatchPlanController, type Member, pauseCodes } from './batch-plan.ts';
import './batch-workspace.css';

export default function PreprocessWorkspace({records,phase,initialRecord,ensureOwnerSession,controller,bootId,refreshVersion=0}:{
  records:CatalogRecord[];phase:string;initialRecord:DatasetRecord|null;ensureOwnerSession:()=>Promise<string>;
  controller:BatchPlanController;bootId:string;refreshVersion?:number;
}) {
  const snapshot=useSyncExternalStore(controller.subscribe,controller.getSnapshot);
  const [tab,setTab]=useState<'apply'|'design'>('apply'),[representative,setRepresentative]=useState(initialRecord);
  const [design,setDesign]=useState<PreprocessDesignState|null>(null),[selected,setSelected]=useState<Record<string,boolean>>({});
  const [versions,setVersions]=useState<Record<string,Version[]>>({}),[bindings,setBindings]=useState<Record<string,string>>({});
  const [loadErrors,setLoadErrors]=useState<Record<string,string>>({}),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const [retrySelection,setRetrySelection]=useState<Record<string,boolean>>({}),[detail,setDetail]=useState<PreprocessRun|null>(null);
  const [detailError,setDetailError]=useState(''),[detailReport,setDetailReport]=useState<Report|null>(null);
  const loadingTicket=useRef(0),navigationTicket=useRef(0),detailTicket=useRef(0);
  const acceptDesign=useCallback((next:PreprocessDesignState)=>setDesign(next),[]);
  useEffect(()=>{setRetrySelection({});setDetail(null);setDetailError('');setDetailReport(null);},[snapshot.active]);
  const recordKey=records.map(r=>r.id+':'+r.available).join('|');
  useEffect(()=>{let valid=true;void ensureOwnerSession().then(owner=>{if(valid)controller.attach(bootId,owner);}).catch(e=>setError(describePreprocessError(e)));return()=>{valid=false;};},[controller,bootId,ensureOwnerSession]);
  useEffect(()=>{
    const ticket=++loadingTicket.current;
    setSelected(previous=>Object.fromEntries(records.map(r=>[r.id,previous[r.id]??true])));
    setLoading(true);setLoadErrors({});let next=0;
    const rows=records;
    const load=async()=>{while(next<rows.length){const row=rows[next++];try{
      const result=await annotations.versions(row.id);
      if(ticket===loadingTicket.current){setVersions(v=>({...v,[row.id]:result.versions}));setBindings(b=>({...b,[row.id]:result.versions.some(v=>v.id===b[row.id])?b[row.id]:''}));}
    }catch(e){if(ticket===loadingTicket.current)setLoadErrors(v=>({...v,[row.id]:describePreprocessError(e)}));}}};
    void Promise.all(Array.from({length:Math.min(4,rows.length)},load)).finally(()=>{if(ticket===loadingTicket.current)setLoading(false);});
    return()=>{loadingTicket.current++;};
  },[recordKey,refreshVersion]);
  useEffect(()=>{
    if(representative&&records.some(r=>r.id===representative.id&&r.available))return;
    const row=records.find(r=>r.available);if(!row)return;
    const ticket=++navigationTicket.current;
    void datasets.get(row.id).then(record=>{if(ticket===navigationTicket.current)setRepresentative(record);}).catch(e=>setError(describePreprocessError(e)));
    return()=>{navigationTicket.current++;};
  },[recordKey]);
  const chooseRepresentative=async(id:string)=>{const ticket=++navigationTicket.current;try{const record=await datasets.get(id);if(ticket===navigationTicket.current)setRepresentative(record);}catch(e){setError(describePreprocessError(e));}};
  const members:Member[]=records.filter(r=>selected[r.id]).map(row=>({cube_id:row.id,name:row.display_name,annotation_version_id:bindings[row.id]||null,
    gap:!row.available?'source_unavailable':loadErrors[row.id]?'unknown':!versions[row.id]?'loading':!versions[row.id].length?'need_annotation':!bindings[row.id]?'need_annotation_selection':undefined}));
  const ready=members.filter(m=>!m.gap).length,plan=snapshot.plans.find(p=>p.id===snapshot.active);
  const rows=plan?planMembers(plan):[];
  const selectionMatches=!!plan&&plan.recipe===design?.version&&plan.members.length===members.length&&plan.members.every(m=>members.some(n=>n.cube_id===m.cube_id&&n.annotation_version_id===m.annotation_version_id&&n.gap===m.gap));
  const disabled=snapshot.busy||loading||phase!=='ready'||!design||design.blocked||!design.version;
  const act=async(work:()=>Promise<unknown>|unknown)=>{setError('');try{await work();}catch(e){setError(describePreprocessError(e));}};
  const labels:Record<string,string>={need_annotation:'缺少保存标注',need_annotation_selection:'请选择标注版本',source_unavailable:'源数据不可读',unknown:'待核对',loading:'正在查询',ready:'待确认',submitting:'已受理／处理中',succeeded:'成功',failed:'失败',not_submitted:'未提交',blocked:'提交被阻止',partial:'部分完成',confirming:'正在核验',running:'处理中',paused:'已暂停',completed:'处理结束'};
  const openDetail=async(runId:string)=>{
    const ticket=++detailTicket.current;
    setDetailError('');setDetail(null);setDetailReport(null);
    let row:PreprocessRun;
    try{row=await preprocessing.getRun(runId);}catch(e){if(ticket===detailTicket.current)setDetailError(describePreprocessError(e));return;}
    if(ticket!==detailTicket.current)return;
    setDetail(row);
    if(row.status!=='succeeded')return;
    try{const report=await preprocessing.getArtifact(row.id,'report');if(ticket===detailTicket.current)setDetailReport(report);}
    catch(e){if(ticket===detailTicket.current)setDetailError(`报告加载失败：${describePreprocessError(e)}`);}
  };
  return <section className="preprocess-workspace ui-page" aria-label="S06 全样品预处理工作台">
    <header className="pp-page-heading"><div><h2>S06 · 预处理工作台</h2><p>选择样品与多个已保存配方，运行后比较预处理前后及配方之间差异，再确定采用的配方。</p></div></header>
    <nav aria-label="预处理视图"><button aria-pressed={tab==='apply'} onClick={()=>setTab('apply')}>应用到样品</button><button aria-pressed={tab==='design'} onClick={()=>setTab('design')}>配方设计</button></nav>
    <label>代表样品<select value={representative?.id??''} onChange={e=>void chooseRepresentative(e.target.value)}><option value="">选择代表样品</option>{records.filter(r=>r.available).map(r=><option key={r.id} value={r.id}>{r.display_name}</option>)}</select></label>
    <p>代表样品用于单样品运行与预览，不改变批量应用范围。</p>
    {error&&<p role="alert">{error}</p>}
    {/* One mounted design owner preserves the shared draft and update queue across tabs and samples. */}
    <div hidden={tab!=='design'}>{representative?<PreprocessPanel record={representative} ensureOwnerSession={ensureOwnerSession} onDesignState={acceptDesign}/>:<p>没有可读样品。导入后可设计配方。</p>}</div>
    <div hidden={tab!=='apply'}>
      <div className="pp-batch-actions"><button disabled={snapshot.busy} onClick={()=>setSelected(Object.fromEntries(records.map(r=>[r.id,true])))}>全选</button><button disabled={snapshot.busy} onClick={()=>setSelected({})}>取消全选</button>
        <button disabled={snapshot.busy||loading} onClick={()=>setBindings(old=>{const next={...old};for(const r of records)if(selected[r.id]&&versions[r.id]?.length===1)next[r.id]=versions[r.id][0].id;return next;})}>采用各样品唯一可用保存版本</button></div>
      <p role="status">目录 {records.length} 项 · 已选 {members.length} · 引用就绪 {ready} · 缺口 {members.length-ready} · 预计 {Math.ceil(ready/32)} 批（每批最多 32 项）</p>
      {phase!=='ready'&&<p role="alert">目录尚未完整加载，暂不能提交。</p>}
      <table className="pp-batch-table"><thead><tr><th>选择</th><th>样品</th><th>保存的标注版本</th><th>状态</th></tr></thead><tbody>{records.map(r=>{
        const member=members.find(m=>m.cube_id===r.id);return <tr key={r.id}><td><input type="checkbox" aria-label={`选择 ${r.display_name}`} checked={!!selected[r.id]} disabled={snapshot.busy} onChange={e=>setSelected(s=>({...s,[r.id]:e.target.checked}))}/></td><td>{r.display_name}</td><td><select aria-label={`${r.display_name} 标注版本`} disabled={snapshot.busy||loading} value={bindings[r.id]??''} onChange={e=>setBindings(s=>({...s,[r.id]:e.target.value}))}><option value="">请选择保存版本</option>{versions[r.id]?.map(v=><option key={v.id} value={v.id}>v{v.version_no} · {v.created_at}</option>)}</select></td><td>{member?.gap?labels[member.gap]:member?'引用就绪':'未选择'}{loadErrors[r.id]&&<small>{loadErrors[r.id]}</small>}</td></tr>;
      })}</tbody></table>
      {representative&&<RecipeMatrix records={records} selectedIds={records.filter(r=>selected[r.id]).map(r=>r.id)} bindings={bindings} design={design} recordId={representative.id} bands={representative.dataset.shape[2]}/>}
      <details className="pp-advanced"><summary>高级：提交计划与恢复</summary><div className="pp-advanced-body">
      <label>已保存配方版本<select value={design?.version??''} disabled={snapshot.busy||!design?.owner} onChange={e=>{if(e.target.value)void act(()=>design?.loadVersion(e.target.value));}}><option value="">请选择已保存版本</option>{design?.recipes.flatMap(r=>r.versions.map(v=><option key={v.id} value={v.id}>{r.name} · v{v.version_no}</option>))}</select></label>
      {design?.blocked&&<p role="status">请在设计区完成草稿保存、同步或冲突处理，再应用到样品。</p>}
      <button className="pp-primary" disabled={disabled||!ready} onClick={()=>void act(()=>controller.create(design!.draft!.draft_id,design!.draft!.revision,design!.version,members))}>生成提交计划</button>
      {snapshot.plans.length>1&&<label>提交计划<select disabled={snapshot.busy} value={snapshot.active??''} onChange={e=>controller.select(e.target.value)}>{snapshot.plans.map((p,i)=><option key={p.id} value={p.id}>计划 {i+1} · {p.members.length} 项 · {labels[p.status]}</option>)}</select></label>}
      {plan&&<section aria-label="批量提交计划"><h3>计划 · {plan.members.length} 个样品 · {labels[plan.status]}</h3>
        <p>确认后版本与范围固定。修改选择需重新生成计划；已受理结果保留。每批有独立确认凭据和提交身份。</p>
        {!selectionMatches&&<p role="status">当前选择与此计划不同；请重新生成计划，或恢复此计划的范围与标注选择后继续。</p>}
        <p>成功 {rows.filter(r=>r.status==='succeeded').length} · 失败 {rows.filter(r=>r.status==='failed').length} · 缺口 {plan.members.filter(m=>m.gap).length} · 待核对 {rows.filter(r=>r.status==='unknown').length}</p>
        {plan.error&&<p role="alert">{plan.error}</p>}
        <div className="pp-batch-actions"><button disabled={disabled||!selectionMatches||!plan.batches.some(b=>b.status==='not_submitted')||plan.batches.some(b=>['unknown','blocked'].includes(b.status))} onClick={()=>void act(controller.execute)}>确认计划并执行／继续未提交批次</button>
          <button disabled={snapshot.busy} onClick={()=>{setSelected(Object.fromEntries(plan.members.map(m=>[m.cube_id,true])));setBindings(Object.fromEntries(plan.members.map(m=>[m.cube_id,m.annotation_version_id??''])));}}>恢复此计划的样品选择</button>
          <button disabled={!snapshot.busy} onClick={()=>controller.stop()}>停止后续批次</button><button disabled={snapshot.busy} onClick={()=>void act(controller.recover)}>核对原提交状态</button>
          <button disabled={disabled||!rows.some(r=>r.status==='failed'&&retrySelection[r.cube_id])} onClick={()=>void act(async()=>{await controller.retry(rows.filter(r=>r.status==='failed'&&retrySelection[r.cube_id]&&!pauseCodes.has(r.error_code??'')).map(r=>r.cube_id),{id:design!.draft!.draft_id,revision:design!.draft!.revision,recipe:design!.version});setRetrySelection({});})}>补跑所选失败项（重新确认）</button></div>
        {plan.batches.map((b,i)=><details key={b.ref}><summary>批次 {i+1} · {b.inputs.length} 项 · {labels[b.status]}{b.retryOf?' · 补跑':''}</summary><p>提交引用：{b.ref}</p>{b.error&&<p role="alert">{b.error}</p>}</details>)}
        <table className="pp-batch-table"><thead><tr><th>补跑选择</th><th>样品</th><th>状态</th><th>运行／原因</th></tr></thead><tbody>{rows.map(r=><tr key={r.cube_id}><td><input type="checkbox" aria-label={`补跑 ${r.name}`} disabled={snapshot.busy||r.status!=='failed'||pauseCodes.has(r.error_code??'')} checked={!!retrySelection[r.cube_id]} onChange={e=>setRetrySelection(s=>({...s,[r.cube_id]:e.target.checked}))}/></td><td>{r.name}</td><td>{labels[r.status]??r.status}</td><td>{r.run_id?<button onClick={()=>{void openDetail(r.run_id!);}}>{r.run_id}</button>:r.error_code??(r.gap?labels[r.gap]:'尚无运行')}{r.run_id&&r.error_code&&<small>{r.error_code}</small>}</td></tr>)}</tbody></table>
        <p>这些成功 run 可用于建模；本页不冻结训练集版本、不自动跳转。</p>
      </section>}
      {detailError&&<p role="alert">{detailError}</p>}{detail&&<section aria-label="批量运行详情"><button onClick={()=>setDetail(null)}>关闭详情</button><h3>{labels[detail.status]??detail.status} · {detail.id}</h3>{detail.error&&<p role="alert">{describePreprocessError(detail.error)}</p>}{detail.metrics&&<MetricsView metrics={detail.metrics} runId={detailReport?.run_id??detail.id} steps={detailReport?.steps}/>}</section>}
      </div></details>
    </div>
  </section>;
}
