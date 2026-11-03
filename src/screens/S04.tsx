import { useCallback, useEffect, useRef, useState } from 'react';
import BandCanvas from '../components/datasets/BandCanvas';
import { describeError, displayName, type DatasetRecord, type DatasetTransport, type Preview } from '../components/datasets/types';

export default function S04({ record, api, onClose }: { record: DatasetRecord; api: DatasetTransport; onClose(): void }) {
  const [band, setBand] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [error, setError] = useState('');
  const live = useRef(true);
  const sequence = useRef(0);
  const loadPreview = useCallback(async (index: number) => {
    const request = ++sequence.current;
    setBand(index); setPreview(null); setPreviewBusy(true); setError('');
    try {
      const result = await api.preview(record.id, index);
      if (live.current && request === sequence.current) setPreview(result);
    } catch (failure) {
      if (live.current && request === sequence.current) setError(describeError(failure));
    } finally {
      if (live.current && request === sequence.current) setPreviewBusy(false);
    }
  }, [api, record.id]);
  useEffect(() => {
    live.current = true;
    void loadPreview(0);
    return () => { live.current = false; sequence.current++; };
  }, [loadPreview]);
  return <section aria-label="单波段预览">
    <header><button onClick={onClose}>返回数据屏</button><h2>数据查看器</h2></header>
    <h3>{displayName(record)}</h3>
    <label>波段索引 <input aria-label="波段索引" type="number" min={0} max={record.dataset.shape[2] - 1} value={band} onChange={event => setBand(Math.max(0, Math.min(record.dataset.shape[2] - 1, Number(event.target.value) || 0)))} /></label>{' '}
    <button disabled={previewBusy} onClick={() => { void loadPreview(band); }}>读取波段</button>
    {error && <pre role="alert">{error}</pre>}
    {previewBusy && <p role="status">正在读取预览…</p>}
    {preview && <><p>波段 {preview.band} · 宽 {preview.width} × 高 {preview.height}</p><BandCanvas preview={preview} /></>}
  </section>;
}
