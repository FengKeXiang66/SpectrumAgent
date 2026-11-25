import type { RefObject } from 'react';
import type { AssistantSession } from './useSession';

export default function MessageInput({ id, session, inputRef }: {
  id: string; session: AssistantSession; inputRef?: RefObject<HTMLTextAreaElement | null>;
}) {
  const { enabled, state, content, setContent } = session;
  return <textarea id={id} ref={inputRef} rows={2} wrap="soft" disabled={!enabled}
    value={content} onChange={event => setContent(event.target.value)}
    placeholder={state.busy ? '可先编辑下一条消息，停止后发送' : state.pending ? '可输入批准、确认保存或拒绝' : '输入需要编排的任务'}
    onKeyDown={event => {
      if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
      event.preventDefault();
      if (!event.repeat && session.canSend && !state.busy && content.trim()) event.currentTarget.form?.requestSubmit();
    }} />;
}
