import { useEffect, useState } from 'react';
import { annotations } from './api.ts';
import { describeAnnotationError, type AnnotationApi, type LabelSchema, type Project } from './types.ts';
import { orderedLabels } from './working.ts';
import LabelPanel from './LabelPanel.tsx';
import './annotation.css';
import './annotation-skin.css';

export default function ProjectLabels({ api = annotations, onOpenData, onCreate }: { api?: AnnotationApi; onOpenData(): void; onCreate(): void }) {
  const [projects, setProjects] = useState<Project[]>([]), [project, setProject] = useState('');
  const [schemas, setSchemas] = useState<LabelSchema[]>([]), [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(true), [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    void api.projects().then(rows => { if (live) { setProjects(rows); setProject(rows[0]?.id ?? ''); } })
      .catch(failure => { if (live) setError(describeAnnotationError(failure)); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [api]);
  useEffect(() => {
    if (!project) return;
    let live = true;
    setBusy(true); setSchemas([]); setSelected(null); setError('');
    void api.labels(project).then(rows => { if (live) setSchemas(rows); })
      .catch(failure => { if (live) setError(describeAnnotationError(failure)); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [api, project]);
  const mutate = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try {
      await operation();
      const tree = await api.labels(project);
      setSchemas(tree);
      setSelected(value => orderedLabels(tree).some(label => label.id === value) ? value : null);
    } finally { setBusy(false); }
  };
  return <section className="annotation-workbench ui-page" aria-label="S05 标注工作台">
    <h2>标注工作台</h2>
    <p>标签统一在 AI 对话中创建，无需先导入数据；此处可选择和删除已有标签。</p>
    {projects.length > 1 && <label>项目<select value={project} disabled={busy} onChange={event => setProject(event.target.value)}>
      {projects.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
    </select></label>}
    {error && <p role="alert" className="annotation-error">{error}</p>}
    {project && <LabelPanel key={project} labels={orderedLabels(schemas)} selectedId={selected}
      disabled={busy} onSelect={setSelected} onCreate={onCreate}
      onDelete={id => mutate(() => api.deleteLabel(id))} />}
    {busy && <p role="status">正在读取标签…</p>}
    <p>导入数据后，选择图片即可开始标注。</p><button type="button" onClick={onOpenData}>前往数据屏</button>
  </section>;
}
