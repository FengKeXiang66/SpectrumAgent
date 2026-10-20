import type { Geometry, Pixel } from '../types.ts';
export type Viewport = { scale: number; x: number; y: number };
export function fitViewport(width: number, height: number, lines: number, samples: number): Viewport {
  const scale = Math.min(width / samples, height / lines);
  return { scale, x: (width - samples * scale) / 2, y: (height - lines * scale) / 2 };
}
export function imagePoint(x: number, y: number, view: Viewport, lines: number, samples: number): Pixel | null {
  const l = (y - view.y) / view.scale, s = (x - view.x) / view.scale;
  return l >= 0 && s >= 0 && l < lines && s < samples ? [Math.floor(l), Math.floor(s)] : null;
}
export function zoomAt(view: Viewport, x: number, y: number, factor: number): Viewport {
  const scale = view.scale * factor;
  if (!Number.isFinite(scale) || scale <= 0) return view;
  return { scale, x: x - (x - view.x) * factor, y: y - (y - view.y) * factor };
}
export function boxFromPoints(a: Pixel, b: Pixel): [number, number, number, number] {
  // Endpoints are pixel indices. Include both endpoint pixels in a half-open box.
  return [Math.min(a[0], b[0]), Math.max(a[0], b[0]) + 1, Math.min(a[1], b[1]), Math.max(a[1], b[1]) + 1];
}
export function rectangle(a: Pixel, b: Pixel): Pixel[] {
  const [l0, l1, s0, s1] = boxFromPoints(a, b);
  return [[l0, s0], [l0, s1], [l1, s1], [l1, s0]];
}
export function freehandGeometry(points: Pixel[]): Geometry | null {
  if (points.length === 1) return { polygon: rectangle(points[0], points[0]) };
  // Freehand region selection sends only its contour. R19 rasterization stays
  // in the sidecar; no brush-width default or local pixel mask is invented.
  return points.length >= 3 ? { polygon: points.map(([l, s]) => [l, s]) } : null;
}
