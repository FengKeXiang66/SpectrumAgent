# TASK-16 执行回报

已完成 B-1/B-2/B-3、C-1/C-2 及授权补充的 C4。未提交 Git commit。

## 1. 逐文件改动

- `src/components/annotation/folder-label.ts`（新增）：纯函数 `folderName(headerPath: string): string | null`、`matchLabel(labels: readonly Label[], folder: string): Label | null`、`catalogCode(catalog: readonly CatalogItem[], folder: string): string | null`。
- `src/components/annotation/folder-label.test.ts`（新增）：8 项纯函数测试，覆盖 Windows / slash / 混合路径、精确匹配、背景排除、目录码、无匹配与无父目录。
- `src/components/annotation/AnnotationWorkbench.tsx`：独立 `labelTouched`、每 cube 提示记录、当前标签所属 cube 守卫、创建待选记录；effect 依赖严格为 `[id, schemas]`，非空标签才运行；鼠标与数字键手选均记录 touched；增加未命中提示及点击创建；移除 MAT 的 import、状态、按钮、渲染块。
- `src/components/annotation/confirm.test.ts`：只更新原 :80 那项测试，改名并加入四条 doesNotMatch，保留 agent 侧语义与原有三条独立断言。**属授权同步，非弱化断言**。其余测试文本逐字未动。
- `src/components/annotation/draft-api.ts`：只增加用户指定的一行注释；保留 confirm 方法及请求构造器。
- `src-python/spectrumagent/api/annotations.py`：只增加指定的一行 TASK-16 deprecated 注释；逻辑零改动。

复用 `.annotation-warning`，没有改 CSS。`ConfirmCard.ts` 未改未删。8 个在途文件（App、annotation.css、AssistantBar、assistant.css、style.css、AssistantPanel、panel-height.test、panel-height）SHA256 与开工记录全部一致；`src-tauri/` 工作区零条目。label_map、regions、快照、版本语义及后端 drafts 逻辑未改。

## 2. B1–B6 / C1–C4

浏览器验收使用实际 AnnotationWorkbench 及全部子组件的静态构建，仅通过 Props 注入模拟传输；未替换组件或 effects。另用真实 FastAPI TestClient 和隔离临时数据库验证 catalog 创建与 confirm 路由。

| 项目 | 结果与证据 |
|---|---|
| B1 | 通过：延迟标签 Promise 时无提示、未选标签；释放后选 PET、确认候选按钮可用；Pe 目录选 PE；工具仍是扩散。大小写 pe/Pe/PE 由纯函数测试全部覆盖。 |
| B2 | 通过：abs 提示原文正确；点击前无 addLabel；取消后保持原选 PE，刷新也不重弹。确认创建请求严格为 `{ project_id, from_catalog: 'plastic', codes: ['ABS'] }`，不传 name/color/tree_path。创建后选 ABS 且可立即确认候选。**选中发生在 addLabel -> execute(metadata=true) -> loadMetadata -> setSchemas(tree) 触发 `[id, schemas]` 的第二次 effect；先匹配再检查 askedFolders，选中后写 labelTouched=true。**真实后端返回 201；ABS 名称、颜色与 catalog 相同，tree_path 为 材料/塑料/ABS。 |
| B3 | 通过：PET 自动选中后鼠标改 PP，覆写保存、另存、刷新及撤销一步仍为 PP；数字 3 改 PP 后刷新仍为 PP。改标签未影响覆写默认勾选；用户取消覆写后，另存与刷新仍保留取消状态。 |
| B4 | 通过：A 手选 PP 后切 B（pet，slash 路径），重新自动选 PET；夹具保持组件实例，额外验证 id 重置与旧 schemas 隔离。 |
| B5 | 通过：E:\临时\single.hdr 提示手动新建，无一键创建；取消后不创建、无报错、原空选择不变；刷新不重弹。 |
| B6 | 通过：`E:\a\pet\x.hdr` 与 `E:/a/pet/x.hdr` 均返回 pet；另覆盖混合分隔符和中文路径。 |
| C1 | 通过：页面 MAT 按钮数 0；工作台不含 ConfirmCard、confirmVersion、drafts.confirm 或旧按钮文案。 |
| C2 | 通过：逐项点验保存并聚合、默认覆写、覆写确认三行、版本列表和历史图、撤销；save/undo 函数、覆写默认与三行 JSX、版本入口与保存按钮与开工副本逐字相同。撤销 30 步由原有 Python 全量测试验证，后端 UNDO_DEPTH=30 未动。 |
| C3 | 通过：真实隔离数据集建立区域后，POST /api/v1/annotations/{id}/draft/confirm 返回 200、overlap_conflicts=0、training_mat_created=true；指定注释存在。全量回归继续覆盖 2GB 闸和重叠仲裁。 |
| C4 | 通过：四条 doesNotMatch 均在，测试名已改，agent import match 保留，其余三条 agent 断言逐字保留；原文件此测试之前的全部文本逐字一致。 |

附加守卫：pe_0602 不被猜为 PE；2026-10-01 不提供一键创建；两者均无静默 addLabel。

## 3. confirm.test.ts 前后对照

属授权同步，非弱化断言。

改前（:80 起）：
```ts
test('REST and HUMAN_CHECK use the same card and pending-call revision stays server-owned', () => {
  const rest = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  const agent = readFileSync(new URL('../assistant/AssistantBar.tsx', import.meta.url), 'utf8');
  for (const source of [rest, agent]) assert.match(source, /import ConfirmCard from/);
  assert.match(rest, /drafts.confirm\(id, \{ revision: view.revision/);
  assert.match(agent, /key=\{state.pending.check_id\}/);
  assert.match(agent, /check_id: state.pending!.check_id, decision: 'approve'/);
  assert.doesNotMatch(agent, /drafts.confirm/);
});
```

改后（:80 起）：
```ts
test('only HUMAN_CHECK uses the confirm card and pending-call revision stays server-owned', () => {
  const rest = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  const agent = readFileSync(new URL('../assistant/AssistantBar.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(rest, /import ConfirmCard from/);
  assert.doesNotMatch(rest, /drafts\.confirm/);
  assert.doesNotMatch(rest, /confirmVersion/);
  assert.doesNotMatch(rest, /确认版本并生成训练 MAT/);
  assert.match(agent, /import ConfirmCard from/);
  assert.match(agent, /key=\{state.pending.check_id\}/);
  assert.match(agent, /check_id: state.pending!.check_id, decision: 'approve'/);
  assert.doesNotMatch(agent, /drafts.confirm/);
});
```

## 4. C 段实际删除与前后对照

实际删除开工副本的 **:13 import、:69 状态、:398 按钮、:399–406 ConfirmCard 渲染块**。ConfirmCard.ts 本体保留。

改前两条声明：
```ts
import ConfirmCard from './ConfirmCard.ts';
  const [confirmVersion, setConfirmVersion] = useState(false);
```

改前保存区（:397–407）：
```tsx
          {exportResult?.ok && exportResult.warning && <p role="status" className="annotation-warning">{exportResult.warning}</p>}
          <button disabled={busy || !ready || Array.from(note).length > 2000} onClick={() => setConfirmVersion(true)}>确认版本并生成训练 MAT</button>
          {confirmVersion && <ConfirmCard key={id} cubeId={id} disabled={busy || !ready} onReject={() => setConfirmVersion(false)} onApprove={async view => {
            let matError: string | undefined;
            const success = await execute(async () => {
              const result = await drafts.confirm(id, { revision: view.revision, overwrite, ...(note ? { note } : {}) });
              matError = result.mat_error;
            }, '标注版本已确认，训练 MAT 已生成。', true);
            if (success) { setConfirmVersion(false); if (matError) setMessage(`标注版本已确认；训练 MAT 生成失败：${matError}`); }
          }} />}
          {confirmOverwrite && <div role="alertdialog" aria-label="确认覆写最新版本" className="annotation-overwrite"><p>{overwriteText ? overwriteText[0] : '将覆写最新版本（信息加载中…）'}</p><p>{overwriteText ? overwriteText[1] : '本次保存将写入当前工作态。'}</p><p>版本号与首次创建时间保留。</p><button disabled={busy} onClick={() => { void save(true); }}>确认覆写最新版本</button><button onClick={() => setConfirmOverwrite(false)}>取消</button></div>}
```

改后（:432–433）：
```tsx
          {exportResult?.ok && exportResult.warning && <p role="status" className="annotation-warning">{exportResult.warning}</p>}
          {confirmOverwrite && <div role="alertdialog" aria-label="确认覆写最新版本" className="annotation-overwrite"><p>{overwriteText ? overwriteText[0] : '将覆写最新版本（信息加载中…）'}</p><p>{overwriteText ? overwriteText[1] : '本次保存将写入当前工作态。'}</p><p>版本号与首次创建时间保留。</p><button disabled={busy} onClick={() => { void save(true); }}>确认覆写最新版本</button><button onClick={() => setConfirmOverwrite(false)}>取消</button></div>}
```

## 5. 自检与执行模式

Windows PowerShell；Node v24.19.0；Python 使用仓库 `.venv/Scripts/python.exe`，未使用系统 Python。pytest 独立 basetemp 位于工作区；没有关闭测试或修改跳过条件。首次默认临时目录跑法遇到 pytest 工厂 WinError 5，改用独立 basetemp 后通过。

| 检查 | 开工实测 | 最终实测 |
|---|---:|---:|
| Python 全量 backend/tests + src-python/tests | 1486 passed / 2 skipped | **1486 passed / 2 skipped**，15 warnings |
| 根目录 node --test | 196 passed / 1 failed | **204 passed / 1 failed**（新增纯函数 8 项全部通过） |
| npm run build（tsc --noEmit + vite） | 通过 | **通过** |
| folder-label.test.ts | 新增前不存在 | **8/8**；B6 的反斜杠与正斜杠在第一项分别断言 |
| folder-label + confirm 聚焦测试 | — | **14/14** |

卡中 Python 1484 / Node 191 通过的基线与当前工作区实测不同：开工即多 2 项 Python、5 项 Node，通过数未下降。唯一既有失败仍为 `src/components/preprocess/panel.test.ts:52` 对 `/projects\[0\]/` 的断言。删除 MAT 时出现的 confirm.test.ts 新失败，已按授权同步消除，没有修改该既有 panel 失败。

命令与日志：
- 开工全量：`.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q -x --basetemp .temp/task16-py-baseline`，`.temp/task16-python-full-baseline.log`。
- 最终全量：`.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q --basetemp .temp/task16-py-final`，`.temp/task16-python-final.log`。
- `node --test`：`.temp/task16-node-baseline.log`、`.temp/task16-node-final-authorized.log`。
- `npm run build`：`.temp/task16-build-baseline.log`、`.temp/task16-build-final-authorized.log`。
- 新测试与确认测试：`.temp/task16-focused-final.log`。
- 浏览器夹具：`.temp/task16-ui/`，`.temp/task16-ui-results.json`，`.temp/task16-abs-prompt.png`、`.temp/task16-abs-selected.png`。
- 真实后端探针：`.temp/task16-backend-probe.py`、`.temp/task16-backend-probe.log`。

## 6. 行号漂移

- 原卡主文件引用在开工时均吻合：selectedId :57、edit 守卫 :227、确认按钮 :381、MAT :398、渲染块 :399、状态 :69、import :13；datasets/types.ts :9 和 api.ts :29 也吻合。
- **补充卡 §2.6 代码摘录的行号有一处偏移**：卡写 for 循环 :84、drafts.confirm 断言 :85；开工实物实际为 **:83、:84**。测试入口 :80 无偏移。
- 改后 AnnotationWorkbench：edit 守卫 :227→247；确认候选按钮 :381→416；覆写弹窗 :407→433；版本记录 :408→434。原 :13/:69/:398–406 已删除。
- draft-api confirm 定义 :30→31（新增注释在 :30）。后端 confirm 装饰器 :207→208（新增注释在 :207）。
- confirm.test.ts：测试入口仍 :80；四条 rest 断言 :83–86；agent import :87；原 agent 三条独立断言 :85–87→88–90。

## 7. 未决问题

无 TASK-16 设计或实现未决项。保留唯一既有 panel.test.ts:52 失败；本任务未扩大范围修复它。浏览器验收采用模拟传输，真实后端关键分支另由隔离探针及全量测试覆盖，未对用户实际数据集做人工生产标注。
