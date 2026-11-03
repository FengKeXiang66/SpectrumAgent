# TASK-21 · P3 S05 换皮回报

代码与 A2–A9 已完成；**A1 部分通过，空格/中键按住拖拽仍待手动验收**。用户回复“暂时无法手动测试”，因此不将这两项记为通过，也不声称整批验收全部通过。未提交 Git。

## 1. 逐文件改动与执行模式

产品源文件恰好两个：

| 文件 | 改动 |
|---|---|
| `src/components/annotation/annotation-skin.css` | 新增 54 行皮肤；变量优先，全部选择器限定在 `.annotation-workbench`；178 / 自适应 / 236 三栏、卡片、按钮、L0–L4、快捷键浮层 |
| `src/components/annotation/AnnotationWorkbench.tsx` | 仅在原 `annotation.css` import 之后增加一行皮肤 import；其余内容逐字符比对 HEAD 一致 |

`milestone21/` 仅归档本任务要求的截图、读数、测试日志与本报告。隔离验收辅助脚本放在 Git 忽略的 `.runtime/task21/`，没有第三个产品源文件。未改既有 CSS、画布逻辑、CandidateQueue、ConfirmCard、测试、依赖、后端或 Rust。

执行模式：PowerShell + Node 原生测试；生产构建在 IAB 浏览器中通过本地 IPC 桥接到项目现有 Python 标注 API。标注读写目录为 `.runtime/task21/acceptance/`，真实高光谱输入只读，未使用正式标注库。不是 Tauri 桌面窗口端到端验证，也没有运行 Rust 测试。before 使用改动前生产构建；after 使用皮肤加入后的生产构建；同一 seed、cube ID、输入和参数重跑。

开工三闸门均通过：初始工作区干净；`git diff --stat 9e26a27 HEAD` 只有 docs/任务卡，HEAD 为 `4808169`，日志含 `9e26a27`；基线 215/215/0；指定行号全部复核匹配。见 `evidence/preflight.txt`、`evidence/baseline-tests.txt`。

## 2. Workbench 完整 diff

```diff
diff --git a/src/components/annotation/AnnotationWorkbench.tsx b/src/components/annotation/AnnotationWorkbench.tsx
index 967e3cd..3812265 100644
--- a/src/components/annotation/AnnotationWorkbench.tsx
+++ b/src/components/annotation/AnnotationWorkbench.tsx
@@ -15,6 +15,7 @@ import { drafts } from './draft-api.ts';
 import DisplayToolbar, { SpectrumReadout } from './display/DisplayToolbar.tsx';
 import { DEFAULT_LUT, changeLut, displayRequest, type DisplayMode, type InspectionMode, type LutParameters } from './display/display.ts';
 import './annotation.css';
+import './annotation-skin.css';
 import type { WorkspaceContext } from '../assistant/api.ts';
 import { candidatePreviewKey } from '../assistant/presentation.ts';
```

## 3. A1–A9 结果

| 项目 | 结果 | 证据/读数 |
|---|---|---|
| A1 快捷键 | **部分通过、两项待手测** | 数字 3→PP、1→PE；C 点选；D 扩散；Enter 确认；Z 撤销；←/→切换两张真实数据；Ctrl+S 保存均实测。按住空格拖拽、按住中键拖拽：当前浏览器接口不能组合按住与拖拽，用户暂时无法手测，未判通过。普通点选工具左键拖拽可平移，但不作为这两项替代证据 |
| A2 主链 | 通过 | 点选→确认 1.44%；右键→0.00%；Shift→不确定 1.44%；扩散候选 140,566 px / 60 超像素；Enter 后确认 95.08%；Z 后恢复 1.44%。额外 30 次编辑 + 30 次 Z，统计准确恢复起点 |
| A3 保存投影 | 通过 | 保存并聚合成功；覆写弹窗三行齐全；实际确认覆写成功，v1 ID 与创建时间保持；JSON 路径可见，文件存在、shapes=1 |
| A4 候选与高亮 | 通过 | 候选 1：140,566 px，最小 0.8622、平均 0.9740；画布悬停块 26，2,127 px、聚乙烯纯度 100%，黄色高亮可见；见 after/hover-highlight.jpg |
| A5 皮肤禁则 | 通过 | 新文件禁则 0；!important 0；39/39 选择器带前缀，含 @media |
| A6 零授权同步 | 通过 | 5 个测试文件零 diff，SHA256 复核一致；65 处断言全保；现有 215 项全绿 |
| A7 视觉对照 | 通过 | 原型与实物左右栏均 178px / 236px；中栏自适应；画布 clientHeight=479px，底色仍 rgb(23,36,44)；卡片 10px 圆角；主按钮 #0e6e8c 实色、普通按钮白底描边；L0–L4 与帮助浮层截图齐全 |
| A8 构建 | 通过 | `npm run build`：tsc --noEmit + Vite build 成功（81 modules） |
| A9 测试基线 | 通过 | 开工 215/215/0；改后原有 215 全过 + 新增 N=0 = **215 tests / 215 pass / 0 fail**；cancelled/skipped/todo 均 0。新增用例清单：无 |

A5 实际执行的 grep 等价命令及输出（`rg` 无匹配时 exit=1，计数仍是 0）：

```powershell
rg --count --include-zero -e 'position:\s*fixed|100vh|z-index' src/components/annotation/annotation-skin.css
0
rg --count --include-zero -e '!important' src/components/annotation/annotation-skin.css
0
```

原 `annotation.css:59` 的 `position:absolute; z-index:4` 完全未动。浮层实测仍 absolute / 4。浏览器 warn/error 日志为 0。

覆写三行原文：

1. 将覆写 v1（2026-11-03T15:45:39.099948+00:00 创建，2,127 px 已标注）
2. 本次保存将写入：聚乙烯 2,127 px · 留白 145,713 px
3. 版本号与首次创建时间保留。

## 4. 五个测试文件（A6）

| 文件 | 断言数 | 是否改动 |
|---|---:|---|
| `src/components/annotation/confirm.test.ts` | 17 | 零 diff |
| `src/components/annotation/display/display.test.ts` | 14 | 零 diff |
| `src/components/annotation/projection.test.ts` | 13 | 零 diff |
| `src/components/annotation/working.test.ts` | 12 | 零 diff |
| `src/components/annotation/overwrite.test.ts` | 9 | 零 diff |

共 65 处。所有既有测试文件都未改；字节 SHA256 与 diff 记录见 `evidence/test-file-checks.json`。

## 5. 截图

| 内容 | 文件 |
|---|---|
| 换皮后三栏全景 | `evidence/after/panorama.jpg` |
| 主/次按钮层级 | `evidence/after/buttons.jpg` |
| L0–L4 指示器 | `evidence/after/levels-buttons.jpg` |
| 快捷键帮助浮层 | `evidence/after/shortcut-help.jpg` |
| 纯度徽标与悬停高亮 | `evidence/after/hover-highlight.jpg` |
| 覆写三行 | `evidence/after/overwrite.jpg` |
| 保存路径 | `evidence/after/saved.jpg` |
| 原型 S05 | `evidence/prototype-s05.jpg` |

![三栏全景](E:/AI_Agent/milestone21/evidence/after/panorama.jpg)

![按钮层级](E:/AI_Agent/milestone21/evidence/after/buttons.jpg)

![快捷键浮层](E:/AI_Agent/milestone21/evidence/after/shortcut-help.jpg)

## 6. 行号漂移与口径冲突

行号漂移：**无**。开工锚点 Workbench:17、annotation.css:1/22/23/58/59、CandidateQueue:7 及原型:1634/1693 全部匹配。新增 import 后后续行自然 +1，不属于开工漂移。

盘点表 §0 的宽泛假设提到可新增包裹层/布局类，而任务卡 §2.2、§3 只授权新 CSS + 一行 import；按任务卡执行，没有新增包裹层、类名或第三个产品文件。提示词与任务卡的执行口径无冲突。

## 7. 选择器全文与变量

所有 39 条选择器（含同一规则的分组项、@media 两项）逐条如下；每条均带 `.annotation-workbench` 前缀，不新增 JSX 类名。对应现有 `annotation.css` 规则位置如下。

| 选择器全文 | 带前缀 | 目标规则/用途 |
|---|---|---|
| `.annotation-workbench` | 是 | annotation.css:1；主色、描边、弱化色变量及根容器留白/文字色 |
| `.annotation-workbench .annotation-heading` | 是 | annotation.css:7；标题行间距 |
| `.annotation-workbench .annotation-columns` | 是 | annotation.css:16、79–80；三栏 178 / 自适应 / 236，间距 12px |
| `.annotation-workbench .annotation-card` | 是 | annotation.css:18；卡片圆角、阴影、内边距与卡间距 |
| `.annotation-workbench .annotation-left .annotation-card` | 是 | annotation.css:18；左栏卡片内边距 |
| `.annotation-workbench .annotation-center > .annotation-card` | 是 | annotation.css:18；中栏卡片内边距 |
| `.annotation-workbench .annotation-right` | 是 | annotation.css:17、79–80；CandidateQueue.tsx:7 右栏宿主的栅格位置与排列 |
| `.annotation-workbench h3` | 是 | annotation.css:3；小标题颜色、底部间距 |
| `.annotation-workbench button` | 是 | annotation.css:19；普通按钮描边、圆角、内边距 |
| `.annotation-workbench button:hover:not(:disabled)` | 是 | annotation.css:20；普通按钮悬停色 |
| `.annotation-workbench .annotation-primary` | 是 | annotation.css:22（:58 的右栏宽度保留）；主按钮实色 |
| `.annotation-workbench .annotation-primary:hover:not(:disabled)` | 是 | annotation.css:23；主按钮悬停深色，同为 0-4-0、后加载 |
| `.annotation-workbench .selected` | 是 | annotation.css:24；选中按钮状态 |
| `.annotation-workbench [aria-selected="true"]` | 是 | annotation.css:24；aria 选中状态 |
| `.annotation-workbench input` | 是 | annotation.css:26；输入描边、圆角、内边距 |
| `.annotation-workbench select` | 是 | annotation.css:26；下拉描边、圆角、内边距 |
| `.annotation-workbench textarea` | 是 | annotation.css:26；文本区描边、圆角、内边距 |
| `.annotation-workbench kbd` | 是 | annotation.css:30；快捷键键帽 |
| `.annotation-workbench .annotation-labels` | 是 | annotation.css:31；标签列表间距 |
| `.annotation-workbench .annotation-tools` | 是 | annotation.css:31；工具列表间距 |
| `.annotation-workbench .annotation-label` | 是 | annotation.css:32；标签按钮内边距与间距 |
| `.annotation-workbench .annotation-levels` | 是 | annotation.css:9；L0–L4 分段容器 |
| `.annotation-workbench .annotation-levels li` | 是 | annotation.css:10；层级单元的边线、底色、内边距 |
| `.annotation-workbench .annotation-levels li:last-child` | 是 | annotation.css:10；移除最后一段右边线 |
| `.annotation-workbench .annotation-levels [aria-current]` | 是 | annotation.css:11；当前 L1 的底色与底部指示线 |
| `.annotation-workbench .annotation-note` | 是 | annotation.css:12；说明卡配色、圆角 |
| `.annotation-workbench .annotation-tabs` | 是 | annotation.css:38；页签间距与底部内边距 |
| `.annotation-workbench .annotation-parameters` | 是 | annotation.css:39；参数区间距 |
| `.annotation-workbench .annotation-statistics` | 是 | annotation.css:36；统计网格间距 |
| `.annotation-workbench .annotation-queue` | 是 | annotation.css:53；候选条目间距 |
| `.annotation-workbench .annotation-queue button` | 是 | annotation.css:54；候选卡圆角、内边距 |
| `.annotation-workbench .annotation-distribution li` | 是 | annotation.css:57；分布行分隔线色 |
| `.annotation-workbench .annotation-warning` | 是 | annotation.css:43；告警圆角 |
| `.annotation-workbench .annotation-color-warning` | 是 | annotation.css:43；颜色告警圆角 |
| `.annotation-workbench .annotation-error` | 是 | annotation.css:15；错误提示圆角 |
| `.annotation-workbench .annotation-overwrite` | 是 | annotation.css:75；覆写确认圆角 |
| `.annotation-workbench .annotation-shortcut-help` | 是 | annotation.css:59；浮层描边、圆角、阴影；原 position:absolute / z-index:4 保留 |
| `.annotation-workbench .annotation-columns` | 是 | ≤720px：恢复单栏；annotation.css:80 |
| `.annotation-workbench .annotation-levels li` | 是 | ≤720px：层级单元内边距；annotation.css:80 |

使用变量：覆盖既有 `--ann-brand:#0e6e8c`、`--ann-line:#e2e7ed`、`--ann-muted:#7b8794`；新增 `--ann-brand-d:#0a5670`、`--ann-brand-soft:#e7f3f7`、`--ann-brand-line:#b9dbe6`。按钮、选中态、说明卡、层级指示器优先引用这些变量。未引用 theme.css 的主题变量。圆角、阴影、间距和栅格用单条规则表达。没有画布选择器覆盖。

## 8. before/after 对照

基线证据目录：`E:/AI_Agent/milestone21/evidence/baseline/`；换皮后证据：`E:/AI_Agent/milestone21/evidence/after/`。

真实输入：`E:/高光谱数据集/plastic/pe/20260804205214_64.hdr`；SLIC n=64、compactness=0.5、PCA=5；同 seed、同 cube ID、同点击像素 [115,319]（块 26）。基线在修改皮肤与 import **之前**完成并归档，之后从隔离 seed 恢复重跑。

| 读数 | before | after | 对照 |
|---|---|---|---|
| 超像素数 | 64 | 64 | 一致 |
| 点选已确认 | 1.44% / 2,127 px | 1.44% / 2,127 px | 一致 |
| 右键擦除后已确认 | 0.00% | 0.00% | 一致 |
| Shift 后不确定 | 1.44% | 1.44% | 一致 |
| 扩散候选 | 140,566 px / 60 超像素 | 140,566 px / 60 超像素 | 一致 |
| 确认候选后已确认 | 95.08% | 95.08% | 一致 |
| 撤销后/保存时已确认 | 1.44% | 1.44% | 一致 |
| JSON shapes | 1 | 1 | 一致 |
| JSON 内容 | 与 after 深比较相同 | 与 before 深比较相同 | 一致 |
| 画布 clientHeight / 底色 | 479px / #17242c | 479px / #17242c | 一致 |
| 左/右栏 | 240 / 254px | 178 / 236px | 按原型调整 |

两次 UI 展示的导出绝对路径完全一致：

```text
E:\AI_Agent\.runtime\task21\acceptance\exports\ab26b266-94da-49e3-8be3-f08cdf7103ed\20260804205214_64.json
```

7 个主链步骤读数逐项相同；`baseline/projection.json` 与 `after/projection.json` 深比较相同。覆写与 30 步撤销属于主链重跑后的补充检查，独立记录在 after/browser-checks.json；不混入上述 7 步 before/after 对照。

机器核验汇总：`evidence/verification.json`。原始读数：两套 browser-checks.json、backend-evidence.json / backend-main-flow.json、保存的 projection.json。测试日志：baseline-tests.txt / frontend-tests.txt；构建日志：build.txt。

未决项仅 A1 两种按住拖拽手势；没有观察到其他功能回归。隔离页面与临时 HTTP 服务在证据保存后关闭，隔离数据与证据保留，可供后续手测复用。
