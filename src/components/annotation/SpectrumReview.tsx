import { useState } from 'react';
import type { Label, Quality } from './types.ts';
import { formatReviewCos, formatReviewNumber, reviewBandTitle, reviewKey, reviewModel, reviewX } from './spectrumReview.ts';

type Props = {
  quality: Quality | null; labels: Label[]; bands: number; wavelengths: number[]; disabled: boolean;
  onRefresh(): void; onBlockErase(block: number): void;
};

export default function SpectrumReview({ quality, labels, bands, wavelengths, disabled, onRefresh, onBlockErase }: Props) {
  const [mode, setMode] = useState<'grouped' | 'selected'>('grouped');
  const [selected, setSelected] = useState<string[]>([]);
  const model = quality ? reviewModel(quality, labels, bands, mode === 'selected' ? new Set(selected) : undefined) : null;
  const suspicious = new Set(quality?.suspicious.map(reviewKey));
  const ticks = [...new Set([0, Math.floor((bands - 1) / 2), bands - 1])].filter(index => index >= 0);
  return <section className="annotation-review" aria-label="谱线复核">
    <div className="annotation-review-heading"><h3>谱线复核 <small>当前工作态 · 原始反射率</small></h3>
      <button disabled={disabled} onClick={onRefresh}>刷新谱线</button></div>
    <p className="annotation-hint">按标签叠加已确认超像素均值谱；粗虚线为同类参考谱。横轴固定 band index，悬停查看波长。剔除由你决定。</p>
    <label>查看方式 <select aria-label="谱线查看方式" value={mode} onChange={event => setMode(event.target.value as typeof mode)}>
      <option value="grouped">按标签分组叠加</option><option value="selected">逐块勾选</option>
    </select></label>
    {!model ? <p role="status">尚无复核结果，请进入复核或刷新谱线。</p> : <>
      <p>已确认组合 {quality!.comparisons.length} 条 · 当前显示 {model.visible.length} 条 · 参考谱 {model.references.length} 条</p>
      <div className="annotation-review-legend">{model.groups.map(group => <span key={group.index}>
        <i className="annotation-swatch" style={{ background: group.color }} />{group.code} · {group.count} 条</span>)}</div>
      {model.range ? <svg className="annotation-review-chart" viewBox="0 0 800 310" role="img" aria-label="谱线叠加图：band index 横轴，共享原始反射率 y 轴">
        <title>所有可见曲线与参考谱共用 y 轴；横轴为 band index</title>
        <rect x={65} y={25} width={710} height={225} fill="none" stroke="#b8c5d2" />
        <text x={3} y={33}>{formatReviewNumber(model.range[1], 4)}</text>
        <text x={3} y={250}>{formatReviewNumber(model.range[0], 4)}</text>
        <text x={65} y={15}>原始反射率</text>
        {model.groups.map(group => <g key={group.index} data-label-index={group.index}>
          {model.curves.filter(curve => curve.label_index === group.index).map(curve => <g key={curve.key}
            data-curve={curve.key} data-reference={curve.reference} stroke={curve.color} fill={curve.color}
            strokeWidth={curve.reference ? 3 : 1.2} opacity={curve.reference ? 1 : .55}
            strokeDasharray={curve.reference ? '6 4' : undefined}>
            <title>{`${curve.code} · ${curve.reference ? '类参考谱' : '#' + curve.key.split(':')[0]}`}</title>
            {curve.runs.map((run, index) => run.length === 1
              ? <circle key={index} cx={65 + run[0][0] * 710} cy={25 + run[0][1] * 225} r={2} />
              : <path key={index} fill="none" d={run.map(([x, y], point) => `${point ? 'L' : 'M'}${65 + x * 710},${25 + y * 225}`).join(' ')} />)}
          </g>)}
        </g>)}
        {Array.from({ length: bands }, (_, index) => {
          const start = bands <= 1 ? 0 : Math.max(0, (index - .5) / (bands - 1));
          const end = bands <= 1 ? 1 : Math.min(1, (index + .5) / (bands - 1));
          return <rect key={index} x={65 + start * 710} y={25} width={(end - start) * 710} height={225} fill="transparent">
            <title>{reviewBandTitle(index, wavelengths)}</title>
          </rect>;
        })}
        {ticks.map(index => <text key={index} x={65 + reviewX(index, bands) * 710} y={275}
          textAnchor={index === 0 ? 'start' : index === bands - 1 ? 'end' : 'middle'}>{reviewBandTitle(index, wavelengths)}</text>)}
        <text x={420} y={301} textAnchor="middle">band index（从 0 开始）</text>
      </svg> : <p role="status">{quality!.comparisons.length ? '未选曲线或无有限曲线数据。' : '暂无已确认的超像素；请先完成标注。'}</p>}
      <p className="annotation-hint">列表按 cos 升序，可疑项优先；余弦无法定义的条目排在末尾。</p>
      <div className="annotation-review-table"><table><thead><tr>
        {mode === 'selected' && <th>显示</th>}<th>超像素</th><th>标签</th><th>像素</th><th>cos</th><th>操作</th>
      </tr></thead><tbody>{model.ordered.map(item => {
        const key = reviewKey(item), label = labels[item.label_index];
        return <tr key={key}>
          {mode === 'selected' && <td><input type="checkbox" aria-label={`显示 #${item.superpixel_id} · ${label?.code ?? item.label_index}`}
            checked={selected.includes(key)} onChange={event => setSelected(previous =>
              event.target.checked ? [...previous, key] : previous.filter(value => value !== key))} /></td>}
          <td>#{item.superpixel_id}</td><td><i className="annotation-swatch" style={{ background: label?.color_hex ?? '#61717e' }} />{label?.code ?? `label_index ${item.label_index}`}</td>
          <td>{item.pixel_count}</td><td>{formatReviewCos(item.cos)}{suspicious.has(key) && <small> · 可疑</small>}</td>
          <td><button disabled={disabled} aria-label={`剔除超像素 #${item.superpixel_id}`} onClick={() => onBlockErase(item.superpixel_id)}>剔除标注</button></td>
        </tr>;
      })}</tbody></table></div>
    </>}
  </section>;
}
