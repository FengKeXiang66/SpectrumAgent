import assert from 'node:assert/strict';
import test from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

test('project creation is outside the current project and deletion requires a reviewed name', async () => {
  const server = await createServer({server: {middlewareMode: true, watch: null, hmr: false}, appType: 'custom'});
  try {
    const {default: useSession} = await server.ssrLoadModule('/src/components/assistant/useSession.ts');
    const {default: Scope} = await server.ssrLoadModule('/src/components/assistant/SessionScope.tsx');
    const {default: Manager, ProjectDeletionReview} = await server.ssrLoadModule('/src/components/assistant/ProjectManager.tsx');
    const {agent, agentClient} = await server.ssrLoadModule('/src/components/assistant/api.ts');
    let session;
    function Probe() {session = useSession({enabled: true, generation: 1}); return null;}
    renderToStaticMarkup(createElement(Probe));
    const view = {...session, projectId: 'b', projects: [{id: 'b', name: '鸡蛋'}]};
    const scope = renderToStaticMarkup(createElement(Scope, {session: view}));
    const manager = renderToStaticMarkup(createElement(Manager, {session: view}));
    assert.doesNotMatch(scope, /<button[^>]*>新建项目|<button[^>]*>删除/);
    assert.match(manager, /新建项目/);
    assert.match(manager, /管理项目/);
    const preview = {id: 'b', name: '鸡蛋', dataset_count: 8, session_count: 3, label_count: 2,
      recipe_count: 1, experiment_count: 4, confirmation_token: 'a'.repeat(64)};
    for (const [name, disabled] of [['', false], ['鸡蛋', true], ['其他项目', false]]) {
      const html = renderToStaticMarkup(createElement(ProjectDeletionReview, {preview, name, disabled, onName() {}, onConfirm() {}, onCancel() {}}));
      assert.match(html, /<button[^>]*disabled=""[^>]*>确认移入回收站/);
      assert.match(html, /8 个数据集 · 3 个对话/);
      assert.match(html, /原始数据文件、标注、模型和结果文件保留/);
    }
    const ready = renderToStaticMarkup(createElement(ProjectDeletionReview, {preview, name: '鸡蛋', disabled: false, onName() {}, onConfirm() {}, onCancel() {}}));
    assert.match(ready, /<button type="button" class="project-danger">确认移入回收站/);

    const calls = [];
    const client = agentClient(async (_command, body) => {calls.push(body.request); return {};});
    await client.projectDeletionPreview('b');
    await client.deleteProject('b', '鸡蛋', preview.confirmation_token);
    await client.restoreProject('b');
    assert.deepEqual(calls, [{op: 'project_deletion_preview', project_id: 'b'},
      {op: 'delete_project', project_id: 'b', confirm_name: '鸡蛋', confirmation_token: preview.confirmation_token},
      {op: 'restore_project', project_id: 'b'}]);

    const transitions = [];
    agent.selectProject = async id => {transitions.push(['select', id]); return {current_project_id: id};};
    agent.listSessions = async () => ({sessions: [], next_cursor: null});
    agent.deleteProject = async id => ({project_id: id, deleted: true, current_project_id: 'a'});
    agent.listProjects = async () => ({projects: [{id: 'a', name: '其他项目'}], current_project_id: 'a', deleted_projects: [{id: 'b', name: '鸡蛋'}]});
    agent.restoreProject = async id => ({id, name: '鸡蛋'});
    agent.createSession = async body => {transitions.push(['new_chat', body.project_id]); return {id: 'chat', project_id: body.project_id};};
    renderToStaticMarkup(createElement(Probe));
    await session.changeProject('b');
    assert.equal(await session.deleteProject('b', '鸡蛋', preview.confirmation_token), true);
    assert.equal(await session.restoreProject('b'), true);
    await session.ensureSession();
    assert.deepEqual(transitions, [['select', 'b'], ['new_chat', 'a']]);
  } finally {await server.close();}
});
