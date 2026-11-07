# TASK-34 草稿判等规范化卡（轻量卡）

> **状态**：**v1.2（2026-11-07 13:10 需求方按执行方即停报告放行行号锚点订正）**。版本链：v1 `dd8caf5`（82 行）→ v1.1 `1d1a650`（91 行，IPC 根因重写 + §5 三断言）→ **v1.2 本版**；代码基线仍 `1c7ed69`（本卡提交只改卡文件、不含代码改动，§3 代码行号不按卡提交号推算）。**v1.2 核心**：v1.1 把 `serde_json::to_vec(&value)` 的调用行误记为 `preprocess.rs:337`（实为 `:336`，`:337` 是紧随的 `.map_err(...)`）——系起草时用 `sed` 相对编号推算 absolute 行号所致，违反「禁止按偏移推算」纪律；执行方按 §7 即停 1 上报正确。**全卡行号精核**：`preprocess.rs:333` `from_slice` ✓、`:336` `to_vec` ✓、`:338` `reject_sensitive(&canonical)`；`Cargo.toml:35` ✓；`pipeline.ts:27-68 / :32 / :35-37 / :63` ✓；`PreprocessPanel.tsx:105-111 / :112-116 / :115-116 / :131-140 / :166-167 / :132` ✓；`panel.test.ts:48-64` ✓；`PipelineEditor.tsx:32` ✓ —— **除 `337` 外无第二处漂移**。**v1.2 只改**：卡头状态行、事实源行、§2 D1 依据栏、§3 IPC 证据行共 4 处（其中 3 处为 `337`→`336`）；D1 修法 / D2 / D3 / §3 其余锚点 / §4 清单 / §5 三断言 / G1–G3 / §7 即停 4 条 / §8 **全部零改动**，属**纯行号订正、不构成口径修订**，轻量卡判据（2 文件 / 零契约 / 无新口径）仍成立。v1.1 轮开工在锚点复核阶段即停、前端基线与 tsc 均未执行，故 v1.2 按新卡**从头重走三项开工自检**，无结果可沿用。**v1.1 历史裁定（继续生效）**：根因为 Tauri IPC 字母序重排 × step 顶层键序，修法双侧编译，详见 §2 D1 / §3 / §5。**本卡不代发提示词**；卡是执行期唯一口径，对话补充无效，变更另出修订版。
> **卡型**：**轻量卡**。判据逐条满足：① 纯前端 **2 文件**（`PreprocessPanel.tsx` + `panel.test.ts`）；② 零契约改动（不动任何 API / DDL / openapi / Rust / 后端）；③ 无边界数学（只改比较方式）；④ **无新口径决策**——`changed` 的意图语义自始是「草稿内容与已存版本是否一致」，本卡只把实现修到符合既有意图，不重新裁定任何口径。
> **事实源**：现象为需求方 2026-11-07 真实界面复现（本机 HEAD `1c7ed69`）；**根因证据链（v1.1 重写）**：`src-tauri/Cargo.toml:35` `serde_json = "=1.0.154"`（无 `preserve_order`）、`src-tauri/src/preprocess.rs:333` `serde_json::from_slice(&bytes)` 与 `:336` `serde_json::to_vec(&value)`、以及本轮 node 字母序模型实测（v1/v2 复现 / 双侧编译修复 / 直连不触发）；后端规范化哈希依据 TASK-30 D2（`sha256/json-canonical-v1`）；版本不可变纪律依据 TASK-05 §2.3；DB 实物与 §3 锚点见下。历史证据 `5f5f2be`（2026-10-21 12:20 +0800）仅说明 `pipeline.ts` / 守卫自该提交未改，**不作现行格式定义**（引用纪律：格式与键清单一律锚当前 HEAD）。
> **不承载**：数据库历史行键序不改写（TASK-30 §8 挂账维持）；「算子链 · v1」legend 写死问题（`PipelineEditor.tsx:32`）**不在本卡**——同族 UI 瑕疵另挂账，保持本卡 2 文件边界。

## 1. 现象（一句话）

S06 载入 `plastic-snv-sg1` 任一历史版本（v1 或 v2）后**未做任何修改**，界面即提示「草稿已变更，请先保存为新版本再执行」，「提交 run」按钮恒禁用；v1 与 v2 均触发（含 10-21 与 11-04 两代行）。

## 2. 根因与定案（D1–D3，不重开）

| # | 定案 | 依据（HEAD `1c7ed69` 实读） |
|---|---|---|
| D1 | **修法 = 判等双侧规范化（v1.1 维持不变，修法本身零改动）**：`PreprocessPanel.tsx:116` 的比较由「`compilePipeline(草稿)` vs 原始存储 JSON」改为「`compilePipeline(草稿)` vs `compilePipeline(存档 steps)`」——两侧均以 `compilePipeline`（`pipeline.ts:27-68`）输出为准，比较仍用 `JSON.stringify`。**守卫语义零变化**：真改过参数 → 编译后仍不等 → 照常拦截；非法草稿链 → `:113` 的 `invalid` 照常拦截。保守回退：**存档侧编译失败或无已存版本时保持 `changed = true`**（不降格判定）。存档侧编译须用与草稿侧**完全相同**的 `record.dataset.wavelengths` / `record.dataset.shape[2]` 输入。**对 `preserve_order` 两种形态均稳健**：`compilePipeline` 输出 step 顶层恒为 `{op,version,params}`（实测：只打乱顶层键序、`params` 保持同一对象时输出逐字相等），故无论 IPC 是否启用 `preserve_order`、存档侧顶层是字母序还是插入序，双侧编译后形态一致 | **v1.1 根因（全文重写）**：`Cargo.toml:35` 的 `serde_json = "=1.0.154"` 未启用 `preserve_order` → `Value::Map` 为 `BTreeMap`、对象键按字母序重排；`preprocess.rs:333` 把后端响应解析成 `Value`、`:336` 再 `to_vec` 回前端，`getRecipe`（草稿来源）与 `listRecipes`（`currentVersion` 来源）走同一条链 → 两侧 step 顶层均为 `{op,params,version}`，而 `compilePipeline` 输出恒为 `{op,version,params}` → `JSON.stringify` 逐字不等 → `changed=true`。**实测（真实函数 + 真实 DB 数据 + 字母序模型，axis 200 / bands 200）**：v1/v2 `changed(现行)=true`、`changed(双侧编译)=false`；直连（不经 IPC）`changed=false` —— 直连不触发正是 v1 误判「现象无法复现」的原因。**注意**：`pipeline.ts:35-37` 的 `keys` 表只是参数白名单校验，`:32` `p={...step.params}` 与 `:63` `next={op,version,params:p}` **不做 params 键序重排**；v1 所写「按必需键表固定输出键序 `window→polyorder→mode→order`」为误读。`save`（`:132`）先过 `compilePipeline`，故 v3+ 新存版本顶层键序标准 |
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
| 本机 DB `preprocess_recipe_version` | `plastic-snv-sg1` v1（2026-10-21）`sg_derivative.params` 键序 `order→window→polyorder`、v2（2026-11-04）`order→polyorder→window`，**两代均无 `mode`**；规范化哈希同值（TASK-30 回填 `43fe2124e53c`）；用这两份数据**直连**模拟 `:116` → `changed=false`（不触发症状） | 只读证据（v1.1 按实物订正），执行方不访问运行库 |
| `src-tauri/Cargo.toml:35` / `src-tauri/src/preprocess.rs:333,336` / `PreprocessPanel.tsx:116` | `serde_json = "=1.0.154"` 无 `preserve_order`（`Value::Map` 为 BTreeMap、键按字母序）；响应 `from_slice` 成 `Value` 再 `to_vec` 回前端；`:116` 单侧编译逐字比对 | **只读**（v1.1 新增证据行）：症状根因链；执行方不改这三个文件 |

## 4. 改动清单（清单外零改动）

| 文件 | 动作 |
|---|---|
| `src/components/preprocess/PreprocessPanel.tsx` | `:115-116` 改为双侧 `compilePipeline` 编译后比较；存档侧编译失败 / 无版本 → `changed = true`（保守回退） |
| `src/components/preprocess/panel.test.ts` | 追加 1 个用例（见 §5），既有断言零改动 |
| 后端 / Rust / DDL / openapi / 数据库 / `pipeline.ts` / `PipelineEditor.tsx` / 其余前端文件 | **零改动** |
| 14 项 step2 噪声 + 1 个 untracked `docs/AI自动标注路径分析.md` | **禁触碰** |

## 5. 新增测试设计（1 个用例、三个断言，非自指）

```ts
test('changed comparison survives IPC key alphabetization because both sides pass compilePipeline', () => {
  // IPC 字母序形态：serde_json 无 preserve_order → step 顶层 {op,params,version}、params 键亦按字母序
  const axis = Array.from({ length: 200 }, (_, i) => 1000 + 2 * i), bands = 200;
  const ipcSteps: Step[] = [
    { op: 'snv', params: {}, version: 1 },
    { op: 'sg_derivative', params: { order: 1, polyorder: 2, window: 15 }, version: 1 },
  ];
  const ipcStored = { steps: ipcSteps };
  const compiled = compilePipeline(structuredClone(ipcStored.steps), axis, bands);
  // ① 复现故障：单侧编译输出 {op,version,params} 与字母序存档 {op,params,version} 逐字不等
  assert.notEqual(JSON.stringify(compiled), JSON.stringify(ipcStored));
  // ② 修复依据：编译器统一 step 顶层键序（只打乱顶层、params 保持同一对象引用）
  const topShuffled: Step = { params: ipcSteps[1].params, version: 1, op: 'sg_derivative' };
  assert.equal(JSON.stringify(compilePipeline([topShuffled], axis, bands)),
               JSON.stringify(compilePipeline([structuredClone(ipcSteps[1])], axis, bands)));
  // ③ 防回退 pin：changed 判定不得再直接 stringify 未编译的存档 pipeline
  assert.doesNotMatch(readFileSync(new URL('./PreprocessPanel.tsx', import.meta.url), 'utf8'),
    /JSON\.stringify\(\s*currentVersion\?\.pipeline\s*\)/);
});
```

（需在文件头部补 `compilePipeline` 与 `type Step` 的 import；`assert` / `test` / `readFileSync` 复用现有 import。**防必红约束**：`compilePipeline` 不做 params 键序重排，实测 `compiled(DB序) === compiled(IPC字母序)` 为 **false** —— 禁止把两种不同 params 键序的 steps 直接比较，断言②必须「只打乱 step 顶层键序、`params` 保持同一对象」。**TDD 顺序**：断言③ 的 pin 正则在未改 `:116` 实现前必然命中、`doesNotMatch` 必失败，须先按 D1 改实现再跑测试；改后三断言全通过、候选代码已实测 `tsc --noEmit` EXIT=0。另实测同一 IPC 字母序 steps 双侧编译后 `changed=false`（v1/v2），即修复后 `:116` 不再误判。）

## 6. 验收门（3 道，可执行、不自指）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 | `node --test "src/**/*.test.ts"`（双层 glob 逐字） | **269+1 / 269+1 pass / 0 fail**（基线 269/269/0 于 HEAD `1c7ed69` 实测）；既有用例不变红变少 |
| G2 | 新用例三断言 + `node node_modules/typescript/bin/tsc --noEmit` | 三断言通过（③ 须在 D1 实现改完后才可能通过）；tsc EXIT=0 |
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
