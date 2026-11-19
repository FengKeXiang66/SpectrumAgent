import type { BatchItem, PreprocessApi, RunBatchResult } from './types.ts';
import { describePreprocessError } from './types.ts';

export type Member = {cube_id:string;name:string;annotation_version_id:string|null;gap?:string};
export type Batch = {ref:string;inputs:BatchItem[];confirmation:string|null;draftId:string;revision:number;
  retryOf?:string;status:'not_submitted'|'submitting'|'unknown'|'blocked'|'succeeded'|'partial'|'failed';receipt:RunBatchResult|null;error?:string};
export type Plan = {id:string;owner:string;boot:string;recipe:string;members:Member[];batches:Batch[];
  status:'ready'|'confirming'|'running'|'paused'|'completed';error:string};
type Snapshot = {plans:Plan[];active:string|null;busy:boolean};
const uncertainCodes=new Set(['OPERATION_IN_PROGRESS','OPERATION_RECONCILIATION_REQUIRED','OPERATION_NEEDS_RECONCILIATION']);
export const pauseCodes=new Set(['SOURCE_CHANGED','RECIPE_CONFIRMATION_STALE',...uncertainCodes]);
const receiptStatus=(receipt:RunBatchResult):Batch['status']=>receipt.items.some(i=>uncertainCodes.has(i.error_code??''))?'unknown':receipt.failed?(receipt.succeeded?'partial':'failed'):'succeeded';

export function verifiedReceipt(value:unknown,inputs:BatchItem[]):RunBatchResult {
  const row=value as RunBatchResult;
  const wanted=new Set(inputs.map(i=>i.cube_id));
  if(!row||row.truncated!==false||!Array.isArray(row.items)||row.items.length!==wanted.size||
    new Set(row.items.map(i=>i.cube_id)).size!==wanted.size||row.items.some(i=>!wanted.has(i.cube_id)||
      !['succeeded','failed'].includes(i.status)||(i.status==='succeeded'&&(!i.run_id||typeof i.run_id!=='string')))||
    row.succeeded!==row.items.filter(i=>i.status==='succeeded').length||row.failed!==row.items.filter(i=>i.status==='failed').length)
    throw new Error('批次回执与固定成员不一致，请核对原提交；未重新执行。');
  return row;
}

export async function recoverBatch(api:Pick<PreprocessApi,'getSubmission'>,batch:Batch,owner:string):Promise<RunBatchResult|null> {
  const submission=await api.getSubmission(batch.ref,owner);
  if(submission.submission_ref!==batch.ref)throw new Error('返回的提交身份不匹配。');
  const batches=submission.operations.filter(op=>op.kind==='preprocess.run_batch');
  const rejected=submission.operations.map(op=>op.receipt).find(r=>r&&'rejected' in r&&r.rejected===true);
  if(rejected)throw rejected;
  if(batches.length!==1||!batches[0].receipt)return null;
  if(!['succeeded','failed'].includes(batches[0].status))return null;
  return verifiedReceipt(batches[0].receipt,batch.inputs);
}

// A member has one current projection; batches retain all attempts separately.
export function planMembers(plan:Plan) {
  return plan.members.map(member=>{
    let status=member.gap||(!member.annotation_version_id?'need_annotation_selection':'ready');
    let run_id:string|null=null,error_code:string|null=null,source:Batch|undefined;
    for(const batch of plan.batches) {
      if(!batch.inputs.some(i=>i.cube_id===member.cube_id))continue;
      const item=batch.receipt?.items.find(i=>i.cube_id===member.cube_id);
      if(status==='succeeded')continue;
      if(item){status=uncertainCodes.has(item.error_code??'')?'unknown':item.status;run_id=item.run_id;error_code=item.error_code;source=batch;}
      else if(['submitting','unknown'].includes(batch.status)){status=batch.status;source=batch;}
    }
    return {...member,status,run_id,error_code,source};
  });
}

export function createBatchPlanController(api:PreprocessApi,storage?:Pick<Storage,'getItem'|'setItem'|'removeItem'>) {
  let state:Snapshot={plans:[],active:null,busy:false},epoch=0,stop=false,owner='',boot='';
  const listeners=new Set<()=>void>(),key='spectrumagent.preprocess-plans';
  const publish=(next:Snapshot)=>{
    state=next;
    try{storage?.setItem(key,JSON.stringify({schema:1,owner,boot,plans:state.plans,active:state.active}));}catch{/* Memory still retains accepted identities. */}
    listeners.forEach(f=>f());
  };
  const active=()=>state.plans.find(p=>p.id===state.active);
  const update=(id:string,fn:(p:Plan)=>Plan)=>publish({...state,plans:state.plans.map(p=>p.id===id?fn(p):p)});
  const changeBatch=(id:string,ref:string,values:Partial<Batch>)=>update(id,p=>({...p,batches:p.batches.map(b=>b.ref===ref?{...b,...values}:b)}));
  const critical=(plan:Plan)=>plan.batches.some(b=>b.status==='blocked'||b.receipt?.items.some(i=>pauseCodes.has(i.error_code??'')));
  const execute=async()=>{
    const selected=active();if(state.busy||!selected)return;
    if(selected.batches.some(b=>b.status==='unknown')||critical(selected))return;
    const id=selected.id,ticket=epoch;stop=false;publish({...state,busy:true});
    const current=()=>state.plans.find(p=>p.id===id)!;
    try {
      update(id,p=>({...p,status:'confirming',error:''}));
      // Confirm the entire plan before starting any numerical execution.
      for(const batch of current().batches.filter(b=>b.status==='not_submitted'&&!b.confirmation)) {
        if(stop||ticket!==epoch)return;
        try {
          const c=await api.confirmDraft(selected.owner,batch.draftId,batch.revision,selected.recipe,batch.inputs);
          if(ticket!==epoch)return;
          changeBatch(id,batch.ref,{confirmation:c.confirmation_id});
        }catch(error){if(ticket===epoch){changeBatch(id,batch.ref,{status:'blocked',error:describePreprocessError(error)});update(id,p=>({...p,status:'paused',error:describePreprocessError(error)}));}return;}
      }
      update(id,p=>({...p,status:'running'}));
      for(const batch of current().batches.filter(b=>b.status==='not_submitted')) {
        if(stop||ticket!==epoch)break;
        changeBatch(id,batch.ref,{status:'submitting'});
        try {
          const result=batch.retryOf
            ?await api.retryDraft(selected.owner,batch.confirmation!,batch.inputs,batch.retryOf,batch.ref)
            :await api.executeDraft(selected.owner,batch.confirmation!,batch.inputs,batch.ref);
          if(ticket!==epoch)return;
          const receipt=verifiedReceipt(result,batch.inputs);
          changeBatch(id,batch.ref,{receipt,status:receiptStatus(receipt)});
          if(receipt.items.some(i=>pauseCodes.has(i.error_code??''))) {stop=true;update(id,p=>({...p,error:'输入或确认状态已改变，后续批次已暂停。'}));}
        }catch(error) {
          if(ticket!==epoch)return;
          const code=typeof error==='object'&&error&&'error' in error?String(error.error):'';
          changeBatch(id,batch.ref,{status:['IDEMPOTENCY_CONFLICT','PREPROCESS_RETRY_SCOPE_MISMATCH','RECIPE_CONFIRMATION_STALE','INVALID_REQUEST','TOOL_ARGS_INVALID','OPERATION_OWNER_MISMATCH'].includes(code)?'blocked':'unknown',error:describePreprocessError(error)});
          update(id,p=>({...p,error:describePreprocessError(error)}));stop=true;
        }
      }
      if(ticket===epoch)update(id,p=>({...p,status:p.batches.some(b=>['not_submitted','unknown','blocked','submitting'].includes(b.status))?'paused':'completed'}));
    }finally{if(ticket===epoch)publish({...state,busy:false});}
  };
  return {
    subscribe(fn:()=>void){listeners.add(fn);return()=>{listeners.delete(fn);};},
    getSnapshot:()=>state,
    invalidate() {
      epoch++;stop=true;
      if(!owner)return;
      owner='';boot='';publish({plans:[],active:null,busy:false});
      try{storage?.removeItem(key);}catch{/* No persistent business state is required. */}
    },
    attach(nextBoot:string,nextOwner:string) {
      if(boot===nextBoot&&owner===nextOwner)return;
      epoch++;boot=nextBoot;owner=nextOwner;state={plans:[],active:null,busy:false};
      try {
        const saved=JSON.parse(storage?.getItem(key)??'null');
        if(saved?.schema===1&&saved.boot===boot&&saved.owner===owner&&Array.isArray(saved.plans)) {
          const plans=saved.plans as Plan[];
          if(plans.some(p=>!p||p.owner!==owner||p.boot!==boot||typeof p.id!=='string'||typeof p.recipe!=='string'||!Array.isArray(p.members)||!Array.isArray(p.batches)||
            p.members.some(m=>!m||typeof m.cube_id!=='string'||typeof m.name!=='string'||(m.annotation_version_id!==null&&typeof m.annotation_version_id!=='string'))||
            new Set(p.members.map(m=>m.cube_id)).size!==p.members.length||
            p.batches.some(b=>!b||!b.ref||typeof b.draftId!=='string'||!Number.isInteger(b.revision)||!Array.isArray(b.inputs)||!b.inputs.length||b.inputs.length>32||b.inputs.some(i=>!i||typeof i.cube_id!=='string'||typeof i.annotation_version_id!=='string'||i.recipe_version_id!==p.recipe))))throw new Error('Invalid plan snapshot');
          state={plans:plans.map(p=>({...p,status:'paused',batches:p.batches.map(b=>b.status==='not_submitted'||b.status==='blocked'?b:{...b,status:'unknown',receipt:null})})),active:saved.active,busy:false};
        }
      }catch{/* A malformed local snapshot never authorizes an execution. */}
      publish(state);
    },
    select(id:string){if(!state.busy&&state.plans.some(p=>p.id===id))publish({...state,active:id});},
    create(draftId:string,revision:number,recipe:string,members:Member[]) {
      if(state.busy)throw new Error('请先核对当前提交。');
      if(state.plans.some(p=>p.batches.some(b=>b.status==='unknown'||b.status==='submitting')))throw new Error('存在待核对的提交，请先核对原状态再创建新计划。');
      if(!owner||!boot||!draftId||!recipe||new Set(members.map(m=>m.cube_id)).size!==members.length)throw new Error('计划绑定不完整。');
      const inputs=members.filter(m=>m.annotation_version_id&&!m.gap).map(m=>({cube_id:m.cube_id,annotation_version_id:m.annotation_version_id!,recipe_version_id:recipe}));
      if(!inputs.length)throw new Error('没有可提交成员，请选择保存版本。');
      const batches:Batch[]=[];
      for(let offset=0;offset<inputs.length;offset+=32)batches.push({ref:crypto.randomUUID(),inputs:inputs.slice(offset,offset+32),confirmation:null,draftId,revision,status:'not_submitted',receipt:null});
      const plan:Plan={id:crypto.randomUUID(),owner,boot,recipe,members:structuredClone(members),batches,status:'ready',error:''};
      publish({...state,plans:[...state.plans,plan],active:plan.id});return plan;
    },
    execute,
    stop(){stop=true;const p=active();if(p)update(p.id,p=>({...p,status:'paused'}));},
    async recover() {
      const p=active();if(!p||state.busy)return;
      const ticket=epoch;publish({...state,busy:true});
      try {
        for(const batch of p.batches.filter(b=>b.status==='unknown'||b.status==='submitting')) {
          try {
            const receipt=await recoverBatch(api,batch,p.owner);if(ticket!==epoch)return;
            if(receipt)changeBatch(p.id,batch.ref,{receipt,error:undefined,status:receiptStatus(receipt)});
          }catch(error){if(ticket===epoch){const rejected=typeof error==='object'&&error&&'rejected' in error&&error.rejected===true;changeBatch(p.id,batch.ref,{...(rejected?{status:'blocked' as const}:{}),error:describePreprocessError(error)});}}
        }
        if(ticket===epoch)update(p.id,plan=>({...plan,status:plan.batches.every(b=>['succeeded','partial','failed'].includes(b.status))?'completed':'paused'}));
      }finally{if(ticket===epoch)publish({...state,busy:false});}
    },
    async retry(cubeIds:string[],draft:{id:string;revision:number;recipe:string}) {
      const p=active();if(!p||state.busy)return;
      if(draft.recipe!==p.recipe)throw new Error('补跑须载入原计划的已保存配方版本。');
      const rows=planMembers(p),groups=new Map<string,BatchItem[]>();
      for(const cube of new Set(cubeIds)) {
        if(p.batches.some(b=>['not_submitted','submitting','unknown'].includes(b.status)&&b.inputs.some(i=>i.cube_id===cube)))throw new Error('该成员已有待完成尝试，请继续或核对原提交。');
        const member=rows.find(m=>m.cube_id===cube);
        if(!member||member.status!=='failed'||!member.source||pauseCodes.has(member.error_code??''))throw new Error('只能补跑明确失败且已核对的成员。');
        const source=member.source.retryOf??member.source.ref;
        const items=groups.get(source)??[];items.push({cube_id:cube,annotation_version_id:member.annotation_version_id!,recipe_version_id:p.recipe});groups.set(source,items);
      }
      if(!groups.size)return;
      update(p.id,plan=>({...plan,status:'ready',error:'',batches:[...plan.batches,...[...groups].map(([retryOf,inputs]):Batch=>({ref:crypto.randomUUID(),retryOf,inputs,confirmation:null,draftId:draft.id,revision:draft.revision,status:'not_submitted',receipt:null}))]}));
      await execute();
    },
  };
}
export type BatchPlanController=ReturnType<typeof createBatchPlanController>;
