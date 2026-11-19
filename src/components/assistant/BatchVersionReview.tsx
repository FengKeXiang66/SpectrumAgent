import {useEffect,useRef,useState} from 'react';
import {agent, type BatchAssessment, type BatchCard} from './api.ts';
import {datasets} from '../datasets/api.ts';
import type {DatasetVersionItem} from '../datasets/types.ts';
import {displayName} from '../datasets/types.ts';
import type {AssistantSession} from './useSession.ts';
import {sameMembers,shortVersion} from './presentation.ts';
import {requestError} from './sse.ts';

export function validVersionMembers(v: DatasetVersionItem): boolean {
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  return uuid.test(v.id) && v.is_frozen===1 && Number.isSafeInteger(v.cube_count) && v.cube_count>0
    && Array.isArray(v.cube_ids) && v.cube_ids.length===v.cube_count && v.cube_ids.every(id=>uuid.test(id))
    && new Set(v.cube_ids).size===v.cube_count;
}

// All asynchronous state and actions belong to one live card. No check is an
// execution token; the explicit execute button sends a normal ledger message.
// 2026-11-13 simplification: one global session only, so there is no scope
// mismatch to resolve and no work session to create — review then execute.
export default function BatchVersionReview({session,card}: {session:AssistantSession;card:BatchCard}) {
  const [versions,setVersions]=useState<DatasetVersionItem[]>([]);
  const [selected,setSelected]=useState<DatasetVersionItem|null>(null);
  const [check,setCheck]=useState<BatchAssessment|null>(null);
  const [loading,setLoading]=useState(false),[error,setError]=useState('');
  const sequence=useRef(0);
  useEffect(()=>()=>{sequence.current++;},[card.key,session.selectionEpoch]);
  const active=()=>session.isBatchActive(card) && !!card.sessionId && card.sessionId===session.active?.id;
  const disabled=!session.enabled || session.state.busy || !!session.state.pending || !active();
  const valid=(ticket:number)=>ticket===sequence.current && active();
  const load=async()=>{
    if(disabled || loading)return;
    const ticket=++sequence.current;setLoading(true);setError('');setSelected(null);setCheck(null);
    try {
      const rows=await datasets.listDatasetVersions();
      if(!valid(ticket))return;
      if(!rows.every(validVersionMembers))throw new Error('冻结版本完整成员清单无法核验，请刷新核对。');
      setVersions(rows);session.rememberVersions(card,rows.map(v=>v.id));
    }catch(e){if(valid(ticket))setError(requestError(e));}finally{if(valid(ticket))setLoading(false);}
  };
  const inspect=async(v:DatasetVersionItem)=>{
    if(disabled || loading || !validVersionMembers(v))return;
    const ticket=++sequence.current;setLoading(true);setError('');setSelected(v);setCheck(null);
    try {const value=await agent.checkBatchPrepare(card.sessionId!,v.id);if(valid(ticket))setCheck(value);}
    catch(e){if(valid(ticket))setError(requestError(e));}finally{if(valid(ticket))setLoading(false);}
  };
  const known=[...session.knownVersionIds,...versions.map(v=>v.id)];
  const original=versions.find(v=>v.id===card.result?.datasetVersionId);
  return <section aria-label="批量分割下一步核对">
    <button disabled={disabled||loading} onClick={()=>void load()}>核对其他已冻结版本</button>
    {versions.map(v=><button key={v.id} disabled={disabled||loading} onClick={()=>void inspect(v)}>版本 {shortVersion(v.id,known)} · {v.cube_count}个样品</button>)}
    {selected && <section aria-label="所选版本真实成员">
      <p>版本 {shortVersion(selected.id,known)} · {selected.cube_count}个样品</p>
      <ol>{selected.cube_ids.slice(0,10).map(id=>{const row=session.records.find(r=>r.id===id);return <li key={id}>{row?displayName(row):'成员'} · {id}</li>;})}</ol>
      {selected.cube_ids.length>10 && <p>仅预览前10项；已取得并核对完整{selected.cube_ids.length}项集合。</p>}
      {original && <p>{sameMembers(original.cube_ids,selected.cube_ids)?'与原目标成员集合相同':'与原目标成员集合不同；数量相同也不表示同范围。'}</p>}
      <p>若你指“前五张”，请明确展示目录的排序或五个成员清单；只有成员集合一致的冻结版本才能代表该范围。这里按完整版本处理。</p>
      {check && <><p role="status">{check.detail}</p><p>检查结论 {check.assessment} · check_code {check.check_code} · constraint {check.constraint} · checked_at {check.checked_at}</p>
        <p>未检查运行时内存；不保证执行成功，执行时重新准入。</p></>}
      <button disabled={disabled||loading||check?.assessment!=='within_profile'} onClick={()=>{if(active() && check)void session.executeBatchVersion(card,check);}}>按已核对完整版本执行默认分割</button>
    </section>}
    {loading && <p>正在核对静态条件…</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
