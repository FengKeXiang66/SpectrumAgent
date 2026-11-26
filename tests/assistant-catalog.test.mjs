import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { createCatalogController } from '../src/components/datasets/catalog.ts';

const rows = Array.from({ length: 11 }, (_, i) => ({
  id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`,
  display_name: `plastic-${i + 1}`, shape: [640, 231, 200],
  wavelength_range: null, raw: false, source_path: '', available: true,
}));
const step = (tool, status) => ({ event: 'step', data: {
  seq: 1, tool, status: 'ok', result_summary: { status, dataset_count: 11, truncated: true },
} });
const imported = step('datasets.import', 'imported');

test('assistant mutations synchronize the dashboard catalog before navigation', async t => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, hmr: false }, appType: 'custom' });
  try {
    const { default: useSession } = await server.ssrLoadModule('/src/components/assistant/useSession.ts');
    const { agent } = await server.ssrLoadModule('/src/components/assistant/api.ts');
    const { default: Dashboard } = await server.ssrLoadModule('/src/screens/S02.tsx');
    const { default: DataIntakeCard } = await server.ssrLoadModule('/src/components/assistant/DataIntakeCard.tsx');
    const { default: AssistantBar } = await server.ssrLoadModule('/src/components/assistant/AssistantBar.tsx');
    const id = '10000000-0000-4000-8000-000000000001';
    const detail = { id, title: 'test', created_at: '', updated_at: '', boot_id: 'boot',
      scope: { kind: 'global' }, pending: null, request: null, history_watermark: 0 };
    agent.createSession = async () => detail;
    agent.getSession = async () => detail;
    agent.getHistory = async () => ({ session_id: id, events: [], next_before: null });

    for (const mode of ['streamed', 'buffered', 'three_directories', 'external_annotations', 'interrupted', 'need_confirm', 'deleted']) {
      await t.test(mode, async () => {
        let available = rows.slice(0, 1), reads = 0, refresh;
        const controller = createCatalogController({ catalog: async (limit, offset) => {
          reads++;
          // Deliberately paginate: event summaries may omit most imported IDs.
          await new Promise(resolve => setTimeout(resolve, 2));
          return { datasets: available.slice(offset, offset + 4), total: available.length, limit, offset };
        } }, () => {});
        controller.reset(1);
        await controller.load();
        const before = reads;
        let navigated = false, navigation, session;
        function Probe() {
          session = useSession({ enabled: true, generation: 1, bootId: 'boot',
            onCatalogChanged: () => (refresh = controller.load()),
            onWorkspaceChange: () => {
              navigated = true;
              assert.equal(controller.snapshot().records.length, 11);
            },
            onWorkspaceNavigate: selection => { navigation = selection; },
          });
          return null;
        }
        renderToStaticMarkup(createElement(Probe));
        agent.sendMessage = async (_id, _body, receive) => {
          const workspace = { event: 'workspace', data: { cube_id: rows[0].id, display_name: rows[0].display_name,
            ...(mode === 'external_annotations' ? { stage: 'preprocess' } : {}) } };
          if (mode === 'three_directories') {
            for (const count of [3, 7, 11]) {
              available = rows.slice(0, count);
              receive(imported);
            }
            receive(workspace);
            return { events: [] };
          }
          available = mode === 'deleted' ? [] : mode === 'need_confirm' ? available : rows;
          const mutation = mode === 'external_annotations' ? step('annotations.external_import', 'saved')
            : mode === 'deleted' ? step('datasets.delete', 'deleted')
            : mode === 'need_confirm' ? step('datasets.import', 'need_confirm') : imported;
          if (mode === 'buffered') return { events: [mutation, workspace] };
          receive(mutation);
          if (mode === 'interrupted') throw new Error('stream interrupted after committed import');
          if (mode === 'streamed' || mode === 'external_annotations') receive(workspace);
          return { events: [] };
        };
        await session.request({ content: '导入全部三个目录' });
        await refresh;
        const state = controller.snapshot();
        assert.equal(state.phase, 'ready');
        assert.equal(state.records.length, mode === 'need_confirm' ? 1 : mode === 'deleted' ? 0 : 11);
        assert.equal(reads > before, mode !== 'need_confirm');
        assert.equal(navigated, ['streamed', 'buffered', 'three_directories', 'external_annotations'].includes(mode));
        assert.equal(navigation?.stage, mode === 'external_annotations' ? 'preprocess' : undefined);
        if (mode === 'streamed' || mode === 'buffered') {
          const html = renderToStaticMarkup(createElement(Dashboard, {
            records: state.records, catalogPhase: state.phase, catalogError: '', runs: [],
            loading: false, error: '', status: { phase: 'Ready', generation_id: 1 },
            onOpenData() {}, onOpenRun() {}, onContinueAnnotation() {},
          }));
          assert.match(html, /已登记 11 个数据集/);
          // A later selected-cube name refresh must retain all imported rows.
          await controller.refreshNames([rows[0].id]);
          assert.equal(controller.snapshot().records.length, 11);
        }
      });
    }

    await t.test('dashboard hides stale counts while loading or after catalog failure', () => {
      for (const phase of ['loading', 'error']) {
        const html = renderToStaticMarkup(createElement(Dashboard, {
          records: rows.slice(0, 1), catalogPhase: phase, catalogError: '目录读取失败', runs: [],
          loading: false, error: '', status: { phase: 'Ready', generation_id: 1 },
          onOpenData() {}, onOpenRun() {}, onContinueAnnotation() {},
        }));
        assert.doesNotMatch(html, /已登记 1 个数据集/);
        assert.match(html, phase === 'loading' ? /正在读取已登记数据集/ : /目录读取失败/);
      }
    });
    await t.test('intake cards expose only actions appropriate to the current stage and disable history', () => {
      const card = { id, stage: 'choose_mode', mode: null, image_names: ['plastic'], annotation_names: [], classes: [],
        image_count: 11, paired_count: 9, missing_count: 2, issue_count: 1, imported_count: 11, ready_count: 9,
        pairs: [{ image_name: 'sample.hdr', annotation_name: 'sample.json', region_count: 3, labels: ['pe'] }] };
      const render = (stage, active = true) => renderToStaticMarkup(createElement(DataIntakeCard, {
        card: { ...card, stage }, active, enabled: true, send() {}, edit() {},
      }));
      const choose = render('choose_mode');
      assert.match(choose, /尚未标注/); assert.match(choose, /已有标注/);
      assert.doesNotMatch(choose, /进入预处理/);
      assert.match(render('need_annotations'), /与原图同目录/);
      const review = render('review');
      assert.match(review, /使用成功配对的 9 个标注/);
      assert.match(review, /sample\.hdr/); assert.match(review, /sample\.json/);
      assert.match(render('imported'), /进入预处理/);
      const labelForm = renderToStaticMarkup(createElement(DataIntakeCard, {
        card: { ...card, stage: 'labels', label_form_open: true }, active: true, enabled: true, send() {}, edit() {},
      }));
      assert.match(labelForm, /aria-label="批量创建标签"/);
      assert.match(labelForm, /<textarea/);
      assert.match(labelForm, /创建并保存标签/);
      assert.doesNotMatch(labelForm, /进入人工标注/);
      const history = render('choose_mode', false);
      assert.equal((history.match(/<button disabled=""/g) ?? []).length, 3);
      assert.match(history, /历史导入记录/);
    });
    await t.test('labels and saved regions are distinct and successful creation recommends annotation', () => {
      const card = { id, stage: 'imported', mode: 'unlabeled', image_names: ['plastic'], annotation_names: [], classes: [],
        image_count: 11, paired_count: 0, missing_count: 0, issue_count: 0, imported_count: 11, ready_count: 0,
        labels: ['PP', 'PET', 'PE'].map((name, index) => ({ id: String(index), name, code: `L00${index}`, color_hex: '#123456', existing: true })) };
      const render = (value, active = true) => renderToStaticMarkup(createElement(DataIntakeCard, {
        card: value, active, enabled: true, send() {}, edit() {},
      }));
      const html = render(card);
      assert.match(html, /标签类别已就绪：PP、PET、PE/);
      assert.match(html, /已保存区域标注 0 个 · 待标注 11 个/);
      assert.match(html, /class="draft-primary"[^>]*>下一步：超像素人工标注/);
      assert.match(html, /点选区域并保存后，才计入已保存区域标注/);
      assert.doesNotMatch(html, /<button[^>]*>进入预处理<\/button>/);
      assert.doesNotMatch(html, /aria-label="批量创建标签"/);
      assert.match(html, /<details><summary>已有区域标注文件？/);
      assert.doesNotMatch(render({ ...card, label_form_open: true }, false), /<textarea/);
      assert.match(render({ ...card, stage: 'need_annotations' }), /返回超像素人工标注/);
    });
    await t.test('the annotation next step renders working mode choices for the intake batch', () => {
      const card = { id, stage: 'imported', mode: 'unlabeled', image_names: ['plastic'], annotation_names: [], classes: [],
        image_count: 11, paired_count: 0, missing_count: 0, issue_count: 0, imported_count: 11, ready_count: 0,
        labels: [{ id: 'label', name: 'PP', code: 'L001', color_hex: '#123456', existing: true }] };
      const entries = [
        { event: 'user', data: { content: '创建标签：PP' } },
        { event: 'done', data: { content: '标签已就绪，下一步进行人工标注', step_count: 1, data_intake: card } },
        { event: 'user', data: { content: `进入人工标注 ${id}` } },
        { event: 'done', data: { content: '请选择超像素生成方式', step_count: 0, data_intake: card,
          annotation_target_cube_ids: rows.map(row => row.id) } },
      ];
      function Probe() {
        const session = useSession({ enabled: true, generation: 1, bootId: 'boot', records: rows });
        return createElement(AssistantBar, { session: { ...session, state: { ...session.state, entries } }, onHistory() {}, onViewer() {} });
      }
      const html = renderToStaticMarkup(createElement(Probe));
      assert.equal((html.match(/data-event="annotation-choice"/g) ?? []).length, 1);
      assert.match(html, /本次已确定的数据，共 11 张/);
      assert.match(html, /<button>逐张生成（推荐）<\/button>/);
      assert.match(html, /<button>提前生成全部<\/button>/);
      assert.equal((html.match(/历史导入记录/g) ?? []).length, 1);
      assert.doesNotMatch(html, /<textarea[^>]*id="intake-labels-/);
    });
  } finally { await server.close(); }
});
