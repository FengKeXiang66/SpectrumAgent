import { useEffect, useRef, useState } from 'react';
import { describeAnnotationError, type Label, type LabelBody } from './types.ts';

type Props = {
  labels: Label[]; projectId: string; selectedId: string | null; disabled: boolean; allowSelection?: boolean;
  onSelect(id: string): void; onAdd(body: LabelBody): Promise<void>; onDelete(id: string): Promise<void>;
};

export default function LabelPanel({ labels, projectId, selectedId, disabled, allowSelection = false, onSelect, onAdd, onDelete }: Props) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState(''), [color, setColor] = useState('#2563eb');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false), [deleting, setDeleting] = useState<string | null>(null);
  const locked = disabled || pending;
  const dialog = useRef<HTMLDialogElement>(null);
  const deletingLabel = labels.find(label => label.id === deleting);
  useEffect(() => {
    if (deletingLabel && !dialog.current?.open) dialog.current?.showModal();
  }, [deletingLabel]);
  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || locked) return;
    setError(''); setPending(true);
    try {
      await onAdd({ project_id: projectId, name: trimmed, color_hex: color });
      setName(''); setAdding(false);
    } catch (failure) { setError(describeAnnotationError(failure)); }
    finally { setPending(false); }
  };
  const remove = async (id: string) => {
    if (locked) return;
    setError(''); setPending(true);
    try { await onDelete(id); setDeleting(null); }
    catch (failure) { setError(describeAnnotationError(failure)); }
    finally { setPending(false); }
  };
  return <section className="annotation-card" aria-label="项目标签">
    <h3>标签</h3>
    <div className="annotation-labels">
      {labels.map(label => <div key={label.id} className="annotation-label-row"><button type="button"
        className={selectedId === label.id ? 'annotation-label selected' : 'annotation-label'}
        disabled={pending || (disabled && !allowSelection)} aria-pressed={selectedId === label.id} onClick={() => onSelect(label.id)}>
        <i className="annotation-swatch" style={{ backgroundColor: label.color_hex }} />
        <span className="annotation-label-name">{label.name}</span>
      </button><button type="button" className="annotation-label-delete" disabled={locked}
        aria-label={`删除标签 ${label.name}`} onClick={() => { setDeleting(label.id); setError(''); }}>删除</button>
      </div>)}
    </div>
    {!labels.length && !adding && <p className="annotation-hint">暂无标签，请新建标签后开始标注。</p>}
    <button type="button" disabled={locked} onClick={() => { setAdding(!adding); setError(''); }}>新建标签</button>
    {adding && <form className="annotation-new-label" aria-label="新建标签" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <label>名字<input required value={name} disabled={locked} onChange={event => setName(event.target.value)} /></label>
      <label>颜色<input type="color" value={color} disabled={locked} onChange={event => setColor(event.target.value)} /></label>
      <div><button type="submit" disabled={locked || !name.trim()}>新建</button>
        <button type="button" disabled={locked} onClick={() => setAdding(false)}>取消</button></div>
    </form>}
    {error && <p role="alert" className="annotation-error">{error}</p>}
    {deletingLabel && <dialog ref={dialog} className="annotation-label-confirm" aria-labelledby="delete-label-title"
      onKeyDown={event => event.stopPropagation()} onCancel={event => { if (pending) event.preventDefault(); else setDeleting(null); }}>
      <h4 id="delete-label-title">永久删除“{deletingLabel.name}”？</h4>
      <p>将清除所有图片当前工作态中该标签的标注及样品关联，删除后无法恢复。已经保存的 JSON 结果及其中的类别信息会保留。</p>
      <button type="button" disabled={locked} onClick={() => { void remove(deletingLabel.id); }}>永久删除</button>
      <button type="button" disabled={locked} autoFocus onClick={() => setDeleting(null)}>取消</button>
      {error && <p role="alert" className="annotation-error">{error}</p>}
    </dialog>}
  </section>;
}
