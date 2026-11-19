import { useState } from 'react';
import type { Label, LabelBody } from './types.ts';

type Props = {
  labels: Label[]; projectId: string; selectedId: string | null; disabled: boolean;
  onSelect(id: string): void; onAdd(body: LabelBody): Promise<void>;
};

export default function LabelPanel({ labels, projectId, selectedId, disabled, onSelect, onAdd }: Props) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState(''), [color, setColor] = useState('#2563eb');
  const [error, setError] = useState('');
  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setError('');
    try {
      await onAdd({ project_id: projectId, name: trimmed, color_hex: color });
      setName(''); setAdding(false);
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
  };
  return <section className="annotation-card" aria-label="项目标签">
    <h3>标签</h3>
    <div className="annotation-labels">
      {labels.map(label => <button key={label.id} type="button"
        className={selectedId === label.id ? 'annotation-label selected' : 'annotation-label'}
        disabled={disabled} aria-pressed={selectedId === label.id} onClick={() => onSelect(label.id)}>
        <i className="annotation-swatch" style={{ backgroundColor: label.color_hex }} />
        <span className="annotation-label-name">{label.name}</span>
      </button>)}
    </div>
    {!labels.length && !adding && <p className="annotation-hint">暂无标签，可直接新建或在编排助手中新建。</p>}
    <button type="button" disabled={disabled} onClick={() => { setAdding(!adding); setError(''); }}>新建标签</button>
    {adding && <form className="annotation-new-label" aria-label="新建标签" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <label>名字<input required value={name} disabled={disabled} onChange={event => setName(event.target.value)} /></label>
      <label>颜色<input type="color" value={color} disabled={disabled} onChange={event => setColor(event.target.value)} /></label>
      <div><button type="submit" disabled={disabled || !name.trim()}>新建</button>
        <button type="button" disabled={disabled} onClick={() => setAdding(false)}>取消</button></div>
    </form>}
    {error && <p role="alert" className="annotation-error">{error}</p>}
  </section>;
}
