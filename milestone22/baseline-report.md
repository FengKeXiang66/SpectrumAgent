> 历史阶段性记录：该布局歧义已由用户裁定并完成实施；最终回报见 report.md。

# TASK-22 开工与功能基线回报（等待 S07 布局口径裁定）

尚未修改任何产品源码。开工 HEAD `5d65914`；三道闸门全部通过，指定行号漂移为“无”。

## 已通过的开工检查

- 初始 `git status --short` 标准输出为空。
- `git diff --stat 5f9f04b HEAD` 只有 TASK-22 任务卡，无 src/src-tauri。
- `node --test "src/**/*.test.ts"`：215 tests / 215 pass / 0 fail，cancelled/skipped/todo 均为 0。
- PreprocessPanel:11、ModelPanel:10、preprocess.css:4、modeling.css:1、src/components/preprocess/panel.test.ts:61–63、原型:1748/1833 全部匹配；两份原 CSS 变量计数均为 0。

## 即停原因

TASK-22 §2.4 写“S07 的栏宽在 TSX 里由内部布局决定，skin 不强行改”，A6 又要求“S07 左栏 ≈ 300px”。但当前 ModelPanel.tsx 的训练页没有左栏：两个直属 fieldset 上下排列，外层 display:block。

实测两块分别为：

| fieldset | x | y | 宽度 |
|---|---:|---:|---:|
| 样品连续量 | 234 | 221.2083 | 992.6667 |
| 训练配置 | 234 | 589.8542 | 992.6667 |

这些是现状读数，证据为 baseline/s07-layout.json 与 s07-layout.jpg；不是新设计尺寸。300px 的目标出处为原型:1833，76rem 整屏上限出处为 modeling.css:1，二者不能等同。

按任务卡红线 8“卡未覆盖的歧义停手回报”，在新增 skin 和 import 前停下。待裁定：仅用 modeling-skin.css 将现有两个 fieldset 排成 300px 左栏 + 自适应右栏，还是保留单列并修订 A6。前者不改 TSX 结构、不改 76rem 上限。

## 已完成的功能基线

执行模式：PowerShell、Node 原生测试；生产构建 + IAB + 隔离真实 FastAPI 桥。使用仓库既有 regression_factory 的 12 个合成回归样品/标注快照/预处理 ready 输入，保存版本、S06 新运行/对比以及 S07 训练均调用真实后端。引擎 Ready/目录选择为受控 IPC。未操作正式标注库，未运行原生 Tauri/Rust 测试。

| 字段 | 基线读数 |
|---|---|
| S06 保存 version_no | 2 |
| S06 提交终态 | succeeded |
| S06 提交 run | 103fc274-5b9b-41db-a5b1-033e60cddf4b |
| CompareResult.runs[].id | 20236539-8cb6-4ff4-b1f0-60ee46ba25ce |
| 对比曲线 report.run_id | 20236539-8cb6-4ff4-b1f0-60ee46ba25ce，属于上述 runs |
| S07 Result.status | succeeded |
| S07 selected_lv | 3 |
| S07 metrics.rmse（UI RMSEC） | 0.3877278749721029 |
| S07 训练 run_id | 33c1b773-6bb7-492e-a7f8-3708ee0da773 |
| 跳转 S08 时读回的 runId | 33c1b773-6bb7-492e-a7f8-3708ee0da773，与训练返回一致 |

S06 已验证载入配方、保存新版本、提交、对比、点对比 run 读图、刷新历史。此夹具 Fisher 为 null，ranking 为空；按卡使用 runs[].id 追踪来源，没有编排名。S07 已验证训练、进入 S08、模型注册视图及批量推理视图往返。

证据目录：`E:/AI_Agent/milestone22/evidence/baseline/`。

原始接口：backend.json；UI：browser-checks.json；汇总：summary.json；截图：s06-compare.jpg、s06-history.jpg、s06-layout.jpg、s07-training.jpg、s08-result.jpg、s07-registry.jpg、s07-inference.jpg、s07-layout.jpg。

## A1–A9 当前状态

| 验收 | 当前状态 |
|---|---|
| A1/A2 | before 功能基线完成；after 未开始，不判通过 |
| A3 | 两个 skin 尚未创建，不判通过 |
| A4 | 产品文件改动 0；两份 TSX diff 均为空，未进入实施 |
| A5 | src/components/preprocess/panel.test.ts 零改动；基线 27 处断言随 215 项测试通过 |
| A6 | S07 布局口径冲突待裁定；没有静默改成两栏或忽略该判据 |
| A7 | 基线 npm run build 成功（tsc --noEmit + Vite，81 modules）；改后未执行 |
| A8 | 开工 215/215/0；新增测试 0；改后未执行 |
| A9 | 基线 panel.test.ts:61/62 为绿，App 与 DatasetPanel 未改 |

行号漂移：无。与卡的冲突点：§2.4 的实际布局描述/不强行改要求与 A6 左栏判据。未完成换皮，不作整批通过结论。
