import type { DisplayMode } from './display.ts';
type Props = { bands: number; wavelengths: number[]; band: number; onBand(value: number): void;
  mode: DisplayMode; onMode(value: DisplayMode): void; rgb: [number, number, number]; onRgb(value: [number, number, number]): void;
  stretch: 'auto' | 'none'; onStretch(value: 'auto' | 'none'): void };

export default function DisplayToolbar({ bands, wavelengths, band, onBand, stretch, onStretch, mode, onMode, rgb, onRgb }: Props) {
  const options = Array.from({ length: bands }, (_, i) => <option key={i} value={i}>{i}{wavelengths[i] === undefined ? '' : ` · ${wavelengths[i]} nm`}</option>);
  return <fieldset aria-label="画布显示"><legend>画布显示</legend>
    <label>模式<select value={mode} onChange={event => onMode(event.target.value as DisplayMode)}>
      <option value="single">单波段</option><option value="rgb" disabled={bands < 3}>手动伪彩</option>
    </select></label>
    {mode === 'single' && <label>单波段<select value={band} onChange={event => onBand(Number(event.target.value))}>{options}</select></label>}
    {mode === 'rgb' && (['R', 'G', 'B'] as const).map((channel, i) => <label key={channel}>{channel}<select value={rgb[i]} onChange={event => {
      const next = [...rgb] as [number, number, number]; next[i] = Number(event.target.value); onRgb(next);
    }}>{options}</select></label>)}
    <label>拉伸<select value={stretch} onChange={event => onStretch(event.target.value as 'auto' | 'none')}>
      <option value="auto">自动 · 2/98 分位</option><option value="none">全量程</option>
    </select></label>
  </fieldset>;
}
