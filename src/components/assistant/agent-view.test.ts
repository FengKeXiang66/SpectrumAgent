import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const bar = read('./AssistantBar.tsx'), css = read('./assistant.css');
const s01 = read('../../screens/S01.tsx'), composer = read('./Composer.tsx');

test('messages use avatar + bubble + phase label instead of a bare text list', () => {
  assert.match(bar, /className=\{`agent-msg /);
  assert.match(bar, /'agent-msg-user' : 'agent-msg-ai'/);
  assert.match(bar, /className="agent-avatar" aria-hidden="true">\{entry\.event === 'user' \? '我' : 'AI'\}/);
  assert.match(bar, /className="agent-bubble"/);
  assert.match(bar, /className="agent-name">\{agentName\(entry\.event\)\}/);
  assert.match(bar, /智能助手 · 已完成/);
  assert.match(bar, /智能助手 · 需要你确认/);
  assert.match(css, /\.agent-msg-user \.agent-avatar \{ border-radius: 50%/);
  assert.match(css, /\.agent-msg-ai \.agent-avatar \{ background: #0e6e8c/);
  assert.match(css, /\.agent-msg-user \.agent-bubble \{ background: #e7f3f7/);
});

test('tool log rows are structured cards with a status badge', () => {
  assert.match(bar, /className="agent-tool" data-event="step"/);
  assert.match(bar, /className="agent-tool-name">\{entry\.data\.tool\}/);
  assert.match(bar, /className="agent-tool-detail"/);
  assert.match(bar, /agent-tool-status \$\{entry\.data\.status === 'ok'/);
  assert.match(bar, /'✓ 完成'/);
  assert.match(css, /border-left: 3px solid #17714a/);
  assert.match(css, /\.agent-tool-status\.is-ok \{ color: #17714a/);
});

test('prototype palette covers ask/error/pending states and the primary send button', () => {
  for (const color of ['#0e6e8c', '#0a5670', '#e7f3f7', '#b9dbe6', '#fdf4e3', '#fdeceb', '#f7f9fb']) {
    assert.ok(css.includes(color), color);
  }
  assert.match(css, /\.agent-check \{[^}]*border: 1px solid #f0dfb8/);
  assert.match(css, /\.agent-error \{[^}]*background: #fdeceb/);
  assert.match(css, /\.assistant-bar button\[type="submit"\][^{]*\{ background: #0e6e8c/);
  assert.match(css, /\.composer button\[type="submit"\] \{ padding: 9px 18px/);
});

test('shell contracts stay intact while the layout becomes card based', () => {
  assert.match(css, /grid-template-columns: 172px minmax\(0, 1fr\) 236px/);
  assert.match(css, /\.assistant-s01-left \{[^}]*border-radius: 10px/);
  assert.match(css, /\.assistant-s01-right \{[^}]*flex-direction: column/);
  assert.match(css, /\.assistant-context::before \{ content: "当前上下文 · 自动继承"/);
  assert.doesNotMatch(css, /var\(--/);
  assert.doesNotMatch(s01, /style=\{|var\(--/);
  assert.doesNotMatch(composer, /style=\{|var\(--/);
});

test('session sidebar uses real session counts, never invented history', () => {
  assert.match(s01, /className="agent-side-title">会话/);
  assert.match(s01, /state\.entries\.length \? `\$\{state\.entries\.length\} 条消息` : '尚未开始'/);
  assert.match(s01, /onClick=\{startNew\}>开始新对话/);
  assert.doesNotMatch(s01, /昨天 \d+ 条|塑料批量建模样品/);
  assert.match(composer, /className="agent-composer-icon"/);
  assert.match(composer, /className="agent-composer-kb">Ctrl\+Enter 发送/);
});
