import { useEffect, useState } from 'react';
import { agent, type ExperimentResult } from './api';

const number=(value:number|null|undefined)=>value==null?'未定义':value.toFixed(6);
const units:Record<string,string>={center_pixel:'中心像元',spectrum:'光谱样本'};
function Plot({sessionId,taskId,name,enabled}:{sessionId:string;taskId:string;name:string;enabled:boolean}) {
  const [image,setImage]=useState(''),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  useEffect(()=>{
    let active=true;setImage('');setError('');
    if(enabled)void agent.experimentPlot(sessionId,taskId,name).then(value=>{
      if(active){if(value.name!==name){setError('曲线身份不一致');return;}setImage('data:image/png;base64,'+value.png_base64);}
    }).catch(()=>{if(active)setError('曲线读取失败或产物校验未通过。');});
    return()=>{active=false;};
  },[sessionId,taskId,name,enabled,retry]);
  return error?<p role="alert">{error}<button disabled={!enabled} onClick={()=>setRetry(x=>x+1)}>重新读取曲线</button></p>
    :image?<img className="experiment-plot" alt={name.includes('processed')?'各类别处理后均值与标准差曲线':'各类别输入均值与标准差曲线'} src={image}/>:<p role="status">正在读取已保存的曲线…</p>;
}

export default function ExperimentResults({sessionId,taskId,enabled}:{sessionId:string;taskId:string;enabled:boolean}) {
  const [result,setResult]=useState<ExperimentResult|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [role,setRole]=useState<'train'|'test'>('test'),[stage,setStage]=useState<'input'|'processed'>('input');
  const [saving,setSaving]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{
    let active=true;setResult(null);setError('');
    if(enabled)void agent.experimentResult(sessionId,taskId).then(value=>{if(active)setResult(value);})
      .catch(()=>{if(active)setError('结果读取失败或产物校验未通过，未显示未经核验的数据。');});
    return()=>{active=false;};
  },[sessionId,taskId,enabled,retry]);
  async function save(kind:'report'|'bundle') {
    if(!result||saving)return;
    setSaving(true);setMessage('');
    try {
      const {save}=await import('@tauri-apps/plugin-dialog');
      const extension=kind==='report'?'html':'zip';
      const path=await save({title:kind==='report'?'保存可独立打开的HTML报告':'保存报告与指标包',
        defaultPath:`experiment-${result.experiment_id.slice(0,8)}.${extension}`,filters:[{name:extension.toUpperCase(),extensions:[extension]}]});
      if(!path)return;
      const saved=await agent.experimentExport(sessionId,taskId,kind,path);
      setMessage(saved.saved?`已保存，${saved.bytes} 字节。HTML可用浏览器打开；导出文件在退出应用后仍保留。`:'未保存文件。');
    } catch(e){setMessage(e&&typeof e==='object'&&'detail' in e?String(e.detail):'导出失败，服务器产物保留，请选择新的文件名后重试。');}
    finally{setSaving(false);}
  }
  if(error)return <p role="alert">{error}<button disabled={!enabled} onClick={()=>setRetry(x=>x+1)}>重新读取结果</button></p>;
  if(!result)return <p role="status">正在读取本地实验结果…</p>;
  const score=result.metrics[role],max=Math.max(1,...score.confusion.flat());
  return <section className="experiment-results" aria-label="实验结果">
    <h4>{result.name} · 训练与测试结果</h4>
    <p>实验 {result.experiment_id.slice(0,8)}。下列数值直接读取已保存产物，不重新训练。</p>
    <div role="group" aria-label="评价数据选择">
      <button aria-pressed={role==='train'} onClick={()=>setRole('train')}>训练集拟合</button>
      <button aria-pressed={role==='test'} onClick={()=>setRole('test')}>测试数据</button>
    </div>
    <p>评价单位：{units[score.evaluation_unit]??score.evaluation_unit}；用途：{score.purpose==='training_fit'?'训练拟合':score.purpose==='development_regression'?'开发复现核验':'独立测试'}。</p>
    {score.purpose==='development_regression'&&<p className="experiment-note">该数据用于既有方案的开发复现，不能作为新的独立泛化成绩。</p>}
    <div className="experiment-table"><table><caption>总体指标</caption><thead><tr><th>指标</th><th>数值</th></tr></thead><tbody>
      <tr><th>样本数／正确数</th><td>{score.n}／{score.correct}</td></tr><tr><th>准确率</th><td>{(score.accuracy*100).toFixed(2)}%</td></tr>
      {(['macro_precision','macro_recall','macro_f1','kappa','weighted_f1','balanced_accuracy'] as const).filter(key=>key in score).map(key=><tr key={key}><th>{{macro_precision:'宏平均精确率',macro_recall:'宏平均召回率',macro_f1:'宏平均 F1',kappa:'Kappa',weighted_f1:'加权 F1',balanced_accuracy:'平衡准确率'}[key]}</th><td>{number(score[key])}</td></tr>)}
    </tbody></table></div>
    <div className="experiment-table"><table><caption>各类别指标</caption><thead><tr><th>类别</th><th>真值样本数</th><th>精确率</th><th>召回率</th><th>F1</th></tr></thead><tbody>
      {score.per_class.map(row=><tr key={row.label}><th>{row.name}</th><td>{row.support}</td><td>{number(row.precision)}</td><td>{number(row.recall)}</td><td>{number(row.f1)}</td></tr>)}
    </tbody></table></div>
    <p>宏平均仅包括真值中出现的类别；无定义指标显示“未定义”。PLS响应未经概率校准。</p>
    <div className="experiment-table"><table><caption>混淆矩阵：行是真值，列是预测；单元格为计数</caption><thead><tr><th>真值 ↓ ／预测 →</th>{score.confusion_labels.map(id=><th key={id}>{result.classes[String(id)]??id}</th>)}</tr></thead><tbody>
      {score.confusion.map((row,i)=><tr key={score.confusion_labels[i]}><th>{result.classes[String(score.confusion_labels[i])]}</th>{row.map((value,j)=><td key={j} style={{backgroundColor:`rgba(30,130,210,${.04+.5*value/max})`}}>{value}</td>)}</tr>)}
    </tbody></table></div>
    <p>颜色按全矩阵最大计数缩放。</p>
    <h4>各类别代表性曲线</h4>
    <div role="group" aria-label="光谱处理阶段"><button aria-pressed={stage==='input'} onClick={()=>setStage('input')}>输入光谱</button><button aria-pressed={stage==='processed'} onClick={()=>setStage('processed')}>处理后曲线</button></div>
    <p>横轴：{stage==='processed'&&result.processed_axis==='component'?'PCA主成分序号':'波长（nm）'}。按每个观测等权求均值，阴影为总体标准差（ddof=0）。</p>
    <Plot sessionId={sessionId} taskId={taskId} name={`${role}_${stage}.png`} enabled={enabled}/>
    <p>图例编号：{Object.entries(result.classes).map(([id,name])=>`${id}=${name}`).join('，')}</p>
    <button disabled={!enabled||saving} onClick={()=>void save('report')}>导出完整HTML报告</button>
    <button disabled={!enabled||saving} onClick={()=>void save('bundle')}>导出报告与指标包</button>
    <p>导出包包含报告、指标、混淆矩阵、曲线、配置与来源记录；不含模型、逐样本预测和原始数据。</p>
    {message&&<p role="status">{message}</p>}
  </section>;
}
