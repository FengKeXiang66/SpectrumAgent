import type { Blocks, EditAction, Label, SegmentsMap } from '../types.ts';

export type DecodedSegments = { ids: Uint16Array; shape: [number, number] };

// The bytes come only from a full-resolution, unscaled RGB id PNG.
export function decodeSegments(rgba: Uint8ClampedArray, map: SegmentsMap): DecodedSegments {
  const [lines, samples] = map.shape;
  if (rgba.length !== lines * samples * 4) throw new Error('超像素 id 图尺寸不一致。');
  const ids = new Uint16Array(lines * samples), counts = new Uint32Array(map.counts.length);
  for (let i = 0; i < ids.length; i++) {
    const id = rgba[4 * i] + 256 * rgba[4 * i + 1];
    if (id >= counts.length) throw new Error('超像素 id 超出块范围。');
    ids[i] = id; counts[id]++;
  }
  if (map.counts.some((count, id) => count !== counts[id])) throw new Error('超像素 id 图像素计数不一致。');
  return { ids, shape: map.shape };
}

export function hitTest(map: DecodedSegments, r: number, c: number): number | null {
  const [lines, samples] = map.shape;
  return Number.isInteger(r) && Number.isInteger(c) && r >= 0 && c >= 0 && r < lines && c < samples
    ? map.ids[r * samples + c] : null;
}

export function isBlockClick(startX: number, startY: number, x: number, y: number): boolean {
  return Math.hypot(x - startX, y - startY) <= 3;
}

export function blockAction(button: number, shiftKey: boolean): EditAction | null {
  return button === 2 ? 'erase' : button === 0 ? shiftKey ? 'uncertain' : 'confirm' : null;
}

export function blockBadge(id: number, counts: number[], blocks: Blocks, labels: Label[]): string {
  const label = blocks.label[id], purity = blocks.purity[id], count = blocks.label_count[id];
  const name = label === -1 ? '未标注' : label === -2 ? '不确定' : labels[label]?.name ?? '';
  return `块 ${id} · ${counts[id]} px · ${name}${label === -1 ? '' : ` ${purity}%`}${count >= 2 ? ` · 含 ${count} 种标记` : ''}`;
}
