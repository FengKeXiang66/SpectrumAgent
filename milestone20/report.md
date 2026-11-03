# TASK-20 P5 执行回报

已完成 S02 工作台、S09 实验台账、S10 检索正式空态、S11 设置入口。依据卡 `82a2976` 执行；改动未提交。

执行模式：Windows PowerShell，Node v24.19.0 / npm 11.17.0；Node 原生 TypeScript 测试；`npm run build`（`tsc --noEmit && vite build`）；IAB 1280×820 加隔离真实 FastAPI 验收桥。未运行原生 Tauri/Rust 测试。

三道闸门均通过：开工前 git status 为空；`82097da..82a2976` 只有任务卡文档变化，无 src/src-tauri；基线 209/209/0；§0 全部锚点及 S03 调试行 :183 匹配。见 `evidence/preflight.txt`、`preflight-anchors.txt`、`baseline-before.txt`。

浏览器加载生产构建。引擎 Ready 与目录选择为受控 IPC；数据和设置读取均经真实 API。独立运行库包含 12 个既有合成回归样品、2 份只读真实 PE 数据、1 个用于真实预处理执行的合成样品，共 15 个数据集；4 条真实 PLS 运行。另用既有夹具插入 1 条 pending 分类预检记录，验证“全部”筛选及不完整详情。空态连接另一份真实空库。未连接正在使用的标注数据库，没有伪造训练成功、指标或预处理时间。

1) 逐文件改动

| 文件 | 改动 |
|---|---|
| `src/App.tsx` | 增加四屏 import/case；S02 的回归请求由 App 持有并过滤 regression，全部卡片数据经 props 传入；连接查看全部、近期运行带 runId、继续标注、S10 回数据屏、S11 打开原 modal。S03 整段逐字一致。 |
| `src/screens/S02.tsx`（新增） | 四张卡：records.length、回归总数及接口顺序前 3 条、中文相位与代次、继续标注。引擎 props 类型仅暴露 phase/generation_id；不显示 pid/port。加载、错误和无运行状态分开显示。 |
| `src/screens/S09.tsx`（新增） | 默认回归列表，task 全部/回归仅客户端过滤；ID 前 8 位、task、status 三列；选行自取详情与指标、质量标签、折叠 leak_report。预处理只查询选中数据集，显示真实 created_at/finished_at/status/b01_branch。请求有卸载/切换失效保护，不完整运行字段显示不适用，不造指标。 |
| `src/screens/S10.tsx`（新增） | 标题、“检索在阶段二提供。”和唯一主行动“返回数据屏”；无屏内搜索框或数据请求。 |
| `src/screens/S11.tsx`（新增） | 设置与出域关系说明、“打开设置”回调、出域记录阶段二说明；复用原 SettingsPanel，未重写 modal。 |
| `src/screens/light-screens.css`（新增） | 仅 1 个布局类，复用现有卡片样式并增加自适应网格列；没有颜色/主题变量。 |
| `src/screens/light-screens.test.ts`（新增） | 6 项静态测试，逐条见第 4 项。 |
| `milestone20/evidence/browser_server.py`、`tauri-shim.js`（新增） | 隔离真实接口、真实训练/预处理、空库与 pending 分类夹具的复现桥。 |
| `milestone20/report.md`、`milestone20/evidence/*`（新增） | 本回报、闸门/测试/构建日志、接口/DOM 记录、校验结果及 8 张截图。 |

无退场文件。现有 CSS、依赖、后端、Rust 均未改；四屏 `var(--brand` 计数为 0。原有测试文件全部未改。

2) A1–A10

| 项 | 结果 | 证据 |
|---|---|---|
| A1 | 通过 | 数据卡 15 = records.length；回归卡 4 = regression 过滤长度，最近 3 条顺序与接口一致。引擎“已就绪；代次 1”，无 pid/port。最近项跳 S08、查看全部回 S03、继续标注走原回退逻辑均实测。 |
| A2 | 通过 | 默认回归表 4 行；DOM 表头严格为“运行 ID / task / status”。静态测试提取回归 table JSX，确认没有 created_at/finished_at/Date/时间/未知；日期字段只用于预处理表。“全部”显示 5 行（含 1 条 pending 分类夹具），切回回归 4 行，筛选不触发新请求。 |
| A3 | 通过 | 点击 082497de → 真 get_run；样品 12、前景像素 48、selected_lv 4、best_lv 1，七个真实 metrics 和“仅可做半定量”显示；leak_report 的 details 默认关闭。 |
| A4 | 通过 | 未选时显示指定提示；选择 ledger-sample 后显示 1 条真实预处理运行。created_at：`2026-11-03T14:53:47.821208+00:00`。两轮验收各发 1 次所选数据集请求，共 2 次，均只查询同一选定 ID，没有按 15 个 records 聚合。 |
| A5 | 通过 | S10 显示正式说明，无屏内 input；点击“返回数据屏”后数据集管理屏可见。 |
| A6 | 通过 | S11 打开原“LLM 设置”dialog，取消后回 S11。出域记录区按钮数 0、表格数 0，只有说明。原 SettingsPanel 源码逐字未改。 |
| A7 | 通过 | panel:61、panel:62、working:94、SettingsPanel:185–187 四处原断言全绿，字面量保留，原测试文件未改。 |
| A8 | 通过 | 原有 209 全过 + 新增 6 全过 = **215/215/0**；skip/cancel 都为 0，无退场测试。 |
| A9 | 通过 | `git diff --stat src/components/annotation/` 标准输出为空，`evidence/annotation-diff-stat.txt` 0 字节。 |
| A10 | 通过 | npm run build 成功，含 tsc --noEmit；Vite 转换 80 个模块。 |

实测预处理行：

```text
created_at  2026-11-03T14:53:47.821208+00:00
finished_at 2026-11-03T14:53:47.862471+00:00
status      succeeded
b01_branch  scale
```

标注目录 diff 输出：

```text
```

最终桥接请求 100 次均 HTTP 200，两个浏览器标签的控制台 warn/error 均为 0。继续标注入口使用现有 S05，附带读取到 canvas host 高度 305；未改 S05 文件。

3) 三锚四处断言核对

| 开工测试位置 | 匹配文本 | 结果 |
|---|---|---|
| `src/components/preprocess/panel.test.ts:61` | App `<PreprocessPanel` | 保留；原断言通过 |
| 同文件 `:62` | DatasetPanel `onOpen('s06', record)` | 原调用未改；原断言通过 |
| `src/components/annotation/working.test.ts:94`（匹配在 :95） | App `<Composer` 与常驻对话条 | 保留；working 与 Composer 均未改；通过 |
| `src/components/settings/SettingsPanel.test.ts:185-187` | import SettingsPanel / 原设置按钮 / Ready 条件渲染 | 三段逐字保留；原断言通过 |

同时逐字校验 App 中 S03 整个 case、AppShell 渲染尾部、Starting/Failed/Stopping 三态区段，以及 AppShell/theme/style/SettingsPanel/依赖清单，均与开工 HEAD 相同。

4) 测试数与新增清单

基线 **209 项全部通过 + 新增 6 项全部通过 = 215 项，0 fail**。未删、改、合并任何原有测试；没有退场文件。

新增 `src/screens/light-screens.test.ts`：

1. `P5 S02 uses props for four cards, recent regression runs and phase plus generation only`
2. `P5 S09 regression table has only id task status and a client task filter without invented timestamps`
3. `P5 S09 fetches selected run details and retains backend metrics quality and collapsed leak report`
4. `P5 S09 preprocess reads only the selected dataset and preserves real time fields and empty states`
5. `P5 S10 has a data-screen action and S11 opens the existing settings modal without fake controls`
6. `P5 inserts four screen cases while preserving source anchors S03 debug text and theme boundary`

原有测试按 `git ls-files "src/**/*.test.ts"` 列表单独运行，结果 209/209/0（`evidence/baseline-after.txt`）；最终全套 `node --test "src/**/*.test.ts"` 215/215/0（`frontend-tests.txt`）；构建日志 `build.txt`。

5) 截图

要求的六类截图均已保存、目视检查，1280×820：

- `evidence/s02-dashboard.jpg`
- `evidence/s09-regression-list.jpg`
- `evidence/s09-detail.jpg`
- `evidence/s09-preprocess.jpg`
- `evidence/s10-empty.jpg`
- `evidence/s11-settings-entry.jpg`

附加 `evidence/s11-settings-modal.jpg`（原设置 modal）、`evidence/s09-empty.jpg`（真实空库两种空态）。

6) 行号漂移、口径说明与未决问题

本轮开工 HEAD `82a2976` 行号漂移：**无**。前轮指出的 S03 :168→:183 已由卡修正；实施后 import/effect/case 插入造成的行号移动属于本次改动，不回写开工锚点。

卡内及实物的差别已显式处理：

- §2.2 仍残留“写未知或干脆不设该列”，而 R2/A2/红线及本轮指令明确要求无时间列；执行不设列，也不写“未知”。
- `modeling/api.ts:51` 的前端类型确实仅声明 id/task/status，但隔离真实 API 的原始 list_runs 响应还附带 created_at。它未进入前端类型，本批严格依卡不消费、不渲染该附加字段，未改接口类型或后端；Result 详情也未引入时间。
- “全部/回归”按客户端 task 过滤执行，默认回归；“全部”包含接口中的非回归记录，仅展示真实已有字段。未添加项目/配方/Kappa 筛选。

未决问题：无。

7) 两种 S09 空态

没有回归运行：**“暂无回归运行记录。请先在建模屏完成训练。”**

判据：运行读取成功、加载完成，默认回归筛选后长度为 0；不渲染假行。若选择“全部”且整个列表为空，则显示“暂无运行记录。请先在建模屏完成训练。”

没有已登记数据集：**“暂无已登记数据集。请先在数据屏登记数据。”**

判据：App 传入 records.length === 0；数据集选择器禁用，不调用 preprocessing.listRuns。records 非空但尚未选择时，按卡显示 **“选择一个数据集查看其预处理运行”**。选定后真实返回空列表则显示“该数据集暂无预处理运行。”。加载/错误均有独立文案，不冒充空态。

复现：先 npm run build，再运行 `.venv/Scripts/python.exe milestone20/evidence/browser_server.py`；主夹具打开 `http://127.0.0.1:1430/`，空库打开 `http://127.0.0.1:1430/?fixture=empty`。测试桥仅限本地隔离验收，未改生产 IPC 或 CSP 配置。
