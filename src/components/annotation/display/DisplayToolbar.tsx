type Props = { bands: number; wavelengths: number[]; band: number; onBand(value: number): void };

export default function DisplayToolbar({ bands, wavelengths, band, onBand }: Props) {
  return <fieldset aria-label="画布显示"><legend>画布显示</legend>
    <label>单波段<select value={band} onChange={event => onBand(Number(event.target.value))}>
      {Array.from({ length: bands }, (_, i) => <option key={i} value={i}>{i}{wavelengths[i] === undefined ? '' : ` · ${wavelengths[i]} nm`}</option>)}
    </select></label>
  </fieldset>;
}
