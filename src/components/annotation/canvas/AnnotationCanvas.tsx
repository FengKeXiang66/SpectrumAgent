import { useEffect, useRef, useState } from 'react';
import type { Geometry, Pixel, Png, Seed, Working } from '../types.ts';
import type { Tool } from '../shortcuts.ts';
import { candidateKey } from '../working.ts';
import { boxFromPoints, fitViewport, freehandGeometry, imagePoint, rectangle, zoomAt, type Viewport } from './viewport.ts';

export type PromptMode = 'point' | 'box' | 'doodle';
type Layer = 'base' | 'superpixels' | 'candidates' | 'confirmed';
type Frame = { layer: Layer; image: HTMLImageElement };
type Props = {
  shape: [number, number, number]; base: Png | null; segmentation: Png | null; working: Working | null;
  selectedKey: string | null; tool: Tool; prompt: PromptMode; disabled: boolean; panHeld: boolean;
  brushPrompt: boolean;
  draft: Geometry | null;
  onSeed(seed: Seed): void; onGeometry(geometry: Geometry): void; onErase(geometry: Geometry): void;
};

export default function AnnotationCanvas(props: Props) {
  const { shape: [lines, samples], base, segmentation, working, selectedKey, tool, prompt, disabled, panHeld } = props;
  const host = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 1, height: 1 });
  const [viewport, setViewport] = useState<Viewport>({ scale: 1, x: 0, y: 0 });
  const [visible, setVisible] = useState<Record<Layer, boolean>>({ base: true, superpixels: true, candidates: true, confirmed: true });
  const [frames, setFrames] = useState<Frame[]>([]), [error, setError] = useState('');
  const [points, setPoints] = useState<Pixel[]>([]);
  const drag = useRef<{ startX: number; startY: number; view: Viewport; points: Pixel[]; pan: boolean } | null>(null);
  const [polygon, setPolygon] = useState<Pixel[]>([]);
  const [pointer, setPointer] = useState<Pixel | null>(null);

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    const observer = new ResizeObserver(entries => {
      const box = entries[0].contentRect;
      setSize({ width: box.width, height: box.height });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { setViewport(fitViewport(size.width, size.height, lines, samples)); }, [size, lines, samples]);
  useEffect(() => { setPolygon([]); setPoints([]); drag.current = null; }, [tool]);

  useEffect(() => {
    let cancelled = false;
    setError('');
    // Only working.queue supplies the candidate layer. Never diffuse.candidates.
    const selected = working?.queue.filter(item => !selectedKey || candidateKey(item) === selectedKey) ?? [];
    const images: { layer: Layer; png: Png }[] = [
      ...(base ? [{ layer: 'base' as const, png: base }] : []),
      ...(segmentation ? [{ layer: 'superpixels' as const, png: segmentation }] : []),
      ...selected.map(item => ({ layer: 'candidates' as const, png: item.overlay })),
      ...(working?.overlay ? [{ layer: 'confirmed' as const, png: working.overlay }] : []),
    ];
    void Promise.all(images.map(async ({ layer, png }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${png.png_base64}`;
      await image.decode();
      return { layer, image };
    })).then(next => { if (!cancelled) setFrames(next); })
      .catch(() => { if (!cancelled) { setFrames([]); setError('后端 PNG 加载失败，请刷新工作态。'); } });
    return () => { cancelled = true; };
  }, [base, segmentation, working, selectedKey]);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const ratio = window.devicePixelRatio || 1;
    node.width = Math.round(size.width * ratio); node.height = Math.round(size.height * ratio);
    const ctx = node.getContext('2d');
    if (!ctx) { setError('Canvas 2D 不可用。'); return; }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, size.width, size.height);
    ctx.save(); ctx.translate(viewport.x, viewport.y); ctx.scale(viewport.scale, viewport.scale);
    ctx.beginPath(); ctx.rect(0, 0, samples, lines); ctx.clip(); ctx.imageSmoothingEnabled = false;
    for (const frame of frames) {
      if (!visible[frame.layer]) continue;
      // Render the authoritative PNGs, including their backend hatch styles.
      // Do not infer a pixel mask or a label from image colors.
      ctx.globalAlpha = frame.layer === 'confirmed' ? 0.55 : 1;
      ctx.drawImage(frame.image, 0, 0, samples, lines);
    }
    ctx.globalAlpha = 1;
    const stroke = [...(props.draft && 'polygon' in props.draft ? props.draft.polygon : []), ...polygon, ...points];
    if (stroke.length) {
      ctx.beginPath(); ctx.moveTo(stroke[0][1] + .5, stroke[0][0] + .5);
      for (const p of stroke.slice(1)) ctx.lineTo(p[1] + .5, p[0] + .5);
      if (props.draft && 'polygon' in props.draft && !points.length && !polygon.length) ctx.closePath();
      if (points.length && (tool === 'erase' || prompt === 'box')) {
        const [l0, l1, s0, s1] = boxFromPoints(points[0], points[points.length - 1]);
        ctx.beginPath(); ctx.rect(s0, l0, s1 - s0, l1 - l0);
      }
      ctx.strokeStyle = 'white'; ctx.lineWidth = 1 / viewport.scale; ctx.stroke();
    }
    ctx.restore();
  }, [frames, visible, viewport, size, lines, samples, polygon, points, tool, prompt, props.draft]);

  const location = (event: { clientX: number; clientY: number }) => {
    const box = canvas.current!.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  };
  const finishPolygon = () => {
    if (polygon.length < 3 || disabled) return;
    props.onGeometry({ polygon: [...polygon] }); setPolygon([]);
  };
  return <div className="annotation-canvas-panel">
    <div className="annotation-layers" aria-label="画布图层">
      {([['base', '底图'], ['superpixels', '超像素轮廓/编号'], ['candidates', '候选高亮'], ['confirmed', '已确认/不确定/留白']] as const).map(([key, label]) =>
        <label key={key}><input type="checkbox" checked={visible[key]} onChange={event => setVisible({ ...visible, [key]: event.target.checked })} />{label}</label>)}
      <button type="button" onClick={() => setViewport(fitViewport(size.width, size.height, lines, samples))}>适合窗口</button>
      <span>缩放 {viewport.scale.toFixed(2)}×</span>
    </div>
    <div ref={host} className="annotation-canvas-host">
      <canvas ref={canvas} aria-label="标注画布：滚轮缩放，空格或中键平移" style={{ cursor: panHeld ? 'grab' : 'crosshair' }}
        onContextMenu={event => event.preventDefault()}
        onWheel={event => {
          event.preventDefault(); const { x, y } = location(event);
          // Exponential wheel transform is a viewport operation, not a model parameter.
          setViewport(previous => zoomAt(previous, x, y, Math.exp(-event.deltaY / Math.max(size.height, 1))));
        }}
        onPointerDown={event => {
          const { x, y } = location(event); const p = imagePoint(x, y, viewport, lines, samples);
          const pan = panHeld || event.button === 1;
          if (!pan && (disabled || !p || event.button !== 0)) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { startX: x, startY: y, view: viewport, points: p ? [p] : [], pan };
          if (!pan && p) setPoints([p]);
        }}
        onPointerMove={event => {
          const { x, y } = location(event); const p = imagePoint(x, y, viewport, lines, samples); setPointer(p);
          const current = drag.current;
          if (!current) return;
          if (current.pan) { setViewport({ ...current.view, x: current.view.x + x - current.startX, y: current.view.y + y - current.startY }); return; }
          if (p && (p[0] !== current.points.at(-1)?.[0] || p[1] !== current.points.at(-1)?.[1])) {
            current.points.push(p); setPoints([...current.points]);
          }
        }}
        onPointerUp={event => {
          const current = drag.current; drag.current = null; setPoints([]);
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
          if (!current || current.pan || disabled || !current.points.length) return;
          const first = current.points[0], last = current.points[current.points.length - 1];
          if (tool === 'erase') { props.onErase({ polygon: rectangle(first, last) }); return; }
          if (tool === 'polygon') { setPolygon(previous => [...previous, last]); return; }
          if (tool === 'brush' && !props.brushPrompt) {
            const geometry = freehandGeometry(current.points);
            if (geometry) props.onGeometry(geometry); else setError('请手绘闭合轮廓，至少经过三个像素；或用单击选择一个像素。');
            return;
          }
          if (tool === 'brush' || prompt === 'doodle') { props.onSeed({ doodle: current.points }); return; }
          if (prompt === 'box') { props.onSeed({ box: boxFromPoints(first, last) }); return; }
          props.onSeed({ point: last });
        }}
        onPointerCancel={() => { drag.current = null; setPoints([]); }} />
      {!base && <p className="annotation-canvas-empty">正在读取底图…</p>}
    </div>
    <div className="annotation-canvas-foot">
      <span>{pointer ? `像素 [行 ${pointer[0]}, 列 ${pointer[1]}]` : '光标移入图像以定位像素'}</span>
      <span>滚轮缩放 · 空格/中键平移</span>
      {tool === 'polygon' && <><span>多边形：逐点单击，再完成</span><button disabled={disabled || polygon.length < 3} onClick={finishPolygon}>完成多边形</button><button onClick={() => setPolygon([])}>取消</button></>}
      {tool === 'erase' && <span>橡皮：拖框擦除；单击擦除一个像素</span>}
      {tool === 'brush' && <span>{props.brushPrompt ? '画笔：涂鸦提示，仅生成候选；选标签后确认' : '画笔：手绘闭合轮廓选择区域，单击选一个像素；再确认标签'}</span>}
    </div>
    {error && <p role="alert">{error}</p>}
  </div>;
}
