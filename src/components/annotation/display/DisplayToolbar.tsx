import { useState } from 'react';
import { DEFAULT_LUT, validLut, type DisplayMode, type LutParameters } from './display.ts';
type Props = { bands: number; wavelengths: number[]; band: number; onBand(value: number): void;
  mode: DisplayMode; onMode(value: DisplayMode): void; rgb: [number, number, number]; onRgb(value: [number, number, number]): void;
  stretch: 'auto' | 'manual'; onStretch(value: 'auto' | 'manual'): void;
  lut: LutParameters; onLut(value: LutParameters): void };

export default function DisplayToolbar({ bands, wavelengths, band, onBand, stretch, onStretch, mode, onMode, rgb, onRgb, lut, onLut }: Props) {
  const [problem, setProblem] = useState('');
  const options = Array.from({ length: bands }, (_, i) => <option key={i} value={i}>{i}{wavelengths[i] === undefined ? '' : ` · ${wavelengths[i]} nm`}</option>);
  return <fieldset aria-label="画布显示"><legend>画布显示</legend>
    <label>模式<select value={mode} onChange={event => onMode(event.target.value as DisplayMode)}>
      <option value="single">单波段</option><option value="rgb" disabled={bands < 3}>手动伪彩</option>
      <option value="auto" disabled={bands < 3}>自动伪彩</option>
    </select></label>
    {mode === 'single' && <label>单波段<select value={band} onChange={event => onBand(Number(event.target.value))}>{options}</select></label>}
    {mode === 'rgb' && (['R', 'G', 'B'] as const).map((channel, i) => <label key={channel}>{channel}<select value={rgb[i]} onChange={event => {
      const next = [...rgb] as [number, number, number]; next[i] = Number(event.target.value); onRgb(next);
    }}>{options}</select></label>)}
    <label>拉伸<select value={stretch} onChange={event => onStretch(event.target.value as 'auto' | 'manual')}>
      <option value="auto">自动 · 2/98 分位</option><option value="manual">手动 · 全量程原图 + LUT</option>
    </select></label>
    {stretch === 'manual' && <div>{([
      ['black', '阴影', 0, 128, 1], ['gamma', '中间调', .2, 5, .1], ['white', '高光', 128, 255, 1],
    ] as const).map(([key, name, min, max, step]) => <label key={key}>{name} {lut[key]}
      <input type="range" min={min} max={max} step={step} value={lut[key]} onChange={event => {
        // Local display state only. No IPC on slider changes.
        const next = { ...lut, [key]: Number(event.target.value) };
        if (validLut(next)) { onLut(next); setProblem(''); }
        else setProblem('高光与阴影至少相差16；保留上次有效值。');
      }} /></label>)}
      <button type="button" onClick={() => { onLut({ ...DEFAULT_LUT }); setProblem(''); }}>重置拉伸</button>
      {problem && <p role="alert">{problem}</p>}
    </div>}
  </fieldset>;
}
