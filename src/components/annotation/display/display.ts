import type { PreviewOptions } from '../../datasets/types.ts';

export type DisplayMode = 'single' | 'rgb' | 'auto';
export function displayRequest(mode: DisplayMode, band: number, rgb: [number, number, number],
  stretch: 'auto' | 'none', bandCount: number): PreviewOptions {
  const valid = (i: number) => Number.isInteger(i) && i >= 0 && i < bandCount;
  if (mode === 'single') {
    if (!valid(band)) throw new Error('请选择有效波段。');
    return { band, stretch, size: 'full' };
  }
  if (mode === 'auto') return { bands: 'auto', stretch, size: 'full' };
  if (!rgb.every(valid) || new Set(rgb).size !== 3) throw new Error('R/G/B 须为三个不同的有效波段。');
  return { bands: rgb.join(','), stretch, size: 'full' };
}
