import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { sampleCommand } from '../src/components/assistant/sample-evaluation-form.ts';

test('sample declaration is explicit and threshold and complete grouping are validated',()=>{
  const form={experiment_id:'experiment',expected_revision:2,form_id:'form',mode:'IMAGE',minimum_valid:100,mapping:[]};
  const command=sampleCommand(form);
  assert.equal(JSON.parse(command.slice('提交实物评价定义 '.length)).minimum_valid,100);
  for(const patch of [{mode:''},{mode:'BATCH'},{minimum_valid:NaN},{minimum_valid:0},{minimum_valid:1.2},
    {mode:'MAPPED'},{mode:'MAPPED',mapping:[{source_ref:'source',sample_id:' '}]}])
    assert.throws(()=>sampleCommand({...form,...patch}));
  assert.doesNotThrow(()=>sampleCommand({...form,mode:'MAPPED',mapping_csv:'E:\\group.csv'}));
});

test('report shows independent object counts, exclusions and pixel comparison; mixed has no object scores',async()=>{
  const server=await createServer({server:{middlewareMode:true,watch:null,hmr:false},appType:'custom'});
  try{
    const {SampleReport,default:Card}=await server.ssrLoadModule('/src/components/assistant/SampleEvaluationCard.tsx');
    const score={n:1,correct:1,accuracy:1,macro_f1:1,confusion_labels:[1,2],confusion:[[1,0],[0,0]],
      per_class:[{label:1,name:'受精',support:1,precision:1,recall:1,f1:1}]};
    const rows=[{sample_id:'egg1',display_id:'egg1',image_count:2,valid:200,truth:1,prediction:1,truth_counts:{1:200},
      correct:true,status:'included',reasons:[]},
      {sample_id:'egg2',display_id:'egg2',image_count:1,valid:99,truth:2,prediction:2,truth_counts:{2:99},
      correct:null,status:'insufficient',reasons:['insufficient']}];
    const role={total:2,included:1,excluded:1,exclusion_counts:{insufficient:1},metrics:score,rows};
    const view={revision:3,applicable:true,form_id:null,sources:[],definition:{mode:'IMAGE',minimum_valid:100,mapping:[]},
      report:{status:'ready',protocol:'sample_vote_v1',total_objects:4,roles:{train:role,test:role},
        pixel_metrics:{train:{n:940000,accuracy:.75,macro_f1:.43,purpose:'training_fit'},
          test:{n:470000,accuracy:.74,macro_f1:.42,purpose:'independent_test'}},
        truth_basis:'只评价保存的观测真值',observation_note:'阈值不是原图全部前景像元',macro_definition:'PLS响应不是概率'}};
    const html=renderToStaticMarkup(createElement(SampleReport,{view,classes:{1:'受精',2:'未受精'}}));
    assert.match(html,/实物数 n=4/);assert.match(html,/940000/);assert.match(html,/有效观测阈值 N=100/);
    assert.match(html,/实物 2，纳入 1，排除 1/);assert.match(html,/未计入实物指标的完整列表/);
    assert.match(html,/有效观测不足/);assert.match(html,/实物混淆矩阵/);assert.match(html,/不是概率/);
    const mixed=renderToStaticMarkup(createElement(SampleReport,{view:{...view,report:{status:'not_applicable',reason:'一图多物，不适用',roles:{}}},classes:{}}));
    assert.match(mixed,/一图多物，不适用/);assert.doesNotMatch(mixed,/实物数 n=|Macro-F1|混淆矩阵/);
    const empty={revision:0,applicable:true,form_id:null,sources:[],definition:null,report:null};
    const form=renderToStaticMarkup(createElement(Card,{initial:empty,experimentId:'id',sessionId:'sid',classes:{},enabled:true}));
    assert.match(form,/<option value="" selected="">请选择，不自动推断/);
    assert.doesNotMatch(form,/<option value="IMAGE" selected/);
    const npz=renderToStaticMarkup(createElement(Card,{initial:{...empty,applicable:false},experimentId:'id',sessionId:'sid',classes:{},enabled:true}));
    assert.match(npz,/groups 可能表示批次/);assert.doesNotMatch(npz,/保存定义并生成/);
  }finally{await server.close();}
});
