import { useEffect, useState } from 'react';
import { agent, type ArchivedExperiment, type ExperimentHistory as History, type ExperimentComparison } from './api';
import ExperimentResults from './ExperimentResults';
import type { OpenInferenceView } from './InferenceResultsView';

const statusNames:Record<string,string>={succeeded:'已完成',failed:'失败',running:'执行中',cancelled:'已取消',interrupted:'已中断',unreadable:'不可读'};
const phaseNames:Record<string,string>={checking:'检查输入',preparing:'准备数据',training:'预处理与训练',testing:'测试评价',reporting:'生成报告'};
const percent=(value:number|null|undefined)=>value==null?'—':(value*100).toFixed(2)+'%';
const unit=(value:string|undefined)=>value==='center_pixel'?'中心像元':value==='spectrum'?'光谱样本':value??'—';
const purpose=(value:string|undefined)=>value==='development_regression'?'开发复现核验':value==='independent_test'?'独立测试':value??'—';
const checks:Record<string,string>={evaluation_unit:'评价单位',test_usage:'测试用途',classes:'类别映射',input_declarations:'输入与划分声明',source_fingerprints:'来源指纹',wavelength_axis:'波长轴',metric_definition:'指标口径'};

export default function ExperimentHistory({sessionId,enabled,onInfer,onCommand,onInferenceView}:{sessionId:string;enabled:boolean;onInfer?:(id:string)=>void;onCommand?:(content:string)=>void;onInferenceView?:OpenInferenceView}) {
  const [page,setPage]=useState<History|null>(null),[offset,setOffset]=useState(0),[refresh,setRefresh]=useState(0);
  const [selected,setSelected]=useState<ArchivedExperiment|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [pair,setPair]=useState<string[]>([]),[comparison,setComparison]=useState<ExperimentComparison|null>(null);
  useEffect(()=>{setSelected(null);setPair([]);setComparison(null);setOffset(0);setPage(null);},[sessionId]);
  useEffect(()=>{
    let active=true;
    if(enabled) {
      setError('');
      void agent.experimentHistory(sessionId,offset).then(value=>{if(active)setPage(value);})
        .catch(()=>{if(active)setError('历史实验读取失败，请刷新重试。');});
    }
    return()=>{active=false;};
  },[enabled,sessionId,offset,refresh]);
  async function select(row:ArchivedExperiment) {
    setBusy(true);setError('');
    try {
      const value=await agent.selectExperiment(sessionId,row.experiment_id);
      if(value.archived_experiment_id!==row.experiment_id)throw new Error('实验身份不一致');
      setSelected({...row,status:value.status});
    } catch {setError('无法打开该实验，请刷新列表并核对归档文件。');}
    finally {setBusy(false);}
  }
  async function compare() {
    if(pair.length!==2)return;
    setBusy(true);setError('');setComparison(null);
    try {setComparison(await agent.compareExperiments(sessionId,pair[0],pair[1]));}
    catch {setError('对比失败：请选择两个成功的实验，并核对归档文件是否完整。');}
    finally {setBusy(false);}
  }
  return <section id="experiment-history-panel" className="experiment-history" aria-label="历史实验与归档模型">
      <p>保存已完成结果和模型；不保存原始输入文件副本。数据源移动后仍可查看报告，但新实验需重新指定来源。</p>
      <button disabled={!enabled||busy} onClick={()=>setRefresh(x=>x+1)}>刷新列表</button>
      {!enabled&&<p>当前引擎不可用，暂时无法读取归档。</p>}
      {error&&<p role="alert">{error}</p>}
      {!page?<p role="status">正在读取归档…</p>:<>
        <p>共 {page.total} 个实验；当前第 {page.total?offset+1:0}–{Math.min(offset+page.items.length,page.total)} 条。</p>
        <div className="experiment-table"><table><thead><tr><th>对比</th><th>实验</th><th>状态</th><th>测试准确率</th><th>评价单位／用途</th><th>操作</th></tr></thead><tbody>
          {page.items.map(row=><tr key={row.experiment_id}>
            <td><input type="checkbox" aria-label={`对比 ${row.name} ${row.experiment_id.slice(0,8)}`} checked={pair.includes(row.experiment_id)}
              disabled={busy||row.status!=='succeeded'||(pair.length>=2&&!pair.includes(row.experiment_id))} onChange={event=>{
                setPair(old=>event.target.checked?[...old,row.experiment_id]:old.filter(id=>id!==row.experiment_id));setComparison(null);
              }}/></td>
            <th>{row.name}<br/><small>{row.experiment_id.slice(0,8)} · {row.created_at?new Date(row.created_at).toLocaleString():'时间未知'}</small></th>
            <td>{statusNames[row.status]??row.status}</td><td>{percent(row.test_accuracy)}</td><td>{unit(row.evaluation_unit)}／{purpose(row.test_usage)}</td>
            <td><button disabled={!enabled||busy||row.status==='unreadable'} onClick={()=>void select(row)}>查看</button></td>
          </tr>)}
        </tbody></table></div>
        <button disabled={!enabled||busy||offset===0} onClick={()=>setOffset(x=>Math.max(0,x-20))}>上一页</button>
        <button disabled={!enabled||busy||offset+page.items.length>=page.total} onClick={()=>setOffset(x=>x+20)}>下一页</button>
        <button disabled={!enabled||busy||pair.length!==2} onClick={()=>void compare()}>比较选中的两个实验</button>
        {pair.length>0&&<p>已选：{pair.map(id=>id.slice(0,8)).join('、')}<button disabled={busy} onClick={()=>{setPair([]);setComparison(null);}}>清空选择</button></p>}
      </>}
      {comparison&&<section aria-label="历史实验对比">
        <p>{comparison.comparable?'输入与评价口径一致。':'输入或评价口径不同，仅并列展示，不能直接据此判断优劣。'}</p>
        {!comparison.comparable&&<p>不同项：{Object.entries(comparison.checks).filter(([,same])=>!same).map(([key])=>checks[key]??key).join('、')}</p>}
        <div className="experiment-table"><table><caption>保存指标对比</caption><thead><tr><th>指标</th><th>{comparison.first.slice(0,8)}</th><th>{comparison.second.slice(0,8)}</th></tr></thead><tbody>
          <tr><th>训练准确率</th>{comparison.metrics.map((score,i)=><td key={i}>{percent(score.train.accuracy)}</td>)}</tr>
          <tr><th>测试准确率</th>{comparison.metrics.map((score,i)=><td key={i}>{percent(score.test.accuracy)}</td>)}</tr>
          <tr><th>测试宏平均 F1</th>{comparison.metrics.map((score,i)=><td key={i}>{score.test.macro_f1.toFixed(6)}</td>)}</tr>
          <tr><th>测试样本数</th>{comparison.metrics.map((score,i)=><td key={i}>{score.test.n}</td>)}</tr>
          <tr><th>评价单位／用途</th>{comparison.metrics.map((score,i)=><td key={i}>{unit(score.test.evaluation_unit)}／{purpose(score.test.purpose)}</td>)}</tr>
        </tbody></table></div><p>{comparison.note}</p>
      </section>}
      {selected&&(selected.status==='succeeded'
        ?<ExperimentResults key={selected.experiment_id} sessionId={sessionId} experimentId={selected.experiment_id} enabled={enabled} onInfer={onInfer} onCommand={onCommand} onInferenceView={onInferenceView}/>
        :<p>实验 {selected.experiment_id.slice(0,8)}：{statusNames[selected.status]??selected.status}。{selected.phase&&`最后记录阶段：${phaseNames[selected.phase]??selected.phase}。`}已完成产物保留；未完成实验不自动续训。</p>)}
  </section>;
}
