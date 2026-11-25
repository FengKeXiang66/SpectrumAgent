import { useState } from 'react';
import type { StudyCandidate, StudyResult } from './api';
import { candidateCommand, candidatePage, candidatePageSize, filterCandidates } from './study-ranking';
export { candidateCommand, topCandidates } from './study-ranking';
export const pct = (value?:number) => value===undefined?'—':(value*100).toFixed(2)+'%';

export function CandidateTable({rows,result,title,enabled,adopt}:{rows:StudyCandidate[];result:StudyResult;
  title:string;enabled:boolean;adopt:(row:StudyCandidate)=>void}) {
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
  const rows = filterCandidates(result.candidates,name,search,eligible,result.one_se_threshold);
  return <section aria-label="完整候选排行榜">
    <h3>候选排行榜</h3>
    <div className="work-actions">
      <select aria-label="筛选预处理" value={name} onChange={event=>{setName(event.target.value);setPage(0);}}>
        <option value="">全部预处理</option>{[...new Set(result.candidates.map(row=>row.name))].map(option=><option key={option}>{option}</option>)}
      </select>
      <input aria-label="搜索候选" value={search} placeholder="按候选编号、预处理搜索"
        onChange={event=>{setSearch(event.target.value);setPage(0);}}/>
      <label><input type="checkbox" checked={eligible} onChange={event=>{setEligible(event.target.checked);setPage(0);}}/>
        仅看达到 1-SE 下界（{pct(result.one_se_threshold)}）</label>
    </div>
    {rows.length?<CandidateTable rows={candidatePage(rows,page)} result={result} title="完整候选"
      enabled={enabled} adopt={row=>send(candidateCommand(result.study_id,row.id))}/>:<p>没有符合条件的候选。</p>}
    <div className="work-actions"><button disabled={!page} onClick={()=>setPage(page-1)}>上一页</button>
      <span>{rows.length?'第 '+(page+1)+' / '+Math.ceil(rows.length/candidatePageSize)+' 页 · '+rows.length+' 条':'0 条'}</span>
      <button disabled={(page+1)*candidatePageSize>=rows.length} onClick={()=>setPage(page+1)}>下一页</button></div>
  </section>;
}
