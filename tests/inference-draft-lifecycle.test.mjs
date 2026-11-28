import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('submitted and legacy inference cards cannot expose editable controls', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: Card, inferenceDraft } = await server.ssrLoadModule('/src/components/assistant/InferenceDraftCard.tsx');
    const base = { revision:3, ready:true, envi:true, foreground_enabled:true,
      todo:'方案说明', groups:[], changes:[], raw:'{}', science:'' };
    const render = card => renderToStaticMarkup(createElement(Card, {card, active:true, canAct:true, send() {}}));
    const archived = render({...base, editable:false, state:'submitted', run_id:'run-old', restart_command:'新建推理方案 3'});
    assert.match(archived, /该方案已执行/);
    assert.match(archived, /新建推理方案/);
    assert.match(archived, /查看上次推理结果/);
    assert.doesNotMatch(archived, /微调参数|微调推理参数|确认推理|重新探查前景|关闭前景筛选|应用修改/);
    const editable = render({...base, editable:true, state:'draft'});
    assert.match(editable, /微调参数/);
    assert.match(editable, /确认推理/);
    const legacy = render(inferenceDraft({inference_card_json:JSON.stringify(base)}));
    assert.match(legacy, /历史方案为只读/);
    assert.doesNotMatch(legacy, /微调参数|确认推理|重新探查前景/);
  } finally { await server.close(); }
});
