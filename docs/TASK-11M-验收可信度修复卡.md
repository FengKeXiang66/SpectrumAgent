# TASK-11M · 验收可信度修复（两小项）

日期：2026-10-29　基准 commit：`6194250`　预估：1 小时　前置：无
两件独立的小事，共同点是**让验收不再假绿 / 不再靠碰运气**。

## A 项：把新增的前端测试挪到组件旁（10 分钟）

### A1 问题

`src-python/tests/data/display_names.test.ts` 是组件测试，却放在 Python 测试目录下。标准跑法是

```bash
node --test "src/**/*.test.ts"
```

**这个 glob 匹配不到它**——本轮是靠显式追加 `"src-python/tests/data/*.test.ts"` 才跑到的。谁按标准命令跑，这 3 条断言就永远不执行，而报告看起来是绿的。

### A2 要求

- 移动到 `src/components/datasets/display_names.test.ts`（与 `types.ts` 同目录，符合现有惯例）。
- 相对导入从 `../../../src/components/...` 简化为 `./types.ts`、`../assistant/presentation.ts`、`../assistant/sse.ts`。
- 断言内容一个字不改。
- 移动后用**标准命令**验证它能被自动发现：
  ```bash
  node --test "src/**/*.test.ts"
  ```
  输出里必须出现 `G3 shared displayName ...`。

### A3 验收

| 编号 | 期望 |
|---|---|
| A-1 | `node --test "src/**/*.test.ts"` 能跑到该用例（贴出含 `G3 shared displayName` 的输出行） |
| A-2 | 前端总数从 176 变为 **176**（只是位置变，不是数量变）；通过数仍 175（既有 1 条失败见 B 项说明） |
| A-3 | `src-python/tests/data/` 下不再有 `.test.ts` |

## B 项：验收脚本支持多颗种子（40 分钟）

### B1 问题

L4（保存 + 预处理闭环）至今未通过，唯一原因是 `annotations.propose` 返回 `below_queue_floor`：

```
(115,320) → min_similarity 0.7186 < 0.8
(156,312) → 0.4319
D2 (115,320) → 0.6022
```

0.72 离 0.8 只差 0.08。**每次手工改坐标重跑一整条三轮对话**，效率极低。脚本应当自己试几颗，命中就继续。

**不改任何判定阈值**——只增加"换颗种子再试"的循环。

### B2 要求

- `--seed` 改为**可重复**：`--seed 115,320 --seed 90,200 --seed 150,400`。
- 用法：按顺序使用；**只有当上一轮 `annotations.propose` 的 `status == "need_seed"` 且还有剩余种子时**，才继续下一颗。
- 继续方式：`POST /api/v1/annotations/{cube_id}/gestures` 换新种子 → 发一条 `--retry-message`（默认 `换了个位置，再试一次`）。
- 一旦某颗种子返回 `preview`，**停止换种子**，继续原有流程（接受候选 → 保存 → 预处理）。
- 报告增加 `seeds_tried: [[row,col], ...]` 与 `seed_used: [row,col] | null`。
- 单颗 `--seed` 时行为与现在**完全一致**（向后兼容）。

### B3 明确不做

- 不放宽 `queue_min_similarity`、不改 `DEFAULT_THRESHOLD`、不改 `propose` 任何逻辑。
- 不自动生成种子坐标（不做网格扫描、不做光谱分析）——**坐标由人给**，脚本只负责按顺序试。
- 不改 `--turns` / `--accept-message` 的现有语义。

### B4 验收

| 编号 | 期望 |
|---|---|
| B-1 | 单颗 `--seed`：事件序列与 `6194250` 版本**逐事件一致**（证明向后兼容） |
| B-2 | 多颗 `--seed`，第一颗就命中：只试 1 颗，`seeds_tried` 长度 1 |
| B-3 | 多颗 `--seed`，前 N 颗 `need_seed` 后命中：`seeds_tried` 长度 N+1，`seed_used` 为命中的那颗 |
| B-4 | 全部种子都 `need_seed`：如实打印 `FAIL at L4`，`seed_used` 为 `null`，不得伪造 |
| B-5 | 回归：`src-python/tests/agent` ≥455；非 agent ≥980（脚本不在测试集内，确认没误伤） |

## C 项：一条既存失败的记录（不改）

`src/components/preprocess/panel.test.ts` L52 的 `assert.match(panel, /projects\[0\]/)` 在基线 `da50ae3` 就已经失败（`PreprocessPanel.tsx` 里该字符串出现次数为 0）。**本卡不修它**，只在回报里确认"仍未通过且原因不变"。清理"源码文本断言"另开卡。

## D 项：证据与提交

- 建议两笔：`test(datasets): 前端显示名测试移到组件旁` / `test(e2e): 验收脚本支持多颗种子重试`。
- 回报附：A-1 的标准命令输出、B-1 与 B-3 的事件序列与报告字段、前端与两段 Python 测试数。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## E 项：回滚

两笔各自 revert。A 项只动测试文件位置；B 项回滚后脚本回到单种子，不影响任何生产代码。
