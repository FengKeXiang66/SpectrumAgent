import { createElement as h, useRef, useState } from 'react';
import { scalarText, type PlanDecision, type PlanEventData } from './sse.ts';

export type PlanChoice = { action: 'reject' } | { action: 'skip' | 'rollback'; step_ref: number };
export type PlanCardViewProps = { plan: PlanEventData; choice: PlanChoice | PlanDecision | null; reason: string;
  disabled: boolean; readOnly: boolean; onChoose(choice: PlanChoice | null): void; onReason(reason: string): void;
  onSubmit(decision: PlanDecision): void };

export function planStepStatus(seq: number, choice: PlanChoice | PlanDecision | null): string {
  if (choice?.action === 'reject') return '未执行（计划已拒绝）';
  if (choice?.action === 'skip' && seq >= choice.step_ref) return '未执行（该步及之后失效）';
  if (choice?.action === 'rollback' && seq < choice.step_ref) return '未执行（从后续步骤开始）';
  return '纳入执行';
}

export function PlanCardView(p: PlanCardViewProps) {
  const submit = () => {
    if (p.disabled || p.readOnly || !p.choice || p.choice.action === 'approve' || !p.reason.trim()) return;
    p.onSubmit({ ...p.choice, reason: p.reason });
  };
  return h('section', { className: 'annotation-card', 'aria-label': '执行计划' },
    h('p', null, p.plan.reason),
    h('p', null, '预估值非实测承诺；当前工具均无 GPU 路径。'),
    h('table', { 'aria-label': '执行计划步骤' },
      h('thead', null, h('tr', null, ...['步骤', '算子', '参数摘要', 'GPU', '预估耗时', '计划状态', ...(p.readOnly ? [] : ['操作'])]
        .map(text => h('th', { key: text, scope: 'col' }, text)))),
      h('tbody', null, ...p.plan.steps.map(step => h('tr', { key: step.seq, 'data-seq': step.seq },
        h('td', null, step.seq), h('td', null, step.tool), h('td', null, scalarText(step.summary) || '—'),
        h('td', null, step.gpu ? '是' : '否'), h('td', null, step.estimate_ms === null ? '—' : `${step.estimate_ms} ms`),
        h('td', null, planStepStatus(step.seq, p.choice)),
        !p.readOnly && h('td', null,
          h('button', { disabled: p.disabled, 'aria-label': `跳过第 ${step.seq} 步及之后`,
            onClick: () => { if (!p.disabled) p.onChoose({ action: 'skip', step_ref: step.seq }); } }, '跳过'),
          h('button', { disabled: p.disabled, 'aria-label': `从第 ${step.seq} 步开始`,
            onClick: () => { if (!p.disabled) p.onChoose({ action: 'rollback', step_ref: step.seq }); } }, `从第 ${step.seq} 步开始`)))))),
    p.readOnly ? p.reason && h('p', null, `原因：${p.reason}`) : h('div', null,
      h('button', { disabled: p.disabled, onClick: () => { if (!p.disabled) p.onSubmit({ action: 'approve' }); } }, '批准'),
      h('button', { disabled: p.disabled, onClick: () => { if (!p.disabled) p.onChoose({ action: 'reject' }); } }, '拒绝'),
      h('label', null, '计划动作原因（跳过、回退或拒绝时必填）', h('input', { 'aria-label': '计划动作原因', value: p.reason,
        disabled: p.disabled, required: !!p.choice && p.choice.action !== 'approve',
        onChange: (event: { target: { value: string } }) => p.onReason(event.target.value) })),
      p.choice && p.choice.action !== 'approve' && h('div', { 'aria-live': 'polite' },
        h('p', null, p.choice.action === 'skip' ? `第 ${p.choice.step_ref} 步及之后全部失效，不会执行。`
          : p.choice.action === 'rollback' ? `从第 ${p.choice.step_ref} 步开始，之前步骤不会执行。` : '整份计划将被拒绝，不会执行。'),
        h('button', { disabled: p.disabled || !p.reason.trim(), onClick: submit, 'aria-label': '确认计划动作' }, '确认操作'),
        h('button', { disabled: p.disabled, onClick: () => { if (!p.disabled) p.onChoose(null); } }, '取消选择'))));
}

export default function PlanCard({ plan, disabled = false, readOnly = false, decision, onAction }: {
  plan: PlanEventData; disabled?: boolean; readOnly?: boolean; decision?: PlanDecision; onAction?(decision: PlanDecision): Promise<void>;
}) {
  const [choice, setChoice] = useState<PlanChoice | null>(null), [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const submit = async (value: PlanDecision) => {
    if (disabled || readOnly || inFlight.current || !onAction || (value.action !== 'approve' && !value.reason.trim())) return;
    inFlight.current = true; setBusy(true);
    try { await onAction(value); } finally { inFlight.current = false; setBusy(false); }
  };
  return h(PlanCardView, { plan, choice: decision ?? choice, reason: decision && 'reason' in decision ? decision.reason : reason,
    disabled: disabled || busy, readOnly, onChoose: setChoice, onReason: setReason, onSubmit: value => void submit(value) });
}
