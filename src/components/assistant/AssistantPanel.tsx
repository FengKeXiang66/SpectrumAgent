import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { clampPanelHeight, DEFAULT_PANEL_HEIGHT, draggedPanelHeight, panelBounds } from './panel-height';

export default function AssistantPanel({ children }: { children: ReactNode }) {
  const panel = useRef<HTMLElement>(null);
  const handle = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; startY: number; startHeight: number } | null>(null);
  const [bounds, setBounds] = useState(() => panelBounds(window.innerHeight));
  const [height, setHeight] = useState(() => clampPanelHeight(DEFAULT_PANEL_HEIGHT, bounds));
  const [resizing, setResizing] = useState(false);

  const stopDragging = () => {
    const pointerId = drag.current?.pointerId;
    drag.current = null;
    setResizing(false);
    if (pointerId !== undefined && handle.current?.hasPointerCapture(pointerId)) handle.current.releasePointerCapture(pointerId);
  };

  useEffect(() => {
    const parent = panel.current?.parentElement;
    if (!parent) return;
    const measure = () => {
      const next = panelBounds(parent.clientHeight);
      setBounds(next);
      setHeight(current => clampPanelHeight(current, next));
      // A window resize ends the current drag so its old origin cannot jump.
      stopDragging();
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    window.addEventListener('blur', stopDragging);
    return () => {
      observer.disconnect();
      window.removeEventListener('blur', stopDragging);
      const pointerId = drag.current?.pointerId;
      drag.current = null;
      if (pointerId !== undefined && handle.current?.hasPointerCapture(pointerId)) handle.current.releasePointerCapture(pointerId);
    };
  }, []);

  const startDragging = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.isPrimary || event.button !== 0 || drag.current) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, startY: event.clientY, startHeight: height };
    setResizing(true);
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    setHeight(draggedPanelHeight(current.startHeight, current.startY, event.clientY, bounds));
  };
  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 40 : 16;
    if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    stopDragging();
    setHeight(current => clampPanelHeight(event.key === 'Home' ? bounds.min : event.key === 'End' ? bounds.max
      : current + (event.key === 'ArrowUp' ? step : -step), bounds));
  };

  return <footer ref={panel} id="assistant-panel" className="assistant-panel" aria-label="常驻对话条"
    data-resizing={resizing || undefined} style={{ height }}>
    <div ref={handle} className="assistant-resize-handle" role="separator" tabIndex={0}
      aria-label="调整编排助手面板高度" aria-orientation="horizontal" aria-controls="assistant-panel"
      aria-valuemin={bounds.min} aria-valuemax={bounds.max} aria-valuenow={height} aria-valuetext={`${Math.round(height)} 像素`}
      title="上下拖动调整高度，也可使用上下方向键"
      onPointerDown={startDragging} onPointerMove={move}
      onPointerUp={event => { if (drag.current?.pointerId === event.pointerId) stopDragging(); }}
      onPointerCancel={event => { if (drag.current?.pointerId === event.pointerId) stopDragging(); }}
      onLostPointerCapture={stopDragging} onKeyDown={keyDown}>
      <span aria-hidden="true" />
    </div>
    <div className="assistant-panel-content">{children}</div>
  </footer>;
}
