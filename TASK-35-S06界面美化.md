# TASK-35 · S06 预处理配方界面美化卡（正式卡）

> **目标**：把 S06 预处理配方页的视觉语言对齐 UI 基线 v2.3 的 S06 段（徽章链、卡片化、参数 hint、真实质量卡），**只改皮、不动筋**。界面上出现的每一个数字与说明都必须由现有真实功能或真实后端字段托底；未实现项与假数据一律不展示。
> **前置**：TASK-34 已收口于 `58995b0`（`fix(task34): 草稿判等双侧编译`，恰 2 文件）。需求方手测（载入 `plastic-snv-sg1` v1 → 无「草稿已变更」且「提交 run」可点；w 15→17 → 提示恢复、按钮禁用）由需求方执行，**不设自动门**，但按 §7 顺序**先手测、再动 UI**。
> **事实源**：**UI 基线 = `E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html`（v2.3，S06 段 `:1738-1835`）**；用户本轮 @ 的 `10月15日/` 副本是 **v2.2 归档，不得作为基线**（项目红线，TASK-25 §0 已立，第三方草稿所写「1722-1815」为归档副本行号，**出卡与验收一律按 v2.3 重取**）。需求 v2.7；代码基线 HEAD `58995b0`。
> **卡型**：**正式卡**。判据：改动 5 个文件（`PreprocessPanel.tsx` / `PipelineEditor.tsx` / `CompareChart.tsx` / `preprocess.css` / `preprocess-skin.css`），超轻量卡 2 文件上限；纯前端、**零契约、无后端、无 DDL、无 openapi、无 Rust、无数据库改动**。
> **三道闸门**：① 开工 `git status` 对照 §0.1 的 **15 项快照**（工作区本来就不干净，不是要求空）；② 开工复跑 §0.1 当前基线并贴原文；③ 开工 `grep -n` 复核 §0.2 全部锚点与 §0.3 全部 pin。
> **即停条款**：行号与实物不符须在回报中显式说明，不得自行改写本卡；卡内未写死的口径一律停下问，不许自造。

---

## 0. 事实底座（2026-11-07 14:37 备卡方实测）

### 0.1 基线

| 项 | 实测值 | 取数命令 |
|---|---|---|
| HEAD / 工作区 | `58995b0` / **15 项**：14 个 `artifacts/step2/*` 噪声（行尾变化，656+/656-）+ 1 个未跟踪 `docs/AI自动标注路由分析.md`，**两者禁触碰、禁提交** | `git log -1 --oneline`；`git status --short` |
| 前端（源码口径） | **270 / 270 pass，fail 0** | `node --test "src/**/*.test.ts"`（禁裸跑） |
| 类型检查 | **EXIT=0** | `npx tsc --noEmit` |
| 五个目标文件行数 | 200 / 62 / 58 / 22 / 30 | `wc -l src/components/preprocess/{PreprocessPanel.tsx,PipelineEditor.tsx,CompareChart.tsx,preprocess.css,preprocess-skin.css}` |

> 收口时 `git status` 对照 **开工 15 项快照**：仅 §4 目标文件为新增 M，噪声与 docs 零变化、未提交。历史 `241 / 269 / 270` 均为各时点溯源值，不作跨卡阈值。

### 0.2 行号锚点（全部 `grep -n` 直取；按 HEAD `58995b0`）

| 事实 | 路径:行 | 要点 |
|---|---|---|
| **UI 基线 S06 起点** | `E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html:1738` | `<!-- S06 预处理配方 -->`；副标题 `:1743`、算子链卡 `:1749-1761`、参数卡 `:1765-1780`、作用范围 `:1782-1788`、配方信息 `:1790-1797`、对比/质量卡 `:1801-1832`、Kappa 表 `:1821-1830` |
| 页头 / 头部按钮 | `src/components/preprocess/PreprocessPanel.tsx:144-145` | `<section className="preprocess-panel">` / `<header>`（现为「返回数据集」+ `h2` + 项目名） |
| 配方库侧栏 | `PreprocessPanel.tsx:147-148` | 「配方库（按 code）」 + 载入按钮 |
| 保存按钮 | `PreprocessPanel.tsx:163-164` | 「保存为新配方」/「保存为新版本」 |
| 算子链编辑器 | `PreprocessPanel.tsx:166`；`src/components/preprocess/PipelineEditor.tsx:32-47` | `<PipelineEditor …>`；`legend 算子链 · v1`（**写死，见 §8 挂账**）/ 添加一步 `:35` / 上移 `:42` / 下移 `:43` / 删除 `:44` / SG 参数 `:46-47` |
| 草稿守卫与提交 | `PreprocessPanel.tsx:169-170` | 「先在 S05 标注并保存」/「草稿已变更」/「提交 run」禁用条件（TASK-34 双侧编译在 `:113-119`） |
| run / report / 对比 | `PreprocessPanel.tsx:177 / :185 / :190-195` | run 详情 / `<CompareChart report={report}>` / `comparison.ranking.map`、boundaries、selection |
| 指标卡（现状） | `PreprocessPanel.tsx:14-25` | `MetricsView`：`snr` 全字段 + `snr_nan_count` / `nan_spectra_skipped` / `interclass_distance` / `intraclass_variance` / `fisher` + `excluded_classes` + `boundaries` / `limitations` + `source` / `variance_definition` |
| 对比图 | `src/components/preprocess/CompareChart.tsx:52` | `<section aria-label="处理前后对比图">` + `h3`（按类 / 「未标注：整体均值」）；`:27` 轴标签 `band index` |
| 现有美化层 | `src/components/preprocess/preprocess-skin.css:1-30` | **已存在一层原型色系皮肤**（卡片、按钮、表格、focus），本次是「补齐视觉语言」不是从零造皮；`PreprocessPanel.tsx:11-12` 同时 import `preprocess.css` 与 `preprocess-skin.css` |
| 真实字段类型 | `src/components/preprocess/types.ts:15-18 / :26-34 / :39` | `Metrics` / `Ranking` / `CompareResult` / `Report.reproducibility_assertion: string` |
| 后端指标来源 | `src-python/spectrumagent/preprocess/compare.py:32 / :45-48 / :65-81 / :86-89` | `x.mean()/rms` 线性比值；`snr {mean,median,p10,p90,n_pixels}`；`fisher` 与 `fisher_components`；Fisher 主排序 |
| 复现断言 | `src-python/spectrumagent/preprocess/run.py:371`；`src-python/tests/preprocess/test_run.py:395` | `report.json` 写入 `reproducibility_assertion` 原文并有断言 |
| 配方哈希 | `src-python/spectrumagent/preprocess/recipes.py:87-124`；`src-python/spectrumagent/preprocess/export.py:252` | `recipe_pipeline_hash` 表 / `recipe_pipeline_sha256` / `recipe_hash_alg` / manifest |
| 配方引用范围 | `src-python/spectrumagent/preprocess/compare.py:88`；`src-python/spectrumagent/modeling/inference.py:178-180` | 建模、批量推理**真实引用**；`src/screens/S10.tsx` 与 `src/components/search/` **无任何 recipe 引用**（检索仍占位） |
| **源码 pin 位置** | `src/components/preprocess/panel.test.ts:50-64 / :68-74 / :84-90 / :122` | 见 §0.3 全清单 |

### 0.3 源码 pin 全清单（`panel.test.ts`，改皮时**位移可以、字面不能变**）

**A 组 · 必须保留（`assert.match`，字符串或代码模式）**

| 行 | 字面 |
|---|---|
| `:53` | `projects.find(`、`annotations.versions(record.id)` |
| `:54` | `先在 S05 标注并保存`、`disabled={!annotationVersion` |
| `:55` | `任务可能已完成`、`submitRun(preprocessing`、`refresh最近|刷新最近` |
| `:56` | `preprocessing.addVersion` |
| `:57` | `comparison.ranking.map` |
| `:58` | `metrics.boundaries`、`metrics.limitations`、`comparison.selection` |
| `:59` | `step.meta.variance_definition`、`分量重构能量占比` |
| `:60` | `未标注：整体均值`、`curveRuns(values)`、`band index`（在 `CompareChart.tsx`） |
| `:61` | `无波长轴，crop/resample 禁用`、`生成目标轴`（在 `PipelineEditor.tsx`） |
| `:62-63` | `<PreprocessPanel`（`App.tsx`）、`onOpen('s06', record)`（`DatasetPanel.tsx`） |
| `:69-73` | `显式导出 ENVI`、`preprocessing.exportRun(run.id)`、`disabled={busy \|\| run.status !== 'succeeded'}`、`item.kind === 'processed_cube'`、`item.relative_path` |
| `:89-90` | `runId={report?.run_id ?? run.id} steps={report?.steps}`、`runId={row.id}` |

**B 组 · 禁止出现（`assert.doesNotMatch`）** —— 比 A 组更容易在美化时翻车

| 行 | 禁止 |
|---|---|
| `:52` | 三个目标文件内出现 `fetch(` / `invoke(` / `http://` |
| `:56` | `.updateRecipe` / `.deleteRecipe` |
| `:57` | `ranking.sort` / `fisher\s*[:=]\s*\w+\s*/` |
| `:64` | **`preprocess.css` 内 `position:fixed` / `100vh` / `z-index`** |
| `:74` | `getArtifact(...'processed_cube'` / `body_base64` / `createObjectURL` |
| `:122` | `JSON.stringify(currentVersion?.pipeline)`（TASK-34 防回退 pin） |

> **纪律**：新增样式优先放 `preprocess-skin.css`（pin 只查 `preprocess.css`），但**不得钻这个空子**——皮肤文件同样禁止 `position:fixed` / `100vh` / `z-index`，卡片化只用常规文档流布局。A 组字符串**可移位、不可删改**；B 组一条都不许踩。若确需修改任一断言 → **即停上报**，不得删改既有断言凑绿。

### 0.4 真实字段托底表（「界面中都要是实际的东西」的判据）

| 想要展示 | 真实来源 | 口径 |
|---|---|---|
| SNR 均值 / 中位数 / P10 / P90 / 像素数 | `Metrics.snr`（`types.ts:15`；`compare.py:45-48`） | **线性比值 `谱均值/相邻波段一阶差分 RMS`，不是 dB**；v2.3 `:1811` 原型自己写明「不使用dB口径」 |
| Fisher / 类间距离 / 类内方差 | `Metrics.fisher` / `interclass_distance` / `intraclass_variance`（`types.ts:16-17`；`compare.py:72-79`） | 无标签时后端置 `null` 并写 `limitations`，界面显示「不适用」，**禁造数** |
| 排除类 / 边界 / 局限 | `excluded_classes` / `boundaries` / `limitations`（`types.ts:17-18`） | 已由 `MetricsView` 渲染，重排即可 |
| 链路可复现说明 | `Report.reproducibility_assertion`（`types.ts:39`；`run.py:371`） | **取字段原文**（可截断显示），不得手写「✓ 配方哈希+数据集哈希+算子版本」当事实 |
| 配方哈希 | `recipe_pipeline_sha256` / `recipe_hash_alg`（`recipes.py:112-124`） | 仅在确有值时显示；无值不显示占位数字 |
| 保存后可引用范围 | 建模 `compare.py:88`、批量推理 `inference.py:178-180` | **只能写「建模与批量推理」；「检索」未实现，禁止出现** |

---

## 1. 范围与明确不做

**本卡做**：纯视觉重排 + 真实数据卡片化，5 个前端文件（允许第 6 个 `panel.test.ts` **仅追加**防假数据断言，见 §5 G1）。

**明确不做**（越界即停）：
- 任何交互逻辑、按钮功能、状态判定、草稿守卫、提交/导出/恢复流程的变化；
- 后端 / API / DDL / openapi / Rust / 数据库 / `pipeline.ts` / `types.ts` / `api.ts` 的任何改动；
- 新增算子（MSC / EMSC）、拖拽排序、单步预览、坏波段剔除、去背景、ROI、Kappa 聚合——全部阶段二；
- 修 `PipelineEditor.tsx:32` 的「算子链 · v1」写死 legend（TASK-34 §8 已挂账，**不得顺手带**）；
- 触碰工作区 14 个 `artifacts/step2/*` 噪声与未跟踪 `docs/AI自动标注路由分析.md`。

## 2. 三条核心口径（不得自行改写）

1. **交互零变化**：所有按钮的 `onClick`、`disabled` 条件、状态渲染、消息文案逻辑原样保留；只调整 DOM 结构、CSS 类、卡片容器与说明文案（非状态类）。
2. **只展示真实**：任何数字来自 §0.4 的真实字段且 `null` 时显示「不适用」；任何说明只描述已实现能力；未实现项与示例数值一律不进界面。
3. **pin 全保留**：§0.3 A/B 两组逐条通过；字符串位移可以，字面与禁止模式一条不动。

---

## 3. 逐项改造

### 3.1 能做（原型样式 × 真实功能/真实数据）

| # | 原型元素（v2.3 行） | 现有真实支撑 | 做法 |
|---|---|---|---|
| M1 | 页头副标题「算子链一旦保存即成为可复用资产…」`:1743` | 配方版本不可变 + 哈希（TASK-30） | 在 `:145` header 下加一行说明，**照抄原型文案** |
| M2 | 头部「载入已有配方 / 保存配方」按钮位 `:1745-1746` | `:147-149` 载入、`:163-164` 两个保存 | 只做布局对位与视觉层级（主按钮高亮），**按钮数量/文案/功能不变**（不新增第三个「保存配方」按钮） |
| M3 | 算子链药丸徽章横排 + 箭头 + 虚线「＋添加算子」`:1749-1761` | `PipelineEditor.tsx:32-47` 的 `ol/li` 与「添加一步」 | 把 `li` 渲染成徽章横排 + `→` 连接；**参数摘要从真实 `step.params` 生成**（如 `w15, p2, d1`），无参数不显示括号；上移/下移/删除保留为徽章内小操作；虚线加号只是 `:35`「添加一步」按钮的视觉样式，`:33` `<select aria-label="添加算子">` 与 `:35` 按钮的 `onClick` 及「添加一步」字面**零改动** |
| M4 | 参数卡「ⅲ SG 一阶导 · 参数」+ hint `:1765-1780` | `PipelineEditor.tsx:46-47` 的 window/polyorder/mode/order | 卡片化 + 参数说明。**hint 用通用真实文案**：「窗口越大越平滑，但会钝化窄特征」；**删掉原型的「1724 nm 附近」场景示例**（用户要求不展示无出处场景）；`p` 的「2（推荐）」/ `d` 的「1（一阶导，消除基线平移）」可作为选项文案，但选项值与逻辑零变化 |
| M5 | 配方信息卡 + 等宽 code + hint `:1790-1797` | `:163-164` 保存、`Recipe.code` | 卡片化，code 用等宽字体。**hint 写「保存后可在建模与批量推理中引用；配方快照随每次实验一并落库」——删「与检索」**（§0.4 已核检索未实现） |
| M6 | 处理前后对比卡标题 `:1801` 区 | `CompareChart.tsx:52` | 只改标题布局（上：原始反射率 / 下：处理后），`h3` 的「未标注：整体均值」等 pin 字符串保留 |
| M7 | 逐像素指标卡真实版 `:1808-1819` | `MetricsView`（`:14-25`）全字段 | 重排为「大数字 = `metrics.snr.mean`（**比值，不标 dB**）+ 列表 = median/p10/p90、`fisher`、类间距离、类内方差、`n_pixels`」；`null` → 「不适用」；`boundaries`/`limitations`/`excluded_classes`/`source`/`variance_definition` 全部保留展示；底部若有 `report` 则显示 **`report.reproducibility_assertion` 原文**（可截断），无 report 不显示该行。**约束**：`panel.test.ts:89-90` 已 pin `MetricsView` 调用处字面 `runId={report?.run_id ?? run.id} steps={report?.steps}` 与 `runId={row.id}`——复现断言须**另起一行渲染，不改 `MetricsView` 签名、不动这两处调用** |
| M8 | 复现口径说明 `:1818` | `compare.py:10` 等真实边界 | 可做成卡片脚注，用 `metrics.boundaries` / `limitations` 的**真实字符串**，禁手写结论 |
| M9 | 同输入多配方对比 `:1802-1804` | `:190-195` `comparison.ranking` / `runs` | 卡片化表格；`ranking` 按后端返回顺序渲染（pin 禁 `ranking.sort`）；无有效 Fisher 时显示 `comparison.selection` 与 boundaries，不排名、不造数 |

### 3.2 不展示（原型有，但未实现或为假数据）

| 原型元素 | 行 | 不展示理由 |
|---|---|---|
| 「已选类别：PP / PET / PS / ABS」 | `:1759` | 真实 label codes 有（`classLegend` / `excluded_classes`），但「已选」暗示可筛选，筛选未实现。**本卡不展示**；若要展示须另出卡定口径为「当前标注类别（只读）」 |
| 作用范围三复选框（坏波段/去背景/ROI）+ hint | `:1782-1788` | 全部阶段二未实现；「2 个坏波段」为示例数 |
| 「按顺序执行 · 可拖拽调整 · 每一步都可单独预览」 | `:1750` | 拖拽与单步预览未实现；**保留按钮式上移/下移**，副标题只写「按顺序执行」（可用真实文案） |
| 「18.6 dB」/「基线漂移已消除」/「1140·1660·1724 nm 峰位未偏移」/「第 61/188 号波段已剔除」 | `:1810-1816` | 假数据；且 SNR 后端是线性比值不是 dB |
| 历史 Kappa 表（0.921 / 0.874 / 0.812） | `:1821-1830` | 无 Kappa 聚合（P1 挂账）；原型自标「阶段二 / 不适用」仍带示例值，按需求方口径不展示 |
| 「未获得数值结果」占位文本 | `:1803 / :1810` | 需求方要求界面都是实际的东西：有真实值显示真实值，无值显示「不适用」，**不照搬占位文案** |
| MSC / EMSC 算子、`＋ 添加算子` 中的未实现项 | — | `OPERATORS` 里没有的不得画出来；虚线加号必须绑定现有「添加一步」 |

---

## 4. 视觉规格与改动清单

| 文件 | 动作 |
|---|---|
| `src/components/preprocess/preprocess-skin.css`（30 行，现有皮肤） | **主要落点**：扩展徽章链、卡片、hint、等宽 code、大数字指标、脚注样式；沿用现有色系变量与 `.preprocess-panel` 前缀；**禁 `position:fixed` / `100vh` / `z-index`** |
| `src/components/preprocess/preprocess.css`（22 行） | 仅在必须调整 grid/spacing 时小改；**B 组 `:64` pin 原样通过** |
| `src/components/preprocess/PipelineEditor.tsx`（62 行） | M3/M4：DOM 重排为徽章链 + 参数卡；`legend` 字面不动（挂账） |
| `src/components/preprocess/PreprocessPanel.tsx`（200 行） | M1/M2/M5/M7/M9：header 副标题、卡片容器、指标卡重排、复现断言展示；交互与所有 pin 字面零变化 |
| `src/components/preprocess/CompareChart.tsx`（58 行） | M6：标题布局；`:52` 的 `h3` pin 字符串保留 |
| `panel.test.ts`（**可选第 6 文件**） | 仅**追加**防假数据断言（见 G1），既有断言零改动 |

**布局原则**：沿用 `preprocess-skin.css:4` 的 `236px minmax(0,1fr)` 两栏；卡片用常规文档流（`grid`/`flex`），不做浮层/吸顶；移动端不新增断点（本卡不承诺响应式）。

---

## 5. 验收门（每条带取数命令，禁自报数不带模式）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 | `node --test "src/**/*.test.ts"` | **270+新增 / 270+新增 pass / 0 fail**（开工基线 270/270/0 于 `58995b0` 实测）；既有用例零变红、零删改。若追加防假数据断言，建议 3 条：`doesNotMatch(面板源码, /18\.6\s*dB|1724\s*nm|0\.921|已选类别/)`、`doesNotMatch(面板源码, /检索中直接引用|与检索/)`、`doesNotMatch(皮肤 css, /position:\s*fixed\|100vh\|z-index/)` |
| G2 | `npx tsc --noEmit` | **EXIT=0** |
| G3 | 收工 `git status --short` 对照开工 15 项快照 | 仅 §4 清单内文件为新增 M；14 噪声 + 1 docs **零变化、未提交**；`git diff --cached --name-only` 提交时须恰为清单文件 |
| G4 | §0.3 A/B 两组 pin 逐条人工走查 + 需求方手测截图 | 全部 pass；手测走查：S06 载入配方 → 徽章链参数摘要与真实 steps 一致 → 参数 hint 不含场景假数据 → 指标卡显示真实 SNR（**无 dB 字样**）→ 未实现项（作用范围 / 类别 / Kappa / 拖拽 / 单步预览）均不出现 → 所有按钮行为与改造前一致 |

**不自指要求**：G1 的新断言须写明「什么情况下会红」；禁止用「断言源码里出现某个类名」这类自我证明的用例。

---

## 6. 红线

1. **交互零变化**：任何 `onClick` / `disabled` / 状态渲染逻辑改动即停；TASK-34 的 `changed` 双侧编译判定（`:113-119`）与「草稿已变更」守卫零改动。
2. **零契约**：后端 / Rust / DDL / openapi / `pipeline.ts` / `types.ts` / `api.ts` 一行不动；不新增 IPC、不新增工具、不新增接口。
3. **不展示假数据**：dB、1724 nm 峰位、Kappa 示例值、坏波段编号、「已选类别」、占位「未获得数值结果」一律不进界面；`null` 显示「不适用」。
4. **基线只用 v2.3**：`10月15日/` 归档副本不得作为实现依据；卡内外引用 S06 一律按 `:1738-1835`。
5. **pin 不可破**：§0.3 A/B 两组逐条保留；删改既有断言凑绿 → 即停。
6. **禁触碰噪声**：14 个 `artifacts/step2/*` 与 `docs/AI自动标注路由分析.md` 不读改、不提交；**逐文件提交，禁 `git add -A` / `git add .`**。
7. **挂账不带**：`PipelineEditor.tsx:32` 的「算子链 · v1」写死 legend 属 TASK-34 §8 挂账，本卡不得顺手修。
8. **行号与实物不符须在回报中显式说明，不得自行改写本卡。**

---

## 7. 交付与提交顺序

1. 需求方先完成 TASK-34 手测（§ 前置），确认主路径通；
2. 执行方按闸门①②③开工，**一次一段**（建议 M3/M4 → M1/M2/M5 → M7/M9 → M6），每段贴 pin 走查与 `node --test` 原文；
3. 收口按 G1–G4 全绿后，**逐文件提交**，提交信息建议 `feat(ui): S06 预处理配方界面按 v2.3 美化（真实数据卡片化）`；
4. 回报格式沿用 TASK-23/24/34：改动文件清单、每条验收的取数命令与原文输出、未决项、遗留债；
5. **本卡不代发提示词、不 push**；发布动作按项目流程由负责人执行。

## 8. 遗留债（本卡不做，不在授权面内）

| # | 债 | 处置 |
|---|---|---|
| D1 | 「算子链 · v1」legend 写死（`PipelineEditor.tsx:32`） | TASK-34 §8 已挂账，另立轻量项 |
| D2 | 拖拽排序 / 单步预览 / 作用范围三复选框 / MSC·EMSC | 阶段二，另立卡 |
| D3 | 历史 Kappa 聚合 | P1 挂账，无后端聚合 |
| D4 | 检索（S10）引用配方 | 未实现；本卡已从 hint 中剔除，待 S10 卡落地后再补文案 |
| D5 | 「当前标注类别」展示口径 | 需拍板是否只读展示，本卡不展示 |
| D6 | 工作区 14 个 step2 噪声 + 1 个未跟踪 docs | 非本卡产物，禁触碰；由负责人另行处置 |

---

## 9. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-07 14:37 | **初版（正式卡）**：按需求方「出 UI 卡」指令起草。事实源锁定 **v2.3 根目录基线**（S06 `:1738-1835`），排除用户 @ 的 v2.2 归档；核实 TASK-34 已于 `58995b0` 收口（270/270/0、tsc 0、工作区 15 项）；§0.3 列全 A/B 两组源码 pin（含第三方草稿漏列的「禁止类」断言）；§0.4 钉死真实字段与三条修正：**hint 删「与检索」**（检索无 recipe 引用）、**SNR 为线性比值不标 dB**（`compare.py:32`、v2.3 `:1811`）、**复现说明取 `reproducibility_assertion` 字段原文**；§3 分「能做 / 不展示」两表，§5 设 G1–G4 与手测走查截图。卡入库后按顺序交执行方，需求方手测先行。 |
