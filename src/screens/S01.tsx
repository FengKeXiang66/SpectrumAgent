import { useEffect, useRef, useState } from 'react';
import AssistantBar from '../components/assistant/AssistantBar';
import type { AssistantSession } from '../components/assistant/useSession';
import { displayName as datasetDisplayName } from '../components/datasets/types';
import '../components/assistant/assistant.css';
import SessionScope from '../components/assistant/SessionScope';
import ProjectManager from '../components/assistant/ProjectManager';
import ExperimentHistory from '../components/assistant/ExperimentHistory';
import WorkViewer, { type ViewerTarget } from '../components/assistant/WorkViewer';

const tabs = {context:'上下文', history:'历史与模型', viewer:'查看器'} as const;
type WorkTab = keyof typeof tabs;
const localTime = new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});

export default function S01({ session }: { session: AssistantSession }) {
  const { enabled, state, runtime, workspace, selected, selectedChoice, displayName, choices } = session;
  const [tab,setTab] = useState<WorkTab>('context');
  const [collapsed,setCollapsed] = useState(false);
  const [viewer,setViewer] = useState<{owner:string|undefined;target:ViewerTarget}|null>(null);
  const sessionId = session.active?.id;
  const [confirmRemoval,setConfirmRemoval] = useState<string|null>(null);
  const previousSession = useRef(sessionId);
  useEffect(()=>{
    if (previousSession.current && previousSession.current!==sessionId) {
      setViewer(null);setTab('context');setCollapsed(false);setConfirmRemoval(null);
    }
    previousSession.current=sessionId;
  },[sessionId]);
  const sessionButtonsDisabled = session.sessionControlsDisabled || session.sessionsLoading;
  function openTab(next:WorkTab) {
    setTab(next);
    setCollapsed(false);
    if(next==='history'&&!sessionId&&!sessionButtonsDisabled)session.startNew();
  }
  function openViewer(target:ViewerTarget) {
    setViewer({owner:sessionId,target});
    openTab('viewer');
  }
  return <section className="assistant-s01" data-drawer={collapsed?'closed':tab==='context'?'compact':'expanded'} aria-label="S01 全屏助手">
    <aside className="assistant-s01-left" aria-label="会话">
      <ProjectManager session={session} />
      <SessionScope session={session} />
      <h3 className="agent-side-title">本项目的对话</h3>
      <button type="button" className="agent-primary" disabled={sessionButtonsDisabled} onClick={session.startNew}>新建对话</button>
      <p className="agent-side-hint">沿用本项目数据，单独保存消息和方案。</p>
      <div className="agent-session-scroll">
        <ul className="agent-session-list" aria-label="本项目的历史对话">
          {session.sessions.map(item=>{
            const title = item.title || '新会话 · '+item.id.slice(0,8);
            const current = item.id===session.activeSessionId;
            const running = item.request?.status==='running' || current&&state.busy;
            const pending = item.pending || current&&!!state.pending;
            const date = new Date(item.updated_at);
            return <li className="agent-session-item" key={item.id} data-active={current}>
              <button type="button" className="agent-session-open" disabled={sessionButtonsDisabled}
                aria-current={current?'true':undefined} onClick={()=>{setConfirmRemoval(null);void session.switchSession(item.id);}}>
                <span className="agent-session-name" title={title}>{title}</span>
                <small><time dateTime={item.updated_at}>{Number.isNaN(date.valueOf())?'—':localTime.format(date)}</time>
                  {running&&<span className="agent-session-badge">执行中</span>}
                  {pending&&<span className="agent-session-badge is-pending">待确认</span>}
                </small>
              </button>
              {confirmRemoval===item.id?<div className="agent-session-remove">
                <p>从列表隐藏，保留实验、模型和报告。</p>
                <button type="button" disabled={sessionButtonsDisabled} onClick={()=>void session.archiveSession(item.id)
                  .then(removed=>{if(removed)setConfirmRemoval(null);})}>
                  {session.archivingSessionId===item.id?'正在移除…':'确认移除'}</button>
                <button type="button" disabled={session.archivingSessionId===item.id} onClick={()=>{setConfirmRemoval(null);session.clearSessionsError();}}>取消</button>
              </div>:<button type="button" className="agent-session-remove-link" aria-label={'移除 '+title}
                disabled={sessionButtonsDisabled} onClick={()=>setConfirmRemoval(item.id)}>移除</button>}
            </li>;
          })}
        </ul>
        {session.sessionsLoading&&<p className="agent-side-hint" role="status">正在加载会话…</p>}
        {!session.sessions.length&&!session.sessionsLoading&&!session.sessionsError&&<p className="agent-side-hint">本项目还没有对话。可以直接在右侧发送消息。</p>}
      </div>
      {session.sessionsError&&<div className="agent-session-error"><p role="alert">{session.sessionsError}</p>
        {!session.sessions.length&&<button type="button" disabled={sessionButtonsDisabled}
          onClick={()=>void session.refreshSessions()}>重试加载</button>}</div>}
      {session.sessionsCursor&&<button type="button" disabled={sessionButtonsDisabled}
        onClick={()=>void session.loadMoreSessions()}>加载更多</button>}
    </aside>
    <div className="assistant-s01-mid">
      <AssistantBar session={session} onHistory={()=>openTab('history')} onViewer={openViewer}/>
    </div>
    {collapsed?<button className="work-drawer-toggle" aria-expanded={false} onClick={()=>setCollapsed(false)}>侧栏</button>:
      <aside className="assistant-s01-right" aria-label="工作侧栏">
        <nav className="work-tabs" aria-label="工作侧栏视图">
          {Object.entries(tabs).map(([key,title])=><button key={key} aria-pressed={tab===key}
            onClick={()=>openTab(key as WorkTab)}>{title}</button>)}
          <button aria-label="收起工作侧栏" onClick={()=>setCollapsed(true)}>收起</button>
        </nav>
        <div className="work-panel">
        {tab==='history'&&(sessionId?<ExperimentHistory key={sessionId} sessionId={sessionId} enabled={enabled}
          onInfer={modelId=>session.setContent('使用模型 '+modelId+' 进行推理，数据目录为')}
          onCommand={text=>{if(!state.busy)return session.request({content:text},{preserveComposer:text.startsWith('提交实物评价定义 ')});}}
          onInferenceView={(result,fileIndex)=>openViewer({kind:'inference',result,fileIndex})}/>
          :<p role="status">{session.loading?'正在打开历史实验…':'会话尚未就绪。'}</p>)}
        {tab==='viewer'&&<WorkViewer key={sessionId} target={viewer?.owner===sessionId?viewer?.target??null:null}
          sessionId={sessionId} onOpen={openViewer} enabled={enabled&&!state.busy&&!state.pending}
          send={text=>{if(!state.busy&&!state.pending)void session.request({content:text});}}/>}
        {tab==='context'&&<>
      <SessionScope session={session} compact />
      <p className="assistant-context" aria-label="当前对话对象">{workspace.cube_id
        ? `当前数据：${(selected && datasetDisplayName(selected)) || selectedChoice?.label || displayName || workspace.cube_id.slice(0, 8)}${workspace.gesture_ref ? ' · 已带入最近的画布提示' : ''}`
        : '可在工作台选择数据，或直接告诉助手要处理哪份数据。'}</p>
      <p className="assistant-runtime" aria-label="当前编排版本">{runtime?.skill_name
        ? `当前编排：${runtime.skill_name} · 工具目录 v${runtime.tool_catalogue_version} · 当前会话 ${session.active?.effective_tool_count ?? runtime.tool_count} 个工具`
        : '当前编排版本读取中…'}</p>
      {choices.length > 0 && <section className="assistant-datasets" aria-label="对话中的数据集选择">
        <p>可按序号选择，也可以继续说“第一个”或数据名称。</p>
        <ol>{choices.map(choice => <li key={choice.id}>
          <button disabled={!enabled || state.busy || !!state.pending} aria-pressed={workspace.cube_id === choice.id}
            onClick={() => { void session.selectCube(choice.id); }}>
            {choice.index}号 · {choice.label} · {choice.id.slice(0, 8)}
          </button>
          <details><summary>数据引用</summary><code>{choice.id}</code></details>
        </li>)}</ol>
      </section>}
        </>}
        </div>
      </aside>}
  </section>;
}
