# TASK-22 · P4 S06 / S07 换皮回报

依据用户本地修订后的 TASK-22 卡执行，A1–A9 全部通过。产品源码恰好四份，未提交 Git。

执行模式：Windows PowerShell；Node 原生 TypeScript 测试；`npm run build`（`tsc --noEmit && vite build`）；生产构建 + IAB + 本地真实 FastAPI 验收桥。前后均使用仓库既有 regression_factory 的同一套隔离 seed（12 个合成回归样品、标注快照、ready 预处理输入），配方保存、新预处理/对比、PLS 训练及结果读取均由真实后端执行。引擎 Ready 和目录选择是受控 IPC。未访问正式标注库；未运行原生 Tauri/Rust 或 Python 全套测试。

开工三闸门已在修改前通过：工作区干净；`5f9f04b..5d65914` 只有任务卡文档；Node 215/215/0；原锚点及用户修订后新增锚点全部吻合。中途发现的 S07 单列/300px 判据冲突已按即停条款上报，再按用户明确授权的 CSS 两栏方案继续。用户未提交的任务卡与断言盘点表修订均保留，未由本次实现改写。

## 1) 逐文件改动（四份产品源码）

| 文件 | 改动 |
|---|---|
| `src/components/preprocess/preprocess-skin.css` | 新增；28 条带 `.preprocess-panel` 前缀的选择器；S06 左栏 236px，卡片、表单、按钮、指标、对比表格密度与配色 |
| `src/components/modeling/modeling-skin.css` | 新增；22 条全部以 `.model-panel[aria-label="PLS 回归工作台"]` 开头；300px 两栏、四类顶部节点跨列、表单全宽及训练页皮肤；不写断点 |
| `src/components/preprocess/PreprocessPanel.tsx` | 原 :11 CSS import 后仅增加一行 import |
| `src/components/modeling/ModelPanel.tsx` | 原 :10 CSS import 后仅增加一行 import |

现有两个 CSS、所有测试、App、DatasetPanel、annotation、AppShell、.p-body、后端、Rust、依赖均零改动。`milestone22/` 是任务要求的回报/截图/基线证据，不是第五份产品源码。辅助验收脚本仅在 Git 忽略的 `.runtime/task22/`。

## 2) 两份 TSX 完整 diff

```diff
diff --git a/src/components/preprocess/PreprocessPanel.tsx b/src/components/preprocess/PreprocessPanel.tsx
index 33ee5e8..93d24e8 100644
--- a/src/components/preprocess/PreprocessPanel.tsx
+++ b/src/components/preprocess/PreprocessPanel.tsx
@@ -9,6 +9,7 @@ import { describePreprocessError, PHASE_TWO, type CompareResult, type Metrics, t
 import CompareChart from './CompareChart';
 import PipelineEditor from './PipelineEditor';
 import './preprocess.css';
+import './preprocess-skin.css';
 
 function MetricsView({ metrics }: { metrics: Metrics }) {
   return <section aria-label="后端指标"><h3>后端逐像素指标</h3><dl className="pp-metrics">
```

```diff
diff --git a/src/components/modeling/ModelPanel.tsx b/src/components/modeling/ModelPanel.tsx
index e3f1e83..0f9c225 100644
--- a/src/components/modeling/ModelPanel.tsx
+++ b/src/components/modeling/ModelPanel.tsx
@@ -8,6 +8,7 @@ import { modeling, type ImportResult, type Target } from './api.ts';
 import RegistryPanel from './RegistryPanel.tsx';
 import InferencePanel from './InferencePanel.tsx';
 import './modeling.css';
+import './modeling-skin.css';
 
 export default function ModelPanel({ records, onClose, onOpenResults }: { records: DatasetRecord[]; onClose(): void; onOpenResults(run: string): void }) {
   const [view, setView] = useState<'training' | 'registry' | 'inference'>('training');
```

机器比对：分别移除新增 import 后，文件内容与 HEAD 完全一致（规范化换行符）；新增 import 紧跟原 CSS import。原 JSX、className、文案、aria-label、字段/节点顺序及事件逻辑全部保留。

## 3) A1–A9

| 验收 | 结果 | 证据 |
|---|---|---|
| A1 S06 功能 | 通过 | 前后均载入 regression-fixture、保存 v2、提交 succeeded、对比成功、点击对比 run 读图、刷新/点击历史；version_no、pipeline、预处理 metrics 与曲线数据逐项一致 |
| A2 S07 功能 | 通过 | 两轮同请求训练 succeeded；selected_lv=3、RMSEC=0.3877278749721029；S08 自取 runId 各自等于训练返回；模型注册/批量推理视图可进入并返回 |
| A3 机器门 | 通过 | 两份新 skin 禁则均 0；各自 !important 均 0；裸 model-panel 作用域扫描 0 行；28/28 与 22/22 选择器前缀正确 |
| A4 改动面 | 通过 | 产品源码 = 2 新 CSS + 2 TSX 各一行 import，共 4；未修改其他产品文件 |
| A5 零同步 | 通过 | src/components/preprocess/panel.test.ts 零 diff，字节 SHA256 与基线一致；15 行 / 27 次源码断言保留；全套测试绿 |
| A6 视觉/布局 | 通过 | S06 左栏实测 236px（原型 :1748）；S07 左栏实测 300px（原型 :1833），右栏随窗口变化；两种尺寸文档与控件均不横向溢出，详见下表 |
| A7 构建 | 通过 | `npm run build` 含 tsc --noEmit 成功；Vite 83 modules |
| A8 基线测试 | 通过 | 开工 215/215/0；最终原有 215 全过 + 新增 N=0 = 215 tests / 215 pass / 0 fail；cancelled/skipped/todo 均 0。新增测试清单：无 |
| A9 越界探测 | 通过 | src/components/preprocess/panel.test.ts:61 的 `<PreprocessPanel` 与 :62 的 `onOpen('s06', record)` 保持绿；App、DatasetPanel、测试文件均未改 |

A6 测量采用 tauri.conf.json:13 的默认/最小窗口尺寸；栏宽目标与 gap 出处分别为原型 :1748/:1833、preprocess.css:4。

| 视口 | S07 左栏 | S07 右栏（实测自适应） | document.scrollWidth / clientWidth | 控件越界数 |
|---|---:|---:|---|---:|
| 1280×820 | 300px | 676.6667px | 1280 / 1280 | 0 |
| 1180×720 | 300px | 576.6667px | 1180 / 1180 | 0 |

两块 fieldset 的 scrollWidth 均等于各自 clientWidth；header/nav/p 实测跨列 `1 / -1`，pre 分支的同规则静态核验通过。max-width 仍 76rem（实测 1216px），原 padding/margin 保留。scope 实测另外七个宿主均不匹配，均保持 display:block、16px、rgb(34,34,34)；记录在 after/shared-hosts.json。

**内容映射按新卡裁定**：左栏是现有“样品连续量”，右栏是现有“训练配置”。原型 :1833 的左栏是“任务/划分与超参”，二者内容不一一对应；本批只验证宽度、右栏自适应和不溢出，没有增加原型中的假预检、假进度或新表单。S06 按更新后的严格 A6 采用固定 236px，没有继续沿用旧 190–240px 区间。

## 4) A3 两条禁则实际输出

使用 rg 执行等价 grep，分别扫描新文件。以下每条标准输出均为一行 `0`，计数 0（rg 无匹配 exit=1 是正常语义）。原始记录见 evidence/grep-report.json。

```powershell
rg --count --include-zero -e 'position:\s*fixed|100vh|z-index' src/components/preprocess/preprocess-skin.css
0
rg --count --include-zero -e 'position:\s*fixed|100vh|z-index' src/components/modeling/modeling-skin.css
0
rg --count --include-zero -e '!important' src/components/preprocess/preprocess-skin.css
0
rg --count --include-zero -e '!important' src/components/modeling/modeling-skin.css
0
```

两条门的依据不同：S06 延续 src/components/preprocess/panel.test.ts:63 对旧 preprocess.css 的意图约束，自备新文件扫描；S07 没有源码断言依据，按卡保持纪律一致性。

作用域附加门（PCRE2 用于兼容用户给定的 `[^[]` 模式）：

```powershell
rg --pcre2 -n '^\s*\.model-panel[^[]' src/components/modeling/modeling-skin.css
```

实际标准输出为空，匹配行数 0。两份 skin 均未声明变量、未引用 theme.css 变量，未写 @media。

## 5) panel.test.ts 是否零改动

是。`git diff -- src/components/preprocess/panel.test.ts` 标准输出为空；字节 SHA256：

```text
5f481501725e3edc05d5a9d092395aabaca25b658e9a53953f9d157d608c751b
```

与修改前 baseline/summary.json 完全一致。所有既有测试均未删、改、合并。`src/components/preprocess/api.test.ts`（明确目录）也未改；没有把另外四个同名 api.test.ts 当作本屏断言来源。

## 6) 两份 skin 的选择器清单

S06 共 28 条分组后的独立选择器：

| 选择器全文 | 前缀正确 | 目标规则/元素 |
|---|---|---|
| `.preprocess-panel` | 是 | preprocess.css:1；根容器配色、正文密度 |
| `.preprocess-panel .pp-layout` | 是 | preprocess.css:4；左栏改为原型 :1748 的 236px |
| `.preprocess-panel h2` | 是 | preprocess.css:3；屏标题字号与色彩 |
| `.preprocess-panel h3` | 是 | 现有配方库/指标标题；原型 :237 的卡标题字号 |
| `.preprocess-panel legend` | 是 | 现有 fieldset 图例；与卡标题协调 |
| `.preprocess-panel .pp-layout aside > section` | 是 | preprocess.css:5；配方卡边线、圆角、内边距 |
| `.preprocess-panel fieldset` | 是 | preprocess.css:7；白底卡片、圆角、内边距、收缩边界 |
| `.preprocess-panel button` | 是 | preprocess.css:10；基础按钮边线、底色与密度 |
| `.preprocess-panel button:hover:not(:disabled)` | 是 | 现有按钮悬停；原型 :228 的品牌弱化色 |
| `.preprocess-panel button:disabled` | 是 | 现有 disabled 状态；原型 :233 的弱化程度 |
| `.preprocess-panel .pp-main > fieldset:first-of-type > button` | 是 | 命名与版本的保存按钮；原型 :229 主按钮层级 |
| `.preprocess-panel .pp-main > fieldset:last-of-type > button:first-of-type` | 是 | 执行与对比的提交 run；原型 :229 主按钮层级 |
| `.preprocess-panel .pp-main > fieldset:first-of-type > button:hover:not(:disabled)` | 是 | 保存按钮悬停；原型 :230 |
| `.preprocess-panel .pp-main > fieldset:last-of-type > button:first-of-type:hover:not(:disabled)` | 是 | 提交 run 悬停；原型 :230 |
| `.preprocess-panel input` | 是 | preprocess.css:10；输入框描边、圆角、文字 |
| `.preprocess-panel select` | 是 | preprocess.css:10；下拉框描边、圆角、文字 |
| `.preprocess-panel input:focus-visible` | 是 | 原有键盘焦点；使用原型品牌色 |
| `.preprocess-panel select:focus-visible` | 是 | 原有键盘焦点；使用原型品牌色 |
| `.preprocess-panel button:focus-visible` | 是 | 原有键盘焦点；使用原型品牌色 |
| `.preprocess-panel input[type=checkbox]` | 是 | 配方对比复选框；清除全局 input 最小宽度/内边距造成的冗余占位 |
| `.preprocess-panel .pp-editor li` | 是 | preprocess.css:12；算子条目的边线与圆角 |
| `.preprocess-panel .pp-main > section` | 是 | 现有 run 详情、CompareChart、配方对比卡片；原型 :235 |
| `.preprocess-panel .pp-metrics div` | 是 | preprocess.css:19；指标卡边线与圆角 |
| `.preprocess-panel .pp-metrics dd` | 是 | preprocess.css:20；指标色与等宽数字 |
| `.preprocess-panel table` | 是 | preprocess.css:21；表格边线合并、左对齐 |
| `.preprocess-panel th` | 是 | 现有对比表头；原型 :266 |
| `.preprocess-panel td` | 是 | 现有对比表单元格；原型 :267 |
| `.preprocess-panel tbody tr:hover` | 是 | 现有对比表行悬停；原型 :269 |

S07 共 22 条，每一条完整保留 aria-label 限定：

| 选择器全文 | 前缀正确 | 目标规则/元素 |
|---|---|---|
| `.model-panel[aria-label="PLS 回归工作台"]` | 是 | modeling.css:1；仅训练页建 300px + minmax(0,1fr) 两栏；保留 padding/max-width/margin |
| `.model-panel[aria-label="PLS 回归工作台"] > header` | 是 | ModelPanel.tsx 原 :50；标题跨两列 |
| `.model-panel[aria-label="PLS 回归工作台"] > nav` | 是 | ModelPanel.tsx 原 :51；建模操作跨两列 |
| `.model-panel[aria-label="PLS 回归工作台"] > p` | 是 | ModelPanel.tsx 原 :52；状态文字跨两列 |
| `.model-panel[aria-label="PLS 回归工作台"] > pre` | 是 | ModelPanel.tsx 原 :52；错误信息跨两列 |
| `.model-panel[aria-label="PLS 回归工作台"] > p:empty` | 是 | 空状态段落的零内容留白，不改节点或条件 |
| `.model-panel[aria-label="PLS 回归工作台"] h2` | 是 | 原有 PLS 回归标题；原型 :221 字号 |
| `.model-panel[aria-label="PLS 回归工作台"] > fieldset` | 是 | modeling.css:3；现有两块表单的卡片外观与收缩边界 |
| `.model-panel[aria-label="PLS 回归工作台"] legend` | 是 | 现有样品连续量/训练配置图例；原型 :237 字号 |
| `.model-panel[aria-label="PLS 回归工作台"] > fieldset label input` | 是 | modeling.css:5；依新卡 §2.5 L3 改块级全宽，清除左偏移 |
| `.model-panel[aria-label="PLS 回归工作台"] > fieldset label select` | 是 | modeling.css:5；依新卡 §2.5 L3 改块级全宽，清除左偏移 |
| `.model-panel[aria-label="PLS 回归工作台"] input` | 是 | 现有训练页输入框；原型 :276–277 |
| `.model-panel[aria-label="PLS 回归工作台"] select` | 是 | 现有训练页下拉框；原型 :283–284 |
| `.model-panel[aria-label="PLS 回归工作台"] input[type=file]` | 是 | ModelPanel.tsx 原 :62 CSV 文件控件；限制在既有 fieldset 内 |
| `.model-panel[aria-label="PLS 回归工作台"] button` | 是 | 现有训练页按钮；原型 :225–226 |
| `.model-panel[aria-label="PLS 回归工作台"] button:hover:not(:disabled)` | 是 | 现有训练页按钮悬停；原型 :228 |
| `.model-panel[aria-label="PLS 回归工作台"] button:disabled` | 是 | 原有 disabled 状态；原型 :233 |
| `.model-panel[aria-label="PLS 回归工作台"] > fieldset:last-of-type > button` | 是 | 原 :77–81 训练 PLS；原型 :229 主按钮 |
| `.model-panel[aria-label="PLS 回归工作台"] > fieldset:last-of-type > button:hover:not(:disabled)` | 是 | 训练主按钮悬停；原型 :230 |
| `.model-panel[aria-label="PLS 回归工作台"] input:focus-visible` | 是 | 现有训练页输入焦点；品牌色 |
| `.model-panel[aria-label="PLS 回归工作台"] select:focus-visible` | 是 | 现有训练页下拉焦点；品牌色 |
| `.model-panel[aria-label="PLS 回归工作台"] button:focus-visible` | 是 | 现有训练页按钮焦点；品牌色 |

尺寸归因：236px/300px → 原型 :1748/:1833；1rem gap → preprocess.css:4；12.4px/16.5px/12.8px 字号 → 原型 :225/:221/:237；按钮 6.5px/13px/7px/1px → :225–226；卡片 14px/16px/9px → :235；表格 8px/11px、7.5px/11px → :266–267；表单 7.5px/10px/7px/100% → :276–284；.35rem 控件上边距 → 新卡 §2.5 L3（原 preprocess.css:10 也有 .35rem 值）；0 为收缩/留白复位（原型 :235–236/:265）；.8rem 段落卡间距 → preprocess.css:7；原 S07 1.25rem/76rem/1rem 容器与 fieldset 值 → modeling.css:1/3，未改。主色、文字和描边参考原型 :9–12；白底/弱化底色沿用原 CSS 或原型 :235/:269，使用直接值、不新建变量层。

## 7) before/after 逐项对照

基线目录：`E:/AI_Agent/milestone22/evidence/baseline/`。

换皮后：`E:/AI_Agent/milestone22/evidence/after/`。

| 卡指定字段 | before | after | 结果 |
|---|---|---|---|
| S06 保存 version_no | 2 | 2 | 一致 |
| S06 run.status | succeeded | succeeded | 一致 |
| CompareResult.runs[].id | 20236539-8cb6-4ff4-b1f0-60ee46ba25ce | 069f5484-09d8-48b0-bf69-d0fb66c05a60 | 各轮真实新运行 |
| 曲线 report.run_id | 20236539-8cb6-4ff4-b1f0-60ee46ba25ce | 069f5484-09d8-48b0-bf69-d0fb66c05a60 | 各自属于同轮 CompareResult.runs |
| S07 Result.status | succeeded | succeeded | 一致 |
| S07 selected_lv | 3 | 3 | 一致 |
| S07 metrics.rmse（UI RMSEC） | 0.3877278749721029 | 0.3877278749721029 | 完全一致 |
| S07 训练返回 run_id | 33c1b773-6bb7-492e-a7f8-3708ee0da773 | f1e3fbd0-edfa-436d-a43c-0d21d8c00b4a | 各轮真实新训练 |
| 跳 S08 后查询的 runId | 33c1b773-6bb7-492e-a7f8-3708ee0da773 | f1e3fbd0-edfa-436d-a43c-0d21d8c00b4a | 各自等于训练返回 |

ID 差异来自从同一 seed 独立重跑后的新版本/新运行 UUID，未伪造为相同 ID。数值与绑定关系分别核验：pipeline、S06 metrics、全部 curves、完整训练请求、全部七个训练 metrics 深比较均一致；不只比较 RMSEC。训练参数为同一 12 个 fixture ready runs、KFold=3、seed=17、测试比例=1/3、手动 LV=3。输入 raw 模式与 seed 均一致。

此夹具只有一个满足 Fisher 条件的前景类，ranking 为空；使用卡允许的 runs[].id，而没有编造 Fisher 排名。前后图表 canvas 均存在，点击的是对应对比 run；曲线由该 run 的 report 自取。

截图：

- baseline/s06-layout.jpg、s06-compare.jpg、s06-history.jpg；after 同名文件。
- baseline/s07-training.jpg、s08-result.jpg、s07-registry.jpg、s07-inference.jpg；after 同名文件。
- after/s07-min-window.jpg；prototype-s06.jpg / prototype-s07.jpg。

![S06 换皮](E:/AI_Agent/milestone22/evidence/after/s06-layout.jpg)

![S07 换皮](E:/AI_Agent/milestone22/evidence/after/s07-training.jpg)

## 8) A9 越界探测

| 源断言 | 目标 | 结果 |
|---|---|---|
| src/components/preprocess/panel.test.ts:61 | App 的 `<PreprocessPanel` | 绿；App 零 diff |
| src/components/preprocess/panel.test.ts:62 | DatasetPanel 的 `onOpen('s06', record)` | 绿；DatasetPanel 零 diff |

原 src/components/preprocess/panel.test.ts:63 旧 CSS 禁则也绿；新 skin 的额外机器门另列于第 4 项，没有弱化测试。

## 9) 行号漂移与口径说明

行号漂移：**无**。开工锚点和用户更新后的 8 个宿主、两个 fieldset、跨列节点、窗口配置、原型行号均与实物匹配。新增 import 后组件后续行自然 +1，不回写开工锚点。

此前 S07 单列与 A6 左栏要求的冲突由用户本地更新卡裁定：允许严格作用域的 CSS 两栏。本轮按新卡实现，未自行改写卡。卡里 S06 “可不改 236”的旧可选说明，与更新 A6 的 236px 要求并存；选择卡已允许、且满足新 A6 的固定 236px（出处 :1748）。无其他冲突或未决问题。

用户未提交的任务卡/盘点表改动不属于本次四份产品源码计数，并已原样保留。初始干净闸门的记录保留在 baseline/summary.json，没有把用户明确授权继续后的文档修订误当作重新开工失败。

汇总证据：evidence/verification.json；测试：evidence/frontend-tests.txt；构建：evidence/build.txt；原始接口与 DOM：baseline/backend.json、after/backend.json、两套 browser-checks.json；范围与禁则：两份 .diff、selectors.json、grep-report.json。浏览器控制台 warn/error=0，接口请求均成功（含保存版本的 HTTP 201）。

临时页面、视口覆盖和本地服务在证据保存后清理；隔离 seed/数据及证据保留。未决问题：无。
