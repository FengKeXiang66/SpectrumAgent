import { useState } from 'react';
import type { StudyCandidate, StudyResult } from './api';
import { candidateCommand, candidatePage, candidatePageSize, compatibleCandidates, filterCandidates } from './study-ranking';
import { sampleReasons } from './sample-evaluation-form';
export { candidateCommand, topCandidates } from './study-ranking';
export const pct = (value?:number|null) => value==null?'—':(value*100).toFixed(2)+'%';

export function StudyProtocol({result}:{result:StudyResult}) {
  const sample=result.evaluation_target==='sample';
  const total=result.candidates.find(row=>row.sample_oof)?.sample_oof?.total;
  return <div aria-label="Study评价口径"><p><strong>evaluation_target: {sample?'sample · 实物':'pixel · 观测'}</strong> · {result.scoring??'fold_mean_macro_f1'}</p>
    {sample?<><p><strong>本次训练实物 n={total??result.group_count}</strong>；每个候选另列实际纳入数。实物 pooled OOF Macro-F1 为主排序，观测 pooled OOF 排名只作对照；不混排两种评价单位。</p>
      <p>实物定义 {result.sample_evaluation?.mode??'未记录'}；有效观测阈值 N={result.sample_evaluation?.minimum_valid??'未记录'}，作用于质量筛选／抽样后保存的观测，不等于全部前景像元。真值须唯一；合并所有视图保存的观测后投票，平票排除。</p>
      <p>折间均值与标准差仅作辅助，不是 pooled OOF 的误差条，不采用1-SE。小样本下名次差异不代表显著优劣。真值冲突、平票、观测不足的排除可能使候选覆盖率不同，请一起核对纳入数。</p>
      <p>任一验证折排除后缺某类实物：sample_metric_undefined，候选不进入实物排名，不降级为观测评分。{result.ranking_status==='sample_metric_undefined'?'本次没有可采用的实物候选。':''}</p></>
      :<p>主排序为观测级 CV 折均值，折间标准差用于既有1-SE规则；不能换算为实物级排名。缺少目标字段的历史记录按 pixel 展示。</p>}
  </div>;
}

export function StudyCandidateDetails({row,classes={}}:{row:StudyCandidate;classes?:Record<string,string>}) {
  if(!row.sample_oof)return null;
  const result=row.sample_oof;
  const label=(id:number|null)=>id==null?'无唯一类别':classes[String(id)]??id;
  return <details><summary>候选 {row.id} · 逐实物 OOF 与各折排除记录</summary>
    <p>观测排名 {row.pixel_rank??'—'} → 实物排名 {row.sample_rank??'无效'}；{row.rank_change==null?'未进入实物排名':row.rank_change>0?`提升 ${row.rank_change} 名`:row.rank_change<0?`下降 ${-row.rank_change} 名`:'名次相同'}。</p>
    <p>观测 OOF F1 {pct(row.pixel_oof_f1)} · 实物 OOF F1 {pct(row.cv_f1)} · 纳入 {result.included} / {result.total}；训练折观测拟合 F1 {pct(row.train_f1)}。</p>
    <p>排除原因（可重叠）：{Object.entries(result.exclusion_counts).map(([key,n])=>`${sampleReasons[key]??key} ${n}`).join('；')||'无'}。</p>
    <div className="experiment-table"><table><caption>保存的逐实物 OOF 预测（类别编号沿用训练配置）</caption><thead><tr><th>实物</th><th>图数</th><th>有效观测</th><th>真值</th><th>预测</th><th>投票计数</th><th>判对／排除原因</th></tr></thead><tbody>
      {result.rows.map(item=><tr key={item.sample_id}><th title={item.sample_id}>{item.display_id}</th><td>{item.image_count}</td><td>{item.valid}</td><td>{item.truth==null?Object.entries(item.truth_counts).map(([id,n])=>`${classes[id]??id}: ${n}`).join('；')||'无真值':label(item.truth)}</td><td>{label(item.prediction)}</td>
        <td>{Object.entries(item.votes).map(([id,n])=>`${classes[id]??id}: ${n}`).join('；')}</td><td>{item.correct==null?item.reasons.map(key=>sampleReasons[key]??key).join('；'):item.correct?'是':'否'}</td></tr>)}
    </tbody></table></div>
    {row.sample_folds?.map(fold=><div key={fold.fold}><p>第 {fold.fold} 折：纳入 {fold.included} / {fold.total} · {fold.defined?'指标可定义':`sample_metric_undefined · 缺少类别 ${fold.missing_classes.map(label).join('、')}`} · F1 {pct(fold.metrics?.macro_f1)}。</p>
      {fold.rows.filter(item=>item.status!=='included').map(item=><p key={item.sample_id}>{item.display_id}：{item.reasons.map(key=>sampleReasons[key]??key).join('；')}（有效观测 {item.valid}）</p>)}
    </div>)}
    {result.metrics&&<details><summary>OOF实物混淆矩阵与每类指标</summary><pre>{JSON.stringify(result.metrics,null,2)}</pre></details>}
  </details>;
}

export function CandidateTable({rows,result,title,enabled,adopt}:{rows:StudyCandidate[];result:StudyResult;
  title:string;enabled:boolean;adopt:(row:StudyCandidate)=>void}) {
  rows=rows.filter(row=>(row.evaluation_target??'pixel')===(result.evaluation_target??'pixel'));
  if(result.evaluation_target==='sample')return <>
    <div className="experiment-table"><table><caption>{title} · 实物 pooled OOF 主排名（折间波动仅辅助）</caption><thead><tr><th>候选</th><th>预处理</th><th>潜变量</th><th>实物 OOF Macro-F1</th><th>实物 OOF 准确率</th><th>实物纳入／总数</th><th>观测 OOF F1</th><th>观测／实物排名</th><th>折 F1 均值 ± SD（辅助）</th><th>操作</th></tr></thead><tbody>
      {rows.map(row=><tr key={row.id}><th>{row.id}{row.id===result.best&&<small>OOF 最高分</small>}</th><td>{row.name}</td><td>{row.n_components}</td><td>{pct(row.cv_f1)}</td><td>{pct(row.cv_accuracy)}</td>
        <td>{row.sample_oof?`${row.sample_oof.included} / ${row.sample_oof.total}`:'—'}</td><td>{pct(row.pixel_oof_f1)}</td><td>{row.pixel_rank??'—'}／{row.sample_rank??'无效'}</td><td>{pct(row.fold_f1_mean)} ± {pct(row.fold_f1_sd)}</td>
        <td>{row.error?<span role="status">{row.error}</span>:<button disabled={!enabled||row.cv_f1===undefined} onClick={()=>adopt(row)}>采用</button>}</td></tr>)}
    </tbody></table></div>{rows.map(row=><StudyCandidateDetails key={row.id} row={row} classes={result.classes}/>)}</>;
  return <div className="experiment-table"><table><caption>{title} · CV 折间均值 ± 标准差</caption>
    <thead><tr><th>候选</th><th>预处理</th><th>潜变量</th><th>CV Macro-F1</th><th>CV 准确率</th><th>训练 Macro-F1</th><th>训练准确率</th><th>操作</th></tr></thead>
    <tbody>{rows.map(row=><tr key={row.id} className={row.id===result.recommended?'study-recommendation':undefined}>
      <th>{row.id}{row.id===result.recommended&&<small>1-SE 推荐</small>}{row.id===result.best&&<small>最高分</small>}</th>
      <td>{row.name}</td><td>{row.n_components}</td>{row.error?<td colSpan={5}>{row.error}</td>:<>
        <td>{pct(row.cv_f1)} ± {pct(row.cv_f1_sd)}</td><td>{pct(row.cv_accuracy)} ± {pct(row.cv_accuracy_sd)}</td>
        <td>{pct(row.train_f1)}</td><td>{pct(row.train_accuracy)}</td>
        <td><button disabled={!enabled} onClick={()=>adopt(row)}>采用</button></td></>}
    </tr>)}</tbody>
  </table></div>;
}

export default function StudyLeaderboard({result,enabled,send}:{result:StudyResult;enabled:boolean;send:(text:string)=>void}) {
  const [name,setName] = useState('');
  const [search,setSearch] = useState('');
  const [eligible,setEligible] = useState(false);
  const [page,setPage] = useState(0);
  const candidates=compatibleCandidates(result);
  const rows = filterCandidates(candidates,name,search,eligible,result.one_se_threshold);
  return <section aria-label="完整候选排行榜">
    <h3>候选排行榜</h3>
    <StudyProtocol result={result}/>
    <div className="work-actions">
      <select aria-label="筛选预处理" value={name} onChange={event=>{setName(event.target.value);setPage(0);}}>
        <option value="">全部预处理</option>{[...new Set(candidates.map(row=>row.name))].map(option=><option key={option}>{option}</option>)}
      </select>
      <input aria-label="搜索候选" value={search} placeholder="按候选编号、预处理搜索"
        onChange={event=>{setSearch(event.target.value);setPage(0);}}/>
      {result.evaluation_target!=='sample'&&<label><input type="checkbox" checked={eligible} onChange={event=>{setEligible(event.target.checked);setPage(0);}}/>
        仅看达到 1-SE 下界（{pct(result.one_se_threshold)}）</label>}
    </div>
    {rows.length?<CandidateTable rows={candidatePage(rows,page)} result={result} title="完整候选"
      enabled={enabled} adopt={row=>send(candidateCommand(result.study_id,row.id))}/>:<p>没有符合条件的候选。</p>}
    <div className="work-actions"><button disabled={!page} onClick={()=>setPage(page-1)}>上一页</button>
      <span>{rows.length?'第 '+(page+1)+' / '+Math.ceil(rows.length/candidatePageSize)+' 页 · '+rows.length+' 条':'0 条'}</span>
      <button disabled={(page+1)*candidatePageSize>=rows.length} onClick={()=>setPage(page+1)}>下一页</button></div>
  </section>;
}
