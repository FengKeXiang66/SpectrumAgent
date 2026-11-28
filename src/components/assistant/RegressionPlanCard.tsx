import { useEffect, useRef, useState } from 'react';
import { agent } from './api';
import type { AssistantSession } from './useSession';
import { regressionCommand, validateRegression, type RegressionDocument, type RegressionPlanView } from './regression-plan-form';
import ResultCard from './ResultCard';
import './preprocessing-editor.css';

export function RegressionReview({ data }: { data: RegressionPlanView }) {
  const review = data.review;
  if (!review) return null;
  const name = (id: string) => data.members.find(row => row.cube_id === id)?.name ?? id;
  const doc = data.document;
  return <section aria-label="回归方案审阅">
    <h4>确认本次训练方案 · 修订 {data.revision}</h4>
    <p>PLS 回归 · {review.target_name}{review.unit ? `（${review.unit}）` : ''} · {review.input_stage}</p>
    <p>KS 测试比例 {doc.test_ratio}；内层 {doc.cv_strategy === 'loo' ? '留一法' : `${review.inner_folds} 折`}；seed {doc.seed}。</p>
    <p>LV：{doc.n_components == null ? `训练集内按 RMSECV 选优及肘点规则，配置上限 ${doc.max_components}` : `固定 ${doc.n_components}`}。当前样品数与原始波段给出的上限 {review.lv_upper_bound}，实际还受折内变换维数和秩约束。</p>
    <p>{review.note}</p>
    <p>评价指标：{review.metrics.join('、')}。协议：{review.training_protocol}</p>
    <details><summary>预处理步骤及参数</summary>{review.pipeline.steps.length ? <ol>{review.pipeline.steps.map((step, i) =>
      <li key={i}>{step.op} v{step.version} · {JSON.stringify(step.params)}</li>)}</ol> : <p>原谱，无附加变换。</p>}</details>
    <table><thead><tr><th>样品</th><th>测量值</th><th>用途</th></tr></thead><tbody>{review.values.map(row => <tr key={row.cube_id}>
      <td>{name(row.cube_id)}</td><td>{row.value}</td><td>{review.train_cube_ids.includes(row.cube_id) ? '训练／内层验证' : '独立测试'}</td>
    </tr>)}</tbody></table>
    {review.coverage_repaired && <p>KS 划分使用了连续量覆盖修正规则；具体名单如上，测试集不参与预处理拟合或 LV 选优。</p>}
  </section>;
}

export default function RegressionPlanCard({ session, onClose }: { session: AssistantSession; onClose(): void }) {
  const [data, setData] = useState<RegressionPlanView | null>(null), [doc, setDoc] = useState<RegressionDocument>({});
  const [dirty, setDirty] = useState(false), [stale, setStale] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const live = useRef(true), serial = useRef(0), submitting = useRef(false), edited = useRef(false), owner = useRef(session.active?.id);
  owner.current = session.active?.id; edited.current = dirty;
  const disabled = busy || !session.canSend || !!session.state.pending || data?.status === 'running';
  const accept = (next: RegressionPlanView) => { setData(next); setDoc(next.document); setDirty(false); setStale(false); };
  const read = async () => {
    const ticket = ++serial.current, sid = await session.ensureSession();
    const next = await agent.regressionPlan(sid);
    return live.current && ticket === serial.current && (!owner.current || owner.current === sid) ? next : null;
  };
  const refresh = async () => {
    setBusy(true); setError('');
    try { const next = await read(); if (next) accept(next); }
    catch { if (live.current) setError('无法读取回归方案，请重试。'); }
    finally { if (live.current) setBusy(false); }
  };
  useEffect(() => { live.current = true; void refresh(); return () => { live.current = false; serial.current++; }; }, []);
  useEffect(() => {
    if (session.state.busy || submitting.current) return;
    if (edited.current) { setStale(true); return; }
    void refresh();
  }, [session.state.entries.length, session.state.busy]);
  useEffect(() => {
    if (data?.status !== 'running' || busy || session.state.busy) return;
    const timer = window.setTimeout(() => void refresh(), 1500);
    return () => window.clearTimeout(timer);
  }, [data, busy, session.state.busy]);
  const change = (patch: Partial<RegressionDocument>) => { setDoc(current => ({ ...current, ...patch })); setDirty(true); setNotice(''); };
  const submit = async (action: 'save' | 'review' | 'execute') => {
    if (disabled || submitting.current || !data) return;
    setError(''); setNotice('');
    try {
      if (action === 'save') validateRegression(doc);
      if (action !== 'save' && dirty) throw new Error('请先保存当前填写内容。');
      const formId = crypto.randomUUID();
      submitting.current = true; setBusy(true);
      await session.request({ content: regressionCommand({ action, form_id: formId, expected_revision: data.revision,
        ...(action === 'save' ? { patch: { ...doc, expected_revision: data.revision } } : {}),
        ...(action === 'execute' ? { review_digest: data.review_digest } : {}),
      }) }, { preserveComposer: true });
      const next = await read();
      if (!next) return;
      if (next.last_form_id === formId && next.last_form_ok) { accept(next); setNotice(action === 'save' ? '已保存，尚未训练。' : action === 'review' ? '请核对下方方案，再确认训练。' : '请查看运行状态与报告。'); }
      else { setData(next); setStale(true); setError('提交未完成，请核对对话结果。当前填写内容已保留；重新审阅前请刷新最新方案。'); }
    } catch (failure) { if (live.current) setError(failure instanceof Error ? failure.message : '方案提交失败。'); }
    finally { submitting.current = false; if (live.current) setBusy(false); }
  };
  const number = (text: string) => text.trim() === '' ? undefined : Number(text);
  return <section className="preprocessing-editor" aria-label="回归训练方案表单">
    <header><strong>回归训练方案</strong><button onClick={onClose}>关闭表单</button></header>
    {busy && <p role="status">正在核对或执行，请等待…</p>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {stale && <p>服务端方案可能已经变化。输入已保留；刷新会载入最新方案。</p>}
    <button disabled={busy} onClick={() => void refresh()}>刷新最新方案{dirty ? '（放弃当前填写）' : ''}</button>
    {data && <><p>状态：{({ draft: '待审阅', reviewed: '已审阅', running: '训练中', succeeded: '训练完成', failed: '失败，请重新审阅', interrupted: '执行中断，请核对已有运行后重新审阅' } as Record<string,string>)[data.status] ?? data.status} · 修订 {data.revision}</p>
      {data.error && <p role="alert">{data.error}</p>}
      <form onSubmit={e => { e.preventDefault(); void submit('save'); }}><fieldset disabled={disabled}>
        <legend>样品与连续量</legend>
        <p>先保存标注并按配方处理，再选择当前可用结果。每张原图只能选一个结果；全部样品须有测量值且使用相同配方。</p>
        <label>连续量字段<select value={doc.target_schema_id ?? ''} onChange={e => change({ target_schema_id: e.target.value })}><option value="">请选择</option>
          {data.schemas.map(row => <option key={row.id} value={row.id}>{row.name}{row.unit ? `（${row.unit}）` : ''}</option>)}</select></label>
        {!data.schemas.length && <p>暂无连续量字段。可在对话中创建字段，并逐样品填写或导入测量值。</p>}
        {data.members.map(member => <label key={member.cube_id}><input type="checkbox" disabled={!member.run_id || member.status !== 'ready'}
          checked={!!member.run_id && !!doc.preprocess_run_ids?.includes(member.run_id)} onChange={e => change({ preprocess_run_ids: e.target.checked ?
            [...(doc.preprocess_run_ids ?? []), member.run_id!] : doc.preprocess_run_ids?.filter(id => id !== member.run_id) })} />
          {member.name} · {member.recipe_name ?? (member.status === 'need_annotation' ? '待标注' : '待预处理')} · 测量值：{data.targets.find(row => row.cube_id === member.cube_id && row.schema_id === doc.target_schema_id)?.value ?? '未填写'}
        </label>)}
        {(doc.preprocess_run_ids ?? []).filter(id => !data.members.some(row => row.run_id === id)).map(id => <p key={id}>所选引用已非当前可用结果：{id} <button type="button" onClick={() => change({ preprocess_run_ids: doc.preprocess_run_ids?.filter(value => value !== id) })}>移除此引用</button></p>)}
        <p>已选择 {doc.preprocess_run_ids?.length ?? 0} 个样品。</p>
      </fieldset><fieldset disabled={disabled}><legend>划分与 PLS 参数</legend>
        <button type="button" onClick={() => { change(data.template); setNotice('已选择 KS 五折模板：测试 1/3、seed 17、自动 LV 上限 10；保存后仍需审阅。'); }}>采用 KS 五折模板（查看并可修改）</button>
        <label>外层划分<select value={doc.split_strategy ?? ''} onChange={() => change({ split_strategy: 'ks' })}><option value="">请选择</option><option value="ks">KS（原始均值谱）</option></select></label>
        <label>测试比例<input type="number" step="any" value={doc.test_ratio ?? ''} onChange={e => change({ test_ratio: number(e.target.value) })} /></label>
        <label>内层验证<select value={doc.cv_strategy ?? ''} onChange={e => change({ cv_strategy: e.target.value as 'kfold' | 'loo' })}><option value="">请选择</option><option value="kfold">按样品 K 折</option><option value="loo">留一法</option></select></label>
        <label>K 折数（留一法按训练样品数计算）<input type="number" min={2} max={256} disabled={doc.cv_strategy === 'loo'} value={doc.cv_folds ?? ''} onChange={e => change({ cv_folds: number(e.target.value) })} /></label>
        <label>随机种子<input type="number" min={0} value={doc.seed ?? ''} onChange={e => change({ seed: number(e.target.value) })} /></label>
        <label>LV 选择<select value={doc.n_components === undefined ? '' : doc.n_components === null ? 'auto' : 'fixed'} onChange={e => change({ n_components: e.target.value === 'auto' ? null : e.target.value === 'fixed' ? 1 : undefined })}><option value="">请选择</option><option value="auto">训练集内选优</option><option value="fixed">固定 LV</option></select></label>
        {doc.n_components != null && <label>固定 LV<input type="number" min={1} value={doc.n_components} onChange={e => change({ n_components: number(e.target.value) })} /></label>}
        <label>LV 上限<input type="number" min={1} value={doc.max_components ?? ''} onChange={e => change({ max_components: number(e.target.value) })} /></label>
      </fieldset><button type="submit" disabled={disabled || !dirty}>保存方案（不训练）</button></form>
      <button disabled={disabled || dirty || !data.revision || data.status === 'succeeded'} onClick={() => void submit('review')}>核对输入并审阅方案（不拟合）</button>
      <RegressionReview data={data} />
      <button disabled={disabled || dirty || stale || data.status !== 'reviewed' || !data.review_digest} onClick={() => void submit('execute')}>确认以上方案并训练</button>
      {data.run_id && <p>运行引用：{data.run_id}；重复确认会复用本次运行。</p>}
      {data.status === 'succeeded' && data.run_id && <ResultCard summary={{ view_kind: 'regression', run_id: data.run_id }} />}
    </>}
  </section>;
}
