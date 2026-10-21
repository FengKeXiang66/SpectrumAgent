type Props = { bands: number; wavelengths: number[]; band: number; onBand(value: number): void;
  stretch: 'auto' | 'none'; onStretch(value: 'auto' | 'none'): void };

export default function DisplayToolbar({ bands, wavelengths, band, onBand, stretch, onStretch }: Props) {
  return <fieldset aria-label="画布显示"><legend>画布显示</legend>
    <label>单波段<select value={band} onChange={event => onBand(Number(event.target.value))}>
      {Array.from({ length: bands }, (_, i) => <option key={i} value={i}>{i}{wavelengths[i] === undefined ? '' : ` · ${wavelengths[i]} nm`}</option>)}
    </select></label>
    <label>拉伸<select value={stretch} onChange={event => onStretch(event.target.value as 'auto' | 'none')}>
      <option value="auto">自动 · 2/98 分位</option><option value="none">全量程</option>
    </select></label>
  </fieldset>;
}
