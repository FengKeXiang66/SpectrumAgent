import { useEffect, useRef, useState } from 'react';
import { describeError, mergeRecords, type DatasetRecord, type DatasetTransport, type Preview } from './types';
import AnnotationWorkbench from '../annotation/AnnotationWorkbench';

function BandCanvas({ preview, thumbnail = false }: { preview: Preview; thumbnail?: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    setError('');
    const bytes = Uint8Array.from(atob(preview.png_base64), char => char.charCodeAt(0));
    void createImageBitmap(new Blob([bytes], { type: 'image/png' })).then(image => {
      if (cancelled) { image.close(); return; }
      const context = canvas.current?.getContext('2d');
      if (!context) { image.close(); setError('无法创建灰度预览画布。'); return; }
      context.clearRect(0, 0, preview.width, preview.height);
      context.drawImage(image, 0, 0);
      image.close();
    }).catch(() => { if (!cancelled) setError('灰度预览图加载失败。'); });
    return () => { cancelled = true; };
  }, [preview]);
  return <>
    <canvas ref={canvas} className={thumbnail ? 'dataset-thumbnail' : 'dataset-canvas'} width={preview.width} height={preview.height} aria-label={`${thumbnail ? '首波段缩略图' : '单波段灰度图'}，宽${preview.width}高${preview.height}`} />
    {error && <p role="alert">{error}</p>}
  </>;
}

function Thumbnail({ record, api }: { record: DatasetRecord; api: DatasetTransport }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    void api.preview(record.id, 0).then(result => { if (!cancelled) setPreview(result); })
      .catch(failure => { if (!cancelled) setError(describeError(failure)); });
    return () => { cancelled = true; };
  }, [api, record.id]);
  return preview ? <BandCanvas preview={preview} thumbnail />
    : error ? <span role="alert">{error}</span> : <span>缩略图读取中…</span>;
}

export default function DatasetPanel({ api }: { api: DatasetTransport }) {
  const [records, setRecords] = useState<DatasetRecord[]>([]);
  const [annotation, setAnnotation] = useState<DatasetRecord | null>(null);
  const [raw, setRaw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [message, setMessage] = useState('选择数据目录，登记数据引用；源文件保持只读。');
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<DatasetRecord | null>(null);
  const [band, setBand] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const live = useRef(true);
  const sequence = useRef(0);
  useEffect(() => {
    live.current = true;
    return () => { live.current = false; sequence.current++; };
  }, []);

  const loadPreview = async (record: DatasetRecord, index: number) => {
    const request = ++sequence.current;
    setSelected(record); setBand(index); setPreview(null); setPreviewBusy(true); setError('');
    try {
      const result = await api.preview(record.id, index);
      if (live.current && request === sequence.current) setPreview(result);
    } catch (failure) {
      if (live.current && request === sequence.current) setError(describeError(failure));
    } finally {
      if (live.current && request === sequence.current) setPreviewBusy(false);
    }
  };

  const choose = async () => {
    setBusy(true); setError(''); setProgress({ done: 0, total: 0 });
    try {
      const paths = await api.chooseDirectories();
      if (!live.current) return;
      if (!paths?.length) { setMessage('已取消选择。'); return; }
      setProgress({ done: 0, total: paths.length });
      let imported = 0, existing = 0;
      for (let i = 0; i < paths.length; i++) {
        setMessage(`正在登记目录 ${i + 1}/${paths.length}…`);
        const result = await api.importDirectory(paths[i], raw);
        if (!live.current) return;
        imported += result.summary.imported; existing += result.summary.existing;
        setRecords(previous => mergeRecords(previous, result.datasets));
        setProgress({ done: i + 1, total: paths.length });
      }
      setMessage(`完成：新增 ${imported} 个，已有 ${existing} 个。`);
    } catch (failure) {
      if (live.current) { setError(describeError(failure)); setMessage('当前目录未登记；先前已完成的目录保持已登记。'); }
    } finally {
      if (live.current) setBusy(false);
    }
  };

  if (annotation) return <AnnotationWorkbench key={annotation.id} record={annotation} records={records} datasets={api}
    onNavigate={setAnnotation} onClose={() => setAnnotation(null)} />;

  return <section aria-label="数据集管理">
    <h2>数据接入</h2>
    <label><input type="checkbox" checked={raw} disabled={busy} onChange={event => setRaw(event.target.checked)} /> 原始 DN 模式（未除 scale factor）</label>{' '}
    <button disabled={busy} onClick={() => { void choose(); }}>{busy ? '正在导入…' : '选择数据目录'}</button>
    <p role="status">{message}</p>
    {busy && <progress aria-label="目录导入进度" {...(progress.total ? { value: progress.done, max: progress.total } : {})} />}
    {error && <pre role="alert" style={{ whiteSpace: 'pre-wrap' }}>{error}</pre>}
    <table aria-label="数据集列表">
      <thead><tr><th>名称</th><th>维度 L×S×B</th><th>波长范围 nm</th><th>读模式</th><th>缩略图 / 预览</th></tr></thead>
      <tbody>{records.map(record => {
        const data = record.dataset;
        return <tr key={record.id}>
          <td>{data.name}</td><td>{data.shape.join('×')}</td>
          <td>{data.wavelengths.length ? `${data.wavelengths[0]}–${data.wavelengths.at(-1)}` : '未提供'}</td>
          <td>{data.metadata.value_mode === 'raw_dn' ? 'DN 原值' : '反射率'}{record.existing ? '（已有）' : ''}</td>
          <td><Thumbnail record={record} api={api} /><button onClick={() => { void loadPreview(record, 0); }}>预览 {data.name}</button>
            <button disabled={busy} onClick={() => setAnnotation(record)}>标注 {data.name}</button></td>
        </tr>;
      })}</tbody>
    </table>
    {selected && <section aria-label="单波段预览">
      <h3>{selected.dataset.name}</h3>
      <label>波段索引 <input aria-label="波段索引" type="number" min={0} max={selected.dataset.shape[2] - 1} value={band} onChange={event => setBand(Math.max(0, Math.min(selected.dataset.shape[2] - 1, Number(event.target.value) || 0)))} /></label>{' '}
      <button disabled={previewBusy} onClick={() => { void loadPreview(selected, band); }}>读取波段</button>
      {previewBusy && <p role="status">正在读取预览…</p>}
      {preview && <><p>波段 {preview.band} · 宽 {preview.width} × 高 {preview.height}</p><BandCanvas preview={preview} /></>}
    </section>}
  </section>;
}
