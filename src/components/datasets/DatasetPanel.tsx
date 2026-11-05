import { useEffect, useRef, useState } from 'react';
import { describeError, type CatalogRecord, type DatasetTransport, type Preview } from './types';
import { createDatasetActions, emptyActions } from './actions.ts';
import { DatasetDialog } from './RecycleView.ts';
import BandCanvas from './BandCanvas';
import './datasets.css';

function Thumbnail({ record, api }: { record: CatalogRecord; api: DatasetTransport }) {
  const [preview, setPreview] = useState<Preview | null>(null), [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    setPreview(null); setError('');
    if (!record.available) return;
    void api.preview(record.id, 0).then(result => { if (!cancelled) setPreview(result); })
      .catch(failure => { if (!cancelled) setError(describeError(failure)); });
    return () => { cancelled = true; };
  }, [api, record.id, record.available]);
  return preview ? <BandCanvas preview={preview} thumbnail />
    : error ? <span role="alert">{error}</span> : <span>缩略图读取中…</span>;
}

type Callbacks = Parameters<typeof createDatasetActions>[1];
export default function DatasetPanel({ api, records, phase, error, onReload, onImported, onDeleted, onOpen }: {
  api: DatasetTransport; records: CatalogRecord[]; phase: 'idle'|'loading'|'ready'|'error'; error: string; onReload(): void;
  onImported: Callbacks['imported']; onDeleted: Callbacks['deleted'];
  onOpen(screen: 's04'|'s05'|'s06'|'s07', record?: CatalogRecord): void;
}) {
  const [raw, setRaw] = useState(false);
  const [state, setState] = useState(emptyActions);
  const live = useRef(true);
  const callbacks = useRef({ onImported, onDeleted });
  callbacks.current = { onImported, onDeleted };
  const actions = useRef<ReturnType<typeof createDatasetActions> | null>(null);
  useEffect(() => {
    live.current = true;
    const current = createDatasetActions(api, {
      imported: rows => callbacks.current.onImported(rows),
      deleted: async id => { await callbacks.current.onDeleted(id); },
    }, setState);
    actions.current = current;
    return () => { live.current = false; current.dispose(); actions.current = null; };
  }, [api]);
  const disabled = state.busy || phase !== 'ready';
  return <section className="dataset-panel" aria-label="数据集管理">
    <div inert={state.dialog !== null}>
      <h2>数据集</h2>
      <div className="dataset-toolbar">
        <button disabled={disabled || !records.some(row => row.available)} onClick={() => onOpen('s07')}>PLS 回归与样品取值</button>
        <label><input type="checkbox" checked={raw} disabled={disabled} onChange={event => setRaw(event.target.checked)} /> 原始 DN 模式（未除 scale factor）</label>
        <button disabled={disabled} onClick={() => { void actions.current?.choose(raw); }}>选择数据目录</button>
        <button disabled={state.busy || phase === 'loading'} onClick={onReload}>重新加载活跃列表</button>
      </div>
      <p role="status">{state.message}</p>
      {phase === 'loading' && <p role="status">正在读取已登记数据集…</p>}
      {error && <pre role="alert">{error}</pre>}
      {state.busy && !state.dialog && <progress aria-label="操作进度" {...(state.total ? { value: state.done, max: state.total } : {})} />}
      {state.error && <pre role="alert">{state.error}</pre>}
      <div className="dataset-table-scroll"><table aria-label="数据集列表">
        <thead><tr><th>名称 / 源路径</th><th>维度 L×S×B</th><th>波长范围 nm</th><th>读模式</th><th>预览与操作</th></tr></thead>
        <tbody>{records.map(record => <tr key={record.id}>
          <td><strong>{record.display_name}</strong><code>{record.source_path}</code>{!record.available && <p className="dataset-unavailable">源文件不可用</p>}</td>
          <td>{record.shape.join('×')}</td><td>{record.wavelength_range?.join('–') ?? '未提供'}</td><td>{record.raw ? 'DN 原值' : '反射率'}</td>
          <td>{record.available && <Thumbnail record={record} api={api} />}
            <div className="dataset-row-actions">
              <button disabled={disabled || !record.available} onClick={() => onOpen('s04', record)}>查看 {record.display_name}</button>
              <button disabled={disabled || !record.available} onClick={() => onOpen('s05', record)}>标注 {record.display_name}</button>
              <button disabled={disabled || !record.available} onClick={() => onOpen('s06', record)}>预处理 {record.display_name}</button>
              <button className="dataset-danger" disabled={disabled} onClick={() => { void actions.current?.requestDelete(record); }}>永久删除 {record.display_name}</button>
            </div></td>
        </tr>)}</tbody>
      </table>{phase === 'ready' && !records.length && <p>暂无活跃数据集。可选择数据目录登记。</p>}</div>
      <p>删除为永久删除：数据库记录与程序产物一并清除，不可恢复；原始 ENVI 源文件保持不变。</p>
    </div>
    {state.dialog && <DatasetDialog dialog={state.dialog} onDecision={value => actions.current?.decide(value)} />}
  </section>;
}
