# TASK-19 P2 执行回报

已完成 S04 数据查看器与 S08 结果屏。依据 HEAD `1920716` 的卡执行；改动未提交。

执行模式：Windows PowerShell，Node v24.19.0 / npm 11.17.0；Node 原生 TypeScript 静态/行为测试；`npm run build`（`tsc --noEmit && vite build`）；IAB 1280×820 加本地隔离 FastAPI 验收桥。浏览器加载生产构建，IPC 由验收桥转发到真实接口；引擎 Ready/目录选择为验收夹具。未运行原生 Tauri/Rust 测试。

浏览器数据：两份只读真实 PE 源数据用于预览，仓库既有 `regression_factory` 的 12 个合成样品用于回归。标注快照和成功预处理记录均是独立运行目录内的既有测试夹具输入；PLS 训练、结果查询、LV 曲线查询均由真实后端执行，没有伪造结果、没有访问正在使用的标注数据库。

三道闸门：开工前工作区干净；`be28705..1920716` 仅任务卡文档变化；基线 205/205/0；§0 全部锚点与开工 HEAD 匹配。原始测试日志、固定 HEAD 的行号摘录见 `evidence/baseline-before.txt`、`evidence/preflight.json`、`evidence/preflight-anchors.txt`。

1) 逐文件改动

| 文件 | 改动 |
|---|---|
| `src/App.tsx` | 新增 `runId`；`openScreen(next, record?, run?)` 仅在 `run !== undefined` 时写值；接通 s04/s08。导航保留 runId；S08 返回列表是唯一 `setRunId(null)` 入口。训练/列表选行带 ID，关闭分别回 s03/s07。去掉 DatasetPanel 的 selectedRecord 传参，App 的 selected 保留。 |
| `src/screens/S04.tsx`（新增） | record 来自 App selected；预览状态与读取链路迁入，进入自动读首波段，保留波段选择、读取、错误提示与异步失效保护；复用 BandCanvas。 |
| `src/screens/S08.tsx`（新增） | 无 runId 时读取并筛选真实回归运行列表；有 runId 时自取 run 和 sweep。迁入六个结果状态、beginCharts/acceptResult/load、原结果段与 RegressionCharts，保留指标、质量标签、预测图和缺失曲线提示。顶栏增加返回列表。 |
| `src/components/datasets/BandCanvas.tsx`（新增） | 原 BandCanvas 函数体原样提为共享模块，仅补模块 import/export。 |
| `src/components/datasets/DatasetPanel.tsx` | Thumbnail 原逻辑不变，改 import 共享画布；预览入口改为“查看”，调用 onOpen('s04', record) 并保留 workspace 副作用；移除预览状态/链路/段落、selectedRecord prop 和同步 effect。 |
| `src/components/modeling/ModelPanel.tsx` | 移出结果段、图表及六状态/读取链路；删除回归记录下拉和其专用 history 拉取；保留训练、CSV、目标值及 registry/inference 视图。训练成功回调进入 S08，失败仍在 S07 报错。 |
| `src/screens/split-screens.test.ts`（新增） | 4 项静态测试，覆盖带参导航保留、共享画布/上下文、S08 自取与列表、S07 边界和原源码锚点。 |
| `milestone19/evidence/browser_server.py`、`tauri-shim.js`（新增） | 隔离浏览器验收桥与复现入口。运行：先 `npm run build`，再 `.venv/Scripts/python.exe milestone19/evidence/browser_server.py`，打开 `http://127.0.0.1:1429/`。 |
| `milestone19/report.md`、`milestone19/evidence/*`（新增） | 本回报、闸门/测试/构建日志、接口与 DOM 验收记录、6 张截图及零字节标注 diff 文件。 |

无退场文件。无依赖、后端、Rust、现有 CSS、AppShell、引擎三态改动；S04/S08 中 `var(--brand` 计数均为 0。

2) A1–A10

| 项 | 结果 | 证据 |
|---|---|---|
| A1 | 通过（按本轮修订） | App 持 runId，第三参可选；不传参数不写 runId；导航保留；唯一清空入口返回列表。新静态测试第 1 项通过。 |
| A2 | 通过 | 真 runs() 返回回归记录 `20cf5937-9d94-47e9-b3c9-86ec17919297`，列表 1 行；点行进入结果。返回列表后结果段消失，列表重新读取。 |
| A3 | 通过 | S07 点击训练 PLS → S08 succeeded → 导航数据 → 导航结果，结果全文一致。数据屏时结果屏 DOM 数为 0，证明已卸载。真实 get_run 与 lv_sweep 各 3 次（初次进入、重挂载、列表选行）。 |
| A4 | 通过 | “查看 20260804205214_64”进入 S04；首波段自动加载；改为 17 并读取，显示 320×116 灰度图；关闭回 S03；composer 保留该数据上下文。 |
| A5 | 通过 | S03 共 14 个缩略图画布；两份真实 PE 画布内在尺寸 320×116、显示尺寸 80×29。已目视检查缩略图正常，截图同时包含“查看”按钮；Thumbnail 与 BandCanvas 原函数体校验一致。 |
| A6 | 通过 | panel:61 / panel:62 / working:94 / SettingsPanel:185–187 的四处断言全绿，原测试文件全部未修改。 |
| A7 | 通过 | S07 的模型注册、批量含量推理均能进入并返回训练页；训练页回归结果段数为 0；回归记录下拉已删除。 |
| A8 | 通过 | 开工 205/205/0；改后原有 205/205/0；新增 4 全过；全套 209/209/0，skip/cancel 均为 0。 |
| A9 | 通过 | `git diff --stat src/components/annotation/` 标准输出为空；证据文件 0 字节。 |
| A10 | 通过 | `npm run build` 成功，含 tsc --noEmit 与 Vite 生产构建，75 个模块。 |

训练实测：12 个样品、48 个前景像素，手动 LV 3；质量标签“仅可做半定量”与各指标由真实后端返回并原样显示。此处验证训练/展示链路，合成夹具不代表业务模型质量。

`git diff --stat src/components/annotation/`：

```text
```

浏览器：144 次桥接 API 请求均 HTTP 200；控制台 warn/error 共 0。记录见 `evidence/bridge-records.json`、`evidence/browser-checks.json`、`evidence/verification.json`。

3) 三锚四处源码断言逐一核对

| 原测试位置 | 原匹配文本 | 结果 |
|---|---|---|
| `src/components/preprocess/panel.test.ts:61` | App `<PreprocessPanel` | 保留；原测试文件未改；通过 |
| 同文件 `:62` | DatasetPanel `onOpen('s06', record)` | 原调用不变；通过 |
| `src/components/annotation/working.test.ts:94`（断言在 :95） | App `<Composer`，以及 Composer 常驻对话条 footer | 保留；原测试与 Composer 均未改；通过 |
| `src/components/settings/SettingsPanel.test.ts:185-187` | import SettingsPanel / 设置按钮 / 条件渲染三段 | 字面量保留；原测试未改；通过 |

4) 测试数与新增清单

原有 **205 项全部通过 + 新增 4 项全部通过 = 209 项，0 fail**。未删、改、合并任何原有测试，无退场文件。

新增 `src/screens/split-screens.test.ts`：

1. `P2 navigation preserves App runId until the results back-to-list action`
2. `P2 S04 and S03 thumbnails share BandCanvas and viewing updates workspace`
3. `P2 S08 loads real regression runs and refetches run plus sweep on mount`
4. `P2 S07 keeps training and internal views while results and source anchors stay intact`

执行记录：原有测试以 `git ls-files "src/**/*.test.ts"` 列表运行，日志 `evidence/baseline-after.txt`；全套命令 `node --test "src/**/*.test.ts"`，日志 `evidence/frontend-tests.txt`。首次新增专项运行 4/4/0；全套同样包含并通过这 4 项。构建日志 `evidence/build.txt`。

5) 截图（均为 1280×820）

- `evidence/s04-preview.jpg`：S04 波段 17 预览。
- `evidence/s08-list.jpg`：S08 真运行列表。
- `evidence/s08-result.jpg`：S07 训练成功后的 S08 结果态。
- `evidence/s03-table.jpg`：S03 表格，含真实 PE 缩略图和“查看”入口。
- `evidence/s08-remount.jpg`：A3 导航返回结果后的截图。
- `evidence/s08-empty.jpg`：尚未训练时的空列表。

6) 行号漂移及口径冲突

开工行号漂移：**无**。锚点以开工 HEAD `1920716` 为准；实施后代码移动是本次拆屏的预期变化。

卡仍有三处旧文残留，均按本轮明确裁定及卡内更具体条款执行，未改任务卡：

- A1 判据仍写“导航跳转处 runId 被清空”，与 §2.1、R2 及本轮指令相反；执行导航保留，仅返回列表清空。
- §2.1 表后“刷新后仍能自取”与 A3 明确边界不一致；验收按切屏重挂载，未实现整页刷新持久化。整页刷新仍回 s03、runId 为 null，下次导航结果即列表态。
- §2.1 入口仍列“训练成功 / 回归记录下拉”，但 §2.3 已裁定删除 S07 下拉；执行删除，由 S08 列表替代。

未决问题：无。

7) S08 空列表显示

文案：**“暂无回归运行记录。请先在建模屏完成训练。”**

判据：`runId === null`，`runs()` 已成功读取（`!listLoading && !listError`），筛选 `task === 'regression'` 后长度为 0。接口返回空数组或仅有非回归运行均满足；加载中显示“正在读取回归运行记录…”，失败显示真实错误，不显示空列表提示。空态已在隔离真实空运行库中实测并截图，没有渲染假记录。
