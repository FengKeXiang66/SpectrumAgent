import assert from 'node:assert/strict';
import test from 'node:test';
import { candidateCommand, candidatePage, compatibleCandidates, filterCandidates, topCandidates } from '../src/components/assistant/study-ranking.ts';

const rows = Array.from({length:225},(_,index)=>({id:index+1,name:index%2?'SG1 / L2':'SG2 / SNV',
  n_components:2+index%15,cv_f1:index===224?undefined:1-index/1000,preprocessing:[]}));

test('compact ranking keeps ten rows with the highest score and the 1-SE recommendation',()=>{
  const top = topCandidates(rows,15);
  assert.equal(top.length,10);
  assert.equal(top[0].id,1);
  assert.equal(top[9].id,15);
  assert.deepEqual(topCandidates(rows,5).map(row=>row.id),rows.slice(0,10).map(row=>row.id));
});

test('full ranking filters candidate metadata, applies the 1-SE threshold and pages in groups of twenty',()=>{
  assert.equal(candidatePage(rows,0).length,20);
  assert.equal(candidatePage(rows,1)[0].id,21);
  assert.equal(candidatePage(rows,11).length,5);
  const subset = filterCandidates(rows,'SG1 / L2','sg1',true,.95);
  assert.ok(subset.length && subset.every(row=>row.name==='SG1 / L2'&&row.cv_f1>=.95));
  assert.deepEqual(filterCandidates(rows,'','225',true,0),[]);
  const id = '91c40554-657f-474f-9003-32c4967d0317';
  assert.equal(candidateCommand(id,225),'采用候选 225新建正式训练 '+id);
});

test('Study highlights render both choices and the viewer renders a twenty-row page',async()=>{
  const { createServer } = await import('vite');
  const { createElement } = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  const server = await createServer({server:{middlewareMode:true,watch:null},appType:'custom'});
  try {
    const { StudyHighlights } = await server.ssrLoadModule('/src/components/assistant/StudyCard.tsx');
    const { default: StudyLeaderboard } = await server.ssrLoadModule('/src/components/assistant/StudyLeaderboard.tsx');
    const result = {study_id:'91c40554-657f-474f-9003-32c4967d0317',best:1,recommended:15,one_se_threshold:.95,
      candidates:rows.map(row=>({...row,cv_f1_sd:.01,cv_accuracy:.9}))};
    const props = {result,enabled:true,send:()=>{}};
    const summary = renderToStaticMarkup(createElement(StudyHighlights,props));
    assert.match(summary,/1-SE 推荐候选/);
    assert.match(summary,/最高分候选/);
    assert.match(summary,/采用推荐方案新建正式训练/);
    assert.match(summary,/采用最高分方案新建正式训练/);
    const full = renderToStaticMarkup(createElement(StudyLeaderboard,props));
    assert.equal((full.match(/<tr[ >]/g)??[]).length,21);
    assert.match(full,/1-SE 推荐/);
    assert.match(full,/最高分/);
    assert.match(full,/225 条/);
    assert.match(full,/evaluation_target: pixel/);
  } finally {await server.close();}
});

test('sample ranking uses pooled OOF, shows both ranks and exclusions, and never mixes pixel rows',async()=>{
  const { createServer }=await import('vite');
  const { createElement }=await import('react');
  const { renderToStaticMarkup }=await import('react-dom/server');
  const server=await createServer({server:{middlewareMode:true,watch:null,hmr:false},appType:'custom'});
  try{
    const {StudyHighlights}=await server.ssrLoadModule('/src/components/assistant/StudyCard.tsx');
    const {default:Leaderboard}=await server.ssrLoadModule('/src/components/assistant/StudyLeaderboard.tsx');
    const object={sample_id:'egg-1',display_id:'egg-1',image_count:2,observations:100,valid:100,truth:1,prediction:2,
      truth_counts:{1:100},votes:{1:49,2:51},correct:false,status:'included',reasons:[]};
    const count={total:41,included:40,excluded:1,defined:true,missing_classes:[],exclusion_counts:{tie:1},rows:[object],metrics:null};
    const candidate={id:2,name:'原谱',preprocessing:[],n_components:2,evaluation_target:'sample',cv_f1:.65,cv_accuracy:.7,
      fold_f1_mean:.64,fold_f1_sd:.2,pixel_oof_f1:.82,pixel_rank:1,sample_rank:2,rank_change:-1,
      sample_oof:count,sample_folds:[{...count,fold:1,defined:false,missing_classes:[2]}]};
    const invalid={...candidate,id:3,name:'invalid-sample',cv_f1:undefined,error:'sample_metric_undefined',sample_rank:undefined,rank_change:null};
    const pixel={id:99,name:'do-not-mix-pixel',n_components:1,preprocessing:[],cv_f1:1};
    const result={study_id:'study',evaluation_target:'sample',scoring:'pooled_oof_sample_macro_f1',best:2,recommended:2,
      sample_evaluation:{mode:'IMAGE',minimum_valid:100},
      one_se_threshold:null,classes:{1:'受精',2:'未受精'},candidates:[candidate,invalid,pixel]};
    assert.deepEqual(compatibleCandidates(result).map(row=>row.id),[2,3]);
    assert.equal(filterCandidates([candidate],'','',true,null).length,0);
    const html=renderToStaticMarkup(createElement(Leaderboard,{result,enabled:true,send:()=>{}}));
    assert.match(html,/evaluation_target: sample/);assert.match(html,/实物 n=41/);assert.match(html,/40 \/ 41/);
    assert.match(html,/有效观测阈值 N=100/);assert.match(html,/不等于全部前景像元/);
    assert.match(html,/pooled OOF/);assert.match(html,/观测／实物排名/);assert.match(html,/下降 1 名/);
    assert.match(html,/预测平票/);assert.match(html,/缺少类别 未受精/);assert.match(html,/sample_metric_undefined/);
    assert.match(html,/egg-1/);assert.doesNotMatch(html,/do-not-mix-pixel|仅看达到 1-SE|1-SE 推荐/);
    const summary=renderToStaticMarkup(createElement(StudyHighlights,{result,enabled:true,send:()=>{}}));
    assert.match(summary,/实物 pooled OOF 最高分/);assert.doesNotMatch(summary,/CV Macro-F1.*±|1-SE 推荐/);
  }finally{await server.close();}
});
