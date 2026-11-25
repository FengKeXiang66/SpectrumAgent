import { useState } from 'react';
import type { Scalars } from './sse';
import InferenceAdjustmentForm from './InferenceAdjustmentForm';

export type InferenceDraft = {
  revision: number;
  ready: boolean;
  envi: boolean;
  foreground_enabled: boolean;
  todo: string;
  groups: {title: string; fields: {label: string; value: string}[]}[];
  changes: {label: string; before: string; after: string}[];
  raw: string;
  science: string;
  checked_files?: number;
  excluded_files?: number;
};

export function inferenceDraft(summary: Scalars): InferenceDraft | undefined {
  if (typeof summary.inference_card_json !== 'string') return;
  try {
    const value = JSON.parse(summary.inference_card_json) as InferenceDraft | null;
    if (value && typeof value.revision === 'number' && typeof value.todo === 'string'
      && Array.isArray(value.groups) && Array.isArray(value.changes)) return value;
  } catch { /* Older or unreadable cards retain the plain text reply. */ }
}

export default function InferenceDraftCard({card, active, canAct, send}:{
  card: InferenceDraft;
  active: boolean;
  canAct: boolean;
  send: (text: string) => void;
}) {
  const [editing,setEditing]=useState(false);
  const changed = new Set(card.changes.map(change => change.label));
  return <section className="draft-review inference-draft" aria-label="推理方案">
    <p className="draft-todo">{card.todo}</p>
    {card.changes.length > 0 && <section className="draft-changes" aria-label="本轮变更">
      <strong>本轮变更</strong>
      <ul>{card.changes.map(change => <li key={change.label}>
        <strong>{change.label}</strong> · <span className="draft-before">{change.before}</span>
        <span aria-hidden="true"> → </span><span className="draft-after">{change.after}</span>
      </li>)}</ul>
    </section>}
    <div className="draft-groups">
      {card.groups.map(group => <section className="draft-group" key={group.title}>
        <h3>{group.title}</h3>
        <dl>{group.fields.map(field => <div className={changed.has(field.label) ? 'draft-field is-changed' : 'draft-field'} key={field.label}>
          <dt>{field.label}{changed.has(field.label) && <span className="draft-field-badge">已改</span>}</dt>
          <dd>{field.value}</dd>
        </div>)}
        {group.title === '模型与输入' && card.checked_files !== undefined && <div className="draft-field">
          <dt>已核验文件</dt><dd>{card.checked_files} 个{Boolean(card.excluded_files) && ' · 按范围排除 ' + card.excluded_files + ' 幅'}</dd>
        </div>}</dl>
      </section>)}
    </div>
    {active && editing && card.envi && <InferenceAdjustmentForm key={card.revision} revision={card.revision}
      canAct={canAct} send={send} onCancel={()=>setEditing(false)}/>}
    {active && !editing && <div className="work-actions">
      {card.ready && <button type="button" className="draft-primary" disabled={!canAct} onClick={() => send('确认推理')}>确认推理</button>}
      {card.envi&&<button type="button" disabled={!canAct} onClick={()=>setEditing(true)}>微调参数</button>}
      {card.envi && (card.ready || card.checked_files !== undefined) && <>
        {card.foreground_enabled && <button type="button" disabled={!canAct} onClick={() => send('关闭前景筛选')}>关闭前景筛选</button>}
        <button type="button" disabled={!canAct} onClick={() => send('探查前景')}>重新探查前景</button>
      </>}
    </div>}
    <details className="draft-details">
      <summary>原始参数、校验值与科学声明 · 修订 {card.revision}</summary>
      <p>{card.science}</p>
      <pre>{card.raw}</pre>
    </details>
  </section>;
}
