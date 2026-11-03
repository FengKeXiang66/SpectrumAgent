# TASK-18 · 对话双形态（P1）

> 目标：把底部「可拖拽面板 + 冒烟表单 + 助手条」三合一，拆成原型定义的两形态——
> **常驻单行 composer**（任意屏可见）与 **S01 全屏三栏**——**同一条会话、同一套执行链路**。
>
> 前置：TASK-17 P0 已落地（`d17f748`），外壳与屏号状态机在。
> **三道闸门**：① `git status` 干净，且**代码基线为 `809f76d`**——其后的提交只允许是纯 docs（本卡自身 `427c2a8` 即属此类，`git diff --stat 809f76d HEAD` 必须只有卡文件）；② 基线 **204/204/0**；③ 开工第一步 grep 复核本卡行号，漂移即停上报。

---

## 0. 已核实事实

| 事实 | 位置 |
|---|---|
| `AssistantBar.tsx` 144 行；会话态集中在 `:30-73` | `src/components/assistant/AssistantBar.tsx` |
| 　`state/dispatch` `:30`、`content` `:31`、`runtime` `:32`、`sessionId` `:33`、`inFlight` `:35`、runtime effect `:38-42`、`choices/selected/selectedChoice` `:43-45`、`request()` `:46-73` | 同上 |
| 　根节点 `<section className="assistant-bar" aria-label="S01 助手">` `:84`；`renderCheck` `:74-83`、渲染体 `:84-144` | 同上 |
| `AssistantPanel.tsx` 78 行，根 `<footer id="assistant-panel" aria-label="常驻对话条">` `:64` | `src/components/assistant/AssistantPanel.tsx` |
| `panel-height.ts` 默认高 360，`panelBounds/clampPanelHeight/draggedPanelHeight` | `src/components/assistant/panel-height.ts` |
| `panel-height.test.ts` 恰 **3** 个 `test(` | 同上 |
| App 的 `assistant` 槽：`<p role="status">{message}</p>` + 冒烟 `<form>` + `<AssistantBar>` | `src/App.tsx:191-207` |
| 全局快捷键：`Ctrl+K` 聚焦冒烟输入、`Ctrl+Enter` 触发冒烟 `send()`，排除域 `.assistant-bar` | `src/App.tsx:122-131` |
| `confirm.test.ts` 读 `AssistantBar.tsx` 断言 ConfirmCard 三处字面量 | `src/components/annotation/confirm.test.ts:80-90` |
| `working.test.ts` 读 `App.tsx` 断言 `<AssistantPanel>`、读 `AssistantPanel.tsx` 断言 `aria-label="常驻对话条"` | `src/components/annotation/working.test.ts:94-97` |
| `shortcuts.test.ts` 断言绑定冲突文案含「常驻对话条」 | `src/components/annotation/shortcuts.test.ts:60` |
| **无**测试断言 `hello 对话条` / `运行冒烟测试` / `agent-input` / `.assistant-bar` 类名 | 已全量 grep |

---

## 1. 范围裁定

### 1.1 做

- 新增 `assistant/useSession.ts`（会话态与执行链路的唯一实例）
- 新增 `assistant/Composer.tsx`（单行常驻条）
- 新增 `screens/S01.tsx`（三栏全屏助手）
- `AssistantBar.tsx` 降级为 S01 中栏的消息渲染，或整体并入 S01（二选一，见 §3 改动清单的裁定）
- 冒烟表单与 `message` 状态行从 App 移入 S01
- 快捷键转归 composer
- **删除** `AssistantPanel.tsx` / `panel-height.ts` / `panel-height.test.ts`
- 同批同步 `working.test.ts:94-97`（授权同步，见 §2.7）

### 1.2 不做（红线）

- **不碰 `src/components/annotation/` 任何文件**（含 `ConfirmCard.ts`——只 import 不改）
- 不引依赖（`dependencies` 保持 4 项）
- 不换皮：S01 / composer 只用现有 `assistant.css` 类体系 + 最小新增布局类，**不引 `theme.css` 变量**
- 不改引擎三态壳外结构、不动 `.p-body`
- 不做假历史会话（无多会话后端 API，见 §2.5 左栏）
- 不做原型「出域情况」卡（无 API）

---

## 2. 口径钉死

### 2.1 单源会话（P1 成败判据）

`useSession` 抽取 `AssistantBar.tsx:30-73` 的**全部**会话态与执行链路：

```ts
useSession({ enabled, workspace, records, displayName,
              onWorkspaceChange, onWorkspaceNavigate, onPreviewCandidate, onDataChanged })
  → { state, dispatch, content, setContent, runtime, request, choices, selected, selectedChoice }
```

- 四个回调（`onWorkspaceChange` / `onWorkspaceNavigate` / `onPreviewCandidate` / `onDataChanged`）已是 App 级 props，**作为 hook 入参**，不在 hook 内部另造。
- **Composer 与 S01 消费同一实例**：App 里 `useSession(...)` 只调用**一次**，返回值分别传给两处。禁止各建一套 `useReducer`——那是两套状态，一定会漂。
- 原型 6.1：对话条与助手页是**同一条会话、同一套执行链路**。
- `renderCheck`（`:74-83`）是渲染，留在 S01 中栏，不进 hook。

### 2.2 冒烟链路归属（拍板）

App.tsx:191-207 的 hello 冒烟表单是**引擎冒烟入口**，"功能不变"红线要求保留。裁定：

- **表单连同 `message` 状态行整体移入 S01 屏**，不并入 composer。理由：composer 是给编排助手用的自然语言输入，冒烟测试是地基自检工具，两者混在一行会让用户以为"输入运行冒烟测试"能对话。
- 冒烟表单的 placeholder 去掉快捷键字样：`运行冒烟测试（Ctrl+K 聚焦，Ctrl+Enter 发送）` → `运行冒烟测试`（已 grep：无测试断言该文案）。
- 冒烟表单的 `label` 文案 `hello 对话条` 属地基期遗留，改为 `冒烟测试`（同样无断言）。

### 2.3 快捷键转归 composer

原型验收清单第 12 条：`Ctrl+K` / `Ctrl+Enter` 属**常驻对话条**。

- 现状 `App.tsx:122-131` 指向冒烟输入与冒烟 `send()`，**改为**：`Ctrl+K` 聚焦 composer 输入框，`Ctrl+Enter` 提交 composer 消息。
- **排除域从 `.assistant-bar` 改为 composer 自身**（在 composer 内按 Ctrl+K 不应再抢焦点）。
- 任意屏生效；`s01` 屏 composer 隐藏，全局两键**让位**——**S01 中栏自带对话输入行**（`AssistantBar.tsx:137-142`），全局键若仍生效会与它抢焦、并可能双发。**理由不是"S01 没有输入框"**，S01 有。

### 2.4 composer 规格

单行，三段：

```
[上下文] 当前数据：PET-20260804195714 · 视图「标注」     [输入框]     [展开助手页] [发送]
```

- 上下文取 `displayName(selected)`（回退 `workspace.cube_id` 前 8 位）+ `SCREEN_TITLE[screen]`
- 「展开助手页」→ `setScreen('s01')`
- **`s01` 屏时整条隐藏**（原型 `:2921` 的 `comp.style.display = (id==='s01') ? 'none' : ''`）
- 根节点必须带 `aria-label="常驻对话条"`——`working.test.ts:97` 与 `shortcuts.test.ts:60` 用的是同一个术语，**术语保持一致**

### 2.5 S01 三栏

| 栏 | 宽 | 内容 |
|---|---|---|
| 左 | 172px | **真数据最小版**：当前会话（一条）+「开始新对话」按钮。**不渲染假历史**（同 R10 的 badge 纪律） |
| 中 | 自适应 | 现有消息流：`assistant-events` 列表 / `PlanCard` / 确认卡（`ConfirmCard`）/ 「执行日志」折叠 / **底部对话输入行 `AssistantBar.tsx:137-142`**。**输入行随渲染体整体搬入、原样保留**——不得因为"composer 在 s01 隐藏"就把它剥掉，否则全屏助手页变成只读 |
| 右 | 236px | 现有 `assistant-context` + `assistant-runtime` 版本行 + `assistant-datasets` 选择区上移 |

- 左栏「开始新对话」沿用现有语义：`sessionId.current = null; dispatch({type:'reset'}); setContent('')`
- 右栏「出域情况」卡**不做**（无 API）
- `ConfirmCard.ts` 在 `annotation/` 目录：**只 import，不改**——A5 不受影响

### 2.6 退场清单

| 文件 | 处理 |
|---|---|
| `src/components/assistant/AssistantPanel.tsx` | **删除**（78 行，拖拽面板） |
| `src/components/assistant/panel-height.ts` | **删除** |
| `src/components/assistant/panel-height.test.ts` | **删除**（3 项） |
| `src/components/assistant/assistant.css` | 删除 `.assistant-panel*` / `.assistant-resize-handle*` 规则；保留消息流类 |

### 2.7 源码断言扫描清单（4 + 1）

| # | 文件:行 | 现状 | 处理 |
|---|---|---|---|
| 1 | `working.test.ts:94-97` | 读 `App.tsx` 断言 `<AssistantPanel>`；读 `AssistantPanel.tsx` 断言 `aria-label="常驻对话条"` | **必红**。同批授权同步：`App.tsx` 的断言改为断言 `<Composer`；`aria-label="常驻对话条"` 的字面量**保留**，目标改指 `Composer.tsx` |
| 2 | `confirm.test.ts:80-90` | 读 `AssistantBar.tsx` 断言 `import ConfirmCard from`（`:8`）/ `key={state.pending.check_id}`（`:76`）/ `decision: 'approve'`（`:78`、`:80`） | **三处全在渲染体，不在 `request()` 里**——"request 上移导致搬家"这个归因是错的。真正的变量是 `AssistantBar.tsx` 文件保不保留（§3 二选一）：保留则不动；并入 S01 则跟着搬，强度不降 |
| 3 | `SettingsPanel.test.ts:185-187` | 读 `App.tsx` 三段字面量（import / 设置按钮 / 渲染块） | P1 改 App.tsx 必须**保留**这三段 |
| 4 | `panel.test.ts:61` | `App.tsx` 的 `<PreprocessPanel` 与 `DatasetPanel` 的 `onOpen('s06', record)` | **不应触碰**；若红了说明动到了不该动的地方 |
| 5 | `panel-height.test.ts` | 3 项 | 随组件删除（见 §2.6） |

### 2.8 不换皮边界

S01 / composer **只用**现有 `assistant.css` 类体系，新增布局类不超过 6 个（如 `.assistant-s01` / `.assistant-s01-left|mid|right` / `.composer` / `.composer-context`）。**不引 `theme.css` 的 `--brand` 等变量**——换皮是 P4。

---

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `src/components/assistant/useSession.ts`（新增） | 会话态 + 执行链路 + 四个回调入参 |
| `src/components/assistant/Composer.tsx`（新增） | 单行常驻条，`aria-label="常驻对话条"` |
| `src/screens/S01.tsx`（新增） | 三栏；中栏承接消息流；含冒烟表单与 `message` 行 |
| `src/components/assistant/AssistantBar.tsx` | 会话态移出；保留渲染体或并入 S01（二选一，回报说明选了哪个） |
| `src/App.tsx` | `useSession` 唯一实例；composer 挂载与 `s01` 隐藏；快捷键改指向 composer；冒烟表单移出 |
| `src/shell/AppShell.tsx` | **不改判屏逻辑**。`assistant` 槽仍是一个 `ReactNode`；`s01` 隐藏由 App 侧条件渲染完成（`screen === 's01' ? null : <Composer .../>`），AppShell 不知道 composer 的存在 |
| `src/components/assistant/assistant.css` | 删面板/把手规则；新增 ≤6 个布局类 |
| `src/components/annotation/working.test.ts` | 授权同步（见 §2.7-1） |
| `src/components/assistant/AssistantPanel.tsx` / `panel-height.ts` / `panel-height.test.ts` | 删除 |

---

## 4. 验收

| # | 断言 | 判据 |
|---|---|---|
| A1 | **单源会话** | `App.tsx` 里 `useSession(` 只出现**一次**；Composer 与 S01 接收同一返回值。源码形状断言：`assert.equal((app.match(/useSession\(/g) ?? []).length, 1)`（`?? []` 是防零匹配时抛 TypeError 而非干净失败） |
| A2 | **composer 单行 + s01 隐藏** | 非 s01 屏可见且为单行（`clientHeight < 80`）；`s01` 屏 `display:none` |
| A3 | **快捷键转归** | 任意非 s01 屏：`Ctrl+K` 聚焦 composer 输入框、`Ctrl+Enter` 提交；在 composer 内按 `Ctrl+K` 不重复抢焦；`s01` 屏两键不生效 |
| A4 | **冒烟链路仍在** | S01 内输入「运行冒烟测试」可执行并回显 `metrics`；placeholder 不再含快捷键字样 |
| A5 | **三栏** | 左 172 / 右 236（±2px），中栏自适应；左栏只有当前会话 + 开始新对话，无假历史 |
| A6 | **退场与基线** | `node --test "src/**/*.test.ts"` → **201/201/0**（204 − 3）；新增静态测试另计并**逐条列名**，禁止为凑数删改现有测试 |
| A7 | **断言同步** | §2.7 四处逐一核对；`panel.test.ts:61` 未触碰 |
| A8 | **不换皮** | `S01.tsx` / `Composer.tsx` 里 `grep -c "var(--brand"` 为 0 |
| A9 | **画布回归** | 退场后 `.p-body` 高度变化，进 S05 量 `.annotation-canvas-host` 的 `clientHeight > 100` |
| A10 | **构建** | `npm run build`（含 `tsc --noEmit`） |

---

## 5. 红线

1. 不碰 `src/components/annotation/`（含 `ConfirmCard.ts`、`annotation.css`）。
2. 不引依赖。
3. 不换皮：不引 `theme.css` 变量。
4. 引擎三态壳外结构、`.p-body` 不动。
5. 不渲染假数据（历史会话、出域记录）。
6. 行号与实物不符须显式说明，不得静默改口径。
7. 卡未覆盖的设计歧义 → 停手回报。

---

## 6. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| R1 | **单源会话**：`useSession` 只实例化一次，两形态消费同一返回值 | 两套 reducer 必漂；原型 6.1 明确是同一会话 |
| R2 | 冒烟表单移入 S01，**不并入 composer** | 冒烟是地基自检，composer 是编排入口，混一行会误导用户 |
| R3 | `Ctrl+K` / `Ctrl+Enter` 转归 composer，排除域改为 composer 自身 | 原型验收清单第 12 条；旧排除域 `.assistant-bar` 随组件退场失效 |
| R4 | 左栏只做「当前会话 + 开始新对话」 | 无多会话后端 API，渲染假历史等于假数据 |
| R5 | `ConfirmCard` 只 import 不改 | 它在 `annotation/` 下，改了撞 A5 |
| R6 | 删除 `AssistantPanel` / `panel-height` / 其测试 | 原型无拖拽面板；基线 204−3=201 已算准 |
| R7 | `aria-label="常驻对话条"` 字面量保留 | `working.test.ts:97` 与 `shortcuts.test.ts:60` 用同一术语，改名会让两处同时红 |
| R8 | 不做「出域情况」卡 | 无 API，同 R10 badge 纪律 |

---

## 7. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-03 | **闸门①自指缺陷修正**：原文写"HEAD 为 `809f76d`"，但卡自身提交（`427c2a8`）必然让 HEAD 前移，形成无法满足的自指条件。改为"代码基线为 `809f76d`，其后的提交只允许纯 docs（`git diff --stat 809f76d HEAD` 只有卡文件）" |
| 2026-11-03 | **复核轮修五处**：①§2.3 理由写错（原文"S01 没有可见输入框"）——S01 中栏自带对话输入行 `AssistantBar.tsx:137-142`，真实理由是**全局两键让位避免抢焦/双发**；②§2.5 中栏补一句"输入行随渲染体整体搬入、原样保留"，防被剥离成只读页；③§3 补 `AppShell.tsx` 并裁定 **composer 的 s01 隐藏由 App 条件渲染，AppShell 不改判屏逻辑**；④A1 断言补 `?? []` 防空匹配抛 TypeError；⑤§2.7 第 2 行归因纠正——ConfirmCard 三处字面量（`:8`/`:76`/`:78`）全在渲染体、不在 `request()` 里，真正的变量是 `AssistantBar.tsx` 保不保留 |
| 2026-11-03 | 初版。P1 范围：单源会话 / composer 单行 / S01 三栏 / 冒烟链路归 S01 / 快捷键转归 / 三文件退场。验收 A1–A10，基线预写死 201（204−3） |
