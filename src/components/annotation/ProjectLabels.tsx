import { useEffect, useState } from 'react';
import { annotations } from './api.ts';
import { describeAnnotationError, type AnnotationApi, type LabelBody, type LabelSchema, type Project } from './types.ts';
import { orderedLabels } from './working.ts';
import LabelPanel from './LabelPanel.tsx';
import './annotation.css';
import './annotation-skin.css';

export default function ProjectLabels({ api = annotations, onOpenData }: { api?: AnnotationApi; onOpenData(): void }) {
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
    <p>标签可独立创建和管理，无需先导入数据。创建和删除会自动保存。</p>
    {projects.length > 1 && <label>项目<select value={project} disabled={busy} onChange={event => setProject(event.target.value)}>
      {projects.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
    </select></label>}
    {error && <p role="alert" className="annotation-error">{error}</p>}
    {project && <LabelPanel key={project} projectId={project} labels={orderedLabels(schemas)} selectedId={selected}
      disabled={busy} onSelect={setSelected} onAdd={(body: LabelBody) => mutate(() => api.addLabel(body))}
      onDelete={id => mutate(() => api.deleteLabel(id))} />}
    {busy && <p role="status">正在读取标签…</p>}
    <p>导入数据后，选择图片即可开始标注。</p><button type="button" onClick={onOpenData}>前往数据屏</button>
  </section>;
}
