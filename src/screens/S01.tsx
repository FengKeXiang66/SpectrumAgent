import AssistantBar from '../components/assistant/AssistantBar';
import type { AssistantSession } from '../components/assistant/useSession';
import { displayName as datasetDisplayName } from '../components/datasets/types';
import '../components/assistant/assistant.css';
import SessionScope from '../components/assistant/SessionScope';

export default function S01({ session }: { session: AssistantSession }) {
  const { enabled, state, runtime, workspace, selected, selectedChoice, displayName, choices } = session;
  return <section className="assistant-s01" aria-label="S01 全屏助手">
    <aside className="assistant-s01-left" aria-label="当前会话">
      <h3 className="agent-side-title">会话</h3>
      <button disabled={!enabled || state.busy || session.loading} onClick={session.startNew}>新建全局会话</button>
      <p className="agent-side-hint">助手只有一个全局会话；底部对话条在每一屏常驻，这里展开后是同一条会话的完整视图。</p>
    </aside>
    <div className="assistant-s01-mid">
      <AssistantBar session={session} />
    </div>
    <aside className="assistant-s01-right" aria-label="会话上下文">
      <SessionScope session={session} />
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
    </aside>
  </section>;
}
