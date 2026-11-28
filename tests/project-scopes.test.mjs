import assert from 'node:assert/strict';
import test from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {createCatalogController} from '../src/components/datasets/catalog.ts';

test('project switching clears old context and new sessions carry the chosen project', async () => {
  const server=await createServer({server:{middlewareMode:true,watch:null,hmr:false},appType:'custom'});
  try {
    const {agent,agentClient}=await server.ssrLoadModule('/src/components/assistant/api.ts');
    const {default:useSession}=await server.ssrLoadModule('/src/components/assistant/useSession.ts');
    const {default:SessionScope}=await server.ssrLoadModule('/src/components/assistant/SessionScope.tsx');
    const calls=[];
    const client=agentClient(async (_command,body)=>{calls.push(body.request);return {};});
    await client.createSession({project_id:'project-b',request_id:'request'});
    await client.selectProject('project-b');
    assert.deepEqual(calls,[{op:'create_session',project_id:'project-b',request_id:'request'}, {op:'select_project',project_id:'project-b'}]);
    const switched=[];
    agent.selectProject=async id=>{switched.push(['select',id]);return {current_project_id:id};};
    agent.listSessions=async ()=>({sessions:[],next_cursor:null});
    agent.createSession=async body=>{
      switched.push(['create',body.project_id]);
      return {id:'session-b',title:'',created_at:'',skill_version_id:'v',project_id:'project-b'};
    };
    let session;
    function Probe() {
      session=useSession({enabled:true,generation:1,onCatalogChanged:async changed=>{switched.push(['catalog',changed]);},
        onWorkspaceChange:()=>switched.push(['clear-canvas'])});
      return null;
    }
    renderToStaticMarkup(createElement(Probe));
    await session.changeProject('project-b');
    await session.ensureSession();
    assert.deepEqual(switched,[['select','project-b'],['clear-canvas'],['catalog',true],['create','project-b']]);
    const html=renderToStaticMarkup(createElement(SessionScope,{session:{...session,
      projectId:'project-b',projects:[{id:'project-a',name:'塑料'},{id:'project-b',name:'蛋'}],records:[],
      active:{project_id:'project-b',total_members:41},state:{busy:false},loading:false}}));
    assert.match(html,/当前项目/);
    assert.match(html,/41/);
    assert.doesNotMatch(html,/全部已导入|全局会话/);
    const {PlanCardView}=await server.ssrLoadModule('/src/components/assistant/PlanCard.ts');
    const blocked=renderToStaticMarkup(createElement(PlanCardView,{plan:{plan_id:'old',reason:'原确认失效',blocked:true,steps:[]},
      choice:null,reason:'',disabled:false,readOnly:false,onChoose(){},onReason(){},onSubmit(){}}));
    assert.match(blocked,/<button[^>]*disabled=""[^>]*>批准/);

  } finally {await server.close();}
});

test('a late catalog response from the old project cannot repopulate the new project', async () => {
  let resolveOld;
  let request=0;
  const controller=createCatalogController({catalog:async ()=>{
    if(++request===1)return new Promise(resolve=>{resolveOld=resolve;});
    return {datasets:[],total:0,offset:0,limit:100};
  }},()=>{});
  controller.reset(1);
  const old=controller.load();
  controller.reset(1);
  await controller.load();
  resolveOld({datasets:[{id:'old',display_name:'旧项目',available:true,shape:[1,1,1]}],total:1,offset:0,limit:100});
  await old;
  assert.equal(controller.snapshot().records.length,0);
});
