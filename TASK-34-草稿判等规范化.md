# TASK-34 草稿判等规范化卡（轻量卡）

> **状态**：**v1 已入库、可执行**（2026-11-07 需求方授权出卡；队列零卡在途——TASK-30~33 四张 P0 卡均已收口入库，本卡不排队）。**本卡不代发提示词**；卡是执行期唯一口径，对话补充无效，变更另出修订版。
> **卡型**：**轻量卡**。判据逐条满足：① 纯前端 **2 文件**（`PreprocessPanel.tsx` + `panel.test.ts`）；② 零契约改动（不动任何 API / DDL / openapi / Rust / 后端）；③ 无边界数学（只改比较方式）；④ **无新口径决策**——`changed` 的意图语义自始是「草稿内容与已存版本是否一致」，本卡只把实现修到符合既有意图，不重新裁定任何口径。
> **事实源**：现象与根因为需求方 2026-11-07 真实界面复现（本机 HEAD `1c7ed69`）；后端规范化哈希依据 TASK-30 D2（`sha256/json-canonical-v1`）；版本不可变纪律依据 TASK-05 §2.3；数据库实物证据见 §2。
> **不承载**：数据库历史行键序不改写（TASK-30 §8 挂账维持）；「算子链 · v1」legend 写死问题（`PipelineEditor.tsx:32`）**不在本卡**——同族 UI 瑕疵另挂账，保持本卡 2 文件边界。

## 1. 现象（一句话）

S06 载入 `plastic-snv-sg1` 任一历史版本（v1 或 v2）后**未做任何修改**，界面即提示「草稿已变更，请先保存为新版本再执行」，「提交 run」按钮恒禁用；v1 与 v2 均触发（含 10-21 与 11-04 两代行）。

## 2. 根因与定案（D1–D3，不重开）

| # | 定案 | 依据（HEAD `1c7ed69` 实读） |
|---|---|---|
| D1 | **修法 = 判等双侧规范化**：`PreprocessPanel.tsx:116` 的比较由「`compilePipeline(草稿)` vs 原始存储 JSON」改为「`compilePipeline(草稿)` vs `compilePipeline(存档 steps)`」——两侧均以 `compilePipeline`（`pipeline.ts:27-68`）输出为准，比较仍用 `JSON.stringify`。**守卫语义零变化**：真改过参数 → 编译后仍不等 → 照常拦截；非法草稿链 → `:113` 的 `invalid` 照常拦截。保守回退：**存档侧编译失败或无已存版本时保持 `changed = true`**（不降格判定）。存档侧编译须用与草稿侧**完全相同**的 `record.dataset.wavelengths` / `record.dataset.shape[2]` 输入 | 根因：`:116` 只对草稿一侧过编译器，存档一侧用原始 `pipeline` JSON 逐字比对；`compilePipeline` 按必需键表（`pipeline.ts:35-37`）固定输出键序 `window→polyorder→mode→order`，而库内两代历史行键序均为 `order→window→polyorder→mode` → 内容相等、字符串不等。后端早已认等价：两版规范化哈希同为 `43fe2124e53c`（本机 DB 实读，TASK-30 回填行）；`save`（`:132`）本就先过 `compilePipeline` → 新存版本（v3+）键序必标准、永不触发 |
| D2 | **数据库零改动**：不改写 v1/v2 的 `pipeline` 文本（版本不可变，TASK-05 §2.3）；不动后端、不动 `recipe_pipeline_hash` 表与哈希算法；本修纯前端状态判定 | 后端契约红线；BUILTIN seed 行键序不改写为 TASK-30 §8 既定挂账 |
| D3 | **防回退 pin**：`panel.test.ts` 追加 `doesNotMatch`，禁止 `changed` 判定退回「直接 `JSON.stringify` 未编译的存档 pipeline」的写法 | 与既有 `:48-64` 三条源码 pin 同款纪律 |

## 3. 现场锚点（HEAD `1c7ed69`，开工 grep，漂移即停）

| 文件:行 | 锚定内容 | 动作 |
|---|---|---|
| `src/components/preprocess/PreprocessPanel.tsx:105-111` | `load` 载入 `structuredClone(version.pipeline.steps)`、默认取最新版 | 不改 |
| `PreprocessPanel.tsx:112-116` | `invalid` / `changed` 判定（现行单侧编译 + 逐字比对） | **改**：`:115-116` 双侧编译比较（D1） |
| `PreprocessPanel.tsx:131-140` | `save` 先 `compilePipeline` 再落库 | 不改（新版本键序标准的保证） |
| `PreprocessPanel.tsx:166-167` | 「草稿已变更」提示与「提交 run」禁用条件 | 不改（守卫渲染零变化） |
| `src/components/preprocess/pipeline.ts:27-68`（`:35-37` 必需键表） | `compilePipeline` 规范化编译器 | 不改（本卡复用，非新算法） |
| `src/components/preprocess/panel.test.ts:48-64` | wiring 源码 pin（`fetch/invoke/http`、`updateRecipe/deleteRecipe`、`ranking.sort/fisher` 三条 doesNotMatch） | **既有断言零改动**；新增用例不得引入上述模式（本修天然不涉及） |
| 本机 DB `preprocess_recipe_version` | `plastic-snv-sg1` v1（2026-10-21）/ v2（2026-11-04）`steps` 键序均为 `order→window→polyorder→mode`，规范化哈希同为 `43fe2124e53c` | 只读证据，执行方不访问运行库 |

## 4. 改动清单（清单外零改动）

| 文件 | 动作 |
|---|---|
| `src/components/preprocess/PreprocessPanel.tsx` | `:115-116` 改为双侧 `compilePipeline` 编译后比较；存档侧编译失败 / 无版本 → `changed = true`（保守回退） |
| `src/components/preprocess/panel.test.ts` | 追加 1 个用例（见 §5），既有断言零改动 |
| 后端 / Rust / DDL / openapi / 数据库 / `pipeline.ts` / `PipelineEditor.tsx` / 其余前端文件 | **零改动** |
| 14 项 step2 噪声 + 1 个 untracked `docs/AI自动标注路径分析.md` | **禁触碰** |

## 5. 新增测试设计（1 个用例、两个断言，非自指）

```ts
test('changed comparison is key-order-insensitive because both sides pass compilePipeline', () => {
  // ① 规范化性质：同一 step 以两种键序构造，compilePipeline 输出必须逐字相等
  //   （这正是 :116 双侧编译比较后键序不再影响判定的依据）
  const reordered = { op: 'sg_derivative', version: 1, params: { order: 1, window: 15, polyorder: 2, mode: 'interp' } };
  const canonical = { op: 'sg_derivative', version: 1, params: { window: 15, polyorder: 2, mode: 'interp', order: 1 } };
  const axis = Array.from({ length: 32 }, (_, i) => 1000 + 2 * i);
  assert.equal(JSON.stringify(compilePipeline([reordered], axis, 32)), JSON.stringify(compilePipeline([canonical], axis, 32)));
  // ② 防回退 pin：changed 判定不得再直接 stringify 未编译的存档 pipeline
  assert.doesNotMatch(readFileSync(new URL('./PreprocessPanel.tsx', import.meta.url), 'utf8'),
    /JSON\.stringify\(\s*currentVersion\?\.pipeline\s*\)/);
});
```

（需在文件头部补 `compilePipeline` 的 import；断言①用 `sg_derivative` 全参数键序对调，覆盖最宽的键序差。）

## 6. 验收门（3 道，可执行、不自指）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 | `node --test "src/**/*.test.ts"`（双层 glob 逐字） | **269+1 / 269+1 pass / 0 fail**（基线 269/269/0 于 HEAD `1c7ed69` 实测）；既有用例不变红变少 |
| G2 | 新用例两断言 + `node node_modules/typescript/bin/tsc --noEmit` | 两断言通过；tsc EXIT=0 |
| G3 | 收工 `git status` 对照开工快照（开工 = 14 M 噪声 + 1 untracked docs，共 15 项） | 仅 §4 两文件为新增 M；噪声与 docs 零变化、未提交 |

**需求方手测回归（收口后由需求方执行，不设自动门）**：载入 `plastic-snv-sg1` v1 → 无「草稿已变更」提示、「提交 run」可点；把 window 15→17 → 提示恢复、按钮禁用（守卫仍在）；v2 同验。

## 7. 即停（4 条）

1. §3 锚点漂移，或开工时两目标文件已为 M → 停，上报。
2. 需要改动第 3 个文件（含 `PipelineEditor.tsx` 的 legend）、后端、数据库或任何契约 → 停（legend 属挂账，不得顺手带）。
3. 删改既有断言凑绿（尤其 `:48-64` 三条 pin 与全部既有用例）→ 停。
4. 为判定而弱化守卫（如无条件 `changed = false`、删「草稿已变更」提示逻辑）→ 停。

## 8. 边界与后续（挂账，不在本卡）

- 「算子链 · v1」legend 写死（`PipelineEditor.tsx:32` 静态文案）——载入 v2+ 时显示失真，另挂轻量项。
- 数据库历史行 / BUILTIN seed 键序不改写（TASK-30 §8 既定挂账；本卡落地后该瑕疵在 UI 上不再可见）。
- 「配方退役 / 归档」软删除（应对库内 `code=1` 遗留测试配方）属新口径，须另出正式卡。

> AI生成
