import type { AssistantSession } from './useSession';

export function currentProjectName(session: AssistantSession) {
  return (session.active?.project_id === session.projectId && session.active?.project_name)
    || session.projects.find(project => project.id === session.projectId)?.name || '项目读取中…';
}

export default function SessionScope({session, compact = false}: {session: AssistantSession; compact?: boolean}) {
  const detail = session.active;
  const disabled = !session.enabled || session.sessionControlsDisabled || session.state.busy || session.loading
    || detail?.request?.status === 'running';
  const count = session.loading || !session.projectId ? undefined : session.catalogPhase !== undefined
    ? session.catalogPhase === 'ready' ? session.records.length : undefined
    : detail?.project_id === session.projectId ? detail?.total_members : undefined;
  const dataLabel = count !== undefined ? `项目数据：${count} 个数据集` : '项目数据：待核对';
  const interrupted = detail?.request?.status === 'interrupted';
  if (compact) return <span className="project-scope-compact" aria-label="当前会话范围">
    项目：{currentProjectName(session)} · {dataLabel}
    {interrupted && <strong> · 请求中断，须核对已知执行结果后明确继续</strong>}
  </span>;
  return <section className="project-scope" aria-label="项目与对话">
    <label className="project-scope-label">当前项目
      <select aria-label="当前项目" value={session.projectId} disabled={disabled || !session.projects.length}
        onChange={event => void session.changeProject(event.target.value)}>
        {!session.projects.length && <option value="">项目读取中…</option>}
        {session.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
    </label>
    <p className="project-data-count">{dataLabel}</p>
    <p className="project-scope-hint">切换项目时，对话列表和数据会一起切换。</p>
    <details className="project-help"><summary>项目、对话和数据是什么关系？</summary>
      <p>项目保存数据、标签、配方、实验和模型。一个项目可以有多个对话。</p>
      <p>同一项目的对话共享这些资源，各自保存消息和方案；新建对话无需重新导入数据。</p>
      <p>继续原来的步骤，打开原对话；同批数据尝试另一方案，新建对话；另一项独立课题，新建项目。</p>
      <p>训练使用哪些数据，以方案卡中确认的样品名单为准。</p>
    </details>
  </section>;
}
