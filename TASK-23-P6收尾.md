# TASK-23 · P6 收尾（S11 全屏 + 断言迁移 + 全量回归）

> 目标：把 LLM 设置从 `<dialog>` 模态改成 **S11 全屏屏**，完成断言迁移，并把 P3/P4 只写在卡里的 skin 禁则门**落成测试**，最后跑满三套全量回归。
> 前置：TASK-22（P4）已收口，HEAD = `2803b5d`。
> **三道闸门**：① `git status` 干净；② 开工前 node 基线 **215/215/0**；③ 开工第一步 `grep -n` 复核本卡全部行号，漂移即停上报。

---

## 0. 事实底座（2026-11-04 现场 grep 重取）

### 0.1 设置入口现状：**两个入口 + 一个模态**

| 事实 | 位置 |
|---|---|
| 模态开关状态 | `src/App.tsx:54` `const [settingsOpen, setSettingsOpen] = useState(false);` |
| 顶栏入口 | `src/App.tsx:230` `<button onClick={() => setSettingsOpen(true)}>设置</button>` |
| S11 内入口 | `src/App.tsx:220` `<S11 onOpenSettings={() => setSettingsOpen(true)} />` |
| 模态挂载点 | `src/App.tsx:235` `{settingsOpen && status.phase === 'Ready' && <SettingsPanel key={status.generation_id} onClose={() => setSettingsOpen(false)} />}` |
| S11 全文 | `src/screens/S11.tsx` **仅 8 行**，只有标题 + 说明 + 1 个「打开设置」按钮 + 一个「出域记录」空态 section |
| 表单视图 | `src/components/settings/SettingsPanel.ts:10` `SettingsPanelView`，返回 `h('dialog', ...)`（`:19`） |
| 模态行为 | `src/components/settings/SettingsPanel.ts:55` `dialog.current.showModal()`；`:22` `onCancel` 拦截 Esc |
| 内联样式 | `SettingsPanel.ts` 有 **4 处** `style:`（`:13` / `:20` / `:27` / `:33`） |

### 0.2 断言迁移面：**12 处 / 3 个文件**（现场命令，禁引旧数）

取数命令（原文，改前改后各跑一次）：

```bash
grep -rn "SettingsPanel\|settingsOpen\|onOpenSettings" src --include=*.test.ts
grep -rn 'role="dialog"' src --include=*.test.ts
grep -n "dialog" src/components/settings/SettingsPanel.test.ts
```

> **取数命令的盲区（第一版就踩了）**：`onOpenSettings` 既不含 `SettingsPanel` 也不含 `settingsOpen`，所以第一版只写前两个关键字时**漏掉了 `light-screens.test.ts:63`**，把迁移面少算成 11 处。第三个关键字 `onOpenSettings` 必须写进命令——这是 `148` 案之后同一个教训的第二次现形：**计数命令本身也要能被检查**。

| # | 位置 | 断言要点 | 全屏改造后 |
|---|---|---|---|
| 1 | `SettingsPanel.test.ts:60` | `assert.match(h.render(), /<dialog[^>]*aria-labelledby="llm-settings-title"/)` | **必破**：不再有 dialog |
| 2 | `SettingsPanel.test.ts:185` | `assert.match(source, /import SettingsPanel from '\.\/components\/settings\/SettingsPanel'/)` | **必破**：App 不再 import |
| 3 | `SettingsPanel.test.ts:186` | `... /onClick=\{\(\) => setSettingsOpen\(true\)\}>设置<\/button>/` | **必破**：settingsOpen 消失 |
| 4 | `SettingsPanel.test.ts:187` | `... /settingsOpen && status.phase === 'Ready' && <SettingsPanel/` | **必破** |
| 5 | `light-screens.test.ts:65` | `assert.equal((settings.match(/<button/g) ?? []).length, 1)` | **必破**：S11 全屏后按钮 > 1 |
| 6 | `light-screens.test.ts:66` | `assert.doesNotMatch(settings, /<table\|SettingsPanel\|role="dialog"/)` | **必破**：S11 将内嵌设置表单 |
| 7 | `light-screens.test.ts:67` | `assert.match(app, /<S11 onOpenSettings=\{\(\) => setSettingsOpen\(true\)\}/)` | **必破**：S11 不再收该 prop |
| 8 | `light-screens.test.ts:79` | 循环 3 个 anchor（import / 设置按钮 / settingsOpen && …） | **必破** |
| 9 | `split-screens.test.ts:56` | `assert.ok(app.includes("import SettingsPanel …"))` | **必破** |
| 10 | `split-screens.test.ts:57` | `assert.ok(app.includes('onClick={() => setSettingsOpen(true)}>设置</button>'))` | **必破** |
| 11 | `split-screens.test.ts:58` | `assert.ok(app.includes("settingsOpen && status.phase === 'Ready' && <SettingsPanel"))` | **必破** |
| 12 | `light-screens.test.ts:63` | `assert.match(settings, /<button onClick=\{onOpenSettings\}>打开设置<\/button>/)` | **必破**：「打开设置」按钮整个消失（第一版漏项，见上） |

> **不迁移、必须保持绿的两条**（容易被"顺手改"误伤，先钉死）：
> - `light-screens.test.ts:64` `assert.match(settings, /出域记录在阶段二提供/)` —— S11 的「出域记录」空态 section **原样保留**，不随设置改造删除。
> - `light-screens.test.ts:62` `assert.doesNotMatch(search, /后续批次启用|<input|useEffect|invoke/)` —— 只读 S10，不受影响。

> **`148` 这个数不可用。** 它出自第四轮统计，同一轮先后报过 105 / 123 / 148 三个数。本卡迁移面一律以 §0.2 的三条命令现场输出为准。
> 参考：全仓 `assert.match|doesNotMatch` 总量按文件统计 = 236 条（18 个测试文件），**与迁移面无关**，不要拿它当分母。

### 0.3 禁则门现状：**只存在于卡里，没有任何测试**

| 屏 | 卡里的门 | 有测试吗 |
|---|---|---|
| S06 | `TASK-22 §2.3`：`grep -cE 'position:\s*fixed\|100vh\|z-index' preprocess-skin.css = 0` | **无** |
| S07 | `TASK-22 §2.3`：同上，`modeling-skin.css` | **无** |
| S05 | `TASK-21` 同款，`annotation-skin.css` | **无** |
| 存量 | `panel.test.ts:63` `assert.doesNotMatch(read('./preprocess.css'), /position:\s*fixed\|100vh\|z-index/)` | 有，但**只读 `preprocess.css`**，不覆盖三个 skin |

> 结论：**意图门不变成断言门，就只是一句劝告**（`docs/P4-断言盘点表.md` §3.2 原话）。P6 必须补一条真测试。

### 0.4 三套全量回归（数字现场重取，禁引 1154/75 等旧数）

```bash
# node（根目录）
node --test "src/**/*.test.ts"

# python（分段跑：本机 safe-delete hook 会拦全量，见项目纪律）
PYTEST_DEBUG_TEMPROOT=<先 mkdir 的 OS 临时目录> .venv/Scripts/python.exe -m pytest backend/tests
PYTEST_DEBUG_TEMPROOT=<同上> .venv/Scripts/python.exe -m pytest src-python/tests
# 必须用 -m 插 cwd 进 sys.path；pytest.exe 直跑 = collection error

# rust（src-tauri）
cargo test
cargo clippy --all-targets -- -D warnings
```

---

## 1. 范围裁定

### 1.1 做

1. **S11 全屏化**：`SettingsPanelView` 由 `h('dialog', …)` 改为 `h('section', …)`，字段名 / `aria-labelledby` / 文案 / `role="status"` / `role="alert"` **一个不改**；S11 渲染该视图。**S11 根节点保留 `model-panel` 并叠加 `settings-screen`**（见 §2.1）。
2. **入口收敛为一个**：顶栏「设置」按钮改 `openScreen('s11')`；删除 `settingsOpen` 状态、`App.tsx:235` 的模态挂载、`S11` 的 `onOpenSettings` prop。
3. **内联样式落成 class**：`SettingsPanel.ts` 的 4 处 `style:` 移入新文件 `src/components/settings/settings.css`，用 class 表达（理由见 §2.3）。
4. **断言迁移**：§0.2 的 **12 处**按 §2.4 裁定表逐条改，**强度不降**。
5. **禁则门落成测试**：新增一个测试文件，把 P3/P4 的 skin 禁则 grep 变成 `assert.doesNotMatch`。
6. **三套全量回归**：§0.4 五条命令全跑，`fail = 0`。

### 1.2 不做（红线）

- **不改 `SettingsPanelView` 的字段名、label 文案、`aria-label`、`role`**——11 条表单行为断言靠它们活着（`SettingsPanel.test.ts` 共 15 条 `match/doesNotMatch`，减去 §0.2 的 4 条 = 11 条）。
- 不改 `form.ts` / `settings-forward.ts` 的任何逻辑。
- 不新增路由/屏号：S11 已经在 `screens.ts` 里，`SCREEN_TITLE` 11 项不动。
- 不引依赖；不改后端；不改 Rust；不动 `AppShell` / `.p-body` / 引擎三态。
- 不把设置表单拆成多个组件。
- **不许把 S11 根节点的 `model-panel` 替换成 `settings-screen`**——只准叠加（§2.1）。替换会让 `.model-panel` 系样式全部失效，且无任何断言会红。

---

## 2. 口径钉死

### 2.1 S11 全屏形态：保留 View，只换宿主

**根节点裁定（必须照做，别按直觉重写）**：`S11.tsx:2` 现在是 `className="model-panel"`，是 P5 复用 `modeling.css` 的共享宿主之一。全屏化时**不许把 `model-panel` 换成 `settings-screen`**——那会让 `.model-panel` 系样式全部失效（S11 裸奔），并连带误伤 P5 的锚点。正确写法是**叠加**：

```tsx
// src/screens/S11.tsx 改后（示意，文案与 aria-label 不变）
<section className="model-panel settings-screen" aria-label="设置与出域记录">
  <h2>设置与出域记录</h2>
  <p>在设置中管理模型连接与出域开关，出域记录用于查看相关操作。</p>
  <SettingsPanel onClose={onBack} />
  <section aria-label="出域记录"><h3>出域记录</h3><p>出域记录在阶段二提供</p></section>
</section>
```

- `:4` 那句说明文字**原样保留**（与 `:2` 的 aria-label、`:6` 的出域记录空态一起，构成"文案不变"的三处锚）；只有 `:5` 的「打开设置」按钮消失。

- `settings.css` 的选择器一律 `.settings-screen` 前缀 → 只管 S11，不碰其它 `.model-panel` 宿主。
- **S11 自身新增 0 颗按钮**：返回由 View 内既有的「取消」承担（`SettingsPanel.ts:41`，文案不改），侧边导航也随时可离开。这条是 §2.4 #5 等值断言成立的前提。
- **「出域记录」空态 section 原样保留**（`light-screens.test.ts:64` 靠它）。

| 项 | 现值 | 改后 |
|---|---|---|
| View 根节点 | `h('dialog', { ref, 'aria-labelledby': 'llm-settings-title', style…, onKeyDown, onCancel })` | `h('section', { 'aria-labelledby': 'llm-settings-title' })`——**不带 className**，样式全部挂在外层 `.settings-screen` 上 |
| `dialogRef` prop | `SettingsPanelViewProps.dialogRef?`（`:5-8`，可选） | **保留可选类型，实现里不再创建 ref**：删 `SettingsPanel.ts:46` `const dialog = useRef<HTMLDialogElement>(null)`、删 `:55` 的 `showModal` effect、删 `:56` 的 `dialogRef: dialog` 传参。**三处必须一起删**——`tsconfig.json:7` 有 `noUnusedLocals: true`，只删后两处会让 `:46` 变成孤儿变量，`tsc --noEmit` 直接报错（A7 假红）。理由：类型可选，删类型要连带改 `SettingsPanelViewProps`，对断言零收益；测试的 `props()` 工厂（`SettingsPanel.test.ts:32`）**本来就没传它** |
| `onCancel` | 拦截 Esc 关模态 | **删除**（全屏没有 Esc 语义） |
| 关闭动作 | 模态「取消」按钮 → `onClose` | 不变：View 内「取消」→ `onClose`；App 传 `() => openScreen('s02')` |
| 保存后 | 留在模态 | **保存成功后不自动跳屏**（保持现值语义，避免新增行为） |

> **有据偏离（原型 ≠ 本批实现，必须写进回报，不得声称"对齐原型"）**：原型 `:2188` 的 S11 是**四页签**结构——`出域记录 / 本机环境 / 模型与网关 / 偏好设置`（`p-seg`，`:2195`），LLM 设置属于其中的「模型与网关」页签。本批**只做"把模态搬进 S11"，不建页签**：页签是新增交互（切换状态、四个面板、默认页签语义），不属于"收尾"范围。**S11 交付形态 = 设置表单 + 现有「出域记录」空态并列**，页签留作后续卡。

### 2.2 入口收敛

| 入口 | 改后 |
|---|---|
| 顶栏「设置」`App.tsx:230` | `<button onClick={() => openScreen('s11')}>设置</button>` |
| S11 `App.tsx:220` | `<S11 onOpenSettings={…} />` → `<S11 onBack={() => openScreen('s02')} />`；S11 内部渲染 `<SettingsPanel onClose={onBack} />`（**不新增 `api` prop**——`App.tsx:235` 现在也没传，别扩大面） |
| 模态挂载 `App.tsx:235` | **整行删除** |
| `settingsOpen` `App.tsx:54` | **整行删除** |

> `openScreen` 在 `App.tsx:186` 定义在 `renderScreen` 之前，顶栏 JSX 在 `return` 内，作用域可达——**不需要上移**。

### 2.3 CSP：内联 `style` 属性必须落成 class

`src-tauri/tauri.conf.json:14`：

```
"csp": "default-src 'self'; img-src 'self' data:; connect-src ipc: http://ipc.localhost; style-src 'self'"
```

`style-src 'self'` **不含 `'unsafe-inline'`**，`style` 属性属于 inline style，打包版会被拦。`SettingsPanel.ts` 现有 4 处 `style:`（`:13` / `:20` / `:27` / `:33`）在打包版大概率**没有生效**（对话框宽度/内边距/grid 间距丢失）。

- **开工第一步实测**：dev 与打包版各看一眼设置屏，确认这 4 处样式是否真的丢失，**把结论写进回报**。
- **无论结论如何都要落 class**：`settings.css` 一个文件，选择器全部 `.settings-screen` 前缀（与 P3/P4 同纪律）。
- 参照 `session-shell.test.ts:59` 的既有强度：S01/Composer 被断言 `doesNotMatch(/var\(--|style=\{/)`。本卡**不要求**给 S11 加同样的门（会与 `SettingsPanelView` 的 `h()` 写法打架），但**新写的代码不得再出现 `style:`**。

### 2.4 断言迁移裁定：**12 处全部授权同步，0 处保留原样**

裁定原则：**断言跟"入口形态"绑定，不跟"能力"绑定**。模态消失 → 入口类断言必须换锚点；但每条新断言必须**仍能红**（写明红的理由），否则等于删门。

| # | 旧断言 | 新断言（必须能红） | 能红的理由 |
|---|---|---|---|
| 1 | `<dialog … llm-settings-title>` | `assert.match(h.render(), /<section[^>]*aria-labelledby="llm-settings-title"/)` | 根节点若退回 dialog 或丢 aria，即红 |
| 2 | App import SettingsPanel | `assert.match(readFileSync(S11), /import SettingsPanel from '\.\/components\/settings\/SettingsPanel'/)`（路径按实际改） | S11 不再挂表单即红 |
| 3 | `onClick={() => setSettingsOpen(true)}>设置</button>` | `assert.match(source, /<button onClick=\{\(\) => openScreen\('s11'\)\}>设置<\/button>/)` | 顶栏入口若还开模态即红 |
| 4 | `settingsOpen && … <SettingsPanel` | `assert.doesNotMatch(source, /settingsOpen/)` | 状态机残留即红 |
| 5 | S11 按钮数 === 1 | **`assert.equal((settings.match(/<button/g) ?? []).length, 0)`**（等值，不是 `>=`） | S11 自身规定 0 颗按钮（§2.1）；多出任何一颗——包括"打开设置"回退——即红 |
| 6 | S11 不含 `SettingsPanel\|role="dialog"` | `assert.match(settings, /<SettingsPanel/)` **且** `doesNotMatch(settings, /role="dialog"/)` | 退回模态即红；没内嵌表单也红 |
| 7 | `<S11 onOpenSettings={() => setSettingsOpen(true)}/>` | `assert.match(app, /<S11 onBack=\{/)` 且 `doesNotMatch(app, /onOpenSettings/)` | prop 回退即红 |
| 8 | `light-screens.test.ts:79` 三 anchor 循环 | 换成 `['onClick={() => openScreen(\'s11\')}>设置</button>', '<S11 onBack={', 'case \'s11\'']` 三条 `includes` | 任一锚点回退即红 |
| 9-11 | `split-screens.test.ts:56/57/58` | 与 #2/#3/#7 同款三条 `includes` | 同上 |
| 12 | `light-screens.test.ts:63`「打开设置」按钮 | `assert.doesNotMatch(settings, /onOpenSettings\|打开设置/)` | 按钮或 prop 任一回归即红；与 #5 的等值断言互为正反证 |

> **禁止**用 `assert.ok(true)` / `assert.doesNotMatch(source, /不可能出现的字符串/)` 这类空断言凑数。每条新断言都要能指出"什么情况下它会红"。
> **#5 与 #12 的关系**：#5 管"数量恰好 0"，#12 管"旧锚点不复活"。只留 #12 会漏掉"新增别的按钮"；只留 #5 会漏掉"用别的写法把入口塞回来"。

### 2.5 禁则门落成测试：**allowlist 精确集合，不用"允许一处"**

新增 `src/shell/skin-guards.test.ts`（与 `screens.test.ts` 同目录，命名同类）。**不要写成 `count <= 1`**——那种写法新增第二个断点也不会红。用逐文件 allowlist：

```ts
const GUARDS = [
  { file: '../../components/annotation/annotation-skin.css', media: ['@media (max-width: 720px)'] },
  { file: '../../components/preprocess/preprocess-skin.css', media: [] },
  { file: '../../components/modeling/modeling-skin.css', media: [], bareModelPanel: true },
];
```

每个文件四条，全部是**等值/存在性**断言：

| # | 断言 | 能红的理由 |
|---|---|---|
| ① | `doesNotMatch(/position:\s*fixed\|100vh\|z-index/)` | 任一出现即红（`panel.test.ts:63` 只守 `preprocess.css`，三个 skin 无人守） |
| ② | `doesNotMatch(/!important/)` | 出现即红（P3/P4 卡里都写了"`!important` 一律停手"） |
| ③ | **`assert.deepEqual((source.match(/@media\s*[^{]*/g) ?? []).map(s => s.trim()), media)`** | **精确集合**：preprocess/modeling 必须为 `[]`，annotation 必须**恰好等于** `['@media (max-width: 720px)']`——多一个断点即红 |
| ④ | `modeling-skin.css` 额外：`doesNotMatch(/^\s*\.model-panel[^[]/m)` | 出现裸 `.model-panel` 作用域即红（8 宿主污染） |

> **③ 必须 `.trim()`，否则这条门天生红**。实测（node 直跑真实文件）：
> `annotation-skin.css` 的 `source.match(/@media[^{]*/g)` 返回 **`["@media (max-width: 720px) "]`——带尾随空格**（`[^{]*` 把 `{` 前的空白也吃了）。不做 `trim()` 时，`deepEqual(["@media (max-width: 720px) "], ["@media (max-width: 720px)"])` 必然失败，codex 会误判成 annotation-skin 违规。`preprocess` / `modeling` 两个返回 `null`，`?? []` 处理正确。
> 本卡早先的两种写法（`['(max-width: 720px)']` 与 `['@media (max-width: 720px)']`）都与实际捕获串不等，已统一为上表这一种。
> 路径以测试文件为基准（`src/shell/` → `../../components/...`），落地时按实际 import 方式写，别照抄相对深度。
> `annotation-skin.css:51` 的 `@media (max-width: 720px)` 是**既存且有意**的（P3 的 720 窄屏降级），所以它在 allowlist 里；这条不是例外条款，是**精确值**。

---

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `src/screens/S11.tsx` | 全屏化：根节点 `className="model-panel settings-screen"`（**叠加，不替换**）；渲染 `SettingsPanel`；删「打开设置」按钮；保留「出域记录」空态 section |
| `src/components/settings/SettingsPanel.ts` | `dialog` → `section`（无 className）；删 `:46` `const dialog = useRef…`、`:55` `showModal` effect、`:56` `dialogRef: dialog` 传参（**三处必须同删**，`noUnusedLocals` 见 `tsconfig.json:7`）；4 处 `style:` 改 class |
| `src/components/settings/settings.css`（新增） | `.settings-screen` 前缀的全部样式 |
| `src/App.tsx` | 删 `settingsOpen`（`:54`）与模态挂载（`:235`）；顶栏入口改 `openScreen('s11')`（`:230`）；S11 prop 改 `onBack`（`:220`） |
| `src/components/settings/SettingsPanel.test.ts` | 迁移 #1–#4（4 处） |
| `src/screens/light-screens.test.ts` | 迁移 #5–#8 + #12（**5 处**） |
| `src/screens/split-screens.test.ts` | 迁移 #9–#11（3 处） |
| `src/shell/skin-guards.test.ts`（新增） | §2.5 四条门 |

**共 6 改 + 2 新增 = 8 个文件。出现第九个即停手回报。**

---

## 4. 验收

| # | 断言 | 判据 |
|---|---|---|
| A1 | **S11 全屏可用** | 顶栏「设置」→ 进 S11 → 五个字段 + 外发开关 + API key 可编辑；保存成功后 `role="status"` 出消息；View 内「取消」回到来源屏（S11 自身 0 颗按钮，§2.1）；**「出域记录」空态 section 仍在** |
| A2 | **无模态残留** | `grep -rn "settingsOpen\|showModal\|<dialog" src --include=*.tsx --include=*.ts \| grep -v "\.test\.ts"` = **0 行**（测试文件里会有 `doesNotMatch(/settingsOpen/)` 这类反证，必须排除，否则这条门永远不成立） |
| A3 | **断言迁移 12 处全绿** | 重跑 §0.2 三条命令，输出**每一条都能在 §2.4 表格里找到对应行**；不得出现表外新增的 `SettingsPanel`/`settingsOpen`/`onOpenSettings` 断言；`light-screens.test.ts:64`（出域记录空态）必须仍绿 |
| A4 | **强度不降** | 每条新断言在回报里写出"什么情况下会红"；空断言 0 条 |
| A5 | **禁则门落成** | `skin-guards.test.ts` 四条门全绿；故意改坏一个 skin（临时插入 `z-index:1`）能红——**验完必须还原并 `git diff` 确认无残留** |
| A6 | **CSP 落 class** | `SettingsPanel.ts` 的 `style:` 计数 = **0**；`settings.css` 选择器全部 `.settings-screen` 前缀 |
| A7 | **构建** | `npm run build`（含 `tsc --noEmit`） |
| A8 | **node 全量** | `node --test "src/**/*.test.ts"` → 215 + 新增数，`fail = 0` |
| A9 | **python 全量** | §0.4 两段命令，`fail = 0`，collected 数与开工基线一致（数字现场重取并贴出） |
| A10 | **rust 全量** | `cargo test` 全绿 + `cargo clippy --all-targets -- -D warnings` 零告警 |
| A11 | **P3 手测悬账（必须真人按键）** | `TASK-21-S05换皮.md:123`：空格平移、中键平移——**两轮未验，本轮必须实测**；同时验数字键选标签 / `Z` / `C` / `Enter` / `←→` / `Ctrl+S` 仍可用 |
| A12 | **P3 1180 副作用（必须拖窗口）** | `TASK-21-S05换皮.md:164`：窗口从 1280 拖到 **1180**，看 S05 中栏是否仍三栏、有无横向溢出；再拖到 S06/S07 各看一眼（P4 只在两个固定尺寸验过，拖动过程未验） |

> A11/A12 是**手测项**，回报里必须写"谁按的、在哪个窗口尺寸、结果如何"，不接受"结构免疫"这类推断。

---

## 5. 红线

1. 不改 `SettingsPanelView` 的字段名 / label 文案 / `aria-label` / `role`。
2. 不动 `form.ts` / `settings-forward.ts`。
3. 不新增屏号；`SCREEN_TITLE` 11 项与 `NAV` 10 项不动。
4. 新写代码禁 `style:`；skin/样式文件禁 `!important`（`@media` 例外见 §2.5）。
5. 只准 8 个文件；出现第九个即停。
6. 断言迁移必须逐条写"能红的理由"，禁空断言。
7. A5 的"故意改坏验证"必须还原，`git diff` 确认无残留。
8. 行号与实物不符按即停条款停止并在回报中显式说明，**不得自行改写本卡**。
