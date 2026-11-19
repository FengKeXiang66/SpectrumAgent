import { useEffect, useRef, useState } from 'react';
import { annotations } from '../annotation/api.ts';
import type { Project } from '../annotation/types.ts';
import type { DatasetRecord } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import { preprocessing } from './api.ts';
import { draftEvents, recipeEvents } from './recipe-events.ts';
import { compilePipeline } from './pipeline.ts';
import { describePreprocessError, type Metrics, type Recipe, type Step, type RecipeDraft } from './types.ts';
import PipelineEditor from './PipelineEditor';
import './preprocess.css';
import './preprocess-skin.css';

export type PreprocessDesignState = {owner:string;draft:RecipeDraft|null;recipes:Recipe[];version:string;blocked:boolean;loadVersion:(id:string)=>Promise<void>};
export function MetricsView({ metrics, runId, steps }: { metrics: Metrics; runId: string; steps?: Pick<Step, 'op' | 'version'>[] }) {
  const provenance = <small>{steps ? steps.map(step => `算子 ${step.op} · 版本 ${step.version}`).join('；') || '无配方算子'
    : '算子 · 版本：报告待加载'} · run_id {runId}</small>;
  return <section className="pp-quality-card" aria-label="后端指标"><h3>后端逐像素指标</h3><p className="pp-hint">SNR 为谱均值 / 相邻波段一阶差分 RMS 的线性比值。</p><dl className="pp-metrics">
    {Object.entries(metrics.snr).map(([key, value]) => <div className={key === 'mean' ? 'pp-metric-hero' : undefined} key={key}><dt>SNR {key}</dt><dd>{value ?? '不适用'}</dd>{provenance}</div>)}
    {(['snr_nan_count', 'nan_spectra_skipped', 'interclass_distance', 'intraclass_variance', 'fisher'] as const).filter(key => key in metrics).map(key =>
      <div key={key}><dt>{key}</dt><dd>{metrics[key] ?? '不适用'}</dd>{provenance}</div>)}
  </dl><div className="pp-metric-notes"><p>{metrics.source}</p><p>{metrics.variance_definition}</p>
    {metrics.excluded_classes.map(item => <p key={item.label_index}>label_index {item.label_index} · {item.pixel_count}：{item.reason}</p>)}
    {[...metrics.boundaries, ...metrics.limitations].map((text, i) => <p key={i}>{text}</p>)}
  </div></section>;
}

export default function PreprocessPanel({ record, ensureOwnerSession, onDesignState }: { record: DatasetRecord; ensureOwnerSession?:()=>Promise<string>;onDesignState?:(state:PreprocessDesignState)=>void }) {
  const [recipes, setRecipes] = useState<Recipe[]>([]), [selected, setSelected] = useState<Recipe[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [recipeId, setRecipeId] = useState(''), [recipeVersion, setRecipeVersion] = useState('');
  const [steps, setSteps] = useState<Step[]>([]), [metadata, setMetadata] = useState({ code: '', name: '', description: '', note: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [message, setMessage] = useState('');
  const [owner, setOwner] = useState(''), [draft, setDraft] = useState<RecipeDraft|null>(null);
  const [draftDirty,setDraftDirty] = useState(false),[draftConflict,setDraftConflict] = useState(false);
  const [incomingDraft,setIncomingDraft] = useState<RecipeDraft|null>(null);
  const [recentDeleted,setRecentDeleted] = useState<Recipe|null>(null);
  const draftRef=useRef<RecipeDraft|null>(null), dirtyRef=useRef(false), stepsRef=useRef(steps), updatingDraft=useRef(false);
  const updateQueue=useRef<Promise<void>>(Promise.resolve()), updateRevisions=useRef(new Map<string,number>()),blockedDrafts=useRef(new Set<string>());
  const pendingUpdates=useRef(0);
  draftRef.current=draft;dirtyRef.current=draftDirty;stepsRef.current=steps;
  const applyDraft=(row:RecipeDraft)=>{draftRef.current=row;dirtyRef.current=false;updateRevisions.current.set(row.draft_id,row.revision);blockedDrafts.current.delete(row.draft_id);setDraft(row);setSteps(row.pipeline.steps);setMetadata(m=>({...m,...row.metadata}));setDraftDirty(false);setDraftConflict(false);setIncomingDraft(null);};
  useEffect(()=>{
    let valid=true;
    if(ensureOwnerSession)void ensureOwnerSession().then(async sid=>{
      const row=await preprocessing.currentDraft(sid)??await preprocessing.createDraft(sid);
      if(valid){setOwner(sid);applyDraft(row);}
    }).catch(e=>{if(valid)setError(describePreprocessError(e));});
    return()=>{valid=false;};
  },[]);
  useEffect(()=>{
    if(!draft?.source_recipe_version_id)return;
    const recipe=recipes.find(r=>r.versions.some(v=>v.id===draft.source_recipe_version_id));
    if(recipe){setRecipeId(recipe.id);setRecipeVersion(draft.source_recipe_version_id);setMetadata(m=>({...m,code:recipe.code,name:recipe.name,description:recipe.description??''}));}
  },[draft?.source_recipe_version_id,recipes]);
  useEffect(()=>{
    const changed=()=>{
      if(!owner)return;
      if(updatingDraft.current)return;
      if(dirtyRef.current){setDraftConflict(true);setMessage('共享草稿已更新，本地修改已保留；请读取最新修订后合并。');return;}
      void preprocessing.currentDraft(owner).then(row=>{if(row&&live.current)applyDraft(row);}).catch(e=>setError(describePreprocessError(e)));
    };
    draftEvents.addEventListener('change',changed);
    return()=>draftEvents.removeEventListener('change',changed);
  },[owner]);
  const editSteps=(next:Step[],nextMetadata?:RecipeDraft['metadata'])=>{
    setSteps(next);stepsRef.current=next;dirtyRef.current=true;setDraftDirty(true);
    const current=draftRef.current;
    if(!owner||!current)return;
    let pipeline={steps:next};
    try{pipeline=compilePipeline(next,record.dataset.wavelengths,record.dataset.shape[2]);}catch{/* Persist incomplete draft content. */}
    pendingUpdates.current++;updatingDraft.current=true;
    updateQueue.current=updateQueue.current.then(async()=>{
      try{
        if(blockedDrafts.current.has(current.draft_id))return;
        const row=await preprocessing.updateDraft(owner,current.draft_id,updateRevisions.current.get(current.draft_id)??current.revision,pipeline,nextMetadata);
        updateRevisions.current.set(row.draft_id,row.revision);
        if(live.current&&draftRef.current?.draft_id===row.draft_id){
          draftRef.current=row;setDraft(row);
          if(JSON.stringify(stepsRef.current)===JSON.stringify(next)){dirtyRef.current=false;setDraftDirty(false);}
        }
      }catch(e){blockedDrafts.current.add(current.draft_id);if(live.current){setDraftConflict(true);setError(describePreprocessError(e));}}
      finally{pendingUpdates.current--;updatingDraft.current=pendingUpdates.current>0;}
    });
  };
  useEffect(()=>{
    const changed=()=>{void preprocessing.listRecipes().then(rows=>{
      if(!live.current)return;
      setRecipes(rows);
      const allowed=new Set(rows.flatMap(r=>r.versions.map(v=>v.id)));
      setRecipeVersion(id=>allowed.has(id)?id:'');setRecipeId(id=>rows.some(r=>r.id===id)?id:'');
      if(project)void preprocessing.listProjectRecipes(project.id).then(setSelected);
    }).catch(e=>setError(describePreprocessError(e)));};
    recipeEvents.addEventListener('change',changed);return()=>recipeEvents.removeEventListener('change',changed);
  },[project]);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    void Promise.all([preprocessing.listRecipes(), annotations.projects(), annotations.versions(record.id)])
      .then(async ([library, projects, saved]) => {
        if (!live.current) return;
        setRecipes(library);
        const current = projects.find(item => item.id === saved.working.project_id) ?? null; setProject(current);
        if (current) {
          const chosen = await preprocessing.listProjectRecipes(current.id);
          if (live.current) setSelected(chosen);
        }
      }).catch(error => { if (live.current) setError(describePreprocessError(error)); });
    return () => { live.current = false; };
  }, [record.id]);
  const task = async (work: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await work(); } catch (error) { if (live.current) setError(describePreprocessError(error)); }
    finally { if (live.current) setBusy(false); }
  };
  const load = async (id: string, versionId?: string) => {
    await updateQueue.current;
    const recipe = await preprocessing.getRecipe(id);
    if (!live.current) return;
    const version = recipe.versions.find(v => v.id === versionId);
    if(!owner||!version)throw new Error('共享草稿尚未就绪，请稍后重试。');
    applyDraft(await preprocessing.createDraft(owner,version.id));
    setRecipeId(id); setRecipeVersion(version.id);
    setMetadata({ code: recipe.code, name: recipe.name, description: recipe.description ?? '', note: '' }); setMessage('编辑后须保存为新版本；历史版本不覆写。');
  };
  let invalid = '';
  try { compilePipeline(steps, record.dataset.wavelengths, record.dataset.shape[2]); } catch (error) { invalid = (error as Error).message; }
  const currentVersion = recipes.find(r => r.id === recipeId)?.versions.find(v => v.id === recipeVersion);
  let changed = true;
  try {
    if (currentVersion) changed = JSON.stringify(compilePipeline(steps, record.dataset.wavelengths, record.dataset.shape[2]))
      !== JSON.stringify(compilePipeline(currentVersion.pipeline.steps, record.dataset.wavelengths, record.dataset.shape[2]));
  } catch { /* Invalid drafts or stored versions cannot run. */ }
  if(draft&&!draftDirty&&currentVersion)changed=draft.validation_result.recipe_pipeline_sha256!==currentVersion.recipe_pipeline_sha256;
  useEffect(()=>{
    onDesignState?.({owner,draft,recipes,version:recipeVersion,blocked:busy||changed||draftDirty||draftConflict||!!invalid||!draft||pendingUpdates.current>0,
      loadVersion:async id=>{const recipe=recipes.find(r=>r.versions.some(v=>v.id===id));if(recipe)await task(()=>load(recipe.id,id));}});
  },[owner,draft,recipes,recipeVersion,busy,changed,draftDirty,draftConflict,invalid,onDesignState]);
  const save = async (newVersion: boolean) => {
    await updateQueue.current;
    if(!owner||!draftRef.current||draftConflict||blockedDrafts.current.has(draftRef.current.draft_id)||updatingDraft.current)throw new Error('请先等待草稿同步或合并修订冲突。');
    const pipeline = compilePipeline(steps, record.dataset.wavelengths, record.dataset.shape[2]);
    if (metadata.note.length > 2000) throw new Error('note 最多 2000 字符');
    let row=draftRef.current;
    if(draftDirty)row=await preprocessing.updateDraft(owner,row.draft_id,row.revision,pipeline);
    const saved=await preprocessing.saveDraft(owner,row.draft_id,{expected_revision:row.revision,
      ...(newVersion?{recipe_id:recipeId}:{code:metadata.code,name:metadata.name,description:metadata.description}),note:metadata.note||null});
    applyDraft(await preprocessing.getDraft(owner,row.draft_id));
    setRecipeId(saved.recipe_id);setRecipeVersion(saved.recipe_version_id);setRecipes(await preprocessing.listRecipes());
    setMessage('已保存不可变配方版本，尚未执行。');return saved;
  };
  return <section className="preprocess-panel" aria-label="S06 预处理工作台">
    <header className="pp-page-heading"><div className="pp-page-title"><h2>S06 · {displayName(record)}</h2><p>算子链一旦保存即成为可复用资产，任何一次实验都能引用它并复现出同样的输入。</p></div><span className="pp-project">项目：{project?.name ?? '未获取'}</span></header>
    <p role="status">{message}</p>{error && <pre role="alert">{error}{error.startsWith('INVALID_REQUEST') ? '\n请检查 code 是否重复及配方参数。' : ''}</pre>}
    <div className="pp-layout"><aside><h3>配方库（按 code）</h3><button disabled={busy||!owner} onClick={()=>{void task(async()=>{applyDraft(await preprocessing.createDraft(owner,undefined,true));setRecipeId('');setRecipeVersion('');setMetadata({code:'',name:'',description:'',note:''});});}}>新建草稿</button>
      {recipes.map(recipe => <section key={recipe.id}><strong>{recipe.code}</strong> · {recipe.name}
        <button disabled={busy} onClick={() => { void task(() => load(recipe.id,recipe.versions.at(-1)?.id)); }}>载入 v{recipe.versions.at(-1)?.version_no}</button>
        <button disabled={busy} onClick={()=>{void task(async()=>{await preprocessing.deleteRecipe(recipe.id);setRecentDeleted(recipe);setMessage('配方已在本次运行中删除，历史引用仍可读。');});}}>删除配方</button>
        <button disabled={busy || !project} onClick={() => { void task(async () => { if (!project) return;
          if (selected.some(r => r.id === recipe.id)) await preprocessing.deselectRecipe(project.id, recipe.id);
          else await preprocessing.selectRecipe(project.id, recipe.id);
          setSelected(await preprocessing.listProjectRecipes(project.id));
        }); }}>{selected.some(r => r.id === recipe.id) ? '取消项目选用' : '项目选用'}</button>
      </section>)}<p>项目选用为只读关联；取消不会删除配方。</p>
      {recentDeleted&&<button disabled={busy} onClick={()=>{void task(async()=>{await preprocessing.restoreRecipe(recentDeleted.id);setRecentDeleted(null);});}}>恢复 {recentDeleted.name}</button>}
    </aside><div className="pp-main">
      <p role="status">共享草稿 {draft?.draft_id.slice(0,8)??'准备中'} · revision {draft?.revision??'—'} · {draftConflict?'修订冲突':draftDirty?'同步中':draft?.validation_result.valid?'定义有效':'待补充参数'}；讨论和编辑不保存正式版本。</p>
      {draft?.differences?.map(change=><p key={change.field}>{change.field} · {change.change}</p>)}
      {draft?.validation_result.fields.map(field=><p key={field.field}>{field.field}：{field.message}</p>)}
      {draftConflict&&<button onClick={()=>{void task(async()=>{const row=await preprocessing.currentDraft(owner);if(row)setIncomingDraft(row);});}}>读取最新修订</button>}
      {incomingDraft&&<section aria-label="草稿冲突比较"><p>服务器 revision {incomingDraft.revision}；当前编辑保留。请比较后选择如何合并。</p>
        <pre>{JSON.stringify(incomingDraft.pipeline,null,2)}</pre>
        <button onClick={()=>applyDraft(incomingDraft)}>采用服务器草稿</button>
        <button onClick={()=>{void task(async()=>{await updateQueue.current;let pipeline={steps};try{pipeline=compilePipeline(steps,record.dataset.wavelengths,record.dataset.shape[2]);}catch{/* Incomplete drafts remain allowed. */}applyDraft(await preprocessing.updateDraft(owner,incomingDraft.draft_id,incomingDraft.revision,pipeline));});}}>按最新修订提交当前编辑</button>
      </section>}
      <fieldset className="pp-recipe-card" disabled={busy}><legend>命名与版本</legend><div className="pp-recipe-fields">{(['code', 'name', 'description', 'note'] as const).map(key => <label key={key}>{key}<input className={key === 'code' ? 'pp-code' : undefined} value={metadata[key]} maxLength={key === 'note' ? 2000 : undefined}
        onChange={e => {const next={...metadata,[key]:e.target.value};setMetadata(next);editSteps(stepsRef.current,next);}} /></label>)}
        {recipeId && <label>配方版本<select value={recipeVersion} onChange={e => { void task(() => load(recipeId, e.target.value)); }}>
          {recipes.find(r => r.id === recipeId)?.versions.map(v => <option key={v.id} value={v.id}>v{v.version_no}</option>)}</select></label>}</div>
        <div className="pp-recipe-actions">
        <button disabled={!!invalid || !metadata.code.trim() || !metadata.name.trim()||draftConflict||!draft} onClick={() => { void task(async()=>{await save(false);}); }}>保存为新配方</button>
        <button className="pp-primary" disabled={!!invalid || !recipeId||draftConflict||!draft} onClick={() => { void task(async()=>{await save(true);}); }}>保存为新版本</button>
        </div><p className="pp-hint">保存后可在建模与批量推理中引用；执行与结果请到「应用到样品」页。</p>
      </fieldset>
      <PipelineEditor steps={steps} onChange={editSteps} initialAxis={record.dataset.wavelengths} bands={record.dataset.shape[2]} disabled={busy||!draft} />
    </div></div>
  </section>;
}
