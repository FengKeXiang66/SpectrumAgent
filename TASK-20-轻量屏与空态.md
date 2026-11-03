# TASK-20 · 轻量屏与空态（P5）

> 目标：把剩下四个占位屏变成有内容但不过度承诺的屏——**S02 工作台 / S09 实验台账 / S10 检索空态 / S11 设置入口**。
> 做完这批，11 个屏全部非占位，P6 的屏清单冒烟才是满配。
> 前置：TASK-19（P2 拆屏）已收口。
> **三道闸门**：① `git status` 干净，且 `git diff --stat 82097da HEAD` 不含 `src/` 与 `src-tauri/` 文件；② 基线 **209/209/0**；③ 开工第一步 grep 复核本卡行号，漂移即停上报。

---

## 0. 已核实事实

| 事实 | 位置 |
|---|---|
| 屏 switch 里 **s02 / s09 / s10 / s11 没有 case**，全部落到 `default` 占位屏 | `App.tsx:198` |
| `modeling.runs()` → `{id, task, status}[]`——**无时间戳** | `modeling/api.ts:51` |
| `modeling.run(id)` → `Result`：`run_id` / `status` / `n_samples` / `n_pixels_used` / `selected_lv` / `best_lv` / `metrics` / `quality_label` / `leak_report` / `error`——**同样无 `created_at`** | `modeling/api.ts:8-10` |
| `preprocess.listRuns(dataset_id)` → `RunSummary[]`，**有 `created_at` / `finished_at`**，但**按 dataset 查询** | `preprocess/types.ts:22`、`types.ts:50` |
| `records`（已登记数据集）与 `status`（引擎快照）都在 App 层 | P0 已提升 |
| App.tsx 三锚：`<PreprocessPanel`（`panel.test.ts:61`）、`<Composer`（`working.test.ts:94`）、设置三段字面量（`SettingsPanel.test.ts:185-187`） | — |
| `DatasetPanel` 的 `onOpen('s06', record)` 断言 | `panel.test.ts:62` |

---

## 1. 范围裁定

### 1.1 做

- S02 工作台：数据集计数 + 最近回归运行 + 引擎状态 + 快捷入口
- S09 台账：回归运行列表（全局）+ 详情自取；预处理运行（按所选数据集）
- S10 检索：正式空态 + 主行动按钮
- S11：设置入口（打开现有 modal）+ 出域记录说明
- 新增静态测试（另计，逐条列名）

### 1.2 不做（红线）

- **不编后端没有的字段**：回归侧无时间戳 → 台账不出现时间列；S09 的筛选器只做客户端 `task` 过滤，不做项目/配方/Kappa
- 不做全局预处理聚合（`listRuns` 按 dataset 查询，全局要 N 次调用）——改为"选中数据集后显示其运行"
- 不碰 `src/components/annotation/`
- 不引依赖；不换皮（不引 `theme.css` 变量）
- 不改后端、不改 Rust、不动 `AppShell` / `.p-body` / 引擎三态
- S11 的 modal→全屏改造留 P6

---

## 2. 口径钉死

### 2.1 S02 工作台

四张卡，全部用现成数据：

| 卡 | 内容 | 数据源 |
|---|---|---|
| 数据集 | `records.length` 个已登记；点「查看全部」→ `openScreen('s03')` | App `records` |
| 回归运行 | 总数 + 最近 3 条（`id` 前 8 位 + `status`）；点某条 → `openScreen('s08', undefined, id)` | `modeling.runs()` 过滤 `regression` |
| 引擎 | **精简版**：`status.phase`（中文相位）+ `generation_id`。**不显示 `pid` / `port`** | App `status` |
| 快捷 | 「继续标注」→ `openScreen('s05')`（无选中时由 `openScreen` 的回退逻辑取 `workspace.cube_id`） | — |

**不做**：标注像素统计、纯度聚合、批次进度——都没有 API，渲染即假数据。

**与 S03 调试行的分工（裁定）**：`pid` / `port` / `generation_id` 现在显示在 S03 屏顶的调试行（`App.tsx:168` 一带）。S02 的引擎卡只做精简版（相位 + 代次），**`pid`/`port` 不重复展示**；S03 的调试行**保持原样**——本卡不动 S03，那行属 P3 换皮范围。两处并存不算冲突，但同一信息不叠两遍。

### 2.2 S09 台账（两层）

**第一层 · 回归运行（全局）**

- 列：`id` 前 8 位 / `task` / `status`。**没有时间列**——`runs()` 与 `Result` 都不返回时间戳，写"未知"或干脆不设该列，**不得用当前时间填充**
- 客户端筛选：`全部 / 回归`（`task` 字段过滤）；原型里的项目/配方/Kappa 筛选**不做**（后端无对应字段）
- 点某行 → 详情区按 `modeling.run(id)` 自取，展示 `n_samples` / `n_pixels_used` / `selected_lv` / `best_lv` / `metrics` / `quality_label`；`leak_report` 折叠

**第二层 · 预处理运行（按数据集）**

- 顶部一个数据集下拉（选项来自 `records`，显示 `displayName`）
- 选中后 `preprocess.listRuns(id)` → 列 `created_at` / `finished_at` / `status` / `b01_branch`（**这些有时间，可以显示**）
- 未选数据集时该区显示"选择一个数据集查看其预处理运行"

两层的差别要在 UI 上说清：**回归侧无时间、预处理侧有时间**，不要为了对齐而编造。

### 2.3 S10 检索空态

正式空态，不是"后续批次启用"：

- 标题 + 一句说明（检索在阶段二提供）
- **主行动按钮**（原型 4.1："空状态必须给下一步动作"）→ `openScreen('s03')`
- 不接数据、不放假搜索框

### 2.4 S11 设置入口

最小屏：

- 一段说明（设置项与出域记录的关系）
- 「打开设置」按钮 → `setSettingsOpen(true)`（复用现有 modal，**不重写**）
- 出域记录区：明确写"出域记录在阶段二提供"——**不放假表格**

### 2.5 三锚保留与基线

P5 会往屏 switch 里插四个 case，**这四处字面量一字不能动**：

```
<PreprocessPanel                                   ← panel.test.ts:61
<Composer                                          ← working.test.ts:94
import SettingsPanel ... / onClick={() => setSettingsOpen(true)}>设置</button> /
settingsOpen && status.phase === 'Ready' && <SettingsPanel   ← SettingsPanel.test.ts:185-187
DatasetPanel 的 onOpen('s06', record)              ← panel.test.ts:62
```

基线 `209/209/0`，无退场文件，新增静态测试另计并逐条列名。

---

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `src/screens/S02.tsx`（新增） | 四张卡，数据全部来自 props |
| `src/screens/S09.tsx`（新增） | 回归运行列表 + 详情自取；预处理运行按数据集 |
| `src/screens/S10.tsx`（新增） | 正式空态 + 主行动 |
| `src/screens/S11.tsx`（新增） | 设置入口 + 出域记录说明 |
| `src/App.tsx` | 屏 switch 插四个 case（在 `default` 之前）；三锚原位保留 |
| 新增静态测试 | 见 A7 |

---

## 4. 验收

| # | 断言 | 判据 |
|---|---|---|
| A1 | **S02 数据真实** | 数据集数 = `records.length`；回归运行数 = `runs()` 过滤后长度；引擎相位与 `status.phase` 一致 |
| A2 | **S09 回归列表** | 行数 = `runs()` 过滤 `regression` 后长度；**表中无时间列**（源码里不出现 `created_at` 用于回归行） |
| A3 | **S09 详情自取** | 点行 → 详情区出现 `metrics` 数值与 `quality_label` |
| A4 | **S09 预处理按数据集** | 选中数据集后出现该数据集的运行行，且含 `created_at`；未选中时有提示文案 |
| A5 | **S10 空态有出口** | 空态含主行动按钮，点击回 `s03` |
| A6 | **S11 打开设置** | 点「打开设置」→ 原 `SettingsPanel` modal 出现；出域记录区为说明文案，无表格 |
| A7 | **三锚保留** | `panel.test.ts:61` / `panel.test.ts:62` / `working.test.ts:94` / `SettingsPanel.test.ts:185-187` 全绿 |
| A8 | **基线** | `node --test "src/**/*.test.ts"` → **209 + N**，`fail = 0`；新增测试逐条列名 |
| A9 | **不碰标注** | `git diff --stat src/components/annotation/` 为空 |
| A10 | **构建** | `npm run build`（含 `tsc --noEmit`） |

---

## 5. 红线

1. 不碰 `src/components/annotation/`。
2. 不引依赖；不换皮（四个新屏里 `var(--brand` 计数为 0）。
3. 不改后端、不改 Rust。
4. **不编字段**：回归侧无时间戳就不设时间列；无 API 的统计与筛选一律不做。
5. `AppShell`、`.p-body`、引擎三态不动。
6. 三锚字面量原位保留。
7. 行号与实物不符须显式说明；卡未覆盖的歧义停手回报。

---

## 6. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| R1 | S09 只做回归全局 + 预处理按数据集 | `listRuns` 按 dataset 查询，全局聚合要 N 次调用；且预处理运行天然属于某个数据集 |
| R2 | 回归台账**不设时间列** | `runs()` 与 `Result` 都不返回时间戳；编一个就是假数据 |
| R3 | S09 筛选器只做 `task` | 项目/配方/Kappa 后端无字段 |
| R4 | S02 不做统计类卡片 | 无 API；四个卡全部来自 `records` / `runs()` / `status` |
| R5 | S11 复用现有 modal，不重写 | modal→全屏是 P6 的事，P5 只补入口 |
| R6 | S10 用正式空态而非占位文案 | 原型 4.1：空状态必须给下一步动作 |

---

## 7. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-03 | **裁定 S02 引擎卡与 S03 调试行的分工**：S02 只显示相位 + `generation_id`，`pid`/`port` 不重复；S03 调试行保持原样（本卡不动 S03，属 P3 范围）。补记：S05 相关断言实测 **65 处**（confirm 17 / display 14 / projection 13 / working 12 / overwrite 9，行=次），`display` 是 11 个 `match` + 3 个 `doesNotMatch` |
| 2026-11-03 | 初版。P5 范围：S02 / S09 / S10 空态 / S11 入口。基线 209/209/0（无退场文件）。核心约束：回归侧无时间戳（R2），不编字段 |
