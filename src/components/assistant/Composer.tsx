import type { RefObject } from 'react';
import { displayName } from '../datasets/types';
import { SCREEN_TITLE, type Screen } from '../../shell/screens';
import type { AssistantSession } from './useSession';
import './assistant.css';

export default function Composer({ session, screen, inputRef, onExpand }: {
  session: AssistantSession; screen: Screen; inputRef: RefObject<HTMLInputElement | null>; onExpand(): void;
}) {
  const { enabled, state, content, setContent, request, selected, workspace } = session;
  const context = selected ? displayName(selected) : workspace.cube_id?.slice(0, 8) ?? '未选择';
  return <footer className="composer" aria-label="常驻对话条">
    <form onSubmit={event => { event.preventDefault(); void request({ content }); }}
      onKeyDown={event => {
        if (!event.ctrlKey) return;
        if (event.key.toLowerCase() === 'k') event.preventDefault();
        if (event.key === 'Enter') { event.preventDefault(); void request({ content }); }
      }}>
      <span className="agent-composer-icon" aria-hidden="true">◈</span>
      <span className="composer-context" title={`当前数据：${context} · 视图「${SCREEN_TITLE[screen]}」`}>当前数据：{context} · 视图「{SCREEN_TITLE[screen]}」</span>
      <label htmlFor="composer-message">对话</label>
      <input ref={inputRef} id="composer-message" value={content} onChange={event => setContent(event.target.value)}
        disabled={!enabled || state.busy} placeholder={state.pending ? '可输入批准、确认保存或拒绝' : '输入需要编排的任务'} />
      <span className="agent-composer-kb">Ctrl+Enter 发送</span>
      <button type="button" onClick={onExpand}>展开助手页</button>
      <button type="submit" disabled={!enabled || state.busy || !content.trim()}>发送</button>
    </form>
  </footer>;
}
