# TASK-17 · UI 外壳与屏号状态机（P0）

> 目标：把现有「单页 + 伪路由」提升为原型定义的**四段式外壳**（左导航 196px / 顶栏 / 内容区 / 底部对话条），功能一行不变。
> 本卡只做 P0。对话双形态（P1）、拆屏（P2）、逐屏换皮（P3–P5）另开卡。
>
> **卡头三道闸门（缺一不得开工）**
> 1. 两次存档提交已落地、`git status` 干净；**本卡内所有行号锚定存档后的 HEAD**，开工第一步是 grep 复核，漂移即停上报。
> 2. 标图已完成，**10 个有效探针 cube**（PE 3 / PET 3 / PP 4，另有 2 个剔除留档），`milestone12/probe-set.txt` 有记录、`milestone12/gate0-report.md` 有结论——S05 换皮要等闸门 0 出结果后再排。
> 3. 基线为 **node 201/201/0**（`node --test "src/**/*.test.ts"`）。任何新增失败必须归因，不得以"改前就有"解释。

---

## 0. 已核实事实

| 事实 | 位置 |
|---|---|
| `App.tsx` 149 行：`<main>` 在 `:101-129`，`<AssistantPanel>` 在 `:130-146` | `src/App.tsx` |
| 伪路由：三个提前 return 覆盖 `:135-140`（AnnotationWorkbench 135–138 / PreprocessPanel 139 / ModelPanel 140） | `src/components/datasets/DatasetPanel.tsx` |
| 数据屏根节点 `aria-label="数据集管理"` | `DatasetPanel.tsx:142` |
| 标注屏根 `aria-label="S05 标注工作台"`（449 行） | `AnnotationWorkbench.tsx:327` |
| 预处理屏根 `aria-label="S06 预处理工作台"`（187 行） | `PreprocessPanel.tsx:138` |
| 建模屏根 `aria-label="PLS 回归工作台"`（122 行） | `ModelPanel.tsx:78` |
| 助手根 `aria-label="S01 助手"`（144 行） | `AssistantBar.tsx:84` |
| 设置组件是 **`.ts` + `createElement as h`**，不是 tsx | `src/components/settings/SettingsPanel.ts` |
| 窗口配置只有 `{label,title,visible}`，**无尺寸** | `src-tauri/tauri.conf.json` |
| CSP `style-src 'self'`（无 `unsafe-inline`） | 同上 |
| `main` 带 `container-type: size`（**存档提交前是未提交状态**） | `src/style.css` |
| 标注画布高度 `clamp(160px, 46cqh, 520px)` | `annotation.css:47` |
| 无 DOM 测试框架（无 jsdom / testing-library） | `package.json` |
| 原型导航：`<aside class="p-nav">` 起 `:1270`，10 个 `data-nav` | 原型 HTML |
| 原型 composer 在 S01 隐藏：`comp.style.display = (id==='s01') ? 'none' : ''` | 原型 HTML `:2921` |

**现有 App 级状态**（外壳改造几乎不用搬，已经在外壳层）：`status` / `records` / `refreshVersions` / `navigation` / `workspace` / `previewCandidates` / `settingsOpen`。

---

## 1. 范围裁定

### 1.1 做

- 新增 `shell/AppShell.tsx`、`shell/screens.ts`、`shell/theme.css`
- 屏号状态机上移到 `App.tsx`；`DatasetPanel` 的三个提前 return 改为回调
- 现有 `AssistantPanel` **整块移进 `.p-main` 底部**（形态不变，仍是可拖拽面板）
- 窗口尺寸写进 `tauri.conf.json`
- `container-type: size` 从 `main` 搬到新内容槽
- 屏清单静态断言 + 浏览器冒烟

### 1.2 不做（红线）

- **不动 `AnnotationWorkbench.tsx` 一个字符**（`git diff` 必须为空）——标图主线，P3 才碰
- 不改对话形态（composer 单行 / S01 全屏）——P1
- 不拆 S03/S04、S07/S08——P2
- 不换皮（不引入 `--brand` 配色到现有屏）——P3–P5；本卡只建 `theme.css` 的变量骨架
- 不动后端、不动 `label_map` / `regions[]` / 快照 / 版本语义
- 不引新依赖（无路由库、无状态库、无 UI 库、无 DOM 测试框架）

---

## 2. 口径钉死

### 2.1 屏号模型

```ts
export type Screen = 's01'|'s02'|'s03'|'s04'|'s05'|'s06'|'s07'|'s08'|'s09'|'s10'|'s11';
```

**11 个屏，10 个导航项。S04（数据查看器）不进导航**——它是 S03 的下钻，屏号为 s04 时导航高亮 `s03`。

```ts
export const NAV: { group: string; items: { screen: Screen; label: string; icon: string }[] }[] = [
  { group: '主入口', items: [{ screen: 's01', label: '智能助手', icon: '◈' }] },
  { group: '我的工作', items: [{ screen: 's02', label: '工作台', icon: '◧' }] },
  { group: '分析流程', items: [
    { screen: 's03', label: '数据', icon: '▤' },
    { screen: 's05', label: '标注', icon: '✎' },
    { screen: 's06', label: '预处理', icon: '⚗' },
    { screen: 's07', label: '建模', icon: '⊞' },
    { screen: 's08', label: '结果', icon: '◫' },
  ] },
  { group: '沉淀与复用', items: [
    { screen: 's09', label: '实验台账', icon: '☰' },
    { screen: 's10', label: '检索', icon: '⌕' },
  ] },
  { group: '本机', items: [{ screen: 's11', label: '设置与出域记录', icon: '⚙' }] },
];
```

**导航徽标不显示数字。** 原型 S05 上有 `<span class="badge">12</span>`，但我们没有"待确认候选数"的接口，填任何数字都是假数据。留 `data-badge` 占位属性，不渲染内容。

### 2.2 外壳结构

```
.app
  .app-main            ← 新增：flex 行，撑满
    .p-nav             ← 196px 固定，#101a24
    .p-main            ← flex:1，列
      .p-top           ← 顶栏（面包屑 + 占位搜索框 + 设置入口）
      .p-body          ← 内容槽：container-type: size / overflow:auto / min-height:0
      AssistantPanel   ← 现有组件整块移入，形态不变
```

`theme.css` 只放 `:root` 变量（`--brand:#0e6e8c`、`--brand-d/soft/line`、`--line`、`--ink*`、`--radius`），**不给现有屏套用**——套用是 P3–P5 的事。

### 2.3 引擎三态必须在壳外

```tsx
if (status.phase === 'Starting') return null;                // 现状保留
if (status.phase === 'Failed')   return <FailurePage .../>;  // 独立错误页，不得套壳
if (status.phase === 'Stopping') return <p role="status">正在关闭</p>;  // 一行字，同样不进壳
// 只有 Ready 才进 AppShell
```

**四个相位里只有 `Ready` 进壳**：`Starting` 空白、`Stopping` 一行字、`Failed` 独立错误页。理由一致——引擎没起来或正在关闭时，导航里每一项都是死链，比没有导航更糟。

### 2.4 窗口尺寸

`tauri.conf.json` 的 `app.windows[0]` 补：

```json
"width": 1280, "height": 820, "minWidth": 1180, "minHeight": 720
```

纯配置，Rust 零改动。1180 的来历：196 导航 + 内容区三栏 + 余量。

> **更正（2026-11-03）**：原文写「标注屏左 260 / 中自适应 / 右 300」，是写卡时的目测数。原型实测为 **左 178 / 右 236**（原型 HTML `:1634` 的 `flex:0 0 178px`、`:1693` 的 `flex:0 0 236px`）。**结论不变**——178+236 比 260+300 更窄，1180 是更宽松的安全值；但视觉对照必须以 178/236 为准。

### 2.5 container 搬家

`style.css` 的 `main { container-type: size }` **必须搬到 `.p-body`**，且新槽要带 `min-height: 0`（flex 子项默认 `min-height:auto`，不加会撑破）。

搬完的自检：标注屏画布高度 = `clamp(160px, 46cqh, 520px)` 且 **不为 0**。塌 0 就是容器没生效。

**AssistantPanel 搬进 `.p-main` 的配套微调**：`assistant.css` 里 `.assistant-resize-handle` 的 `margin: 0 -24px` 是为旧 `main` 的 24px padding 做的出血量；搬到 `.p-main` 后没有那层 padding，它会向左侧 196px 深色导航压进 24px（hover 时可见浅色条）。本卡允许把这行改成 `margin: 0`，并顺带把面板内边距对齐 `.p-body` 的 18px——属搬位置的配套，不算换皮。

### 2.6 CSP

`style-src 'self'` 拦截内联 `<style>` 块与 HTML `style="..."` 属性。**原型 HTML 不能整段拷贝**：所有样式进 `theme.css` / 组件 css，class 化。

（React 的 `style={{}}` 走 CSSOM，通常不受限，但本卡不依赖这一点。）

### 2.7 状态映射（三个提前 return 上移）

| 现在 | 之后 |
|---|---|
| `DatasetPanel` 内 `annotation` 状态 → 整屏 return | App 持 `screen='s05'` + `selected: DatasetRecord` |
| `preprocess` 状态 → 整屏 return | `screen='s06'` + `selected` |
| `modeling` 布尔 → 整屏 return | `screen='s07'` |
| 各屏 `onClose={() => setX(null)}` | `onClose={() => setScreen('s03')}` |

`DatasetPanel` 新增 props：`onOpen(screen: 's05'|'s06'|'s07', record?: DatasetRecord)`。

**默认屏 = `'s03'`（数据）**。理由：现状就是入口即数据列表，外壳化不改变用户的第一步；`s01` 助手是第二入口，不是首屏。

**`navigation` 的消费必须整段上移到 App。** `DatasetPanel:67-91` 的 effect 消费 `navigation`，内部调用 `setAnnotation` / `setPreprocess` / `setModeling`——这三个状态删掉后 effect 无法原地存活。上移后逐分支翻译，语义不变：

| 原分支 | 之后 |
|---|---|
| `stage === 'annotation'` | `screen='s05'` + `selected=record` |
| `stage === 'preprocess'` | `screen='s06'` + `selected=record` |
| 其余 stage，且当前在 s05/s06 | 只换 `selected`，屏号不变 |
| 其余 stage，且当前在 s07 | `screen='s03'`（对应原 `setModeling(false)`） |
| `record` 不在 `records` 里 | 沿用原 `api.get` + `mergeRecords` 补齐逻辑 |

**`navigation` 不作为 prop 传入 S05 / S07**——`AnnotationWorkbench` 与 `ModelPanel` 今天都不接收该 prop（S05 里只有 `annotation-navigation` 这个 className），加 prop 就要改 S05 文件，直接撞 A5。

**注意 `records` 的传递**：S05 的 `onNavigate` 要换下一个 cube，S07 要整个 `records`——这两个都在 App 层，直接传，不要经 DatasetPanel 中转。

**已知可接受差：`DatasetPanel` 卸载导致的预览便利态重置。** 现状是 `annotation`/`preprocess`/`modeling` 三个提前 return 时，`DatasetPanel` 组件本身仍挂载，内部 `selected` / `band` / `preview` 保持；屏号上移后 `screen !== 's03'` 会让它卸载，从 S05 返回 S03 时"单波段预览"的已选波段与已加载图会重置，点一次「读取波段」即恢复。`records` 在 App 层不受影响。**属 P2 拆 S03/S04 时本来就要重构的部分，P0 不处理、不因此停手。**

### 2.8 App.tsx 的三段字面量必须保留

`SettingsPanel.test.ts:185-187` 读 `App.tsx` 源码断言：

```ts
assert.match(source, /import SettingsPanel from '\.\/components\/settings\/SettingsPanel'/);
assert.match(source, /onClick=\{\(\) => setSettingsOpen\(true\)\}>设置<\/button>/);
assert.match(source, /settingsOpen && status.phase === 'Ready' && <SettingsPanel/);
```

外壳改造**可以**保留这三段（设置按钮移进顶栏、渲染块留在 App 根部即可）。若结构上必须改，**同一提交内授权同步该测试**（非弱化：断言意图不变，只改匹配文本），并在回报中说明。

---

### 2.9 占位屏（P0 只落地 4 个真实屏）

`Screen` 有 11 个值，P0 只接通 4 个：`s03` 数据、`s05` 标注、`s06` 预处理、`s07` 建模。
其余 7 个（`s01` `s02` `s04` `s08` `s09` `s10` `s11`）渲染**统一占位屏**：

```tsx
<section className="screen-placeholder" data-screen={screen} aria-label={`${SCREEN_TITLE[screen]}（后续批次启用）`}>
  <p>本屏在后续批次启用。</p>
  <button onClick={() => setScreen('s03')}>返回数据屏</button>
</section>
```

三条约束：**不接数据、不放假内容、不引 `theme.css` 的主题变量**。占位屏是"位置已就位、能力还没搬"，不是空态设计。

`s04`（数据查看器）在 P0 不可达——它是 S03 的下钻，拆屏是 P2 的事。`navHighlight('s04') === 's03'` 仍要在 A1 里静态覆盖，因为屏号模型现在就得完整。

---

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `src/shell/screens.ts`（新增） | `Screen` 类型、`NAV` 表、`SCREEN_TITLE` 映射、`navHighlight(screen)`（s04→s03） |
| `src/shell/AppShell.tsx`（新增） | 外壳骨架：nav / top / body / children 槽；面包屑取 `SCREEN_TITLE[screen]` |
| `src/shell/theme.css`（新增） | `:root` 变量 + `.app-main` / `.p-nav` / `.p-top` / `.p-body` 布局 |
| `src/App.tsx` | 屏号状态 + 屏 switch；三态判断留在壳外；AssistantPanel 移入 `.p-main` |
| `src/components/datasets/DatasetPanel.tsx` | 删三个提前 return（`:135-140`）；新增 `onOpen` 回调；列表屏不变 |
| `src/style.css` | `main` 规则改为 `.p-body`（含 `container-type: size` / `min-height: 0` / `overflow: auto`） |
| `src-tauri/tauri.conf.json` | 窗口尺寸四键 |
| `src/shell/screens.test.ts`（新增） | 屏清单静态断言（见 A1） |

**S05 零改动**：`git diff --stat src/components/annotation/` 必须为空。

**`panel.test.ts:61` 的授权同步（非弱化）**：该用例原本断言 `DatasetPanel.tsx` 里有 `<PreprocessPanel`——S06 的挂载点从 DatasetPanel 搬到 App 后这条必然红。允许把断言目标改为 `App.tsx`，并**补一条** `DatasetPanel.tsx` 含 `onOpen('s06', record)` 的连线断言。断言条数由 1 增到 2，强度不降、用例总数不变。这是"搬挂载点"的必然连带，不是新增设计。

---

## 4. 验收

| # | 断言 | 判据 |
|---|---|---|
| A1 | **屏清单静态**（node，无 DOM） | `NAV` 恰好 5 组；组内项数 1/1/5/2/1；扁平后 10 项且 `screen` 互不重复；`NAV` 里**不出现 `s04`**；`SCREEN_TITLE` 覆盖全部 11 个 `Screen`；`navHighlight('s04') === 's03'` |
| A2 | **10 屏可切换**（浏览器） | 逐一点击 10 个导航项，每屏内容区渲染出对应根节点（4 个真实屏 + 6 个占位屏）；`s04` 在 P0 **不可达**，只由 A1 静态覆盖；截图 10 张存 `milestone17/evidence/` |
| A3 | **引擎三态在壳外** | 制造 `Failed`（临时改 engine_status 返回值或断网）：错误页**不含** `.p-nav`；`Starting` 返回 null；`Stopping` 只有一行字 |
| A4 | **画布不塌** | 进 S05，`.annotation-canvas-host` 的 `clientHeight > 100`（`46cqh` 生效） |
| A5 | **S05 零改动** | `git diff --stat src/components/annotation/` 为空 |
| A6 | **基线不退化** | `node --test "src/**/*.test.ts"`：**原有 201 项全部通过**，新增的 `screens.test.ts` 用例另计（总数 = 201 + N，N ≥ 1），`fail = 0`。**禁止为了把总数凑回 201 而删改现有测试**；A8 若授权同步了断言，数量不变但断言意图不变 |
| A7 | **构建过** | `npm run build`（含 `tsc --noEmit`） |
| A8 | **设置入口仍可达** | 顶栏「设置」按钮点开仍是原 `SettingsPanel`；`SettingsPanel.test.ts` 三条断言保持绿（或同批授权同步） |

---

## 5. 红线

1. **不碰 `src/components/annotation/` 任何文件**（含 css）。
2. 不引依赖：`package.json` 的 `dependencies` 保持 4 项。
3. 不改后端、不改 Rust（`tauri.conf.json` 是配置不是代码，允许）。
4. 不把失败页/启动页套进外壳。
5. 不做换皮：`theme.css` 的变量**不得**被现有屏引用（本卡只建骨架）。
6. 导航徽标不填数字。
7. 行号与实物不符须在回报中显式说明，不得静默改口径。
8. 卡未覆盖的设计歧义 → 停手回报，不自行拍板。

---

## 6. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| R1 | 屏号状态机，**不引路由库** | Tauri 单窗口无地址栏，URL 对用户不可见；原型 6.1 的路由表本质是屏标识符约定 |
| R2 | **S04 不进导航**，高亮归 S03 | 原型导航实为 10 项（`:1270-1288`），S04 是数据屏的下钻 |
| R3 | 引擎三态留壳外 | 失败页套壳会出现"每一项都是死链"的空导航 |
| R4 | **P0 不碰 S05** | 用户正在标图；`git diff` 为空是唯一可信的证明 |
| R5 | 现有 `AssistantPanel` 整块移入 `.p-main` 底部，**形态不变** | P1 才做单行 composer；本卡只搬位置，减少一次改动面 |
| R6 | `container-type` 搬到 `.p-body` 且必须带 `min-height: 0` | flex 子项默认 `min-height:auto`，不加会撑破；`46cqh` 失效即画布塌 0 |
| R7 | 窗口尺寸进 `tauri.conf.json`，不改 Rust | 纯配置项 |
| R8 | 屏清单用**静态断言 + 浏览器冒烟**，不引 jsdom | 项目无 DOM 测试框架，为一次冒烟引 jsdom 不划算；静态断言能锁住"屏没丢"，浏览器冒烟能锁住"能切换" |
| R9 | `SettingsPanel.test.ts` 的三段 App.tsx 字面量优先保留 | 能保留就不动测试；必须动则同批授权同步并说明 |
| R10 | 导航徽标不填数字 | 无"待确认候选数"接口，填数即假数据 |

---

## 7. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-03 | 初版。P0 范围：外壳 + 屏号状态机 + 窗口尺寸 + container 搬家；R4 写死"S05 零改动"，R8 说明为何不引 jsdom。前置闸门：存档提交落地 + 标图 9 张 + 基线 201/201/0 |
| 2026-11-03 | 复核轮补三处空隙：①新增 **§2.9 占位屏**（11 个 `Screen` 值里 P0 只接通 4 个，其余 7 个统一占位；`s04` 在 P0 不可达）；②**A2 修正**——原文写"由 S03 进入 S04"与 §1.2「不拆 S03/S04」自相矛盾，改为"10 屏可切换 + s04 由 A1 静态覆盖"；③§2.7 补**默认屏 `'s03'`**（原只写在提示词里，卡未覆盖）。另 §2.5 补 AssistantPanel 搬家的配套微调（`.assistant-resize-handle` 的 `margin: 0 -24px` 在 `.p-main` 里会压进导航 24px，允许改 `margin: 0`） |
| 2026-11-03 | 补 §2.7 末「已知可接受差」：屏号上移后 `DatasetPanel` 在 `screen !== 's03'` 时卸载，单波段预览的已选波段/已加载图会重置（原行为保留）；属 P2 拆屏时重构，P0 不处理、不因此停手 |
| 2026-11-03 | **实现落地**。补 §3 一条授权同步：`panel.test.ts:61` 的 `<PreprocessPanel` 断言随挂载点上移到 `App.tsx`，并补 `onClose`/`onOpen` 连线断言（1 条→2 条，非弱化，用例总数不变）。实现结果：A4 clientHeight 166px（1180×720 下 160px）、A5 零 diff、A6 204/204/0、A7 构建通过 |
| 2026-11-03 | **执行方即停后补两处卡内冲突**：①§2.3 的注释「Ready / Stopping 才进 AppShell」与 A3 自相矛盾——改为**四相位里只有 Ready 进壳**（Starting 空白 / Stopping 一行字 / Failed 独立错误页），并给出代码形态；②**A6 与 A1 冲突**——A1 要求新增 `screens.test.ts`，A6 却写死总数 201。改为「原有 201 项全过，新增用例另计（201+N，N≥1），fail=0」，并明写**禁止为凑总数删改现有测试** |
| 2026-11-03 | 发送前修正：§2.7 补 **`navigation` 消费的归属**——它由 `DatasetPanel:67-91` 的 effect 消费（内部调 `setAnnotation`/`setPreprocess`/`setModeling`），三个提前 return 删掉后必须**整段上移到 App**，按 stage 映射 s05/s06，且**不得作为 prop 传入 S05/S07**（两者今天都不接收，加 prop 就撞 A5 零改动）。另闸门 2 的"9 张"更正为"10 个有效 cube（PE3/PET3/PP4）" |
