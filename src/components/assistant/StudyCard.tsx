import { useEffect, useRef, useState } from 'react';
import { agent, type StudyCandidate, type StudyResult, type StudyStatus } from './api';
import { CandidateTable, candidateCommand, pct, topCandidates } from './StudyLeaderboard';

const labels={queued:'排队中',running:'运行中',succeeded:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
const grouping:Record<string,string>={image:'按原图探索性分组（实物独立性未知）',sample:'实物分组',batch:'批次分组',npz_group:'NPZ 分组字段',exploratory:'探索性分层，实物分组未知'};

function Curve({rows}:{rows:StudyCandidate[]}) {
  const ref=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{
    const ctx=ref.current?.getContext('2d');
    if(!ctx || !rows.length)return;
    const values=[...rows].sort((a,b)=>a.n_components-b.n_components);
    const left=56, right=616, top=16, bottom=174;
    ctx.clearRect(0,0,640,220);
    ctx.font='14px sans-serif';
    ctx.fillStyle='#3c4b58';
    for(const value of [0,.25,.5,.75,1]){
      const y=bottom-value*(bottom-top);
      ctx.strokeStyle='#d1dce5';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
      ctx.fillText(Math.round(value*100)+'%',7,y+5);
    }
    const first=values[0].n_components,last=values[values.length-1].n_components;
    const x=(value:number)=>first===last?(left+right)/2:left+(value-first)/(last-first)*(right-left);
    for(const item of values.filter((_,i)=>i===values.length-1||i%Math.max(1,Math.ceil(values.length/13))===0)){
      ctx.fillText(String(item.n_components),x(item.n_components)-4,bottom+19);
    }
    ctx.fillText('PLS-DA 潜变量',268,215);
    for(const [key,color] of [['train_f1','#b45309'],['cv_f1','#1260a1']] as const){
      ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2.5;ctx.beginPath();
      values.forEach((row,i)=>{
        const px=x(row.n_components), py=bottom-(row[key]??0)*(bottom-top);
        if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
      });
      ctx.stroke();
      values.forEach(row=>{
        ctx.beginPath();ctx.arc(x(row.n_components),bottom-(row[key]??0)*(bottom-top),3,0,Math.PI*2);ctx.fill();
      });
    }
  },[rows]);
  return <figure style={{margin:'0.8rem 0'}}>
    <figcaption>Macro-F1 · <span style={{color:'#1260a1'}}>验证折</span> · <span style={{color:'#b45309'}}>训练折拟合</span></figcaption>
    <canvas ref={ref} width={640} height={220} style={{width:'100%'}} aria-label="潜变量与训练折及验证折 Macro-F1 曲线"/>
  </figure>;
}

export function StudyHighlights({result,enabled,send}:{result:StudyResult;enabled:boolean;send:(text:string)=>void}) {
  const recommended = result.candidates.find(row=>row.id===result.recommended);
  const best = result.candidates.find(row=>row.id===result.best);
  const id = result.study_id;
  return <div className="study-highlights">
        {([['1-SE 推荐候选',recommended,'推荐方案'],['最高分候选',best,'最高分方案']] as const).map(([title,row,command])=>row&&
          <section key={title}><h4>{title}</h4><p>{row.name} · {row.n_components} 潜变量</p>
            <p>CV Macro-F1 {pct(row.cv_f1)} ± {pct(row.cv_f1_sd)}<br/>CV 准确率 {pct(row.cv_accuracy)}</p>
            {(command==='推荐方案'||result.recommended!==result.best)&&<button disabled={!enabled}
              onClick={()=>send('采用'+command+'新建正式训练 '+id)}>采用{command}新建正式训练</button>}
          </section>)}
      </div>;
}

export default function StudyCard({sessionId,id,enabled,send,onView}:{sessionId:string;id:string;enabled:boolean;
  send:(text:string)=>void;onView:(result:StudyResult)=>void}) {
  const [state,setState]=useState<StudyStatus|null>(null),[result,setResult]=useState<StudyResult|null>(null);
  const [choice,setChoice]=useState(''),[error,setError]=useState(''),[revision,setRevision]=useState(0);
  useEffect(()=>{
    if(!enabled)return;
    let active=true,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      try{
        const status=await agent.study(sessionId,id);
        if(!active)return;
        setState(status);
        if(status.status==='succeeded'){
          const saved=await agent.studyResult(sessionId,id);
          if(active){setResult(saved);setChoice(saved.candidates.find(row=>row.id===saved.recommended)?.name??'');}
        }else if(status.status==='queued'||status.status==='running')timer=setTimeout(()=>void poll(),700);
      }catch{if(active)setError('无法读取寻优记录，请重试。');}
    };
    setError('');void poll();
    return()=>{active=false;clearTimeout(timer);};
  },[sessionId,id,enabled,revision]);
  const curve=result?.candidates.filter(row=>row.name===choice&&row.cv_f1!==undefined)??[];
  const ranked=result?.candidates.filter(row=>row.cv_f1!==undefined)??[];
  return <section className="experiment-task-card" aria-label="训练集寻优">
    <h3>训练集寻优 · {state?labels[state.status]:'正在查询'}</h3>
    {state?.status==='running'&&state.phase==='preparing'&&<p role="status">准备训练侧光谱
      {state.file_total!==undefined&&` · 第 ${state.file_index}／${state.file_total} 幅`}
      {state.rows_total!=null&&` · ${state.rows_done}／${state.rows_total} 行`}</p>}
    {state?.status==='running'&&state.phase==='evaluating'&&<p role="status">候选 {state.candidate}／{state.total} · 潜变量 {state.component} · 第 {state.fold}／{state.folds} 折</p>}
    {(state?.status==='queued'||state?.status==='running')&&<button disabled={!enabled} onClick={()=>{
      void agent.study(sessionId,id,'cancel').catch(()=>setError('取消请求失败，请重试。'));
    }}>取消寻优</button>}
    {(state?.error||error)&&<p role="alert">{state?.error||error}</p>}
    {error&&<button disabled={!enabled} onClick={()=>setRevision(v=>v+1)}>重新读取</button>}
    {result&&<>
      <p>{result.folds} 折 · {grouping[result.grouping]}{result.group_count!==null&&`（${result.group_count} 组）`} · {result.samples} {result.evaluation_unit==='center_pixel'?'中心像元':'条光谱'}。1-SE 下界 {pct(result.one_se_threshold)}。</p>
      <StudyHighlights result={result} enabled={enabled} send={send}/>
      {result.component_upper_reached&&<p role="status">最高分潜变量已触及本次上界，可扩宽潜变量范围继续寻优。</p>}
      <label>曲线方案 <select value={choice} onChange={event=>setChoice(event.target.value)}>
        {[...new Set(ranked.map(row=>row.name))].map(name=><option key={name}>{name}</option>)}
      </select></label>
      {curve.length>0&&<Curve rows={curve}/>}
      <CandidateTable result={result} rows={topCandidates(result.candidates,result.recommended)} title="候选前十"
        enabled={enabled} adopt={row=>send(candidateCommand(result.study_id,row.id))}/>
      <button onClick={()=>onView(result)}>查看全部候选（共 {result.candidates.length} 条）</button>
    </>}
  </section>;
}
