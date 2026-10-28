# TASK-11a · L0 可测量段（codex 任务卡）

日期：2026-10-28　基准 commit：`cdda282`　上级方案：`docs/TASK-11-对话标注与预处理实现方案.md`
预估：1 天（纯工程，零算法改动；验收用例 11 条）　前置：无（本卡是所有后续卡的测量仪）
**顺序约束**：L1 卡（`docs/TASK-11c-L1-引用层任务卡.md`）硬依赖本卡创建的 `agent/task.py`（`CONTEXT_KEYS`）与用例 H，**两卡不得并行，本卡先落地**。

## §0 开工前状态确认（先跑，逐条回报，不符即停并在首段说明）

```bash
git log --oneline -1
grep -n "api/v1" scripts/e2e_task10.py          # 期望 L52 / L69 / L81 三处
grep -n "read_to_end" src-tauri/src/agent.rs    # 期望 L414
grep -n "def evaluate_task" -r src-python/      # 期望无输出（本卡新建）
grep -n "CREATE TABLE IF NOT EXISTS annotation_version" -r src-python/
grep -n "CREATE TABLE IF NOT EXISTS preprocess_run" -r src-python/
```

行号与实物不符时**必须在回报首段显式列出**，不得自行改判、不得按记忆施工。

另有一条判据探针（2026-10-28 已实测，codex 复跑确认即可，不必改）：

```bash
.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'src-python'); sys.path.insert(0,'.')
from spectrumagent.agent import context as m
print('A', m.observe({'selected_cube_id':'c1'},'annotations.propose',{'cube_id':'c1'},
      {'cube_id':'c1','status':'need_seed'}))
print('B', m.observe({'selected_cube_id':'c1'},'preprocess.run_default',{'cube_id':'c1'},
      {'cube_id':'c1','status':'need_annotation'}))
"
```

期望：A 的 `next_action=need_seed` 且**无** `last_error`；B 除 `selected_cube_id` 外**不新增任何键**。若与期望不符，说明 §4.2(c) 的三源判据前提变了，先回报再施工。

## §1 本卡解决的可演示问题（一句话）

**"对话能不能真正完成一次标注 + 预处理"这个问题，第一次能被可信地回答（PASS/FAIL 有据），而不是靠翻日志猜。**

演示动作：一条命令跑完，终端逐级打印 L1 鉴权 / L2 工具目录 / L3 模型原生调用 / L4 业务产物 四级证据，末尾一行 `PASS` 或 `FAIL at L3: 模型未选择 v2 工具`。

## §2 允许改动的文件（全称，越界即停）

| 文件 | 动作 |
|---|---|
| `scripts/e2e_task10.py` | 改 |
| `src-python/spectrumagent/agent/task.py` | 新建 |
| `src-python/spectrumagent/agent/workflow.py` | 改（三处 yield 的 payload + 一个局部变量 `last_status`） |
| `src-python/tests/agent/test_task.py` | 新建 |
| `src-python/tests/agent/test_conversation_workflows.py` | 改（补 task_result 断言） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行进度，仅此） |

## §3 明确不做（本卡出现以下任一改动即视为越界）

- 不改 `agent/state.py` 的 `State` 枚举、不改 `agent/migrations.py`、不新增任何表或列。
- **不改 `agent/context.py`**。探针已证明 `need_annotation` 在 state 里无任何落点，但补它是 L2 的活；L0 用 `workflow.py` 的局部 `last_status` 绕开，不碰 `observe`。
- 不改 `agent/tools/` 下任何文件、不改任何工具 schema。
- 不改 `src-tauri/`、不改 `src/` 前端。
- 不做 `requested_stages`、不做引用类型化、不做显示名——那是 L1/L2。
- 不改 `data/model.py` 的 `SpectrumDataSet`（`extra="forbid"` + `frozen=True`，`data/schema.json` 是冻结资源，`src-python/tests/data/test_model.py:60` 断言字节相等）。
- 不为了让脚本"跑绿"而放宽判定、加 `try/except` 吞错、或把 L4 判据降级成"有 step 就算过"。

## §4 逐项实现要求

### 4.1 修 `/api/v1` 双前缀

现状：`scripts/e2e_task10.py` L81 `base = f"http://127.0.0.1:{port}/api/v1"`，而 L52 又拼 `f"{base}/api/v1/agent/sessions/{sid}/messages"`、L69 拼 `f"/api/v1/agent/sessions/{sid}/steps"` → 实际请求 `/api/v1/api/v1/...`。其余调用点（L84 `"/agent/runtime"`、L90/91 `"/settings/llm*"`、L96 `"/agent/sessions"`）已是相对路径，是对的。

要求：
- `base` 只保留 `http://127.0.0.1:{port}`，**全部** path 自带 `/api/v1`，与 L84 等既有写法统一。
- 启动后先单独 GET `/api/v1/agent/runtime`，失败立即退出并打印**实际请求的完整 URL**。
- 禁止"失败后换一种前缀重试"的兼容分支。

### 4.2 新建 `src-python/spectrumagent/agent/task.py`

三样东西，全部纯函数 / 纯常量，不做任何 IO。

#### (a) 任务结果枚举

```python
TASK_RESULTS = ("working", "needs_input", "needs_review", "succeeded", "failed", "cancelled")
```

#### (b) 上下文 schema 版本 + 白名单

```python
TASK_SCHEMA_VERSION = 1
CONTEXT_KEYS = frozenset({...})          # 见下，必须与 context.py 实际写入键逐字相等
def normalize_context(context): ...      # 纯函数：白名单投影 + 戳版本号
```

`CONTEXT_KEYS` 取 2026-10-28 实测的 22 个键（`grep -oP 'state\["[a-z_]+"\]' src-python/spectrumagent/agent/context.py | sort -u`）：

```
accepted_candidate_ref, annotation_version_id, authorization_cube_id, auto_execute,
candidate_ref, class_codes, dataset_catalog, display_name, gesture_ref,
include_background, intent, last_error, last_run_id, next_action, recipe_version_id,
rejected_candidate_ref, revision, save_denied, save_requested, selected_cube_id,
stage, use_defaults
```

另有一个**预留键** `cancelled`（`evaluate_task` 判据 1 用它，但 `context.py` 目前不写）——必须一并放进 `CONTEXT_KEYS`，并在注释里标 `# reserved: written by L2 cancellation`。因此白名单与实写的核对是**单向包含**（实际写入 ⊆ `CONTEXT_KEYS`），不是相等；见 §5 用例 H。

`normalize_context(context)`：返回白名单投影 + `"task_schema_version": TASK_SCHEMA_VERSION`；不改输入、不抛错。

**L0 明确不把 `normalize_context` 接进运行时。** 理由：运行时投影会把未来新增的键静默丢掉，风险大于收益。L0 只交付"白名单是显式的 + 漂移会被测试抓住"（见 §5 用例 H）。接进运行时是 L2 的事——**codex 不得在 `workflow.generate` 或 `store.save_context` 处调用它**。

#### (c) `evaluate_task(state, artifacts)`

`artifacts` 至少含两个键：

| 键 | 来源 | 无值时 |
|---|---|---|
| `run_status` | `state["last_run_id"]` 对应 `preprocess_run.status` | `None` |
| `last_status` | 本轮最后一个执行步骤 `result_summary` 里的 `status` | `None` |

判据顺序固定：

1. **cancelled**：`state.get("cancelled")` 为真。
2. **failed**：`state.get("last_error")` 存在，且 ∉ `RECOVERABLE`（**复用 `workflow.py` L15-16 那个常量，不得另建一份**）。
3. **needs_input**：以下任一成立
   - `state["next_action"] ∈ {"need_seed", "need_annotation"}`
   - `artifacts["last_status"] ∈ {"need_seed", "need_annotation"}`
   - `state["last_error"] ∈ {"GESTURE_NOT_FOUND", "GESTURE_EXPIRED", "GESTURE_NOT_CURRENT", "LABEL_NOT_FOUND", "ANNOTATION_VERSION_REQUIRED"}`
4. **needs_review**：`candidate_ref` 存在且 `accepted_candidate_ref != candidate_ref`；或 `stage == "annotation"` 且无 `annotation_version_id`。
5. **succeeded**：`annotation_version_id` 存在，且（`last_run_id` 为空 或 `artifacts["run_status"] == "succeeded"`）。
6. 其余 **working**。

**为什么 needs_input 必须三源（2026-10-28 探针实测，勿删）**：

- `need_seed` 是 `annotations.propose` 的**正常返回**，只落 `next_action`（`context.py` L158），**不进 `last_error`**；
- `need_annotation` 是 `preprocess.run_default` 的正常返回，**state 里一个键都不落**（探针输出 `{}`）；
- `last_error` 只在工具结果含 `error` 键时写入（`context.py` L119-122），值是 DataError code，**大写蛇形**（如 `CANDIDATE_STALE`）。

只按 `last_error` 判会漏掉真实的"缺种子 / 缺标注"，错落成 `working`。

约束：返回值为 `TASK_RESULTS` 之一；不得返回 dict、不得夹带数字；同一输入必得同一输出。

### 4.3 `workflow.py` 三处事件带 `task_result`

- L156 `yield "done"/"clarify"`
- L210 / L217 `yield "clarify"`（拒绝候选、未授权候选）
- L264 `yield "error"`

在 payload 里增加 `"task_result": evaluate_task(state, {...})`，其余键不变、顺序不变。

另需在 `generate` 内维护局部变量 `last_status`：每执行完一个 step，从 `json.loads(step["result_summary"])` 取 `status` 覆盖它，三个 yield 点作为 `artifacts["last_status"]` 传入。**不得为此改动 `context.observe`，也不得往 state 里加新键。**

**禁止**在模型回复里出现"完成/已保存"字样时直接置 `succeeded`——必须走 `evaluate_task`。

### 4.4 脚本改多轮 + 四级证据

- 默认消息改为场景原话：`对第一个数据标注 PP，其余背景，参数默认，保存后做预处理`（现 L76 缺"保存后做预处理"，必须改）。
- 新增 `--follow-up`（默认 `继续`）与 `--turns N`（默认 2），第二轮流式事件同样打印。
- 会话创建时记录基线：`SELECT COALESCE(MAX(version_no),0) FROM annotation_version WHERE cube_id=?` 与 `SELECT COUNT(*) FROM preprocess_run`；结束后对比，得出"本任务新产生的版本号 / run 数"。
- 四级证据逐级打印并判定，**前一级不通过就不往下判**：
  - **L1 鉴权**：`/api/v1/settings/llm` 的 `has_key` 为真且 `/api/v1/agent/runtime` 返回 200。
  - **L2 工具目录**：本会话 `llm_call.tool_names` 含 `annotations.prepare` 等 v2 工具名。**只证明"提供了"，不证明"用了"**，报告里字段名必须是 `catalogue_offered`，不得叫 `tools_used`。
  - **L3 模型原生调用**：本会话新增 `agent_step` 中存在 v2 工具行（证明模型自己选了）。
  - **L4 业务产物**：`annotation_version` 新增 ≥1 且对应 `preprocess_run.status == 'succeeded'`。
- 任一级不通过 → 非零退出，打印 `FAIL at L<n>: <具体原因>`。
- 报告写入 `.runtime/e2e_task10_report.json`，必含 `evidence_levels`、`task_result`、`stop_reason`、`session_id`；**不得包含 key、完整 prompt 或谱值**。

## §5 验收用例

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 真实模型 + 真实数据，默认参数 | L1/L2 必过；L3 若模型正确执行则过；L4 视模型行为。**L4 不通过不算本卡失败**，但必须打印停在 L3 的具体工具序列 |
| B | 不提供 key | L1 失败、非零退出；输出里不得出现"编排通过"类字样 |
| C | 反例：构造 state 只有 `dataset_catalog`（无 `annotation_version_id`） | `evaluate_task` 必须返回 `needs_review` 或 `working`，**绝不返回 `succeeded`** |
| D | 反例：state 有 `candidate_ref` 但 `accepted_candidate_ref` 不匹配 | 必须 `needs_review` |
| E | 单测：`evaluate_task` 六种返回值各至少一条 | 全绿 |
| F | 单测：证明纯函数不读库 | monkeypatch `connect_database` 抛异常，`evaluate_task` 仍正常返回 |
| G | 回归 | `src-python/tests/agent` 分段跑全绿（见 §6 纪律） |
| H | 漂移测试：实际写入键 ⊆ `CONTEXT_KEYS`（**单向包含，不是相等**） | 两条路径都断言——① 正则扫 `context.py` 的 `state["..."]` 赋值；② 实跑 `remember_user`/`observe` 若干组合后收集 `state.keys()`。出现未登记键即红；`CONTEXT_KEYS` 里有未被写入的预留键（如 `cancelled`）不算红 |
| I | needs_input 三源各一条 | ① `next_action="need_seed"`；② `artifacts["last_status"]="need_annotation"`；③ `last_error="GESTURE_EXPIRED"` → 三条均须 `needs_input` |
| J | 反例：`last_error="CANDIDATE_STALE"`（在 `RECOVERABLE` 内但不属 needs_input 子集） | 必须 `working`；**不得 failed、不得 needs_input** |
| K | 反例：`last_error="AGENT_BUDGET_EXCEEDED"`（不在 `RECOVERABLE`） | 必须 `failed` |

### 5.1 执行权限边界（2026-10-28 补，避免再次停等）

**codex 自己做、不需要 key、不需要真实数据**——这是本卡 4.1 的核心证据，必须交：

```bash
# 1) 起引擎（不需要模型 key；用仓库 venv，dev_sidecar 要求 3.12.13）
.venv/Scripts/python.exe scripts/dev_sidecar.py --data-root <绝对路径> &

# 2) 等 run/handshake.json 出现后，不带 key 跑脚本
.venv/Scripts/python.exe scripts/e2e_task10.py --data-root <同一绝对路径>
```

期望：`RUNTIME:` 行打印出 200 的响应体（含 `skill_name`），随后 `FAIL at L1`、**退出码非零**。
**若在 RUNTIME 阶段就 404 → 说明 4.1 没修对，继续修，不得以"环境没起来"结案。**
这一条就是"`/api/v1` 双前缀已修"的可判定证据，全程不需要 key。

**必须由科祥执行、codex 不得自行尝试**：用例 A 的 L3（模型原生调用）与 L4（业务产物）。原因：key 由设置页注入、内存持有，codex 不持有也不应索要。

三条红线：

- **不得向任何人索要 key**，不得把 key 写进脚本、命令行、日志或回报；
- 不得把"没有 key"当作本卡未完成的理由——本卡的完成判据是 B/C/D/E/F/G/H/I/J/K 全绿 + 上述无 key 证据；
- 回报末尾单列「待科祥执行」清单，只写用例编号与所需环境（真实数据 + 已配置模型的引擎），**不写 key**。

临时 `--data-root` 用绝对路径（建议 `.runtime/l0-engine/`），跑完删除；先确认 C 盘空闲 > 3 GB。

## §6 证据产物与提交方式

- **逐文件提交**，禁 `git add -A` / `git add .`。建议四至五笔：`task.py`+测试 / `workflow.py` / 脚本 / 文档；§8 附条单独一笔。
- 提交信息格式沿用仓库惯例（`feat(agent): ...` / `test(agent): ...`）。
- 回报必须附：
  1. `§0` 逐条状态确认结果；
  2. 每文件 diff 摘要（行数，非全文）；
  3. 测试数与**执行模式**（例：`src-python/tests/agent 分段跑 118 passed`）；
  4. 脚本一次真实运行的 report 关键字段；
  5. 未做项 / 偏离项 + 原因；
  6. 行号与实物不符处。
- **测试跑法纪律**：本机全量 pytest 会被 safe-delete hook 拦（`.lock` 删除 + tmpdir `WinError 5`，栈里零项目帧），必须分段跑：
  `cd E:\AI_Agent && .venv/Scripts/python.exe -m pytest src-python/tests/agent -q`
  跑前先确认 C 盘空闲 > 3 GB，否则先清 `%TEMP%\pytest-tmp-*`。

## §7 回滚

四笔 commit 各自独立 `git revert` 即可，无 DB 迁移、无数据回滚。`task.py` 被 `workflow.py` 引用，回滚顺序：先 `workflow.py` 再 `task.py`。

## §8 附条 L0b（独立提交，不阻塞本卡）

**升级后挂起计划的行为记录。** 现状：`agent/skill.py` L188 `UPDATE agent_session SET skill_version_id=...` 原地改写 v1 会话绑定，有 `skill_upgrade_guard` 防重入但**不定义语义**：挂起的 `agent_round.status='plan_check'` 在升级后能否 continue，无人测过。

要求（只记录，不修）：
- 在 `src-python/tests/agent/test_skill.py` 增加一条用例：构造 v1 会话 + 一条 `plan_check` 轮次 → 调 `upgrade_builtin_sessions` → 断言 `skill_version_id` 已变更，并断言挂起轮次的**实际可继续性**（能 continue 就断言成功；报错就断言错误码）。
- 测试名必须包含 `recorded_behavior`，并在 docstring 写明"本用例只记录现状，不代表期望行为"。
- 若实际行为是静默丢失，在回报中单列一条，供 L2 决策。

## §9 完成后向 TASK-11 §11 追加一行

在 `docs/TASK-11-对话标注与预处理实现方案.md` §11 表格下追加一行进度记录：`L0 完成于 <commit>，四级证据可判定，L4 实测结果 <通过/未通过 + 停点>`。除此之外不改该文档任何内容。
