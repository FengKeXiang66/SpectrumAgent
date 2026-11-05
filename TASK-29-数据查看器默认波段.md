# TASK-29 数据查看器默认波段卡（v2 轻量卡）

> **状态**：待执行。TASK-26 在途，按「两卡不同时在途」排队至其落库或需求方明确放行后才可发提示词。卡先单文件提交入库；**本卡是执行期唯一口径**，对话补充无效，需变更另出修订版。
> **事实源**：需求 v2.7 `artifacts/step3/requirements-v2.7.txt`；ui-v2.3 `.runtime/docs/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.txt`；归档版本禁引。
> **行号时效**：2026-11-05 在途状态实测；开工先逐条 grep §3，漂移即停，禁止按偏移推算。
> **版本**：v1 → v1.1（需求方复核，D1 边界修正，提交 `2229a44`）→ **v2（需求方拍板降为轻量卡）**：文档骨架瘦身（锚点 12→6、闸门并自检、验收门 5→3、即停 7→4），修订链与复跑证据压入下方「D1 由来」；**功能口径零改动**——D1 表达式、2 文件清单、范围与 v1.1 完全一致。**D1 是防越界的技术代码，不是流程装饰，禁止"简化"掉。**提交前复核另修正 §6 门 1 的「新增 2 pass」误述（node:test 按 test 计 pass，2 条 pin 断言不增加 pass 数），属验收预期校正、不动功能口径。

## 1. 改什么（一句话）

S04 数据查看器默认展示**第 100 波段**（≥200 波段的主流形态），其余形态退中带；2 文件、约 5 行，零后端、零 Rust、零 openapi、零新 FR（既有波段预览功能的默认值微调，S04 的 FR 映射 G01·G02·G04·A06 语义均不同，不挂靠）。

## 2. 定案口径（不重开）

- **D1 默认值（逐字）**：`Math.max(0, record.dataset.shape[2] >= 200 ? 100 : Math.floor((record.dataset.shape[2] - 1) / 2))`
  - **为什么必须兜底**：事实源支持 8 波段多光谱（`v2.7:4279`）；API 对 band 只校验非负（`datasets.py:80`），越界由 `model.py:75-79` 抛 `INVALID_INDEX` → S04 首屏报错页。写死 `useState(100)` 不兜底 = 8 波段数据一打开就坏。
  - **为什么阈值是 `>=200` 不是 `>100`（v1.1 由来）**：100 只在面阵 200 / 推扫 224 两种主流形态下落在中部质量区间（50.3% / 44.8%）；`>100` 下 N=101 时 100 恰为末波段（100.0%）、N=128 落 78.7%，均复跑坐实——与"避开边缘噪声带"的卡动机自相矛盾。N≤199 一律中带：8→3、101→50、128→63、199→99（199 退 99 属阈值语义一致性，非缺陷）。`Math.max(0, …)` 防 N=0 时表达式产出 -1（ENVI 实际无 0 波段，防御性）。
- **D2** 范围仅 S04；S05 `displayBand`（`AnnotationWorkbench.tsx:55`，在途 M 禁触碰）不动，如需对齐另立小卡。
- **D3** 手动波段输入框保留（诊断入口，坏波段须可查看）。
- **D4** `100` 旁必须带来源注释（需求方 2026-11-05 指定）。

## 3. 现场锚点（开工 grep，漂移即停）

| 文件:行 | 锚定内容 | 动作 |
|---|---|---|
| `src/screens/S04.tsx:6` | `const [band, setBand] = useState(0);` | **改** |
| `src/screens/S04.tsx:26` | `void loadPreview(0);` | **改** |
| `src/screens/split-screens.test.ts:22-34` | S04 测试块（`:31`/`:32` 锁请求路径与 sequence，**不锁默认值**） | 块内追加 pin，既有条目零改动 |
| `src-python/spectrumagent/api/datasets.py:80` | `band` 仅 `ge=0` 无上界 | 不改（兜底依据） |
| `src-python/spectrumagent/data/model.py:75-79` | `_indices` 抛 `INVALID_INDEX` | 不改（兜底依据） |
| `requirements-v2.7.txt:4269/:4274/:4279` | 224 / 200 / 8 波段三形态 | 事实源 |

**开工自检**（通过后才动代码）：① `git status --short` 全文贴回报，两文件须为**非 M**；② 跑 `node --test "src/**/*.test.ts"`（逐字双层 glob，单层假绿禁用）记录基线，唯一断言「既有用例不变红变少」；Python / Rust 零改动不触发其基线。

## 4. 改动清单（清单外零改动）

| 文件 | 动作 |
|---|---|
| `src/screens/S04.tsx` | 改 2 处（`:6`、`:26`）+ D4 注释 |
| `src/screens/split-screens.test.ts` | 追加 2 条 pin 断言 |
| 其余在途文件（48 M）与 7 个 untracked | **禁触碰**；`artifacts/step2/` 14 项行尾噪声不恢复、不提交 |

## 5. 实现代码

```tsx
// 默认波段：需求方 2026-11-05 指定固定 100——仅限 ≥200 波段主流形态（面阵 200 / 推扫 224）；
// 其余形态退中带防越界（API 只校验非负，越界由 model._indices 抛 INVALID_INDEX）
const defaultBand = Math.max(0, record.dataset.shape[2] >= 200 ? 100 : Math.floor((record.dataset.shape[2] - 1) / 2));
```

`:6` → `useState(defaultBand)`；`:26` → `void loadPreview(defaultBand);`

测试 pin（`split-screens.test.ts` S04 块内追加；正则可按实际实现微调，语义须等价）：

```ts
assert.match(viewer, /Math\.max\(0, record\.dataset\.shape\[2\] >= 200 \? 100 : Math\.floor\(\(record\.dataset\.shape\[2\] - 1\) \/ 2\)\)/);
assert.match(viewer, /void loadPreview\(defaultBand\)/);
```

## 6. 验收（3 道门）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| 1 前端全量 | `node --test "src/**/*.test.ts"` | **0 fail**、既有用例**不变红变少**；新增 2 条 pin 断言并入 `split-screens.test.ts` 既有 test 块——node:test 按 test 计 pass、不按 assert 数计（实测 1 test 含 3 assert 仍为 `# pass 1`），故 **pass 数 = 基线值，不会 +2**；禁为凑数新增空 test |
| 2 默认值锁定 | 新增 pin 断言 | 表达式与初始调用两条均通过 |
| 3 清单隔离 | 收工 `git status` 对照开工快照 | 仅 §4 两文件为新增改动；在途项零变化 |

## 7. 即停（4 条）

1. §3 锚点漂移，或两文件开工时已为 M → 停，上报。
2. 需要改 Python / Rust / `openapi.json` / 任何在途文件，或既有用例变红变少 → 停，禁止删改既有测试凑数。
3. 想把 D1「简化」成 `useState(100)`、去掉兜底或 `Math.max` → 停（8 波段数据会首屏报错，见 §2）。
4. 任何门给不出真实数字 → 停，写「未验证」，空断言零容忍。

## 8. 提交与发送

卡先单文件提交入库再发提示词；功能提交仅含 §4 两文件，逐文件 `git add`（禁 `-A`）；远程推送归需求方本人。基线耗时是记录值不是断言值；warning 类环境噪声与代码错误分开陈述；收据落 `.runtime/` 不进 git。

> 卡 v2（轻量）。功能口径 = v1.1 定案（`2229a44` 可溯源），文档骨架按需求方 2026-11-05 拍板瘦身。

> AI生成
