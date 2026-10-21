import { useEffect, useRef } from 'react';
import type { Label } from '../annotation/types.ts';
import { curveRuns } from './pipeline.ts';
import { classLegend, type Report } from './types.ts';

export default function CompareChart({ report, labels, inputBands }: { report: Report; labels: Label[]; inputBands: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const node = canvas.current, context = node?.getContext('2d');
    if (!node || !context) return;
    const width = 900, height = 520, left = 68, right = width - 25;
    context.clearRect(0, 0, width, height);
    context.font = '13px sans-serif';
    for (const [panel, key] of (['before', 'after'] as const).entries()) {
      const top = panel * 260 + 35, bottom = top + 170;
      const axis = key === 'before' ? report.curves.wavelengths_in : report.curves.wavelengths_out;
      const bands = key === 'before' ? inputBands : report.steps.reduce((count, step) =>
        typeof step.meta.axis_len === 'number' ? step.meta.axis_len
          : ['pca', 'mnf', 'ica'].includes(step.op) ? Number(step.params.n_components) : count, inputBands);
      let low = Infinity, high = -Infinity;
      for (const item of report.curves.classes) for (const value of item[key] ?? []) {
        if (value !== null && Number.isFinite(value)) { low = Math.min(low, value); high = Math.max(high, value); }
      }
      context.fillStyle = '#26374b';
      context.fillText(key === 'before' ? '配方前 · B01 反射率' : '配方后', left, top - 12);
      context.strokeStyle = '#b8c5d2'; context.strokeRect(left, top, right - left, bottom - top);
      context.fillText(axis?.length ? '波长（数据集轴）' : 'band index（无波长轴）', left, bottom + 38);
      if (!Number.isFinite(low)) { context.fillText('无有限曲线数据', left + 15, top + 35); continue; }
      context.fillText(String(high), 2, top + 8); context.fillText(String(low), 2, bottom);
      for (const item of report.curves.classes) {
        const values = item[key];
        if (!values) continue;
        const xAt = (i: number) => left + (axis && axis.length === values.length && axis.length > 1
          ? (axis[i] - axis[0]) / (axis.at(-1)! - axis[0])
          : Math.round(i * (bands - 1) / Math.max(1, values.length - 1)) / Math.max(1, bands - 1)) * (right - left);
        context.strokeStyle = classLegend(item.label_index, report.label_index, labels).color;
        context.fillStyle = context.strokeStyle;
        for (const points of curveRuns(values)) {
          context.beginPath();
          points.forEach(([i, value], j) => {
            const y = high === low ? (top + bottom) / 2 : bottom - (value - low) / (high - low) * (bottom - top);
            if (j === 0) context.moveTo(xAt(i), y); else context.lineTo(xAt(i), y);
          });
          if (points.length === 1) context.fillRect(xAt(points[0][0]), high === low ? (top + bottom) / 2 : bottom - (points[0][1] - low) / (high - low) * (bottom - top), 2, 2);
          context.stroke();
        }
      }
      context.fillText(String(axis?.[0] ?? 0), left, bottom + 17);
      context.fillText(String(axis?.at(-1) ?? Math.max(0, bands - 1)), right - 55, bottom + 17);
    }
  }, [report, labels, inputBands]);
  return <section aria-label="处理前后对比图"><h3>{report.curves.labeled ? '按类处理前后对比' : '未标注：整体均值'}</h3>
    <canvas ref={canvas} width={900} height={520} aria-label="上：配方前 B01 反射率，下：配方后；空值断线" />
    <ul className="pp-legend">{report.curves.classes.map(item => { const entry = classLegend(item.label_index, report.label_index, labels);
      return <li key={item.label_index}><span style={{ background: entry.color }} />{entry.code} · {item.count} 像素{item.after === null ? '（处理后无有限谱）' : ''}</li>; })}</ul>
    <p>{report.curves.sampling}</p>
  </section>;
}
