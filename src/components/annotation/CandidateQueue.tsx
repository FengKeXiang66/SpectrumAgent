import type { Label, Working } from './types.ts';
import { candidateKey, statistics } from './working.ts';
type Props = { working: Working | null; labels: Label[]; selectedKey: string | null; disabled: boolean;
  onSelect(key: string): void; onSave(): void };
export default function CandidateQueue({ working, labels, selectedKey, disabled, onSelect, onSave }: Props) {
  const stats = statistics(working);
  return <aside className="annotation-right" aria-label="候选与分布">
    <section className="annotation-card">
      <h3>候选区域队列 <small>{working?.queue.length ?? '—'}</small></h3>
      <p className="annotation-note">机器只给候选，不赋标签。相似度以种子谱为参照。</p>
      <div className="annotation-queue" role="list">
        {working?.queue.map((item, index) => {
          const key = candidateKey(item);
          return <button type="button" role="listitem" key={`${key}:${index}`} disabled={disabled} aria-pressed={selectedKey === key}
            className={selectedKey === key ? 'selected' : ''} onClick={() => onSelect(key)}>
            <b>候选 {index + 1} · {item.pixel_count.toLocaleString()} px</b>
            <span>最小 {item.min_similarity.toFixed(4)} · 平均 {item.avg_similarity.toFixed(4)}</span>
            <small>{item.superpixels.length} 个超像素 · #{item.superpixels.slice(0, 3).join(' / ')}{item.superpixels.length > 3 ? ' …' : ''}</small>
          </button>;
        })}
        {!!working && !working.queue.length && <p className="annotation-hint">队列为空。点选或绘制提示以生成候选。</p>}
      </div>
      <p className="annotation-hint">默认入队下限 0.80（UI 原型 S05），可调；沿链增长的相似度可能低于扩散阈值。</p>
    </section>
    <section className="annotation-card">
      <h3>已标注像素分布</h3>
      <ul className="annotation-distribution">
        {labels.map((label, index) => <li key={label.id}><span><i className="annotation-swatch" style={{ backgroundColor: label.color_hex }} />{label.code}</span><b>{stats ? (stats.label_counts[String(index)] ?? 0).toLocaleString() : '—'} px</b></li>)}
        <li><span>不确定（-2）</span><b>{stats?.uncertain_pixels.toLocaleString() ?? '—'} px</b></li>
        <li><span>留白（-1）</span><b>{stats?.blank_pixels.toLocaleString() ?? '—'} px</b></li>
      </ul>
      <button className="annotation-primary" disabled={disabled || !working?.params} onClick={onSave}>聚合为样本级标签</button>
      <p className="annotation-hint">保存即聚合；默认创建新版本。</p>
    </section>
  </aside>;
}
