import { useState } from 'react';
import type { BatchResult } from './api.ts';
import { batchExplanation } from './presentation.ts';

export function batchBusinessLabel(result: BatchResult | null): string {
  return result ? ({ ready: '分割准备完成，等待人工点选', partial: '部分就绪', failed: '未就绪', blocked: '未执行',
    need_version: '需要补充信息', need_scope: '需要补充信息' } as const)[result.status]
    : '无法核验';
}

export default function BatchPrepareCard({ result, disabled, onOpen, onRetry }: {
  result: BatchResult | null; disabled: boolean; onOpen(): void; onRetry(): boolean;
}) {
  const [filled, setFilled] = useState(false);
  return <section className="batch-prepare-card" aria-label="批量分割结果">
    <h3>{batchBusinessLabel(result)} · 默认分割</h3>
    {result ? <>
      <p>{result.datasetVersionId
        ? `${result.memberCount}个样品`
        : `本次范围 ${result.memberCount}个样品`} · 就绪 {result.readyCount} / {result.memberCount}</p>
      <p>分割就绪后等待人工点选；尚未识别材质或保存标注。</p>
      <p>就绪表示持久分割已核验，可按需换入；不要求全部样品常驻内存。</p>
      <p role="status">{batchExplanation(result)}</p>
      <p>本次拟使用的默认配置：目标块数200，compactness 0.5，PCA 5；回显不代表已执行。</p>
      <details><summary>查看具体限制与完整引用</summary>
        <p>本次选中的样品范围</p>
        {result.admission ? <p>check_code: {result.admission.code} · constraint: {result.admission.constraint} · 实际 {result.admission.actual ?? '未提供'} · 上限 {result.admission.limit ?? '未提供'} · checked_at: {result.admission.checkedAt}</p>
          : <p>具体准入条件未提供</p>}
      </details>
      <ol>{result.members.map((item, index) => <li key={item.cubeId}>
        <strong>批内 {index + 1} · {item.displayName}</strong> · {{ ready: '就绪', failed: '失败', conflict: '冲突', not_attempted: '尚未执行' }[item.status]}
        {item.superpixelCount !== null && <span> · 实际 {item.superpixelCount} 块</span>}
        {item.status === 'ready' && <span> · {{ generated: '生成并保存', reused: '内存复用', restored: '磁盘恢复', retained: '保留成功项', none: '' }[item.action]}</span>}
        {item.detail && <p>{item.detail}</p>}
      </li>)}</ol>
    </> : <p role="alert">无法核验完整批次摘要，未开启标注入口。</p>}
    <button disabled={disabled || !result?.readyMembers.length} onClick={onOpen}>开始标注成功项</button>
    <button disabled={disabled || !result?.batchRef || result.readyCount === result.memberCount}
      onClick={() => { if (onRetry()) setFilled(true); }}>仅重试未就绪项</button>
    {filled && <p role="status">重试请求已填入对话输入，尚未执行；请检查后发送。</p>}
    {disabled && <p>当前结果暂不可操作；新对话或引擎换代后旧回执不可继续使用。</p>}
  </section>;
}
