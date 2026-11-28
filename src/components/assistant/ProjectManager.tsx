import {useEffect, useRef, useState} from 'react';
import type {AssistantSession} from './useSession';
import {agent, type ProjectDeletionPreview} from './api';
import {requestError} from './sse';

export function ProjectDeletionReview({preview, name, disabled, onName, onConfirm, onCancel}: {
  preview: ProjectDeletionPreview; name: string; disabled: boolean;
  onName(value: string): void; onConfirm(): void; onCancel(): void;
}) {
  return <section className="project-delete-review" aria-label="确认删除项目">
    <strong>删除「{preview.name}」？</strong>
    <p>{preview.dataset_count} 个数据集 · {preview.session_count} 个对话 · {preview.label_count} 个标签 · {preview.recipe_count} 个配方 · {preview.experiment_count} 个实验／寻优记录</p>
    <p>项目及其内容将从正常列表移入回收站，可恢复。原始数据文件、标注、模型和结果文件保留，数据记录仍归属原项目。</p>
    <p>删除当前项目后，会切换到其他可用项目。至少保留一个可用项目。</p>
    <label>输入项目名称确认<input value={name} disabled={disabled} autoComplete="off" onChange={e => onName(e.target.value)} /></label>
    <div className="work-actions">
      <button type="button" className="project-danger" disabled={disabled || name !== preview.name} onClick={onConfirm}>确认移入回收站</button>
      <button type="button" disabled={disabled} onClick={onCancel}>取消</button>
    </div>
  </section>;
}

export default function ProjectManager({session}: {session: AssistantSession}) {
  const [creating, setCreating] = useState(false), [managing, setManaging] = useState(false);
  const [name, setName] = useState(''), [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [preview, setPreview] = useState<ProjectDeletionPreview | null>(null);
  const previewTicket = useRef(0);
  useEffect(() => {previewTicket.current++; setPreview(null); setConfirmation(''); setError('');}, [session.projectId]);
  const disabled = session.sessionControlsDisabled || !session.enabled || !session.projectId || busy;
  async function review(id: string) {
    const ticket = ++previewTicket.current;
    const epoch = session.currentEpoch();
    setBusy(true); setError(''); setPreview(null); setConfirmation('');
    try {
      const value = await agent.projectDeletionPreview(id);
      if (ticket === previewTicket.current && session.isCurrentEpoch(epoch)) setPreview(value);
    } catch (e) {if (ticket === previewTicket.current) setError(requestError(e));}
    finally {setBusy(false);}
  }
  return <section className="project-management" aria-label="项目管理">
    <header><h3>项目</h3><button type="button" disabled={disabled} aria-expanded={creating}
      onClick={() => {setCreating(!creating); setPreview(null);}}>新建项目</button>
      <button type="button" disabled={disabled} aria-expanded={managing}
        onClick={() => {setManaging(!managing); setPreview(null);}}>管理项目</button></header>
    {creating && <div className="project-create">
      <label>项目名称<input value={name} maxLength={100} disabled={disabled} placeholder="例如：鸡蛋受精识别" onChange={e => setName(e.target.value)} /></label>
      <p>适合另一项独立课题；创建后会切换到新项目。</p>
      <button type="button" disabled={disabled || !name.trim()} onClick={async () => {
        setBusy(true);
        try {if (await session.createProject(name.trim())) {setName(''); setCreating(false);}}
        finally {setBusy(false);}
      }}>{busy ? '正在创建…' : '创建并切换'}</button>
      <button type="button" disabled={busy} onClick={() => setCreating(false)}>取消</button>
    </div>}
    {managing && <div className="project-management-list">
      <p>删除项目可在下方回收站恢复；运行中的项目须先结束任务。</p>
      <button type="button" disabled={disabled} onClick={() => void session.refreshProjects()}>刷新项目列表</button>
      <ul aria-label="可用项目">{session.projects.map(project => <li key={project.id}>
        <strong>{project.name}{project.id === session.projectId && '（当前）'}</strong>
        <button type="button" className="project-danger" aria-label={'删除项目 '+project.name}
          disabled={disabled || session.projects.length <= 1} onClick={() => void review(project.id)}>删除</button>
      </li>)}</ul>
      {session.projects.length <= 1 && <p>至少保留一个可用项目。</p>}
      <details><summary>项目回收站（{session.deletedProjects.length}）</summary>
        {!session.deletedProjects.length && <p>回收站为空。</p>}
        <ul>{session.deletedProjects.map(project => <li key={project.id}>
          <span>{project.name}</span><button type="button" disabled={disabled} aria-label={'恢复项目 '+project.name}
            onClick={async () => {setBusy(true); try {await session.restoreProject(project.id);} finally {setBusy(false);}}}>恢复</button>
        </li>)}</ul>
      </details>
    </div>}
    {preview && <ProjectDeletionReview preview={preview} name={confirmation} disabled={disabled} onName={setConfirmation}
      onCancel={() => setPreview(null)} onConfirm={async () => {
        setBusy(true);
        try {if (await session.deleteProject(preview.id, confirmation, preview.confirmation_token)) setPreview(null);}
        finally {setBusy(false);}
      }} />}
    {error && <p className="agent-session-error" role="alert">{error}</p>}
  </section>;
}
