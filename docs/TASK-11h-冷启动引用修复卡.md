# TASK-11h · 冷启动引用（L1b，修真实模型验收暴露的死锁）

日期：2026-10-29　基准 commit：`90a0156`　预估：40 分钟　前置：L1 已落地
**顺序：本卡修完后必须重跑真实模型验收**（这是唯一能证明修好的判据）。

## §0 缺陷现场（2026-10-29 真实模型验收实测，非推测）

```
TURN 1  SSE clarify {"pending_clarify": {"asked": true, "kind": "dataset", "reason": "not_found"},
                     "question": "当前没有可确定的数据，请明确指认或先列出对应列表。",
                     "task_result": "working"}
TURN 2  SSE done {"content": "仍未确定，保持当前选择", "step_count": 0, "task_result": "working"}
FAIL at L2: no v2 catalogue offered
```

用户原话是卡里指定场景：`对第一个数据标注 PP，其余背景，参数默认，保存后做预处理`。

**注意 `step_count: 0` 且 `no v2 catalogue offered`** —— 模型**一次都没被调用**。L2 失败是后果，不是病因。

## §1 病因（两处，缺一不可）

**① 空目录被判成 `not_found`。** `context.py` L112-113：

```python
if not items:
    return kind, None, {"reason": "not_found"}
```

新会话的 `catalogs` 是空的 → "第一个数据" → `not_found`。但"目录还没建立"和"用户指的序号不存在"是两件事，被合并成了一件。

**② 只有 `stale` 会触发重列。** `workflow.py`：

```python
if pending and pending["reason"] == "stale" and not pending["asked"]:
```

`not_found` 直接走澄清分支 → 问用户 → 返回。第二轮 `asked=true` → "仍未确定" → **永久卡死**。

**合起来的后果**：任何**新会话的第一条消息**只要带序号，就必然死锁。而卡里指定的验收场景恰好就是这种消息。

## §2 允许改动的文件（越界即停）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/context.py` | 改（`resolve_reference` 的空目录判定，**1–3 行**） |
| `src-python/spectrumagent/agent/workflow.py` | 改（重列触发条件，**1–3 行**） |
| `src-python/tests/agent/test_context_references.py` | 改（新增冷启动用例） |
| `src-python/tests/agent/test_conversation_workflows.py` | 改（新增端到端冷启动用例） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行） |

## §3 明确不做

- 不改澄清话术、不改 `only_one` 语义、不改 `asked` 的两轮上限。
- 不新增工具、不改任何工具 schema 或描述。
- 不动 `select()`、`CLEAR_ON_DATASET`、`requested_stages`。
- 不做"自动选第一条数据"——**必须列出后再按序号解析**，不许猜。

## §4 实现要求

**① 空目录 → `stale`（需要先列），而不是 `not_found`**

规则要能区分两种空：

- **目录键不存在**（新会话，从未列过）→ `{"reason": "stale"}` → 触发重列。
- **目录键存在但 `items` 为空**（例如 `propose` 返回 `need_seed` 后主动清空候选目录）→ 保持 `{"reason": "not_found"}`。

```python
catalog = state.get("catalogs", {}).get(kind)
if index is not None:
    if not catalog or "items" not in catalog:      # 从未列过
        return kind, None, {"reason": "stale"}
    if not catalog["items"]:                       # 已知为空
        return kind, None, {"reason": "not_found"}
    ...
```

**② 重列条件加上"目录仍为空"**

```python
catalog = state.get("catalogs", {}).get(pending["kind"]) if pending else None
needs_list = not catalog or not catalog.get("items")
if pending and not pending["asked"] and (
        pending["reason"] == "stale" or (pending["reason"] == "not_found" and needs_list)):
    ... 原重列逻辑不动 ...
```

这样：新会话首条消息 → 列一次 → 再解析 → 命中 → 继续走模型；用户指了不存在的序号（目录有 3 项、他说第 9 个）→ `not_found` 且 `needs_list` 为假 → 直接澄清，不浪费一次读取。

**③ 重列产生的 step 必须仍无 `tool_call_id`**（L0 的四级证据依赖这一点），不得改动。

## §5 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 纯函数：空 state + `"第一个数据"` | 返回 `reason == "stale"`，**不是 `not_found`** |
| B | 纯函数：`catalogs.candidate.items == []` + `"第一个候选"` | 仍返回 `not_found`（已知为空，不重列） |
| C | 端到端：**新建会话**，第一条消息 `对第一个数据标注 PP，其余背景，参数默认，保存后做预处理` | 事件序列里**出现 `step datasets.list`**（控制器重列），随后**调用模型**（`llm_call` 新增一行），不得只回 clarify |
| D | 端到端：目录有 3 项、用户说"第 9 个数据" | 澄清一次，**不触发重列** |
| E | 回归 | `src-python/tests/agent` 全绿（≥436）；`src-python/tests backend/tests --ignore=src-python/tests/agent` 全绿（≥976） |
| F | **真实模型重跑**（科祥执行） | `--data-root "$env:LOCALAPPDATA\SpectrumAgent"`，至少过 L2，并贴完整输出 |

**C 是本卡的核心**：它必须证明"新会话首条带序号的消息能走到模型"，而不是靠预热过的夹具。

## §6 证据与提交

- 建议两笔：`context.py`+测试 / `workflow.py`+测试；或单笔 `fix(agent): 冷启动引用先列目录再解析`。
- 回报附：A/B 两个纯函数返回值、C 的完整 SSE 事件序列（含 `step datasets.list`）、`llm_call` 新增行数、两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

两笔各自 revert。回滚后退回"新会话首条带序号即澄清"，不影响已有数据。
