import { useEffect, useRef, useState } from 'react';
import { agent } from './api';
import { sampleCommand, sampleReasons, type SampleMode, type SampleView } from './sample-evaluation-form';

const percent=(n:number|undefined)=>n==null?'未定义':`${(100*n).toFixed(2)}%`;
const label=(classes:Record<string,string>,id:number|null)=>id==null?'无唯一类别':classes[String(id)]??String(id);

export function SampleReport({view,classes}:{view:SampleView;classes:Record<string,string>}) {
  const report=view.report;
  if(!report)return <p>尚未声明实物定义，不根据 sample_id、文件名或批次自动推断实物。</p>;
  if(report.status!=='ready')return <p role="status">{report.reason} 原观测指标继续保留。</p>;
  return <div aria-label="实物级报告">
    <p><strong>全实验实物数 n={report.total_objects}</strong>，不是像元数。协议 {report.protocol} · 修订 {view.revision}。</p>
    <p>声明 {view.definition?.mode}；有效观测阈值 N={view.definition?.minimum_valid}；同实物全部图像的保存观测合并投票。平票、真值冲突、跨训练测试及观测不足均排除。</p>
    {(['train','test'] as const).map(role=>{
      const result=report.roles[role],pixel=report.pixel_metrics[role],score=result.metrics;
      return <section key={role}>
        <h5>{role==='train'?'训练拟合':'测试'}：实物 {result.total}，纳入 {result.included}，排除 {result.excluded}</h5>
        <p>用途：{pixel.purpose==='training_fit'?'训练拟合':pixel.purpose==='development_regression'?'开发复现核验，不能作为独立泛化成绩':'独立测试'}。</p>
        <div className="experiment-table"><table><caption>原观测与实物指标并列</caption><thead><tr><th>评价单位</th><th>纳入 n</th><th>准确率</th><th>Macro-F1</th></tr></thead><tbody>
          <tr><th>{pixel.evaluation_unit==='center_pixel'?'中心像元':'光谱观测'}</th><td>{pixel.n}</td><td>{percent(pixel.accuracy)}</td><td>{percent(pixel.macro_f1)}</td></tr>
          <tr><th>实物</th><td>{result.included}</td><td>{percent(score?.accuracy)}</td><td>{percent(score?.macro_f1)}</td></tr>
        </tbody></table></div>
        <p>排除原因（可重叠）：{Object.entries(result.exclusion_counts).map(([key,n])=>`${sampleReasons[key]??key} ${n}`).join('；')||'无'}。</p>
        {([true,false] as const).map(included=><details key={String(included)} open={!included&&result.excluded>0}>
          <summary>{included?'纳入评价的逐实物结果':'未计入实物指标的完整列表'}</summary>
          <div className="experiment-table"><table><thead><tr><th>实物</th><th>图数</th><th>有效观测</th><th>真值</th><th>预测</th><th>判对</th><th>状态／原因</th></tr></thead><tbody>
            {result.rows.filter(row=>(row.status==='included')===included).map(row=><tr key={row.sample_id}>
              <th title={row.sample_id}>{row.display_id}</th><td>{row.image_count}</td><td>{row.valid}</td>
              <td>{row.truth==null?Object.entries(row.truth_counts).map(([id,n])=>`${classes[id]??id}: ${n}`).join('；')||'无保存真值':label(classes,row.truth)}</td>
              <td>{label(classes,row.prediction)}</td><td>{row.correct==null?'未计入':row.correct?'是':'否'}</td>
              <td>{row.reasons.map(reason=>sampleReasons[reason]??reason).join('；')||'纳入'}</td>
            </tr>)}
          </tbody></table></div>
        </details>)}
        {score&&<details><summary>实物混淆矩阵与各类别指标</summary><div className="experiment-table"><table><caption>行是真值，列是预测；单位：实物</caption><thead><tr><th>真值 ↓ ／预测 →</th>{score.confusion_labels.map(id=><th key={id}>{label(classes,id)}</th>)}</tr></thead><tbody>
          {score.confusion.map((row,i)=><tr key={i}><th>{label(classes,score.confusion_labels[i])}</th>{row.map((n,j)=><td key={j}>{n}</td>)}</tr>)}
        </tbody></table><table><thead><tr><th>类别</th><th>实物数</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>
          {score.per_class.map(row=><tr key={row.label}><th>{row.name}</th><td>{row.support}</td>{[row.precision,row.recall,row.f1].map((n,i)=><td key={i}>{percent(n??undefined)}</td>)}</tr>)}
        </tbody></table></div></details>}
      </section>;
    })}
    <p>{report.truth_basis} {report.observation_note} {report.macro_definition}</p>
    <p>本报告仅派生已保存预测，不重训、不更改 Study 排序；不能用此报告把旧 Study 换算为实物选优结果。</p>
  </div>;
}

export default function SampleEvaluationCard({initial,experimentId,sessionId,classes,enabled,onCommand}:{
  initial:SampleView;experimentId:string;sessionId:string;classes:Record<string,string>;enabled:boolean;
  onCommand?:(content:string)=>void|Promise<void>;
}) {
  const [view,setView]=useState(initial),[mode,setMode]=useState<SampleMode|''>(initial.definition?.mode??'');
  const [minimum,setMinimum]=useState(initial.definition?.minimum_valid??100);
  const [mapping,setMapping]=useState<Record<string,string>>(Object.fromEntries((initial.definition?.mapping??[]).map(row=>[row.source_ref,row.sample_id])));
  const [csv,setCsv]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const ticket=useRef(0),locked=useRef(false);
  useEffect(()=>()=>{ticket.current++;},[sessionId,experimentId]);
  const accept=(next:SampleView)=>{setView(next);setMode(next.definition?.mode??'');setMinimum(next.definition?.minimum_valid??100);
    setMapping(Object.fromEntries((next.definition?.mapping??[]).map(row=>[row.source_ref,row.sample_id])));setCsv('');};
  const read=async()=>{
    const next=await agent.archivedExperimentResult(sessionId,experimentId);
    if(!next.sample_evaluation)throw new Error('后端尚不支持实物评价。');
    return next.sample_evaluation;
  };
  const run=async(submit:boolean)=>{
    if(locked.current||!enabled)return;
    locked.current=true;setBusy(true);setError('');setMessage('');const current=++ticket.current;
    try {
      let formId:string|undefined;
      if(submit){
        if(!onCommand||!mode)throw new Error('请明确选择实物定义。');
        formId=crypto.randomUUID();
        const content=sampleCommand({experiment_id:experimentId,expected_revision:view.revision,form_id:formId,mode,minimum_valid:minimum,
          mapping:mode==='MAPPED'&&!csv?view.sources.map(row=>({source_ref:row.source_ref,sample_id:(mapping[row.source_ref]??'').trim()})):[],
          ...(mode==='MAPPED'&&csv?{mapping_csv:csv}:{})});
        await onCommand(content);
      }
      const next=await read();if(current!==ticket.current)return;
      if(formId&&next.form_id!==formId)throw new Error('提交未应用，请核对对话结果。输入已保留；可刷新最新定义后重试。');
      accept(next);setMessage(submit?'已保存派生报告，原训练与 Study 保留。':'已读取最新定义，未生成或修改报告。');
    }catch(failure){if(current===ticket.current)setError(failure instanceof Error?failure.message:'读取或提交失败，输入已保留。');}
    finally{locked.current=false;if(current===ticket.current)setBusy(false);}
  };
  const chooseCsv=async()=>{
    const current=ticket.current;
    try {const {open}=await import('@tauri-apps/plugin-dialog');const path=await open({multiple:false,filters:[{name:'分组表',extensions:['csv']}]});
      if(current===ticket.current&&typeof path==='string')setCsv(path);
    }catch{if(current===ticket.current)setError('无法打开文件选择器，可填写完整分组表。');}
  };
  const disabled=busy||!enabled;
  return <section aria-label="实物评价定义与报告">
    <h4>实物评价（报告阶段）</h4>
    <SampleReport view={view} classes={classes}/>
    {!view.applicable?<p>{view.unavailable_reason??'当前报告要求有原图来源。NPZ 的 groups 可能表示批次，不能自动解释为实物编号，本阶段不支持从该字段派生实物报告。'}</p>:<details>
      <summary>声明或调整实物定义</summary>
      <fieldset disabled={disabled}>
        <label>数据中的实物关系 <select value={mode} onChange={event=>setMode(event.target.value as SampleMode|'')}>
          <option value="">请选择，不自动推断</option><option value="IMAGE">IMAGE：一图一物</option>
          <option value="MAPPED">MAPPED：多图一物，提供完整分组表</option><option value="MIXED">MIXED：一图多物／混合材质，实物评价不适用</option>
        </select></label>
        <p>一图一物须由你明确声明；多图一物复用 sample_id，同一个编号的所有图必须同类别。batch 不能代替实物编号。</p>
        <label>最少有效观测 N <input type="number" min="1" max="1000000" value={minimum} onChange={event=>setMinimum(Number(event.target.value))}/></label>
        {mode==='MAPPED'&&<><p>CSV 列为 source（HDR绝对路径）、sample_id；需完整覆盖训练和测试的每幅图。也可填写下表，相同 sample_id 表示同一实物。</p>
          <button type="button" onClick={()=>void chooseCsv()}>选择分组表 CSV</button>{csv&&<p>已选择：{csv} <button onClick={()=>setCsv('')}>改用下表</button></p>}
          {!csv&&<div className="experiment-table"><table><thead><tr><th>原图</th><th>用途</th><th>sample_id</th></tr></thead><tbody>
            {view.sources.map(row=><tr key={row.source_ref}><th title={row.source_ref}>{row.name} · {row.source_ref.slice(0,8)}</th><td>{row.roles.join(' / ')}</td><td>
              <input aria-label={`${row.name} sample_id`} value={mapping[row.source_ref]??''} maxLength={160} onChange={event=>setMapping({...mapping,[row.source_ref]:event.target.value})}/>
            </td></tr>)}
          </tbody></table></div>}
        </>}
        <p>同实物所有图的观测合并投票；真值必须唯一；平票排除。阈值针对保存的有效观测，不等于原图全部前景像元。</p>
        <button disabled={!mode||!onCommand} onClick={()=>void run(true)}>保存定义并生成实物报告</button>
      </fieldset>
    </details>}
    <button disabled={disabled} onClick={()=>void run(false)}>刷新定义（替换本表单未保存输入）</button>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  </section>;
}
