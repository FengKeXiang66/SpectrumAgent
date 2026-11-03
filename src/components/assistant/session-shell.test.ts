import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync, readFileSync } from 'node:fs';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('P1 A1 App owns one session shared by Composer and S01; renderers have no reducer', () => {
  const app = read('../../App.tsx'), hook = read('./useSession.ts');
  assert.equal((app.match(/useSession\(/g) ?? []).length, 1);
  assert.match(app, /const session = useSession\(/);
  assert.match(app, /<Composer session=\{session\}/);
  assert.match(app, /<S01 session=\{session\}/);
  assert.equal((hook.match(/useReducer\(/g) ?? []).length, 1);
  for (const source of [read('./Composer.tsx'), read('./AssistantBar.tsx'), read('../../screens/S01.tsx')]) {
    assert.doesNotMatch(source, /useReducer\(|useSession\(/);
  }
  for (const callback of ['onWorkspaceChange', 'onWorkspaceNavigate', 'onPreviewCandidate', 'onDataChanged']) assert.match(hook, new RegExp(callback + '\\?\\.\\('));
  assert.match(hook, /if \(!enabled \|\| inFlight.current\) return/);
  assert.match(hook, /validateWorkspaceEvent\(event.data\)/);
});

test('P1 A2 A3 composer hiding and global shortcuts leave S01 input independent', () => {
  const app = read('../../App.tsx'), composer = read('./Composer.tsx'), bar = read('./AssistantBar.tsx');
  assert.match(app, /assistant=\{screen === 's01' \? null : <Composer/);
  assert.match(app, /if \(screen === 's01' \|\| !event.ctrlKey/);
  assert.match(app, /closest\('\.composer'\)/);
  assert.doesNotMatch(app, /closest\('\.assistant-bar'\)/);
  assert.match(app, /composerInput.current\?\.focus\(\)/);
  assert.match(app, /session.request\(\{ content: session.content \}\)/);
  assert.match(composer, /aria-label="常驻对话条"/);
  assert.match(composer, /onKeyDown=/);
  assert.match(composer, /event.key === 'Enter'.*event.preventDefault\(\); void request\(\{ content \}\)/);
  assert.match(bar, /<form onSubmit=\{event => \{ event.preventDefault\(\); void request\(\{ content \}\); \}\}>/);
  assert.match(bar, /<label htmlFor="assistant-message">对话<\/label>/);
  assert.match(bar, /<input id="assistant-message" value=\{content\}/);
  assert.match(bar, /<button type="submit" disabled=\{!enabled \|\| state.busy \|\| !content.trim\(\)\}>发送<\/button>/);
});

test('P1 A4 A5 smoke stays in S01 and the three columns use current session context', () => {
  const s01 = read('../../screens/S01.tsx'), css = read('./assistant.css'), hook = read('./useSession.ts');
  assert.match(s01, /<AssistantBar session=\{session\}/);
  assert.match(s01, /<label htmlFor="agent-input">冒烟测试<\/label>/);
  assert.match(s01, /placeholder="运行冒烟测试"/);
  assert.match(s01, /void smoke.send\(\)/);
  assert.match(s01, /aria-label="冒烟测试真实结果"/);
  assert.doesNotMatch(read('./Composer.tsx'), /运行冒烟测试|smoke/);
  assert.match(css, /grid-template-columns: 172px minmax\(0, 1fr\) 236px/);
  assert.match(s01, /onClick=\{startNew\}>开始新对话/);
  assert.match(hook, /sessionId.current = null; dispatch\(\{ type: 'reset' \}\); setContent\(''\)/);
  for (const name of ['assistant-context', 'assistant-runtime', 'assistant-datasets']) assert.match(s01, new RegExp('className="' + name + '"'));
});

test('P1 A6 A8 retired panel files and rules are absent with only six new layout classes', () => {
  for (const path of ['./AssistantPanel.tsx', './panel-height.ts', './panel-height.test.ts']) assert.equal(existsSync(new URL(path, import.meta.url)), false);
  const css = read('./assistant.css');
  assert.doesNotMatch(css, /assistant-panel|assistant-resize-handle|var\(--/);
  const layout = new Set([...css.matchAll(/\.(assistant-s01(?:-[a-z]+)?|composer(?:-[a-z]+)?)(?![\w-])/g)].map(match => match[1]));
  assert.deepEqual([...layout].sort(), ['assistant-s01', 'assistant-s01-left', 'assistant-s01-mid', 'assistant-s01-right', 'composer', 'composer-context'].sort());
  for (const source of [read('../../screens/S01.tsx'), read('./Composer.tsx')]) assert.doesNotMatch(source, /var\(--|style=\{/);
});
