import type { RefObject } from 'react';
import { displayName } from '../datasets/types';
import { SCREEN_TITLE, type Screen } from '../../shell/screens';
import type { AssistantSession } from './useSession';
import './assistant.css';
import SessionScope from './SessionScope';
import RequestStatus from './RequestStatus';
import MessageInput from './MessageInput';

export default function Composer({ session, screen, inputRef, onExpand }: {
  session: AssistantSession; screen: Screen; inputRef: RefObject<HTMLTextAreaElement | null>; onExpand(): void;
}) {
  const { enabled, state, content, request, selected, workspace } = session;
  const context = selected ? displayName(selected) : workspace.cube_id?.slice(0, 8) ?? '未选择';
  return <footer className="composer" aria-label="常驻对话条">
    <RequestStatus session={session}/>
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}
      onKeyDown={event => {
        if (!event.ctrlKey) return;
        if (event.key.toLowerCase() === 'k') event.preventDefault();
      }}>
      <span className="agent-composer-icon" aria-hidden="true">◈</span>
      <span className="composer-context" title={`画布：${context} · 视图「${SCREEN_TITLE[screen]}」`}><SessionScope session={session} compact /> · 画布：{context} · 视图「{SCREEN_TITLE[screen]}」</span>
      <label htmlFor="composer-message">对话</label>
      <MessageInput inputRef={inputRef} id="composer-message" session={session}/>
      <div className="assistant-compose-actions">
      <span className="agent-composer-kb">Shift+Enter 换行</span>
      <button type="button" onClick={onExpand}>展开助手页</button>
      {state.busy?<button type="button" className="agent-stop" disabled={!enabled||session.stopping} onClick={()=>void session.stop()}>{session.stopping?'正在停止…':'停止'}</button>
        :<button type="submit" disabled={!session.canSend || !content.trim()}>发送</button>}
      </div>
    </form>
  </footer>;
}
