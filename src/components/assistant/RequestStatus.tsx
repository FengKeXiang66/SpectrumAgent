import type { AssistantSession } from './useSession';

export default function RequestStatus({session}:{session:AssistantSession}) {
  const {state,stopping,elapsedSeconds,stopError,syncError,active}=session;
  const interrupted=active?.request?.status==='interrupted';
  const recoverable=!state.preExecution&&(!!state.error||!syncError&&(interrupted||active?.request?.status==='failed'));
  return <>
    {state.busy&&<p role="status" className="agent-busy">
      {stopping?'正在停止，等待当前操作安全结束':state.phase??'正在核对请求状态'} · 已等待 {elapsedSeconds??0} 秒
      {elapsedSeconds>=30&&!stopping&&' · 可停止本次请求，已完成结果会保留'}
    </p>}
    {stopError&&<p role="alert" className="agent-error">{stopError}</p>}
    {syncError&&<p role="alert" className="agent-error">{syncError}</p>}
    {recoverable&&!state.busy&&<div className="agent-interrupted" role="status">
      <span>请求未完成。已完成结果保留；已受理的后台任务请在任务卡片中核对。</span>
      <button type="button" disabled={!session.canSend} onClick={session.editLastRequest}>重新编辑请求</button>
      <button type="button" disabled={!session.canSend} onClick={()=>void session.continueRequest()}>核对并继续未完成</button>
    </div>}
    {(stopError||syncError||state.error)&&!state.busy&&<button type="button" onClick={()=>void session.refreshSession().catch(()=>undefined)}>核对会话状态</button>}
  </>;
}
