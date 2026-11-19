import { useState } from 'react';
import { DEFAULT_LUT, validLut, type DisplayMode, type InspectionMode, type LutParameters } from './display.ts';
import type { MeanSpectrum } from '../../datasets/types.ts';
type Props = { bands: number; wavelengths: number[]; band: number; onBand(value: number): void;
  mode: DisplayMode; onMode(value: DisplayMode): void; rgb: [number, number, number]; onRgb(value: [number, number, number]): void;
  stretch: 'auto' | 'manual'; onStretch(value: 'auto' | 'manual'): void;
  lut: LutParameters; onLut(value: LutParameters): void;
  inspection: InspectionMode; onInspection(value: InspectionMode): void };

export default function DisplayToolbar({ bands, wavelengths, band, onBand, stretch, onStretch, mode, onMode, rgb, onRgb, lut, onLut, inspection, onInspection }: Props) {
  const [problem, setProblem] = useState('');
  const options = Array.from({ length: bands }, (_, i) => <option key={i} value={i}>{i}{wavelengths[i] === undefined ? '' : ` · ${wavelengths[i]} nm`}</option>);
  return <fieldset aria-label="画布显示"><legend>画布显示</legend>
    <label>模式<select value={mode} onChange={event => onMode(event.target.value as DisplayMode)}>
      <option value="single">单波段</option><option value="rgb" disabled={bands < 3}>手动伪彩</option>
      <option value="auto" disabled={bands < 3}>自动伪彩</option>
    </select></label>
    <label>画布操作<select value={inspection} onChange={event => onInspection(event.target.value as InspectionMode)}>
      <option value="edit">标注编辑</option><option value="point">单点取谱 · 只读</option>
      <option value="box">框选均值谱 · 只读</option>
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

export function SpectrumReadout({ spectrum, wavelengths }: { spectrum: MeanSpectrum; wavelengths: number[] }) {
  // These bounds only map backend values to screen coordinates; no spectral
  // statistic, band choice, smoothing, derivative or interpolation is computed.
  const finite = spectrum.mean.filter((value): value is number => value !== null);
  const low = Math.min(...finite), high = Math.max(...finite);
  const axis = wavelengths.length === spectrum.mean.length ? wavelengths : spectrum.mean.map((_, i) => i);
  let path = '', drawing = false;
  spectrum.mean.forEach((value, i) => {
    if (value === null) { drawing = false; return; }
    const x = 10+(axis[i]-axis[0])/(axis.at(-1)!-axis[0] || 1)*620;
    const y = 150-(value-low)/(high-low || 1)*140;
    path += `${drawing ? 'L' : 'M'}${x},${y} `; drawing = true;
  });
  return <figure aria-label="只读取谱结果"><figcaption>{spectrum.count === 1 ? '单点谱' : '区域均值谱'} · {spectrum.count} 像素 · {wavelengths.length ? '波长 nm' : '波段序号'} · null 断线</figcaption>
    <svg viewBox="0 0 640 160" role="img" aria-label="后端返回光谱，null不连接"><path d={path} fill="none" stroke="currentColor" /></svg>
    <details><summary>逐波段原值（非有限值=null）</summary><table><thead><tr><th>波段</th><th>波长</th><th>数值</th></tr></thead>
      <tbody>{spectrum.mean.map((value, i) => <tr key={i}><td>{i}</td><td>{wavelengths[i] ?? '未知'}</td><td>{value === null ? 'null' : value}</td></tr>)}</tbody></table></details>
  </figure>;
}
