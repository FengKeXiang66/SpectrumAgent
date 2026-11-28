import { useEffect, useReducer, useRef, useState } from 'react';
import { agent, type BatchCard, type BatchScope, type BatchResult, type TaskCard, type MessageBody, type RuntimeInfo, type WorkspaceContext, type SessionDetail, type SessionSummary, type HistoryEvent, type CreateSessionInput, type Project } from './api.ts';
import { initialChat, reduceChat, requestError, validateWorkspaceEvent, type WorkspaceEventData, type ChatEntry, type AgentEvent } from './sse.ts';
import { catalogChanged, changedCubes, datasetChoices, proposedCandidates, parseBatchSummary } from './presentation.ts';
import type { DatasetReference } from '../datasets/types.ts';
import { recipesChanged, draftsChanged } from '../preprocess/recipe-events.ts';

const CANVAS_ANNOTATION_TOOLS = new Set([
  'annotations.prepare', 'annotations.propose', 'annotations.apply_candidate',
  'annotations.set_background', 'annotations.mark_region', 'annotations.edit_region',
  'annotations.undo',
  'annotations.prepare_batch',
]);

const activeSessionKey = 'spectrumagent.active-session';
function savedSession(): string | null {
  try {
    const id=localStorage.getItem(activeSessionKey);
    return id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id) ? id : null;
  } catch { return null; }
}
function rememberSession(id: string | null) {
  try { if (id) localStorage.setItem(activeSessionKey, id); else localStorage.removeItem(activeSessionKey); }
  catch { /* Backend session discovery remains available. */ }
}

const SESSION_PAGE_SIZE = 20;

function summarize(detail: SessionDetail): SessionSummary {
  const {id,title,created_at,updated_at,pending,request,history_watermark} = detail;
  return {id,title,created_at,updated_at,pending:Boolean(pending),request,history_watermark};
}

function newSessionSummary(created: Pick<SessionSummary,'id'|'title'|'created_at'>): SessionSummary {
  const {id,title,created_at}=created;
  return {id,title,created_at,updated_at:created_at,pending:false,request:null,history_watermark:0};
}

function sessionOrder(a: SessionSummary, b: SessionSummary) {
  return b.updated_at.localeCompare(a.updated_at) || b.id.localeCompare(a.id);
}

export default function useSession({ enabled, generation, bootId, workspace = {}, records = [], catalogPhase, displayName,
  onWorkspaceChange, onSessionReset, onWorkspaceDisplayChange, onWorkspaceNavigate, onBatchOpen, onBatchReset, onPreviewCandidate, onDataChanged, onCatalogChanged }: {
  enabled: boolean; generation: number; bootId?: string | null; workspace?: WorkspaceContext; records?: DatasetReference[]; displayName?: string;
  catalogPhase?: 'idle' | 'loading' | 'ready' | 'error';
  onSessionReset?(): void;
  onWorkspaceChange?(workspace: WorkspaceContext): void;
  onWorkspaceDisplayChange?(selection: WorkspaceEventData): void;
  onWorkspaceNavigate?(selection: WorkspaceEventData): void;
  onBatchOpen?(scope: BatchScope): void;
  onBatchReset?(): void;
  onPreviewCandidate?(cubeId: string, candidateRef: string): void;
  onDataChanged?(cubeIds: string[]): void;
  onCatalogChanged?(projectChanged?: boolean): Promise<void>;
}) {
  const [state, dispatch] = useReducer(reduceChat, initialChat);
  const [content, setContent] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [deletedProjects, setDeletedProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>('');
  const projectRef = useRef('');
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [batchCards, setBatchCards] = useState<BatchCard[]>([]);
  const [taskCards, setTaskCards] = useState<TaskCard[]>([]);
  const callbacks = useRef({ onBatchOpen, onBatchReset, enabled, generation, bootId });
  callbacks.current = { onBatchOpen, onBatchReset, enabled, generation, bootId };
  const sessionId = useRef<string | null>(null);
  const creatingSession=useRef<Promise<string>|null>(null);
  const restoringSession=useRef<Promise<void>|null>(null);
  const latestRequest = useRef<string | null>(null);
  // One guard covers both views, including clicks before disabled buttons commit.
  const inFlight = useRef(false);
  const epoch = useRef(0);
  const [active, setActive] = useState<SessionDetail | null>(null);
  const activeRef = useRef<SessionDetail | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsCursor, setSessionsCursor] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [archivingSessionId, setArchivingSessionId] = useState<string | null>(null);
  const sessionRows = useRef<SessionSummary[]>([]);
  const listOperation = useRef<{overrides: Map<string, SessionSummary | null>} | null>(null);
  const sessionOperation = useRef<symbol | null>(null);
  const [historyBefore, setHistoryBefore] = useState<number | null>(null);
  const historyRows = useRef<HistoryEvent[]>([]);
  const localEntries=useRef<{after:number;entries:ChatEntry[]}[]>([]);
  const [recoveryFailed, setRecoveryFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const stopRequested = useRef(false);
  const stopInFlight = useRef(false);
  const refreshing = useRef(false);
  const lastUserMessage = useRef('');
  const currentTicket = (ticket: number) => ticket === epoch.current && callbacks.current.enabled;
  function setSessionRows(rows: SessionSummary[]) {
    sessionRows.current = rows;
    setSessions(rows);
  }
  function updateSessionRow(id: string, row: SessionSummary | null) {
    listOperation.current?.overrides.set(id,row);
    const rows = sessionRows.current.filter(item=>item.id!==id);
    if (row) rows.push(row);
    setSessionRows(rows.sort(sessionOrder));
  }
  function setSessionDetail(detail: SessionDetail) {
    activeRef.current=detail;
    setActive(detail);
    updateSessionRow(detail.id,summarize(detail));
  }
  async function fetchSessions(cursor?: string) {
    if (!callbacks.current.enabled || listOperation.current) return;
    const operation = {overrides:new Map<string, SessionSummary | null>()};
    const startingGeneration = callbacks.current.generation;
    const current = () => listOperation.current===operation && callbacks.current.enabled && callbacks.current.generation===startingGeneration;
    listOperation.current=operation;
    setSessionsLoading(true);
    setSessionsError(null);
    try {
      const page = await agent.listSessions({limit:SESSION_PAGE_SIZE,cursor});
      if (!current()) return;
      const rows = new Map((cursor ? sessionRows.current : []).map(item=>[item.id,item]));
      for (const item of page.sessions) if (!rows.has(item.id)) rows.set(item.id,item);
      for (const [id,item] of operation.overrides) {
        if (item) rows.set(id,item);
        else rows.delete(id);
      }
      const next=[...rows.values()].sort(sessionOrder);
      setSessionRows(next);
      setSessionsCursor(page.next_cursor);
      return next;
    } catch (error) {
      if (current()) setSessionsError(requestError(error));
    } finally {
      if (listOperation.current===operation) {
        listOperation.current=null;
        setSessionsLoading(false);
      }
    }
  }
  const refreshSessions=()=>fetchSessions();
  const loadMoreSessions=()=>sessionsCursor ? fetchSessions(sessionsCursor) : Promise.resolve(undefined);

  const ensureSession=async()=>{
    if (sessionOperation.current) throw new Error('请等待会话切换或移除完成');
    if(restoringSession.current) await restoringSession.current;
    if(sessionId.current)return sessionId.current;
    if(creatingSession.current)return creatingSession.current;
    const ticket=epoch.current;
    const creation=agent.createSession({scope:{kind:'global'},request_id:crypto.randomUUID(), ...(projectRef.current?{project_id:projectRef.current}:{})}).then(created=>{
      if(!currentTicket(ticket))throw new Error('会话创建期间引擎已变化');
      sessionId.current=created.id;
      rememberSession(created.id);
      updateSessionRow(created.id,newSessionSummary(created));
      return created.id;
    });
    creatingSession.current=creation;
    try{return await creation;}finally{if(creatingSession.current===creation)creatingSession.current=null;}
  };
  const displayEntries = (rows: HistoryEvent[]): ChatEntry[] => {
    const converted=rows.flatMap(row => {
    if (row.kind === 'decision') return [{event: 'user', data: {content: '确认决定：' + String(row.payload.decision ?? row.payload.action ?? '')}} as ChatEntry];
    if (row.kind === 'workspace') return []; // restoration never replays old navigation
    return [{event: row.kind, data: row.payload, requestId: row.request_id} as ChatEntry];
    });
    for(const item of localEntries.current) {
      if((rows.at(-1)?.seq??0)<item.after)continue;
      if(item.after===0?Boolean(rows.length&&rows[0].seq>1):!rows.some(row=>row.seq===item.after))continue;
      const firstAfter=rows.find(row=>row.seq>item.after&&row.kind!=='workspace');
      const index=firstAfter?converted.findIndex(entry=>entry.requestId===firstAfter.request_id):converted.length;
      converted.splice(index<0?converted.length:index,0,...item.entries);
    }
    return converted;
  };
  const hydrate = (detail: SessionDetail, rows: HistoryEvent[]) => {
    const pending = detail.pending;
    dispatch({ type: 'hydrate', entries: displayEntries(rows), busy:detail.request?.status==='running', pending: pending ?
      ('check_id' in pending ? {check_id: pending.check_id, tool: pending.tool, summary: pending.summary, reason: pending.reason, blocked:pending.blocked}
        : {plan_id: pending.plan_id, steps: pending.steps, reason: pending.reason, blocked:pending.blocked}) : null });
    const restored:TaskCard[]=rows.flatMap(row=>{
      const summary=row.kind==='step'&&['annotations.prepare_batch','annotations.task'].includes(String(row.payload.tool))
        ? row.payload.result_summary as Record<string,unknown> : null;
      const taskId=row.kind==='done'?row.payload.annotation_task_id:summary?.status==='accepted'?summary.task_id:null;
      return typeof taskId==='string'?[{taskId,sessionId:detail.id,generation,requestId:row.request_id,
        ...(typeof row.payload.annotation_flow_id==='string'?{authorizationId:row.payload.annotation_flow_id}:{}),
      }]:[];
    });
    if(detail.annotation_flow)restored.push({taskId:detail.annotation_flow.task_id,sessionId:detail.id,generation,
      requestId:detail.annotation_flow.request_id,targetCubeIds:detail.annotation_flow.cube_ids,
      onDemand:detail.annotation_flow.mode==='per_image',authorizationId:detail.annotation_flow.authorization_id});
    setTaskCards(current=>[...new Map([...current.filter(card=>card.sessionId===detail.id&&card.generation===generation),...restored]
      .map(card=>[card.taskId,{...current.find(old=>old.taskId===card.taskId),...card}])).values()]);
  };
  function clearSession() {
    const ticket = ++epoch.current;
    latestRequest.current=null; lastUserMessage.current='';
    setRecoveryFailed(false); setSyncError(null); setStopError(null); setStopping(false);
    stopRequested.current=false; stopInFlight.current=false; refreshing.current=false;
    sessionId.current=null; activeRef.current=null; setActive(null);
    dispatch({type:'reset'}); setContent(''); setBatchCards([]); setTaskCards([]);
    callbacks.current.onBatchReset?.(); onWorkspaceChange?.({}); onSessionReset?.();
    historyRows.current=[]; localEntries.current=[]; setHistoryBefore(null);
    return ticket;
  }
  const openSession = async (id: string, ticket = clearSession()): Promise<boolean> => {
    setLoading(true);
    try {
      const detail = await agent.getSession(id);
      if (!currentTicket(ticket)) return false;
      if (detail.id !== id || !detail.boot_id || callbacks.current.bootId && detail.boot_id!==callbacks.current.bootId
          || detail.scope.kind !== 'global') throw new Error('会话身份校验失败');
      if(detail.project_id && projectRef.current && detail.project_id!==projectRef.current) throw new Error('会话不属于当前项目');
      const page = await agent.getHistory(id);
      if (!currentTicket(ticket)) return false;
      if (page.session_id !== id) throw new Error('会话返回范围不一致');
      sessionId.current=id; setSessionDetail(detail);
      latestRequest.current = detail.request?.status==='running' ? detail.request.request_id : null;
      historyRows.current = page.events; setHistoryBefore(page.next_before); hydrate(detail, page.events);
      if (detail.canvas_focus?.cube_id) onWorkspaceChange?.(detail.canvas_focus);
      rememberSession(id);
      return true;
    } catch (error) {
      if (currentTicket(ticket)) {
        if (error && typeof error === 'object' && 'error' in error && ['SESSION_NOT_FOUND','SESSION_ARCHIVED'].includes(String(error.error))) {
          rememberSession(null);
          updateSessionRow(id,null);
          try {
            const latest = sessionRows.current[0]?.id ?? await agent.latestSession();
            if (!currentTicket(ticket)) return false;
            if (latest && latest !== id) return await openSession(latest,ticket);
          } catch(discoveryError) {
            if(currentTicket(ticket)){setRecoveryFailed(true);dispatch({type:'failed',detail:requestError(discoveryError)});}
          }
          return false;
        }
        setRecoveryFailed(true);dispatch({type: 'failed', detail: requestError(error)});
      }
      return false;
    }
    finally { if (currentTicket(ticket)) setLoading(false); }
  };
  function beginSessionChange() {
    if (!enabled || loading || state.busy || inFlight.current || sessionOperation.current ||
        restoringSession.current || activeRef.current?.request?.status==='running') return null;
    const operation=Symbol();
    sessionOperation.current=operation;
    return operation;
  }
  function endSessionChange(operation: symbol) {
    if (sessionOperation.current===operation) sessionOperation.current=null;
  }
  const clearSessionsError = () => setSessionsError(null);
  const switchSession = async (id: string): Promise<boolean> => {
    clearSessionsError();
    if (activeRef.current?.id===id) return true;
    const operation=beginSessionChange();
    if (!operation) return false;
    try { return await openSession(id); }
    finally { endSessionChange(operation); }
  };
  const createSession = async () => {
    const current=activeRef.current;
    if (current && !current.title && current.history_watermark===0 && !state.entries.length && !state.pending) return;
    const operation=beginSessionChange();
    if (!operation) return;
    const ticket=epoch.current;
    setLoading(true);
    try {
      const body: CreateSessionInput = {scope:{kind:'global'},request_id:crypto.randomUUID(), ...(projectRef.current?{project_id:projectRef.current}:{})};
      const created=await agent.createSession(body);
      if (!currentTicket(ticket)) return;
      updateSessionRow(created.id,newSessionSummary(created));
      await openSession(created.id);
    } catch (error) {
      if (currentTicket(ticket)) setSessionsError(requestError(error));
    } finally {
      if (currentTicket(ticket)) setLoading(false);
      endSessionChange(operation);
    }
  };
  const openProject = async (id:string) => {
    clearSession(); rememberSession(null);
    projectRef.current=id; setProjectId(id);
    setSessionRows([]); setSessionsCursor(null);
    await onCatalogChanged?.(true);
    const rows=await refreshSessions();
    if(rows?.[0]) await openSession(rows[0].id);
  };
  const changeProject = async (id:string) => {
    if (id===projectRef.current) return;
    const operation=beginSessionChange();
    if (!operation) return;
    setLoading(true);
    try {
      await agent.selectProject(id);
      await openProject(id);
    } catch(error) {setSessionsError(requestError(error));}
    finally {setLoading(false);endSessionChange(operation);}
  };
  const deleteProject = async (id:string, name:string, token:string) => {
    const operation=beginSessionChange();
    if(!operation) return false;
    setLoading(true); setSessionsError(null);
    let deleted=false;
    try {
      const receipt=await agent.deleteProject(id,name,token);
      if(!receipt.deleted || receipt.project_id!==id) throw new Error('项目删除回执不一致');
      deleted=true;
      setProjects(rows=>rows.filter(row=>row.id!==id));
      setDeletedProjects(rows=>[...rows.filter(row=>row.id!==id),{id,name}]);
      if(projectRef.current===id) await openProject(receipt.current_project_id);
      const page=await agent.listProjects();
      setProjects(page.projects);setDeletedProjects(page.deleted_projects??[]);
    } catch(error) {setSessionsError(requestError(error));}
    finally {setLoading(false);endSessionChange(operation);}
    return deleted;
  };
  const restoreProject = async (id:string) => {
    const operation=beginSessionChange();
    if(!operation) return false;
    setLoading(true); setSessionsError(null);
    try {
      const project=await agent.restoreProject(id);
      setProjects(rows=>[...rows.filter(row=>row.id!==id),project]);
      setDeletedProjects(rows=>rows.filter(row=>row.id!==id));
      return true;
    } catch(error) {setSessionsError(requestError(error));return false;}
    finally {setLoading(false);endSessionChange(operation);}
  };
  const createProject = async (name:string) => {
    const operation=beginSessionChange();
    if(!operation) return false;
    setLoading(true); setSessionsError(null);
    try {
      const item=await agent.createProject(name);
      setProjects(current=>[...current,item]);
      await agent.selectProject(item.id);
      await openProject(item.id);
      return projectRef.current === item.id;
    } catch(error) {setSessionsError(requestError(error));return false;}
    finally {setLoading(false);endSessionChange(operation);}
  };
  const refreshProjects = async () => {
    const operation=beginSessionChange();
    if(!operation) return;
    setLoading(true); setSessionsError(null);
    try {
      const page=await agent.listProjects();
      setProjects(page.projects);setDeletedProjects(page.deleted_projects??[]);
      if(!page.projects.some(project=>project.id===projectRef.current)) await openProject(page.current_project_id);
    } catch(error) {setSessionsError(requestError(error));}
    finally {setLoading(false);endSessionChange(operation);}
  };
  const startNew = () => { void createSession(); };
  const archiveSession = async (id: string): Promise<boolean> => {
    const operation=beginSessionChange();
    if (!operation) return false;
    let ticket=epoch.current;
    const wasCurrent=sessionId.current===id;
    let archived=false;
    setArchivingSessionId(id);
    setSessionsError(null);
    if (wasCurrent) setLoading(true);
    try {
      const receipt=await agent.archiveSession(id);
      if (!currentTicket(ticket)) return false;
      if (!receipt.archived || receipt.session_id!==id) throw new Error('会话归档回执不一致');
      archived=true;
      updateSessionRow(id,null);
      if (wasCurrent) {
        rememberSession(null);
        ticket=clearSession();
        const next=sessionRows.current[0]?.id ?? await agent.latestSession();
        if (currentTicket(ticket) && next && next!==id) await openSession(next,ticket);
      }
      return true;
    } catch (error) {
      if (currentTicket(ticket)) setSessionsError(requestError(error));
      return archived;
    } finally {
      if (currentTicket(ticket)) {
        setArchivingSessionId(null);
        if (wasCurrent) setLoading(false);
      }
      endSessionChange(operation);
    }
  };
  const selectCube = async (cube: string | null) => {
    if (!sessionId.current || inFlight.current || sessionOperation.current || state.pending || loading || !enabled) return false;
    const id=sessionId.current, ticket=++epoch.current;
    // Selection invalidates old card actions; App retains an already-open
    // batch's ready subset while moving to another member of that subset.
    setBatchCards([]);
    setLoading(true);
    try {
      const detail=await agent.selectCube(id,cube);
      if (!currentTicket(ticket) || sessionId.current!==id || detail.id!==id) return false;
      setSessionDetail(detail);onWorkspaceChange?.(cube ? {cube_id:cube} : {});
      return true;
    } catch (error) {if (currentTicket(ticket)) dispatch({type:'failed',detail:requestError(error)});return false;}
    finally {if (currentTicket(ticket))setLoading(false);}
  };
  const loadOlder = async () => {
    if (!sessionId.current || historyBefore===null || loading) return;
    const id=sessionId.current,ticket=epoch.current;
    try {
      const page=await agent.getHistory(id,{before:historyBefore});
      if (!currentTicket(ticket) || sessionId.current!==id || !activeRef.current) return;
      const all=[...page.events,...historyRows.current];
      historyRows.current=[...new Map(all.map(e=>[e.seq,e])).values()].sort((a,b)=>a.seq-b.seq);
      setHistoryBefore(page.next_before);
      dispatch({type:'prepend',entries:displayEntries(page.events)});
    } catch(error){if(currentTicket(ticket))dispatch({type:'failed',detail:requestError(error)});}
  };
  // A new engine invalidates transient cards, then restores the explicit last id.
  useEffect(() => {
    ++epoch.current;
    localEntries.current=[];
    latestRequest.current = null;
    inFlight.current=false; activeRef.current=null;sessionId.current=null;setActive(null);
    stopRequested.current=false;stopInFlight.current=false;refreshing.current=false;setStopping(false);setStopError(null);setSyncError(null);
    creatingSession.current=null;
    restoringSession.current=null;setLoading(false);
    sessionOperation.current=null;listOperation.current=null;setSessionRows([]);setSessionsCursor(null);
    setSessionsLoading(false);setSessionsError(null);setArchivingSessionId(null);
    dispatch({type:'reset'});setBatchCards([]);setTaskCards([]);callbacks.current.onBatchReset?.();setRuntime(null);
    if (!enabled) return;
    setLoading(true);
    void agent.getRuntime().then(value=>{if(callbacks.current.enabled && callbacks.current.generation===generation)setRuntime(value);}).catch(()=>undefined);
    const ticket=epoch.current;
    const listing=agent.listProjects().then(page=>{
      if(!currentTicket(ticket))return;
      setProjects(page.projects);setDeletedProjects(page.deleted_projects??[]);setProjectId(page.current_project_id);projectRef.current=page.current_project_id;
      return refreshSessions();
    });
    const restoration=(async()=>{
      try {
        const available=await listing;
        const saved=savedSession();
        const previous=available?.find(row=>row.id===saved)?.id ?? available?.[0]?.id;
        if (currentTicket(ticket) && previous) await openSession(previous);
      } catch(error) {
        if(currentTicket(ticket)){setRecoveryFailed(true);dispatch({type:'failed',detail:requestError(error)});}
      } finally { if(currentTicket(ticket))setLoading(false); }
    })();
    restoringSession.current=restoration;
    void restoration.finally(()=>{if(restoringSession.current===restoration)restoringSession.current=null;});
    return ()=>{epoch.current++;};
  }, [enabled,generation]);
  useEffect(()=>{
    if(!state.busy){setElapsedSeconds(0);return;}
    const started=Date.now();
    const timer=setInterval(()=>setElapsedSeconds(Math.floor((Date.now()-started)/1000)),1000);
    return()=>clearInterval(timer);
  },[state.busy]);

  const refreshSession = async () => {
    const id=sessionId.current,ticket=epoch.current;
    const anchor=latestRequest.current;
    if(!id||refreshing.current||inFlight.current)return;
    refreshing.current=true;
    try {
      const detail=await agent.getSession(id);
      const page=await agent.getHistory(id);
      if(!currentTicket(ticket)||sessionId.current!==id||latestRequest.current!==anchor||inFlight.current)return;
      if(detail.id!==id||page.session_id!==id||callbacks.current.bootId&&detail.boot_id!==callbacks.current.bootId)throw new Error('会话身份校验失败');
      setSessionDetail(detail);setRecoveryFailed(false);setStopError(null);setSyncError(null);
      historyRows.current=page.events;setHistoryBefore(page.next_before);hydrate(detail,page.events);
      latestRequest.current=detail.request?.status==='running'?detail.request.request_id:null;
      if(detail.request?.status!=='running'){setStopping(false);stopRequested.current=false;}
    } finally {if(currentTicket(ticket))refreshing.current=false;}
  };
  // A transport timeout or a reloaded UI never means the server stopped.
  // Reconcile a detached request until its authoritative lease is terminal.
  useEffect(()=>{
    if(!enabled||active?.request?.status!=='running')return;
    let closed=false;
    const timer=setInterval(()=>{
      if(!closed&&!inFlight.current)void refreshSession().catch(error=>{if(!closed)setStopError(requestError(error));});
    },1000);
    return()=>{closed=true;clearInterval(timer);};
  },[enabled,generation,active?.id,active?.request?.status]);

  const stop = async () => {
    if(!enabled||stopInFlight.current)return;
    const requestId=latestRequest.current??activeRef.current?.request?.request_id;
    if(!requestId)return;
    const ticket=epoch.current;
    stopRequested.current=true;stopInFlight.current=true;setStopping(true);setStopError(null);
    try {
      // Session creation/HTTP admission can race the first stop click.
      for(let attempt=0;attempt<8;attempt++){
        if(!currentTicket(ticket))return;
        if(!inFlight.current&&activeRef.current?.request?.status!=='running'){setStopping(false);return;}
        const id=sessionId.current;
        if(id){
          try{
            const receipt=await agent.cancelRequest(id,requestId);
            if(receipt.session_id!==id||receipt.request_id!==requestId||callbacks.current.bootId&&receipt.boot_id!==callbacks.current.bootId)throw new Error('停止回执身份校验失败');
            return;
          }
          catch(error){
            const code=(error as {error?:string})?.error;
            if(code!=='REQUEST_NOT_FOUND'||attempt===7)throw error;
          }
        }
        await new Promise(resolve=>setTimeout(resolve,100));
      }
      if(currentTicket(ticket))setStopping(false);
    } catch(error){if(currentTicket(ticket)){setStopping(false);setStopError('停止请求未确认：'+requestError(error)+'。可再次停止或核对会话状态。');}}
    finally{if(currentTicket(ticket))stopInFlight.current=false;}
  };
  const choices = datasetChoices(state.entries, records);
  const selected = records.find(record => record.id === workspace.cube_id);
  const selectedChoice = choices.find(choice => choice.id === workspace.cube_id);
  const isBatchActive = (card: BatchCard) => callbacks.current.enabled
    && card.epoch === epoch.current && card.generation === callbacks.current.generation
    && (!card.sessionId || card.sessionId === sessionId.current)
    && (!card.requestId || card.requestId === latestRequest.current);
  const openBatch = (card: BatchCard) => {
    if (!isBatchActive(card) || state.busy || inFlight.current || !card.result?.readyMembers.length) return;
    callbacks.current.onBatchOpen?.({ result: card.result, epoch: card.epoch, generation: card.generation });
  };
  const retryBatch = (card: BatchCard) => {
    if (!isBatchActive(card) || state.busy || inFlight.current || !card.result?.batchRef) return false;
    // The server restores the exact scope from the parent receipt. No version
    // id and no restated member list belong in a segmentation retry.
    setContent('仅重试本次范围的未就绪项：annotations.prepare_batch ' + JSON.stringify({
      retry_of: card.result.batchRef }));
    return true;
  };
  const request = async (body: MessageBody, options: { preserveComposer?: boolean } = {}) => {
    if (!enabled || recoveryFailed || inFlight.current || sessionOperation.current || loading || activeRef.current?.request?.status === 'running') return;
    if ('content' in body && !body.content.trim()) return;
    if ('check_id' in body && (!state.pending || !('check_id' in state.pending) || state.pending.check_id !== body.check_id)) return;
    if ('plan_id' in body && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== body.plan_id)) return;
    const requestWorkspace = 'content' in body ? body.workspace ?? workspace : workspace;
    const requestEpoch = epoch.current;
    const requestId = crypto.randomUUID();
    latestRequest.current = requestId;
    const requestGeneration = generation;
    inFlight.current = true;
    stopRequested.current=false;setStopping(false);setStopError(null);
    const displayedInput='content' in body&&/^设置API\s*KEY为/i.test(body.content.trim())?'设置 API KEY（内容已隐藏）':'content' in body?body.content:'';
    if('content' in body){lastUserMessage.current=displayedInput;if (!options.preserveComposer) setContent('');}
    if ('content' in body) dispatch({ type: 'send', content: displayedInput, requestId });
    else if ('check_id' in body) dispatch({ type: 'decision', decision: body.decision });
    else dispatch({ type: 'plan', ...body });
    try {
      if('content' in body&&/^(?:打开(?:设置|模型设置)|(?:开启|关闭)(?:LLM)?外发|检查模型连接|运行冒烟测试|选择(?:数据源|输出)目录|设置(?:数据源|输出目录|模型|接口地址|API\s*KEY)为[\s\S]+)[。！!\s]*$/i.test(body.content.trim())) {
        const {executeLocalCommand,localInputLabel}=await import('./local-commands.ts');
        let answer:Awaited<ReturnType<typeof executeLocalCommand>>;
        try {answer=await executeLocalCommand(body.content);}
        catch(error) {
          if(currentTicket(requestEpoch)) {
            const event:AgentEvent={event:'error',data:{code:'LOCAL_COMMAND_FAILED',detail:requestError(error)}};
            localEntries.current.push({after:historyRows.current.at(-1)?.seq??0,entries:[
              {event:'user',data:{content:localInputLabel(body.content)},requestId},{...event,requestId}]});
            dispatch({type:'events',events:[event],requestId});
          }
          return;
        }
        if(currentTicket(requestEpoch)) {
          const events:AgentEvent[]=[...(answer.summary?[{event:'step' as const,data:{seq:1,tool:'ui.local',status:'ok',result_summary:answer.summary}}]:[]),
            {event:'done',data:{content:answer.content,step_count:0,request_status:'finished',reply_status:'replied'}}];
          localEntries.current.push({after:historyRows.current.at(-1)?.seq??0,entries:[
            {event:'user',data:{content:localInputLabel(body.content)},requestId},...events.map(event=>({...event,requestId}))]});
          dispatch({type:'events',events,requestId});
        }
        return;
      }
      const requestSessionId=await ensureSession();
      if(epoch.current!==requestEpoch)return;
      if(stopRequested.current){dispatch({type:'failed',detail:'请求已停止，尚未提交执行。'});setStopping(false);return;}
      const streamed:AgentEvent[]=[];
      let catalogRefresh: Promise<void> | undefined;
      const result = await agent.sendMessage(requestSessionId, 'content' in body
        ? { content: body.content, request_id: requestId, ...(requestWorkspace.cube_id ? { workspace: requestWorkspace } : {}) } : {...body,request_id:requestId}, event=>{
          if(epoch.current!==requestEpoch||callbacks.current.generation!==requestGeneration)return;
          if(event.event==='workspace')validateWorkspaceEvent(event.data);
          streamed.push(event);
          dispatch({type:'events',events:[event],requestId,streaming:true});
          // Refresh committed imports even if a later model/transport step fails.
          if (catalogChanged([event])) catalogRefresh = onCatalogChanged?.();
          if(event.event==='step'&&['annotations.prepare_batch','annotations.task'].includes(event.data.tool)&&event.data.result_summary.status==='accepted'
            &&typeof event.data.result_summary.task_id==='string'){
            const card:TaskCard={taskId:event.data.result_summary.task_id,sessionId:requestSessionId,generation,requestId};
            setTaskCards(current=>[...new Map([...current,card].map(item=>[item.taskId,item])).values()]);
          }
        },()=>epoch.current===requestEpoch&&!stopRequested.current);
      if (epoch.current !== requestEpoch || callbacks.current.generation !== requestGeneration) return;
      const buffered=result.events;
      result.events=[...streamed,...buffered];
      if (catalogChanged(buffered)) catalogRefresh = onCatalogChanged?.();
      // Navigation refreshes only the selected cube's name. Finish the full
      // catalog reload first so that it cannot be replaced by that narrow read.
      await catalogRefresh;
      if (epoch.current !== requestEpoch || callbacks.current.generation !== requestGeneration) return;
      for (const event of result.events) if (event.event === 'workspace') validateWorkspaceEvent(event.data);
      dispatch({ type: 'events', events: buffered, requestId });
      for (const event of result.events) if(event.event==='step'&&event.data.status==='ok') {
        if(event.data.tool.startsWith('preprocess.draft_')) draftsChanged();
        if(event.data.tool === 'preprocess.form_update') { draftsChanged(); recipesChanged(); }
        if(['preprocess.recipe_create','preprocess.recipe_version_add','preprocess.draft_save','preprocess.recipe_delete','preprocess.recipe_restore'].includes(event.data.tool)) recipesChanged();
      }
      const batchSteps = result.events.filter(event => event.event === 'step' && event.data.tool === 'annotations.prepare_batch');
        const acceptedTasks = result.events.flatMap(event=>event.event==='step'&&['annotations.prepare_batch','annotations.task'].includes(event.data.tool)&&event.data.result_summary.status==='accepted'
          && typeof event.data.result_summary.task_id==='string'?[{taskId:event.data.result_summary.task_id,sessionId:sessionId.current!,generation,requestId}]:[]);
        if(acceptedTasks.length)setTaskCards(current=>[...new Map([...current,...acceptedTasks].map(c=>[c.taskId,c])).values()]);
        const cards = batchSteps.filter(event=>event.event==='step'&&event.data.result_summary.status!=='accepted').map((event, index): BatchCard => {
        if (event.event !== 'step') throw new Error('批次事件非法');
        return { result: event.data.status === 'ok' ? parseBatchSummary(event.data.result_summary) : null,
          stepStatus: event.data.status, epoch: requestEpoch, generation,
          sessionId: sessionId.current!, requestId,
          key: `${requestEpoch}:${state.entries.length}:${event.data.seq}:${index}` };
      });
      if (cards.length) setBatchCards(current => [...current, ...cards]);
      const needsCanvas = !batchSteps.length && result.events.some(event =>
        event.event === 'step' && event.data.status === 'ok' && CANVAS_ANNOTATION_TOOLS.has(event.data.tool));
      let lastWorkspace: WorkspaceEventData | null = null;
      for (const event of result.events) if (event.event === 'workspace') {
        onWorkspaceChange?.({ cube_id: event.data.cube_id, ...(event.data.gesture_ref ? { gesture_ref: event.data.gesture_ref } : {}) });
        onWorkspaceDisplayChange?.(event.data);
        lastWorkspace = event.data;
        if (needsCanvas || event.data.stage === 'preprocess' || result.events.some(item => item.event === 'done'
            && item.data.data_intake?.stage === 'imported')) onWorkspaceNavigate?.(event.data);
      }
      if (cards.length) {
        const last = cards.at(-1)!;
        if (isBatchActive(last) && last.result?.status === 'ready' && last.result.autoOpen
            && lastWorkspace?.stage === 'annotation' && lastWorkspace.cube_id === last.result.openCubeId) {
          callbacks.current.onBatchOpen?.({ result: last.result, epoch: requestEpoch, generation });
        }
      }
      for (const preview of proposedCandidates(result.events)) onPreviewCandidate?.(preview.cube_id, preview.candidate_ref);
      const changed = changedCubes(result.events, requestWorkspace);
      if (changed.length) onDataChanged?.(changed);
      const id=requestSessionId;
      try {
        const detail=await agent.getSession(id);
        const page=await agent.getHistory(id);
        if (currentTicket(requestEpoch) && sessionId.current===id) {
          if(detail.id!==id||page.session_id!==id||!detail.boot_id
            ||callbacks.current.bootId&&detail.boot_id!==callbacks.current.bootId)throw {error:'SESSION_IDENTITY_MISMATCH'};
          setSessionDetail(detail);historyRows.current=page.events;setHistoryBefore(page.next_before);
          hydrate(detail,page.events);setRecoveryFailed(false);setSyncError(null);
        }
      } catch(error) {
        if(currentTicket(requestEpoch)&&sessionId.current===id){
          // The authenticated response already arrived. A failed readback does
          // not turn its completed tools or reply into a failed submission.
          setRecoveryFailed(true);
          setSyncError('本次响应已保留，但会话状态刷新失败：'+requestError(error)+'。请核对会话状态，未自动重发。');
        }
      }
    } catch (error) {
      if (epoch.current === requestEpoch) {
        if(error&&typeof error==='object'&&(error as {pre_execution?:boolean}).pre_execution){
          setRecoveryFailed(false);setStopError(null);
          if('content' in body && !options.preserveComposer)setContent(draft=>draft||body.content);
          dispatch({type:'failed',detail:requestError(error),preExecution:true});
          return;
        }
        setRecoveryFailed(true);
        dispatch({ type: 'failed', detail: requestError(error) + '；先核对会话状态和历史，未自动重发。' });
        const id=sessionId.current;
        if (id) {
          try { const detail=await agent.getSession(id);const page=await agent.getHistory(id);
            if(currentTicket(requestEpoch)&&sessionId.current===id){setSessionDetail(detail);setRecoveryFailed(false);historyRows.current=page.events;setHistoryBefore(page.next_before);hydrate(detail,page.events);}
          } catch { /* Unknown remains unknown. A new send requires an explicit user action. */ }
        }
      }
    } finally { if (epoch.current === requestEpoch) {inFlight.current = false;setStopping(false);} }
  };
  const startAnnotation = async(mode:'per_image'|'all',targets?:string[])=>{
    if(!enabled||inFlight.current||sessionOperation.current||state.pending||loading)return;
    const cubeIds=targets?[...targets]:records.map(row=>row.id);
    if(!cubeIds.length)return;
    const ticket=epoch.current;inFlight.current=true;setLoading(true);
    const requestId=crypto.randomUUID();
    dispatch({type:'send',content:mode==='all'?'选择提前生成全部超像素':'选择逐张生成超像素',requestId});
    try {
      const id=await ensureSession();
      if(!currentTicket(ticket))return;
      const accepted=await agent.startAnnotation(id,cubeIds,mode,requestId);
      if(!currentTicket(ticket)||sessionId.current!==id)return;
      setTaskCards(current=>[...current,{taskId:accepted.task_id,sessionId:id,generation,requestId,targetCubeIds:cubeIds,onDemand:mode==='per_image',authorizationId:accepted.flow_id}]);
      const detail=await agent.getSession(id);
      const page=await agent.getHistory(id);
      if(currentTicket(ticket)){setSessionDetail(detail);historyRows.current=page.events;setHistoryBefore(page.next_before);hydrate(detail,page.events);}
    } catch(e){if(currentTicket(ticket))dispatch({type:'failed',detail:requestError(e)});}
    finally {if(currentTicket(ticket)){inFlight.current=false;setLoading(false);}}
  };
  const taskActive=(card:TaskCard)=>enabled&&card.sessionId===sessionId.current&&card.generation===generation;
  const prepareCube=async(cubeId:string,authorizationId?:string)=>{
    const id=sessionId.current,startingGeneration=callbacks.current.generation;
    if(!id)throw new Error('请先在助手中选择标注方式');
    const submitted=await agent.prepareCube(id,cubeId,crypto.randomUUID(),authorizationId);
    while(callbacks.current.enabled&&callbacks.current.generation===startingGeneration&&sessionId.current===id){
      const result=await agent.annotationTask(id,submitted.task_id);
      if(result.session_id!==id||result.task_id!==submitted.task_id||callbacks.current.bootId&&result.owner_boot_id!==callbacks.current.bootId)throw new Error('准备任务归属不一致');
      if(result.task_status==='completed'&&result.counts.ready===1)return;
      if(['completed','failed','canceled'].includes(result.task_status))throw new Error(result.error??'本图超像素未就绪，请返回助手核查或重试');
      await new Promise(resolve=>setTimeout(resolve,750));
    }
    throw new Error('会话或引擎已变化，已停止等待旧任务');
  };
  const openTask=(card:TaskCard,result:BatchResult)=>{
    if(!taskActive(card)||inFlight.current||state.busy)return;
    const targetCubeIds=card.targetCubeIds??result.members.map(m=>m.cubeId);
    if(result.readyMembers.some(m=>!targetCubeIds.includes(m.cubeId)))return;
    onDataChanged?.(result.readyMembers.map(m=>m.cubeId));
    callbacks.current.onBatchOpen?.({result,epoch:epoch.current,generation,targetCubeIds,onDemand:true,authorizationId:card.authorizationId??result.authorizationId});
  };
  const retriedTask=(card:TaskCard,taskId:string,requestId:string,mode:'failed'|'remaining')=>{
    if(taskActive(card)){
      setTaskCards(current=>[...current,{...card,taskId,requestId}]);
      if(inFlight.current||state.busy||state.pending)return; // The journal is restored with the active request; do not clear its pending/busy state.
      dispatch({type:'send',content:mode==='failed'?'重试失败项':'继续未完成的超像素任务',requestId});
      dispatch({type:'events',requestId,events:[{event:'done',data:{content:'超像素任务已受理。',step_count:0,task_result:'working',annotation_task_id:taskId}}]});
    }
  };
  const focusCanvas=async(cubeId:string,focused:boolean)=>{
    const ticket=epoch.current;
    const id=focused?await ensureSession():sessionId.current;
    if(id){
      await agent.focusCanvas(id,cubeId,focused);
      if(focused&&!activeRef.current){
        const detail=await agent.getSession(id);
        if(currentTicket(ticket)&&sessionId.current===id){setSessionDetail(detail);}
      }
    }
  };
  return { projects, deletedProjects, projectId, changeProject, createProject, deleteProject, restoreProject, refreshProjects, state, dispatch, content, setContent, runtime, request, choices, selected, selectedChoice, startNew,
    enabled: enabled && !loading, canSend:enabled&&!loading&&!archivingSessionId&&!recoveryFailed&&!state.busy&&active?.request?.status!=='running',
    active, activeSessionId:sessionId.current, historyBefore, loading, sessions, sessionsCursor, sessionsLoading, sessionsError, archivingSessionId,
    refreshSessions, loadMoreSessions, archiveSession, clearSessionsError,
    sessionControlsDisabled:!enabled||loading||state.busy||inFlight.current||!!archivingSessionId||active?.request?.status==='running',
    stop, stopping, stopError, syncError, elapsedSeconds, refreshSession,
    editLastRequest:()=>setContent(lastUserMessage.current||[...state.entries].reverse().find(entry=>entry.event==='user')?.data.content||''),
    continueRequest:()=>request({content:'请先核对上一请求的真实执行结果，仅继续尚未执行的部分，保留已完成结果，不重复执行已完成操作。'}),
    switchSession, selectCube, loadOlder, selectionEpoch: epoch.current, isCurrentEpoch: currentTicket, currentEpoch: () => epoch.current,
    workspace, records, catalogPhase, displayName, onWorkspaceChange, batchCards, isBatchActive, openBatch, retryBatch,
    taskCards, taskActive, openTask, retriedTask, startAnnotation, prepareCube, focusCanvas, bootId, ensureSession };
}

export type AssistantSession = ReturnType<typeof useSession>;
