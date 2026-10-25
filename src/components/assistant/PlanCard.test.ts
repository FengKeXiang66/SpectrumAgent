import test from 'node:test';
import assert from 'node:assert/strict';
import { Children, createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { PlanCardView, planStepStatus, type PlanCardViewProps, type PlanChoice } from './PlanCard.ts';
import { requests, type MessageBody } from './api.ts';
import type { PlanDecision, PlanEventData } from './sse.ts';

const plan: PlanEventData = { plan_id: 'round-1', reason: '执行计划待确认', steps: [
  { seq: 1, tool: 'datasets.list', summary: {}, gpu: false, estimate_ms: null },
  { seq: 2, tool: 'annotations.draft_confirm', summary: { cube_id: 'cube-1', revision: 2 }, gpu: false, estimate_ms: 1700 },
  { seq: 3, tool: 'training_mat.export', summary: { version_id: 'v-1' }, gpu: false, estimate_ms: 650 }] };
type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode, tag: string): Element[] {
  const result: Element[] = [];
  function visit(value: ReactNode) {
    if (!isValidElement<Record<string, unknown>>(value)) return;
    if (value.type === tag) result.push(value);
    Children.forEach(value.props.children as ReactNode, visit);
  }
  visit(node); return result;
}
function harness(disabled = false) {
  let choice: PlanChoice | null = null, reason = '';
  const decisions: PlanDecision[] = [];
  const props = (): PlanCardViewProps => ({ plan, choice, reason, disabled, readOnly: false,
    onChoose: value => { choice = value; }, onReason: value => { reason = value; }, onSubmit: value => decisions.push(value) });
  const tree = () => PlanCardView(props());
  return { tree, decisions, props, render: () => renderToStaticMarkup(createElement(PlanCardView, props())),
    click(label: string) {
      const button = elements(tree(), 'button').find(value => value.props['aria-label'] === label || value.props.children === label);
      assert.ok(button); (button.props.onClick as () => void)();
    },
    reason(value: string) {
      (elements(tree(), 'input')[0].props.onChange as (event: { target: { value: string } }) => void)({ target: { value } });
    } };
}

test('plan card renders table, scalar metadata, estimates, aria labels and chosen invalidation', () => {
  const h = harness();
  const html = h.render();
  assert.match(html, /aria-label="执行计划步骤"/);
  assert.match(html, /cube_id: cube-1 · revision: 2/);
  assert.match(html, /1700 ms/); assert.match(html, /650 ms/); assert.match(html, /—/);
  assert.match(html, /预估值非实测承诺/); assert.match(html, /当前工具均无 GPU 路径/);
  h.click('跳过第 2 步及之后');
  assert.match(h.render(), /第 2 步及之后全部失效，不会执行/);
  assert.equal(planStepStatus(1, h.props().choice), '纳入执行');
  for (const seq of [2, 3]) assert.match(planStepStatus(seq, h.props().choice), /未执行/);
  h.click('从第 3 步开始');
  for (const seq of [1, 2]) assert.match(planStepStatus(seq, h.props().choice), /未执行/);
  assert.equal(planStepStatus(3, h.props().choice), '纳入执行');
});

test('all destructive choices require a reason and IPC projects only plan contract fields', () => {
  for (const label of ['跳过第 2 步及之后', '从第 3 步开始', '拒绝']) {
    const h = harness(); h.click(label);
    assert.match(h.render(), /required=""/);
    for (const value of ['', '   ']) {
      h.reason(value); h.click('确认计划动作'); assert.deepEqual(h.decisions, []);
      assert.match(h.render(), /disabled="" aria-label="确认计划动作"/);
    }
    h.reason(' 原因原文 '); h.click('确认计划动作');
    assert.equal(h.decisions.length, 1);
    const decision = h.decisions[0];
    assert.ok('reason' in decision && decision.reason === ' 原因原文 ');
    assert.deepEqual(requests.sendMessage('session', { plan_id: plan.plan_id, ...decision, key: 'secret', url: '/health' } as unknown as MessageBody),
      { op: 'send_message', id: 'session', body: { plan_id: plan.plan_id, ...decision } });
  }
  const h = harness(); h.click('批准');
  assert.deepEqual(h.decisions, [{ action: 'approve' }]);
  assert.deepEqual(requests.sendMessage('s', { plan_id: 'p', action: 'approve', reason: 'extra', step_ref: 2 } as MessageBody),
    { op: 'send_message', id: 's', body: { plan_id: 'p', action: 'approve' } });
});

test('disabled controls cannot submit and history keeps the plan decision without action buttons', () => {
  const h = harness(true);
  for (const button of elements(h.tree(), 'button')) assert.equal(button.props.disabled, true);
  assert.equal(elements(h.tree(), 'input')[0].props.disabled, true);
  for (const label of ['批准', '拒绝', '跳过第 1 步及之后', '从第 3 步开始']) h.click(label);
  assert.deepEqual(h.decisions, []); assert.equal(h.props().choice, null);
  const html = renderToStaticMarkup(createElement(PlanCardView, { ...h.props(), disabled: false, readOnly: true,
    choice: { action: 'skip', step_ref: 2, reason: '暂不确认' }, reason: '暂不确认' }));
  assert.doesNotMatch(html, /<button|<input/);
  assert.match(html, /原因：暂不确认/);
  assert.equal((html.match(/未执行（该步及之后失效）/g) ?? []).length, 2);
});
