import { useEffect, useRef, useState } from 'react';
import { agent } from './api';
import type { AssistantSession } from './useSession';
import PipelineEditor from '../preprocess/PipelineEditor';
import { compilePipeline } from '../preprocess/pipeline';
import type { Step } from '../preprocess/types';
import { draftEvents, recipeEvents } from '../preprocess/recipe-events';
import ClassificationFields from './ClassificationPreprocessingFields';
import { formCommand, recipeMemberStatus, validateClassification, type EditorKind, type EditorState, type ExperimentStep } from './preprocessing-form';
import './preprocessing-editor.css';

export default function PreprocessingEditorCard({ session, kind, onClose }: {
  session: AssistantSession; kind: EditorKind; onClose(): void;
}) {
  const [data, setData] = useState<EditorState | null>(null);
  const [steps, setSteps] = useState<EditorState['steps']>([]);
  const [axisId, setAxisId] = useState(''), [recipeId, setRecipeId] = useState(''), [name, setName] = useState('');
  const [targets, setTargets] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false), [stale, setStale] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState('');
  const live = useRef(true), serial = useRef(0), owner = useRef(session.active?.id);
  owner.current = session.active?.id;
  const localBusy = useRef(false);
  const edited = useRef(false); edited.current = dirty;
  const disabled = busy || !session.canSend || !!session.state.pending;
  const scopeTargets = targets.filter(id => session.records.some(row => row.id === id && (!('available' in row) || row.available !== false)));
  const accept = (next: EditorState) => { setData(next); setSteps(next.steps); setName(next.name); setRecipeId(next.recipe_id ?? ''); setDirty(false); setStale(false); };
  const read = async (axis = axisId) => {
    const ticket = ++serial.current;
    const id = await session.ensureSession();
    const next = await agent.preprocessingEditor(id, kind, kind === 'recipe' && axis ? axis : undefined);
    if (!live.current || ticket !== serial.current || owner.current && owner.current !== id) return null;
    return next;
  };
  const reload = async () => {
    setBusy(true); setError('');
    try { const next = await read(); if (next) accept(next); }
    catch { if (live.current) setError('无法读取当前草稿，请重试。'); }
    finally { if (live.current) setBusy(false); }
  };
  const reloadCurrent = useRef(reload); reloadCurrent.current = reload;
  useEffect(() => { live.current = true; void reload(); return () => { live.current = false; serial.current++; }; }, []);
  const journal = session.state.entries.length;
  useEffect(() => {
    if (session.state.busy || localBusy.current) return;
    if (edited.current) { setStale(true); return; }
    void reload();
  }, [journal, session.state.busy]);
  useEffect(() => {
    const changed = () => { if (edited.current) setStale(true); else if (!localBusy.current) void reloadCurrent.current(); };
    draftEvents.addEventListener('change', changed); recipeEvents.addEventListener('change', changed);
    return () => { draftEvents.removeEventListener('change', changed); recipeEvents.removeEventListener('change', changed); };
  }, []);
  const submit = async (action: 'open' | 'update' | 'save', selectedRecipe?: string) => {
    if (disabled || localBusy.current) return;
    setError(''); setMessage('');
    try {
      let submitted = steps;
      if (action === 'update') {
        if (kind === 'classification') validateClassification(steps as ExperimentStep[]);
        else {
          if (!data) throw new Error('请先载入配方草稿。');
          if (!axisId && steps.some(step => ['crop', 'resample'].includes(step.op)))
            throw new Error('裁剪和重采样需要选择波长轴参考样品。');
          // Without a sample, check parameter syntax now and leave the band
          // limits to the existing per-sample execution validation.
          submitted = compilePipeline(steps as Step[], data.axis, axisId ? data.bands : Number.MAX_SAFE_INTEGER).steps;
        }
      }
      localBusy.current = true; setBusy(true);
      const formId = crypto.randomUUID();
      const body = { kind, action, form_id: formId, ...(action === 'open' ? { recipe_id: selectedRecipe || null } : {
        draft_id: data?.draft_id, expected_revision: data?.revision,
        ...(action === 'update' ? { steps: submitted, ...(kind === 'recipe' ? { ...(axisId ? { axis_cube_id: axisId } : {}), ...(name.trim() ? { name: name.trim() } : {}) } : {}) }
          : { recipe_id: data?.recipe_id, name: name.trim() || data?.name }),
      }) };
      await session.request({ content: formCommand(body) }, { preserveComposer: true });
      const next = await read();
      if (!next) return;
      const applied = next.last_form_id === formId && next.last_form_ok;
      if (applied) { accept(next); setMessage(action === 'save' ? '已保存配方，未执行处理。' : '已更新草稿，未执行处理或训练。'); }
      else { setStale(true); setError('未能应用这次提交，请核对对话中的结果。输入已保留，可刷新最新草稿。'); }
    } catch (failure) { if (live.current) setError(failure instanceof Error ? failure.message : '表单提交失败，请核对对话记录。'); }
    finally { localBusy.current = false; if (live.current) setBusy(false); }
  };
  const changeAxis = async (id: string) => {
    setAxisId(id); setBusy(true); setError('');
    try { const next = await read(id); if (next) setData(current => current ? { ...current, axis: next.axis, bands: next.bands, axis_cube_id: id } : next); }
    catch { if (live.current) setError('参考样品元数据读取失败。'); }
    finally { if (live.current) setBusy(false); }
  };
  return <section className="preprocessing-editor" aria-label={kind === 'classification' ? '分类预处理参数表单' : '高级配方参数表单'}>
    <header><strong>{kind === 'classification' ? '分类训练预处理' : '回归／高级配方'}</strong><button type="button" onClick={onClose}>关闭表单</button></header>
    {busy && <p role="status">正在同步草稿…</p>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {stale && <p role="status">方案可能已更新，当前填写内容已保留。提交仍会校验修订号；刷新会载入服务端最新内容。</p>}
    <button type="button" disabled={busy} onClick={() => void reload()}>刷新最新草稿{dirty ? '（放弃当前填写）' : ''}</button>
    {kind === 'recipe' && <fieldset disabled={disabled}><legend>配方与样品</legend>
      <label>已有配方<select value={recipeId} onChange={event => setRecipeId(event.target.value)}><option value="">选择配方</option>
        {data?.recipes.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      <button type="button" disabled={!recipeId} onClick={() => void submit('open', recipeId)}>载入配方草稿</button>
      <button type="button" onClick={() => void submit('open')}>新建空白草稿</button>
      <label>波长轴参考样品<select value={axisId} onChange={event => void changeAxis(event.target.value)}><option value="">请选择</option>
        {session.records.filter(row => !('available' in row) || row.available !== false).map(row => <option key={row.id} value={row.id}>{row.display_name ?? row.id}</option>)}</select></label>
      <p>参考样品用于波段校验；未选择时仅检查参数格式，裁剪和重采样必须选择参考。实际执行时仍逐个校验所选样品。</p>
    </fieldset>}
    {data?.draft_id ? <form onSubmit={event => { event.preventDefault(); void submit('update'); }}>
      <p>当前草稿修订 {data.revision}</p>
      {kind === 'classification' ? <ClassificationFields steps={steps as ExperimentStep[]} disabled={disabled || !!data.busy}
        onChange={next => { setSteps(next); setDirty(true); }} /> : <>
        <label>{data.recipe_id ? '当前配方名称' : '新配方名称'}<input value={name} disabled={disabled || !!data.recipe_id} maxLength={80} onChange={event => { setName(event.target.value); setDirty(true); }} /></label>
        <PipelineEditor steps={steps as Step[]} initialAxis={data.axis} bands={axisId ? data.bands : Number.MAX_SAFE_INTEGER} disabled={disabled}
          onChange={next => { setSteps(next); setDirty(true); }} />
      </>}
      <button type="submit" disabled={disabled || !dirty || !!data.busy}>提交参数到当前草稿</button>
      {kind === 'recipe' && <button type="button" disabled={disabled || dirty || !name.trim()} onClick={() => void submit('save')}>保存当前配方（不执行）</button>}
    </form> : !busy && <p>{kind === 'classification' ? '当前还没有分类训练方案，请先在对话中选择已标注数据或配置训练来源。' : '请选择已有配方，或新建空白草稿。'}</p>}
    {kind === 'recipe' && <fieldset disabled={disabled}><legend>后续处理范围</legend>
      <p>选择要处理的样品，保存配方后可将请求填入对话；此处不会自动执行。</p>
      {session.records.map(row => <label key={row.id}><input type="checkbox" disabled={'available' in row && row.available === false} checked={scopeTargets.includes(row.id)} onChange={event =>
        setTargets(current => event.target.checked ? [...current, row.id] : current.filter(id => id !== row.id))} />
        {row.display_name ?? row.id} · {{ ready: '此配方结果可用', need_annotation: '待保存标注', need_preprocess: '待按此配方处理' }[recipeMemberStatus(data, row.id)]}
      </label>)}
      <p>本次选择 {scopeTargets.length} 个样品；{scopeTargets.filter(id => recipeMemberStatus(data, id) !== 'ready').length} 个尚无此配方的可用结果。</p>
      <button type="button" disabled={dirty || !data?.recipe_id || !scopeTargets.length} onClick={() => {
        session.setContent(current => current.trim() ? current : `使用配方“${data!.name}”，对样品 ${scopeTargets.join('、')} 执行预处理，请先查询并核对该配方和样品范围。`);
        setMessage('处理请求已填入对话，核对范围后点击发送。');
      }}>将处理请求填入对话</button>
    </fieldset>}
  </section>;
}
