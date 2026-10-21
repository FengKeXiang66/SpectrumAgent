import type { PreviewOptions } from '../../datasets/types.ts';

export type DisplayMode = 'single' | 'rgb' | 'auto';
export type LutParameters = { black: number; white: number; gamma: number };
export const DEFAULT_LUT: Readonly<LutParameters> = { black: 0, white: 255, gamma: 1 };

export function validLut(value: LutParameters): boolean {
  return Object.values(value).every(Number.isFinite) && value.black >= 0 && value.black <= 128
    && value.white >= 128 && value.white <= 255 && value.gamma >= .2 && value.gamma <= 5
    && value.white-value.black >= 16;
}
export function changeLut(previous: LutParameters, next: LutParameters): LutParameters {
  return validLut(next) ? next : previous;
}
export function makeLut(value: LutParameters): Uint8ClampedArray {
  if (!validLut(value)) throw new Error('拉伸参数非法：高光与阴影至少相差16。');
  return Uint8ClampedArray.from({ length: 256 }, (_, i) =>
    Math.round(Math.max(0, Math.min(1, (i-value.black)/(value.white-value.black))) ** (1/value.gamma)*255));
}
export function applyLut(source: Uint8ClampedArray, lut: Uint8ClampedArray): Uint8ClampedArray {
  if (lut.length !== 256 || source.length % 4) throw new Error('LUT或RGBA像素格式非法。');
  const result = source.slice();
  for (let i = 0; i < source.length; i += 4) {
    for (let channel = 0; channel < 3; channel++) result[i+channel] = lut[source[i+channel]];
  }
  return result;
}
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
