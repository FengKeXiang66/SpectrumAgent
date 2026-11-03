import AssistantBar from '../components/assistant/AssistantBar';
import type { AssistantSession } from '../components/assistant/useSession';
import { displayName as datasetDisplayName } from '../components/datasets/types';
import '../components/assistant/assistant.css';

export type SmokeMetrics = { nan_ratio: number; reflectance_range: [number, number]; bands: number; shape: [number, number, number]; elapsed_ms: number };
export default function S01({ session, smoke }: { session: AssistantSession; smoke: {
  text: string; setText(value: string): void; message: string; busy: boolean;
  metrics: SmokeMetrics | null; send(): Promise<void>;
} }) {
  const { enabled, state, startNew, runtime, workspace, selected, selectedChoice, displayName, choices, onWorkspaceChange, request } = session;
  return <section className="assistant-s01" aria-label="S01 全屏助手">
    <aside className="assistant-s01-left" aria-label="当前会话">
      <p aria-current="true">当前会话</p>
      <button disabled={!enabled || state.busy || !!state.pending} onClick={startNew}>开始新对话</button>
    </aside>
    <div className="assistant-s01-mid">
      <AssistantBar session={session} />
      <section aria-label="引擎冒烟测试">
        <p role="status">{smoke.message}</p>
        <form onSubmit={event => { event.preventDefault(); void smoke.send(); }}>
          <label htmlFor="agent-input">冒烟测试</label>
          <input id="agent-input" value={smoke.text} onChange={event => smoke.setText(event.target.value)} disabled={smoke.busy} placeholder="运行冒烟测试" />
          <button type="submit" disabled={smoke.busy}>{smoke.busy ? '运行中' : '发送'}</button>
        </form>
        {smoke.metrics && <pre aria-label="冒烟测试真实结果">{JSON.stringify(smoke.metrics, null, 2)}</pre>}
      </section>
    </div>
    <aside className="assistant-s01-right" aria-label="会话上下文">
      <p className="assistant-context" aria-label="当前对话对象">{workspace.cube_id
        ? `当前数据：${(selected && datasetDisplayName(selected)) || selectedChoice?.label || displayName || workspace.cube_id.slice(0, 8)}${workspace.gesture_ref ? ' · 已带入最近的画布提示' : ''}`
        : '可在工作台选择数据，或直接告诉助手要处理哪份数据。'}</p>
      <p className="assistant-runtime" aria-label="当前编排版本">{runtime?.skill_name
        ? `当前编排：${runtime.skill_name} · 工具目录 v${runtime.tool_catalogue_version} · ${runtime.tool_count} 个工具`
        : '当前编排版本读取中…'}</p>
      {choices.length > 0 && <section className="assistant-datasets" aria-label="对话中的数据集选择">
        <p>可按序号选择，也可以继续说“第一个”或数据名称。</p>
        <ol>{choices.map(choice => <li key={choice.id}>
          <button disabled={!enabled || state.busy || !!state.pending} aria-pressed={workspace.cube_id === choice.id}
            onClick={() => { onWorkspaceChange?.({ cube_id: choice.id }); void request({ content: `选择第${choice.index}个数据集`, workspace: { cube_id: choice.id } }); }}>
            {choice.index}号 · {choice.label} · {choice.id.slice(0, 8)}
          </button>
          <details><summary>数据引用</summary><code>{choice.id}</code></details>
        </li>)}</ol>
      </section>}
    </aside>
  </section>;
}
