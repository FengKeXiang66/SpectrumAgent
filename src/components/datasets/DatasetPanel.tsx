import { useCallback, useEffect, useRef, useState } from 'react';
import { describeError, type CatalogRecord, type DatasetTransport, type Preview, type RecycleList } from './types';
import { createDatasetActions, emptyActions } from './actions.ts';
import { byteSize, DatasetDialog, releaseDate } from './RecycleView.ts';
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
export default function DatasetPanel({ api, records, phase, error, onReload, onImported, onDeleted, onRestored, onOpen }: {
  api: DatasetTransport; records: CatalogRecord[]; phase: 'idle'|'loading'|'ready'|'error'; error: string; onReload(): void;
  onImported: Callbacks['imported']; onDeleted: Callbacks['deleted']; onRestored: Callbacks['restored'];
  onOpen(screen: 's04'|'s05'|'s06'|'s07', record?: CatalogRecord): void;
}) {
  const [raw, setRaw] = useState(false), [filter, setFilter] = useState<'active'|'deleted'>('active');
  const [state, setState] = useState(emptyActions);
  const [recycle, setRecycle] = useState<RecycleList | null>(null), [recycleError, setRecycleError] = useState('');
  const [recycleLoading, setRecycleLoading] = useState(false);
  const live = useRef(true), recycleTicket = useRef(0);
  const callbacks = useRef({ onImported, onDeleted, onRestored });
  callbacks.current = { onImported, onDeleted, onRestored };
  const actions = useRef<ReturnType<typeof createDatasetActions> | null>(null);
  const loadRecycle = useCallback(async () => {
    const ticket = ++recycleTicket.current;
    setRecycleLoading(true); setRecycleError('');
    try {
      const value = await api.recycleList();
      if (live.current && ticket === recycleTicket.current) setRecycle(value);
    } catch (failure) { if (live.current && ticket === recycleTicket.current) setRecycleError(describeError(failure)); }
    finally { if (live.current && ticket === recycleTicket.current) setRecycleLoading(false); }
  }, [api]);
  useEffect(() => {
    live.current = true;
    const current = createDatasetActions(api, {
      imported: rows => callbacks.current.onImported(rows),
      deleted: async id => { await callbacks.current.onDeleted(id); if (live.current) await loadRecycle(); },
      restored: async id => { await callbacks.current.onRestored(id); if (live.current) await loadRecycle(); },
    }, setState);
    actions.current = current;
    return () => { live.current = false; recycleTicket.current++; current.dispose(); actions.current = null; };
  }, [api, loadRecycle]);
  useEffect(() => { if (filter === 'deleted') void loadRecycle(); }, [filter, loadRecycle]);
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
      <label>数据集状态<select value={filter} disabled={state.busy} onChange={event => setFilter(event.target.value as 'active'|'deleted')}>
        <option value="active">活跃数据集</option><option value="deleted">已删除（回收站）</option>
      </select></label>
      {filter === 'active' ? <div className="dataset-table-scroll"><table aria-label="数据集列表">
        <thead><tr><th>名称 / 源路径</th><th>维度 L×S×B</th><th>波长范围 nm</th><th>读模式</th><th>预览与操作</th></tr></thead>
        <tbody>{records.map(record => <tr key={record.id}>
          <td><strong>{record.display_name}</strong><code>{record.source_path}</code>{!record.available && <p className="dataset-unavailable">源文件不可用</p>}</td>
          <td>{record.shape.join('×')}</td><td>{record.wavelength_range?.join('–') ?? '未提供'}</td><td>{record.raw ? 'DN 原值' : '反射率'}</td>
          <td>{record.available && <Thumbnail record={record} api={api} />}
            <div className="dataset-row-actions">
              <button disabled={disabled || !record.available} onClick={() => onOpen('s04', record)}>查看 {record.display_name}</button>
              <button disabled={disabled || !record.available} onClick={() => onOpen('s05', record)}>标注 {record.display_name}</button>
              <button disabled={disabled || !record.available} onClick={() => onOpen('s06', record)}>预处理 {record.display_name}</button>
              <button className="dataset-danger" disabled={disabled} onClick={() => { void actions.current?.requestDelete(record); }}>移入回收站 {record.display_name}</button>
            </div></td>
        </tr>)}</tbody>
      </table>{phase === 'ready' && !records.length && <p>暂无活跃数据集。可选择数据目录登记，或在回收站恢复。</p>}</div> : <>
        <p>删除后保留 30 天；源文件不删除，回收站产物仍占本机空间。</p>
        {recycleLoading && <p role="status">正在读取回收站…</p>}
        {recycleError && <pre role="alert">{recycleError}</pre>}
        <button disabled={state.busy || recycleLoading} onClick={() => { void loadRecycle(); }}>刷新回收站</button>
        {recycle && <><p>{recycle.count} 个条目 · {byteSize(recycle.total_bytes)}</p>
          <div className="dataset-table-scroll"><table aria-label="回收站列表"><thead><tr><th>名称 / 源路径</th><th>占用</th><th>预计释放日期</th><th>恢复</th></tr></thead>
            <tbody>{recycle.items.map(row => <tr key={row.deletion_id}><td><strong>{row.display_name}</strong><code>{row.source_path}</code></td>
              <td>{byteSize(row.total_bytes)}</td><td>{releaseDate(row.expires_at)}</td><td>
                {row.status !== 'READY' ? <span role="status">不完整，等待人工处理，已禁止恢复与自动清理。</span>
                  : Date.parse(row.expires_at) <= Date.now() ? <span role="status">已到期，等待释放。</span>
                  : <button disabled={state.busy || recycleLoading} onClick={() => { void actions.current?.requestRestore(row); }}>恢复 {row.display_name}</button>}
              </td></tr>)}</tbody></table></div>
          {!recycle.count && <p>回收站为空。</p>}
          {recycle.count > recycle.items.length && <p>另有隔离条目，等待人工处理，不会自动删除。</p>}
        </>}
      </>}
    </div>
    {state.dialog && <DatasetDialog dialog={state.dialog} onDecision={value => actions.current?.decide(value)} />}
  </section>;
}
