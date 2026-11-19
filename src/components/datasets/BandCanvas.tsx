import { useEffect, useRef, useState } from 'react';
import type { Preview } from './types';

export default function BandCanvas({ preview, thumbnail = false }: { preview: Preview; thumbnail?: boolean }) {
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

