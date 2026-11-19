import type { AssistantSession } from './useSession';

export default function SessionScope({session}: {session: AssistantSession}) {
  const detail=session.active;
  if (!detail) return <span>全局上下文：全部已导入数据 · {session.records.length} 张</span>;
  return <span aria-label="当前会话范围">全局会话 · 上下文：全部已导入数据 · {session.records.length} 张
    {detail.request?.status==='interrupted' && <strong> · 请求中断，须核对已知执行结果后明确继续</strong>}</span>;
}
