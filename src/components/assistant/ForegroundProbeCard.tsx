import {useEffect,useState} from 'react';
import {agent,type ForegroundProbe} from './api';

export default function ForegroundProbeCard({sessionId,enabled,canAct,send}:{
  sessionId:string;enabled:boolean;canAct:boolean;send:(text:string)=>void;
}) {
  const [probe,setProbe]=useState<ForegroundProbe|null>(null);
  const [error,setError]=useState(false);
  useEffect(()=>{
    if(!enabled)return;
    let current=true;
    void agent.foregroundProbe(sessionId).then(value=>{if(current)setProbe(value);}).catch(()=>{if(current)setError(true);});
    return()=>{current=false;};
  },[sessionId,enabled]);
  if(error)return <p role="alert">无法读取前景探查预览。</p>;
  if(!probe)return <p role="status">正在读取前景探查预览…</p>;
  return <section className="experiment-task-card" aria-label="前景探查">
    <h3>前景探查 · {probe.sample}</h3>
    <p>{probe.note}</p>
    {probe.png_base64&&<img className="experiment-plot" src={'data:image/png;base64,'+probe.png_base64} alt="前景筛选采样预览，黑色为低亮度，浅灰为边缘"/>}
    {probe.sample_retained!==undefined&&<p>采样保留 {(probe.sample_retained*100).toFixed(1)}% · 估计左／右边缘 {probe.estimated_left}／{probe.estimated_right} 列</p>}
    {probe.current&&<><button disabled={!canAct} onClick={()=>send('采用前景建议')}>采用前景建议</button>
      <button disabled={!canAct} onClick={()=>send('关闭前景筛选')}>关闭前景筛选</button></>}
  </section>;
}
