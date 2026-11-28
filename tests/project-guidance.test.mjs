import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('project guidance distinguishes shared data, individual chats and unverified counts', async t => {
  const server = await createServer({server: {middlewareMode: true, watch: null, hmr: false}, appType: 'custom'});
  try {
    const {default: useSession} = await server.ssrLoadModule('/src/components/assistant/useSession.ts');
    const {default: Scope, currentProjectName} = await server.ssrLoadModule('/src/components/assistant/SessionScope.tsx');
    const {default: S01} = await server.ssrLoadModule('/src/screens/S01.tsx');
    const {default: Welcome} = await server.ssrLoadModule('/src/components/assistant/ProjectWelcome.tsx');
    const {default: Intake} = await server.ssrLoadModule('/src/components/assistant/DataIntakeCard.tsx');
    let baseline;
    function Probe() {baseline = useSession({enabled: true, generation: 1}); return null;}
    renderToStaticMarkup(createElement(Probe));
    const session = {...baseline, projectId: 'eggs', catalogPhase: 'ready',
      projects: [{id: 'eggs', name: '鸡蛋'}, {id: 'plastic', name: '塑料'}],
      records: Array.from({length: 8}, (_, id) => ({id: String(id)})),
      active: {id: 'chat', project_id: 'eggs', project_name: '鸡蛋', title: '基线分类', total_members: 52},
    };

    await t.test('catalog counts belong to the project, not the selected image or an old session snapshot', () => {
      const html = renderToStaticMarkup(createElement(Scope, {session}));
      assert.match(html, /项目数据：8 个数据集/);
      assert.doesNotMatch(html, /52 个/);
      assert.match(html, /新建对话无需重新导入数据/);
      for (const catalogPhase of ['idle', 'loading', 'error']) {
        const pending = renderToStaticMarkup(createElement(Scope, {session: {...session, catalogPhase}}));
        assert.match(pending, /项目数据：待核对/);
        assert.doesNotMatch(pending, /8 个数据集|52 个数据集/);
      }
      const empty = renderToStaticMarkup(createElement(Scope, {session: {...session, active: null, records: []}}));
      assert.match(empty, /项目数据：0 个数据集/);
      const compact = renderToStaticMarkup(createElement(Scope, {session, compact: true}));
      assert.match(compact, /项目：鸡蛋/);
      assert.doesNotMatch(compact, /<select|<button/);
      assert.equal(currentProjectName({...session, active: {...session.active, project_id: 'plastic', project_name: '塑料'}}), '鸡蛋');
    });

    await t.test('the project encloses the chat list and remains visible throughout an existing conversation', () => {
      const existing = {...session, state: {...session.state, entries: [{event: 'user', data: {content: '继续'}}]}};
      const html = renderToStaticMarkup(createElement(S01, {session: existing}));
      assert.ok(html.indexOf('aria-label="当前项目"') < html.indexOf('本项目的对话'));
      assert.match(html, /新建对话/);
      assert.match(html, /沿用本项目数据/);
      assert.match(html, /当前对话：基线分类/);
      assert.match(html, /当前操作项目：<strong>鸡蛋/);
      assert.doesNotMatch(html, /新建全局会话|开始本项目的对话/);
      const fresh = renderToStaticMarkup(createElement(S01, {session: {...session, active: null}}));
      assert.match(fresh, /开始本项目的对话/);
      assert.match(fresh, /当前对话：新对话/);
    });

    await t.test('onboarding fills a data query without submitting a job or clearing existing data', () => {
      const actions = [];
      const tree = Welcome({session, onImport: () => actions.push('import'),
        onEdit: text => actions.push(text), onHistory: () => actions.push('history')});
      function buttons(node) {
        if (!node || typeof node !== 'object') return [];
        if (node.type === 'button') return [node];
        return [node.props?.children].flat(Infinity).flatMap(buttons);
      }
      const controls = buttons(tree);
      for (const control of controls) control.props.onClick();
      assert.deepEqual(actions, ['import', '查看已导入的数据', 'history']);
      assert.equal(session.records.length, 8);
      const pending = {...session, canSend: false};
      const html = renderToStaticMarkup(createElement(Welcome, {session: pending, onImport() {}, onEdit() {}, onHistory() {}}));
      assert.equal((html.match(/<button[^>]*disabled=""/g) ?? []).length, 3);
    });

    await t.test('intake cards identify their parent project even when showing a historical record', () => {
      const card = {id: 'intake', stage: 'choose_mode', image_names: ['test'], annotation_names: [], classes: []};
      const html = renderToStaticMarkup(createElement(Intake, {card, active: false, enabled: true,
        projectName: '鸡蛋', send() {}, edit() {}}));
      assert.match(html, /所属项目：<strong>鸡蛋/);
      assert.match(html, /历史导入记录，操作已停用/);
    });
  } finally {await server.close();}
});
