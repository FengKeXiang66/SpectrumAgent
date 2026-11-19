import { createElement as h, useEffect, useRef, useState } from 'react';
import { drafts, type DraftView } from './draft-api.ts';
import { loadConfirmation, mayConfirm } from './confirm.ts';

export type ConfirmCardViewProps = { view: DraftView | null; error: string; disabled: boolean; additional: boolean;
  approveLabel: string; rejectLabel: string; onApprove(): void; onReject(): void; onAdditional(): void; onBack(): void };
export function ConfirmCardView(p: ConfirmCardViewProps) {
  return h('section', { className: 'annotation-card', 'aria-label': '确认标注版本与训练 MAT' },
    h('p', null, p.view ? `estimated_mat_bytes: ${p.view.estimated_mat_bytes} 字节 · revision: ${p.view.revision}` : '正在读取草稿体积…'),
    p.error && h('p', { role: 'alert' }, p.error),
    h('button', { disabled: p.disabled || !p.view || !!p.error || p.additional, onClick: p.onApprove }, p.approveLabel),
    h('button', { disabled: p.disabled, onClick: p.onReject }, p.rejectLabel),
    p.additional && h('div', { role: 'alertdialog', 'aria-label': '超过 2GB 再次确认' },
      h('p', null, '预计训练 MAT 超过 2GB，生成将占用较多内存与磁盘。是否继续？'),
      h('button', { disabled: p.disabled, onClick: p.onAdditional }, '继续生成训练 MAT'),
      h('button', { disabled: p.disabled, onClick: p.onBack }, '返回')));
}

export default function ConfirmCard({ cubeId, disabled = false, approveLabel = '确认版本并生成训练 MAT',
  rejectLabel = '取消', onApprove, onReject }: { cubeId: string; disabled?: boolean; approveLabel?: string; rejectLabel?: string;
    onApprove(view: DraftView): Promise<void>; onReject(): void }) {
  const [view, setView] = useState<DraftView | null>(null), [error, setError] = useState('');
  const [additional, setAdditional] = useState(false), [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  useEffect(() => {
    let cancelled = false;
    setView(null); setError(''); setAdditional(false);
    void loadConfirmation(drafts, cubeId).then(value => { if (!cancelled) setView(value); })
      .catch(failure => { if (!cancelled) setError(`${failure?.error ?? 'DRAFT_READ_FAILED'}：${failure?.detail ?? '读取草稿体积失败'}`); });
    return () => { cancelled = true; };
  }, [cubeId]);
  const approve = async (second: boolean) => {
    if (!view || error || disabled || inFlight.current) return;
    if (!mayConfirm(view.estimated_mat_bytes, second)) { setAdditional(true); return; }
    inFlight.current = true; setBusy(true);
    try { await onApprove(view); }
    catch (failure) { const e = failure as { error?: string; detail?: string }; setError(`${e.error ?? 'CONFIRM_FAILED'}：${e.detail ?? '确认失败'}`); }
    finally { inFlight.current = false; setBusy(false); setAdditional(false); }
  };
  return h(ConfirmCardView, { view, error, disabled: disabled || busy, additional, approveLabel, rejectLabel,
    onApprove: () => void approve(false), onReject, onAdditional: () => void approve(true), onBack: () => setAdditional(false) });
}
