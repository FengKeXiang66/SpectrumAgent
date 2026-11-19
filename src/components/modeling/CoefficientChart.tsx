import { coefficientChart, type CoefficientInput } from './chart.ts';
import { ChartCanvas } from './RegressionCharts.tsx';

export default function CoefficientChart({ input }: { input: CoefficientInput }) {
  const chart = coefficientChart(input)[0];
  return <figure className="model-chart model-coefficient-chart" aria-label="注册模型波段系数图">
    <header><h4>{chart.title}</h4>{chart.qualityLabel && <strong className="model-chart-quality">{chart.qualityLabel}</strong>}</header>
    <ChartCanvas chart={chart} />
    <figcaption>
      {chart.message && <p role="status">{chart.message}</p>}
      {!!chart.legend.length && <ul className="model-chart-legend">{chart.legend.map(item => <li key={item.label}>
        <span style={{ background: item.color }} aria-hidden="true" />{item.label}
      </li>)}</ul>}
      {chart.notes.map(note => <p className="model-chart-note" key={note}>{note}</p>)}
      {chart.definition && <p className="model-chart-note">{chart.definition}</p>}
      <p className="model-chart-note">系数图非定量结论。</p>
    </figcaption>
  </figure>;
}
