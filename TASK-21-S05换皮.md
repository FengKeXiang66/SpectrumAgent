# TASK-21 · S05 标注屏换皮（P3）

> 目标：把 S05 标注工作台的视觉对齐原型，**功能一行不改**。
> 这是六批里唯一碰 `src/components/annotation/` 的批次，所以验收从"零 diff"换成"功能回归"。
> 前置：TASK-20（P5）已收口。事实底座：`docs/P3-断言盘点表.md`（65 处断言逐条判定）。
> **三道闸门**：① `git status` 干净，且 `git diff --stat 9e26a27 HEAD` 不含 `src/` 与 `src-tauri/` 文件；② 基线 **215/215/0**；③ 开工第一步 grep 复核本卡行号，漂移即停上报。

---

## 0. 事实底座（已核实）

| 事实 | 位置 |
|---|---|
| S05 组件 449 行；样式入口 **`import './annotation.css'`** | `AnnotationWorkbench.tsx:17` |
| 主要类名：`annotation-columns` / `-left` / `-center` / **`-right`** / `-card` / `-primary` / `-hint` / `-tools` / `-parameters` / `-quality` / `-history` / `-overwrite` / `-error` / `-warning` / `-navigation` / `-levels` | 同上 |
| **`annotation-right` 的宿主是 `CandidateQueue.tsx:7`**（右栏容器），不在 Workbench 里；skin 用 `.annotation-workbench .annotation-right` 覆盖即可，**不改该文件** | `CandidateQueue.tsx:7` |
| 变量体系已存在：`--ann-brand` / `--ann-line` / `--ann-muted` | `annotation.css:1` |
| 既有浮层层级：`.annotation-shortcut-help` 带 `z-index:4` + `position:absolute` | `annotation.css:59` |
| 65 处源码断言分布在 5 个测试文件（confirm 17 / display 14 / projection 13 / working 12 / overwrite 9） | `docs/P3-断言盘点表.md` |
| 其中**锁 `annotation-*` 类名的只有 2 处**：`projection.test.ts:20`（`annotation-error`）、`:21`（`annotation-warning`） | 同上 |
| `working.test.ts:93` 读的是 **`annotation.css` 这个具体文件**，断言其中无 `position: fixed` | — |
| 画布底 `#17242c` 已是深色，与原型一致 | `annotation.css` |

**关键结论**：在这 65 处里，**62 处不触碰、3 处触碰但可保、0 处必须同步**——前提是换皮**只加类、不改类名**。

---

## 1. 范围裁定

### 1.1 做

- 新增 `src/components/annotation/annotation-skin.css`
- `AnnotationWorkbench.tsx` 加**一行** `import './annotation-skin.css';`（放在 `:17` 之后，保证后加载）
- 用现有类名选择器覆盖视觉：卡片圆角/阴影/间距、按钮层级（`annotation-primary`）、提示与徽标配色、三栏栅格间距、层级指示器
- **优先改 `--ann-*` 变量值**（主色、描边、弱化色），只有变量表达不了的才写单条规则

### 1.2 不做（红线）

- **不改任何现有 `className`**——不重命名、不删除、不合并
- 不改文案、`aria-label`、JSX 结构、条件表达式、事件处理器
- 不引入 `position: fixed` / `100vh` / `z-index`
- 不动画布相关逻辑与 `#17242c` 底色
- 不碰 `AnnotationCanvas.tsx` / `CandidateQueue.tsx` / `ConfirmCard.ts` 的结构（只允许被新皮肤选择器覆盖）
- 不引依赖；不改后端

---

## 2. 口径钉死

### 2.1 「保类名」是第一硬约束（不是注意事项）

`docs/P3-断言盘点表.md` 的 62/3/0 全部建立在"类名不变"上。一旦重命名：

- `projection:20/21` 立刻转"必须同步"
- **"零授权同步"这条验收门（A6）随之失效**

所以本批的判定标准很简单：**`git diff` 里 `AnnotationWorkbench.tsx` 只能多一行 import，一行都不能改。**

### 2.2 唯一授权路径

```
新增：src/components/annotation/annotation-skin.css
修改：AnnotationWorkbench.tsx  仅 +1 行 import（在 :17 之后）
```

**除此之外对 `annotation/` 的任何改动即停上报**——包括"顺手把某个 div 包一层"。

### 2.3 覆盖策略（前缀选择器 + 变量优先）

**先查变量，能调变量就不写规则。** `annotation.css:1` 已经建好变量体系：

```css
.annotation-workbench { --ann-brand:#24638b; --ann-line:#dce3e8; --ann-muted:#61717e; }
```

skin 里一条 `.annotation-workbench { --ann-brand: … }` 就能换掉全局主色，实现量最小，且天然绕开特异性问题。**换色/换描边/换弱化色优先走这条路。**

**规则一律带 `.annotation-workbench` 前缀，禁止裸类选择器。** 原因是 `annotation.css` 是混合特异性：

| 原规则 | 特异性 |
|---|---|
| `.annotation-workbench .annotation-primary`（`:22`） | 0-2-0 |
| `.annotation-workbench .annotation-primary:hover:not(:disabled)`（`:23`） | 0-4-0 |
| `.annotation-right .annotation-primary`（`:58`） | 0-2-0 |

CSS 的裁决是**特异性先于源顺序**：skin 里写裸 `.annotation-primary`（0-1-0），加载再晚也盖不过 0-2-0。**裸类只对一部分原规则有效**，会逼出 `!important`。

带前缀后：

- 对原**裸类**规则（0-1-0）→ skin 的 0-2-0 直接胜出
- 对原**前缀**规则（0-2-0）→ 同特异性，后加载胜出
- `@media (max-width:720px)` 里的覆盖**同样带前缀**

**后加载**：`import './annotation-skin.css'` 放在 `import './annotation.css'` 之后。

**`!important` 一律停手回报**——那说明该重写整条规则，而不是加军备。

**存量 `z-index` 不属于禁令范围**：`annotation.css:59` 的 `.annotation-shortcut-help` 自带 `z-index:4` + `position:absolute`，是快捷键浮层的既有层级。A5 只扫 **新文件**，这条既有规则**不迁移、不改、不动**——看到它不要以为禁令自相矛盾。

### 2.4 画布不动

画布底 `#17242c` 已与原型一致，S05 换皮的重心在**卡片、按钮、层级、间距**，不在画布本身。改画布配色会连带影响显示模式（`display.ts` 的 `size: 'full'` 与拉伸逻辑），超出本批范围。

---

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `src/components/annotation/annotation-skin.css`（新增） | 皮肤规则，全部用现有类名选择器 |
| `src/components/annotation/AnnotationWorkbench.tsx` | **仅 +1 行 import** |

**没有第三个文件。** 若需要第三个文件，停手回报。

---

## 4. 验收

> 本批 **A9「标注目录零 diff」退役**——P3 就是来改它的。取而代之的是功能回归。

| # | 断言 | 判据 |
|---|---|---|
| A1 | **快捷键全跑** | 数字键选标签、`Z` 撤销、`C` 点选、`Enter` 确认候选、`←/→` 上下张、`Ctrl+S` 保存、空格/中键平移——逐条实测 |
| A2 | **标注主链** | 点选赋类 / 右键擦除 / Shift 不确定 / 扩散种子 → 候选 → 确认；撤销 30 步可用 |
| A3 | **保存与投影** | 保存并聚合成功；覆写弹窗三行文案在；JSON 投影路径可见且 `shapes` 非空 |
| A4 | **候选队列** | 队列渲染、纯度徽标、悬停高亮正常 |
| A5 | **皮肤禁则（机器门）** | `grep -cE 'position:\s*fixed|100vh|z-index' src/components/annotation/annotation-skin.css` = **0** |
| A6 | **零授权同步** | 5 个测试文件**一个字节未改**；`node --test` 全绿 |
| A7 | **视觉对照** | 截图与原型 S05 并排比对：三栏比例、卡片、按钮层级、层级指示器 |
| A8 | **构建** | `npm run build`（含 `tsc --noEmit`） |
| A9 | **基线** | `node --test "src/**/*.test.ts"` → **215 + N**，`fail = 0`；新增测试（如有）逐条列名 |

---

## 5. 红线

1. `AnnotationWorkbench.tsx` **只允许 +1 行 import**，其余零改动。
2. 不改任何现有 `className` / 文案 / `aria-label` / JSX 结构 / 逻辑。
3. 只新增 `annotation-skin.css` 一个文件。
4. 禁 `position: fixed` / `100vh` / `z-index`；禁 `!important`（要用了就停手）。
5. 不碰画布逻辑与底色、不碰 `ConfirmCard.ts`、不碰 `CandidateQueue.tsx` 结构。
6. 不引依赖、不改后端。
7. 行号与实物不符须显式说明；卡未覆盖的歧义停手回报。

---

## 6. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| R1 | **保类名**，换皮只加规则 | 65 处断言里 62 不触碰、3 可保——前提就是类名不变；改名会让"零授权同步"失效 |
| R2 | 唯一新增文件 + 一行 import | 授权面越小，"零授权同步"越可信；多一个文件就多一处失控点 |
| R3 | 不用 `!important` | 用了就是选择器权重设计有问题，应重写整条规则；`!important` 一旦开始就收不住 |
| R4 | 画布不动 | `#17242c` 已对；改它连带影响显示模式逻辑，超范围 |
| R5 | 禁用规则靠自备 grep（A5） | `working.test.ts:93` 只扫 `annotation.css`，新皮肤文件不在任何断言范围内——**意图门必须自己变成机器门** |

---

## 7. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-03 | **修 §2.3 技术错误（必改）**：原文写「同权重选择器即可（后加载胜出）」，但 `annotation.css` 是混合特异性——`:22` 与 `:58` 是 0-2-0、`:23` 是 0-4-0，skin 里的裸类（0-1-0）加载再晚也盖不过。改为**一律带 `.annotation-workbench` 前缀**，并给出「对裸类高特异性胜出、对前缀同特异性后加载胜出」的判定。另补三处注记：①`annotation.css:59` 存量 `z-index:4` 不属禁令范围；②`annotation-right` 宿主是 `CandidateQueue.tsx:7`，补进 §0 类名清单；③**变量优先**——`--ann-*` 已存在，能调变量不写规则 |
| 2026-11-04 | **记录 1180 断点的有意覆盖**：skin 的 `.annotation-workbench .annotation-columns`（0-2-0）在 ≤1180 时胜出 `annotation.css:78` 的 `@media` 裸类规则（媒体查询不增特异性），因此**恰好 1180 时保持三栏**、不再降级为两栏。裁定**维持现状**（原型本身就是无断点桌面三栏；中栏 510px 与原型数据宽同量级）。如需降级，在 skin 里补一个带前缀的 `@media (max-width:1180px)` 块即可。另：`annotation.css:16` 的原值是 240 / 1fr / 254，与原型 178/236 不同——skin 覆盖它是有原型背书的 |
| 2026-11-03 | 初版。P3 范围：S05 换皮，唯一授权 = 新增 `annotation-skin.css` + 一行 import。验收从"零 diff"换成功能回归 + A5 皮肤禁则 grep。基线 215/215/0 |
