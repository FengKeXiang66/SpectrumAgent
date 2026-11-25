import assert from 'node:assert/strict';
import test from 'node:test';
import { candidateCommand, candidatePage, filterCandidates, topCandidates } from '../src/components/assistant/study-ranking.ts';

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
  } finally {await server.close();}
});
