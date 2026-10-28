# TASK-11e · L2 阶段与版本绑定（codex 任务卡）

日期：2026-10-29　基准 commit：`ef987b0`　上游：`docs/TASK-11-对话标注与预处理实现方案.md` §6/§8
预估：1.5 天　前置：L0（`task.py`）、L1（`catalogs`/`pending_clarify`/`set_*`）均已落地

## §0 状态确认（先跑，逐条回报，不符即停）

```bash
git log --oneline -1
rg -n "requested_stages|stages_done" src-python/          # 期望无输出（本卡新建）
rg -n "def run_default" -A 12 src-python/spectrumagent/agent/tools/workflows.py
rg -n "tools.validate|resolve_arguments" src-python/spectrumagent/agent/workflow.py
rg -n "CLEAR_ON_DATASET" -A 3 src-python/spectrumagent/agent/context.py
rg -n "denied_candidate|denied_save|denied_defaults" src-python/spectrumagent/agent/workflow.py
```

**顺序锚点（本卡设计的根基，必须先确认）**：`workflow.py` 中 `machine.tools.validate(...)` 在 L262、`memory.resolve_arguments(...)` 在 L263 —— **校验先于注入**。若实际顺序相反，停手回报，§4.3 的方案要改。

## §1 本卡解决的可演示问题（三句话）

1. **"对第一个数据标注 PP，其余背景，参数默认"** → 保存后**不会**自动跑预处理。
2. **"……保存后做预处理"** → 用**刚保存的那一版**跑，不是"库里最新的那一版"。
3. **"用第二个配方做预处理"** → 用刚选的那个配方版本，**不回落内置 `snv_sg1`**。

演示动作（真实界面）：第 1 句之后看运行记录区无新 run；第 2 句之后回读该 run 的 `annotation_version_id`，等于刚保存的版本；第 3 句之后回读 `recipe_version_id`，等于配方目录 P2 的版本。

## §2 允许改动的文件（全称，越界即停）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/context.py` | 改（`requested_stages`/`stages_done`、注入、切数据清理） |
| `src-python/spectrumagent/agent/task.py` | 改（`CONTEXT_KEYS` 加 2 键；`evaluate_task` 支持复合完成判定） |
| `src-python/spectrumagent/agent/workflow.py` | 改（阶段守卫一条；`need_version` 归入 needs_input 路径） |
| `src-python/spectrumagent/agent/tools/workflows.py` | 改（**仅 `run_default` 与它的工具描述**） |
| `src-python/tests/agent/test_stages.py` | 新建 |
| `src-python/tests/agent/test_conversation_workflows.py` | 改 |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行进度） |

## §3 明确不做（越界即停）

- **不改 `CLEAR_ON_DATASET` 那 11 个键**（L1 复核已确认逐字相等，任何增删都算越界）。
- 不做规则表抽离（`agent/rules.py`）、不改 `_workflow_enabled` 的协议判据——归 L2b。
- 不改前端、不改 Rust、不改迁移、不加表。
- 不做多候选共存、不做无种子候选、不做前端 choices。
- 不改 `annotations.*` 任何工具的 schema 或描述。
- **不改 `DefaultRunArguments` 的字段类型（保持 `Optional`）**——理由见 §4.3，改必填会直接失效。

## §4 实现要求

### 4.1 `requested_stages` / `stages_done`

值域固定：`{"annotation", "save", "preprocess", "compare"}`。

**写入（`remember_user`）**：

- 出现"标注" → add `annotation`；出现"保存/确认保存/保存后" → add `save`；出现"预处理/跑一下/执行预处理" → add `preprocess`；出现"比较/对比" → add `compare`。
- **append 语义，不覆盖**。这修的就是"标注后预处理"只留 annotation 的老毛病。
- 否定优先：`不要|不用|先不|暂不|别 + 阶段词` → remove 该阶段（例如"先不要预处理"→ remove `preprocess`）。
- `intent` 键**保留并改为派生值**（`preprocess` 当且仅当有 preprocess 且无 annotation；否则 `annotation`），避免破坏既有读取点。

**推进（`observe`）**：

- `annotations.draft_confirm` 且 `result["version_id"]` → add `annotation`、`save`。
- `preprocess.run_default` 且 `result["status"] == "succeeded"` → add `preprocess`。

**清理（`select`）**：切数据时 `state.pop("requested_stages", None)`、`state.pop("stages_done", None)` —— **用两行显式 pop，不要动 `CLEAR_ON_DATASET` 集合本身**。

**登记**：`task.py` 的 `CONTEXT_KEYS` 加 `requested_stages`、`stages_done`（L0 的漂移测试是单向包含，加键不会变红，但漏加会红）。

### 4.2 `run_default` 去掉隐式选择

现状（`tools/workflows.py` L440-449）：`annotation_version_id is None` 时查库最新；`recipe_version_id is None` 时 `recipe_ensure("snv_sg1")`。**两处都要删。**

改为：

```python
if version is None or recipe_id is None:
    missing = "annotation_version" if version is None else "recipe_version"
    return {"cube_id": arguments.cube_id, "status": "need_version", "missing": missing,
            "detail": "请先明确使用哪个标注版本与哪个配方版本，不采用库中最新或内置默认。"}
```

工具描述同步改（现在写的是"按显式版本或当前最新标注运行"），改为明确"必须显式指定标注版本与配方版本；省略由控制器注入，仍缺则拒绝"。

**注意**：改工具描述会改变 `tools_json`，`ensure_workflow_skill` 会因此生成新的 skill 版本。这是预期行为，见 §5 用例 J。

### 4.3 `resolve_arguments` 增加 None 注入（**必须在 validate 之后**）

`workflow.py` L262 校验 → L263 注入。所以：

- **不要把字段改成必填**。改必填会让模型省略参数时在校验阶段就被拒，注入永远没机会执行（这是本卡最容易踩的坑）。
- 在 `resolve_arguments` 现有的 `targets` 机制上，为 `preprocess.run_default` 增加：`annotation_version_id is None` → 用 `state.get("annotation_version_id")`；`recipe_version_id is None` → 用 `state.get("recipe_version_id")`。
- **只在值为 None 时注入**；模型显式给了值就原样透传，不覆盖。
- 注入的值只能来自 state（由 `observe` 从工具出参写入的**已确认**值），不得查库、不得猜。

### 4.4 阶段守卫（一条，写在现有 `denied_*` 链里）

```python
denied_stage = (call["name"] == "preprocess.run_default"
                and state.get("requested_stages")
                and "preprocess" not in state["requested_stages"])
```

命中时不执行，回 clarify：

> 你只要求了标注，没有要求预处理。需要我继续预处理吗？

规则边界：

- `requested_stages` **为空或不存在时不拦**（老会话、信息不足时保持宽松，避免误伤）。
- 只拦写操作 `preprocess.run_default`；`preprocess.recipes` / `preprocess.run_get` 是只读，不拦。

### 4.5 `evaluate_task` 支持复合完成

```python
def evaluate_task(state, artifacts):
    ...
    if state.get("annotation_version_id") and (...):
        requested = set(state.get("requested_stages") or ())
        if requested and not requested <= set(state.get("stages_done") or ()):
            return "working"          # 还有用户要求的阶段没完成
        return "succeeded"
```

`requested_stages` 为空时行为与 L0 完全一致（不得改变现有 11 条用例的期望）。

## §5 验收用例

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 只标注：请求无"预处理" | 保存后 `preprocess_run` 计数不变；`requested_stages == ["annotation","save"]` |
| B | 标注后预处理 | run 的 `annotation_version_id` == 刚保存的 `version_id`（**不是**库最新） |
| C | 库中已有更新的标注版本，用户说"刚才保存的那版" | run 仍绑定刚保存的那一版；不得取库最新 |
| D | 只说"做预处理"，未指定配方 | `status == "need_version"`、`missing == "recipe_version"`；**不得回落 `snv_sg1`** |
| E | state 有 `recipe_version_id`，模型省略该参数 | 注入该版本后运行成功 |
| F | 模型显式传入版本 | 原样使用，不被注入覆盖 |
| G | 只标注 + 模型尝试 `preprocess.run_default` | clarify「你只要求了标注……」；无 run 产生 |
| H | `requested_stages` 为空（老会话） | 不拦，行为与 L1 一致 |
| I | `requested_stages={annotation,save,preprocess}`，`stages_done` 缺 preprocess | `evaluate_task` 返回 `working`，不得 `succeeded` |
| J | 工具描述变更后启动 | `ensure_workflow_skill` 生成新 skill 版本；存量会话升级后仍能 continue（**这条同时覆盖 L0b 未做项**） |
| K | `CONTEXT_KEYS` 含两新键；L0 的 H 漂移检查仍绿 | 两条都过 |
| L | 回归 | `src-python/tests/agent` 全绿（≥415）；`src-python/tests backend/tests --ignore=src-python/tests/agent` 全绿（≥976） |

## §6 证据与提交

- 逐文件提交，禁 `git add -A` / `git add .`。建议四笔：`context.py`+`task.py` / `workflows.py` / `workflow.py` / 测试与文档。
- 回报必须附：
  1. §0 逐条结果（含"校验先于注入"的顺序确认）；
  2. 用例 A / B / G 的**实际 SSE 事件序列**（事件名、顺序、`task_result`）；
  3. 用例 B / C 的**数据库回读**：run 的 `annotation_version_id` 与刚保存的 `version_id` 逐字相等；
  4. 用例 D 的实际返回 JSON（证明没有回落 `snv_sg1`）；
  5. 用例 J 的 `skill_version_no` 前后值；
  6. 两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

四笔 commit 各自 revert。`workflow.py` 依赖 `context.py` 的新键与 `task.py` 的新判据，回滚顺序：`workflow.py` → `workflows.py` → `context.py`/`task.py`。skill 版本升级**不可回滚**（append-only），但旧版本仍可切换，不影响数据。
