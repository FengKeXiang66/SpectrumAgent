import { useEffect, useRef } from 'react';
import { FRAME, SERIES, type ChartModel } from './chart.ts';

function ChartCanvas({ chart }: { chart: ChartModel }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const context = canvas.current?.getContext('2d');
    if (!context) return;
    context.clearRect(0, 0, FRAME.width, FRAME.height);
    context.fillStyle = '#fff'; context.fillRect(0, 0, FRAME.width, FRAME.height);
    context.font = '18px sans-serif'; context.fillStyle = '#26374b';
    context.textAlign = 'left'; context.textBaseline = 'alphabetic';
    if (chart.status !== 'ready') {
      // Status text remains visible in HTML too if Canvas is unavailable.
      context.fillText(chart.message, FRAME.left, FRAME.top + 80, FRAME.right - FRAME.left);
      return;
    }
    context.lineWidth = 1;
    for (const tick of chart.yTicks) {
      context.strokeStyle = '#e3e9ef'; context.beginPath(); context.moveTo(FRAME.left, tick.at); context.lineTo(FRAME.right, tick.at); context.stroke();
      context.textAlign = 'right'; context.fillText(tick.label, FRAME.left - 12, tick.at + 6);
    }
    for (const tick of chart.xTicks) {
      context.strokeStyle = '#cbd5e1'; context.beginPath(); context.moveTo(tick.at, FRAME.bottom); context.lineTo(tick.at, FRAME.bottom + 7); context.stroke();
      context.textAlign = 'center'; context.fillText(tick.label, tick.at, FRAME.bottom + 30);
    }
    context.strokeStyle = '#a4b2c1'; context.strokeRect(FRAME.left, FRAME.top, FRAME.right - FRAME.left, FRAME.bottom - FRAME.top);
    context.textAlign = 'center'; context.fillText(chart.xLabel, (FRAME.left + FRAME.right) / 2, FRAME.height - 25);
    context.save(); context.translate(25, (FRAME.top + FRAME.bottom) / 2); context.rotate(-Math.PI / 2); context.fillText(chart.yLabel, 0, 0); context.restore();
    context.save(); context.beginPath(); context.rect(FRAME.left - 5, FRAME.top - 5, FRAME.right - FRAME.left + 10, FRAME.bottom - FRAME.top + 10); context.clip();
    for (const line of chart.lines) {
      context.strokeStyle = line.color; context.lineWidth = line.color === '#b0bdcc' ? 1 : 2;
      context.setLineDash(line.dashed ? [8, 6] : []); context.beginPath();
      line.points.forEach((point, index) => { if (index) context.lineTo(point.x, point.y); else context.moveTo(point.x, point.y); });
      if (line.points.length === 1) { const point = line.points[0]; context.fillStyle = line.color; context.fillRect(point.x - 3, point.y - 3, 6, 6); }
      context.stroke();
    }
    context.setLineDash([]);
    for (const bar of chart.bars) {
      context.fillStyle = SERIES.find(series => series.set === bar.set)!.color;
      context.fillRect(bar.x, bar.y, bar.width, bar.height);
    }
    for (const point of chart.points) {
      context.fillStyle = SERIES.find(series => series.set === point.set)!.color;
      if (point.square) context.fillRect(point.x - 5, point.y - 5, 10, 10);
      else if (point.set === 'calibration') { context.beginPath(); context.arc(point.x, point.y, 5, 0, Math.PI * 2); context.fill(); }
      else { context.beginPath(); context.moveTo(point.x, point.y - 7); context.lineTo(point.x + 6, point.y + 5); context.lineTo(point.x - 6, point.y + 5); context.closePath(); context.fill(); }
    }
    chart.markers.forEach((marker, index) => {
      context.strokeStyle = marker.color; context.fillStyle = marker.color; context.lineWidth = 2;
      context.setLineDash([5, 5]); context.beginPath(); context.moveTo(marker.x, FRAME.top); context.lineTo(marker.x, FRAME.bottom); context.stroke(); context.setLineDash([]);
      context.strokeRect(marker.x - 7 - index * 2, marker.y - 7 - index * 2, 14 + index * 4, 14 + index * 4);
      // Separate top flags keep coincident saved LV recommendations visible.
      context.fillRect(marker.x - 5, FRAME.top + index * 18, 10, 10);
    });
    context.restore();
  }, [chart]);
  return <div className="model-chart-viewport"><canvas ref={canvas} width={FRAME.width} height={FRAME.height} role="img"
    aria-label={chart.title + (chart.message ? '：' + chart.message : '；' + chart.legend.map(item => item.label).join('，'))}>
    {chart.message || chart.title}
  </canvas></div>;
}

export default function RegressionCharts({ charts }: { charts: ChartModel[] }) {
  return <section className="model-charts" aria-label="回归评价图">
    <h3>回归评价图</h3>
    <p className="model-chart-scope">回归散点、残差、潜变量曲线与预测含量分布；校准集与预测集分开显示。</p>
    <div className="model-chart-grid">{charts.map(chart => <figure className="model-chart" key={chart.kind}>
      <header><h4>{chart.title}</h4>{chart.qualityLabel && <strong className="model-chart-quality">{chart.qualityLabel}</strong>}</header>
      <ChartCanvas chart={chart} />
      <figcaption>
        {chart.message && <p role="status">{chart.message}</p>}
        {!!chart.legend.length && <ul className="model-chart-legend">{chart.legend.map(item => <li key={item.label}>
          <span style={{ background: item.color }} aria-hidden="true" />{item.label}
        </li>)}</ul>}
        {chart.notes.map(note => <p key={note} className="model-chart-note">{note}</p>)}
        {chart.definition && <details className="model-chart-note"><summary>查看产物中的 LV 定义</summary><p>{chart.definition}</p></details>}
      </figcaption>
    </figure>)}</div>
  </section>;
}
