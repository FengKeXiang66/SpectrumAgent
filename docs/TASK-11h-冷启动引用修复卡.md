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
| `src-python/spectrumagent/agent/context.py` | 改（`resolve_reference`：加"从未列过"分支 + 把空判据挪到过期判据之后，**约 5 行**） |
| `src-python/tests/agent/test_context_references.py` | 改（新增冷启动与空目录用例） |
| `src-python/tests/agent/test_conversation_workflows.py` | 改（新增端到端冷启动用例） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行） |

**`workflow.py` 不在清单内**——按 §4② 的新解法，它的重列逻辑原样可用。

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

**② 把"空"的判据挪到"过期"之后 —— 这样 `workflow.py` 一行都不用改**

原来 `if not items` 排在 `stale` 判定**之前**，于是"上轮列过、当时为空、之后用户导入了数据"永远停在 `not_found`，自愈不了。把顺序换过来：

```python
if kind is None:
    return None, None, {"reason": "not_found"}
catalog = state.get("catalogs", {}).get(kind)          # None = 从未列过
items = catalog.get("items", []) if catalog is not None else []
if index is not None:
    if catalog is None:                                  # ① 从未列过
        return kind, None, {"reason": "stale"}
    if catalog.get("round_id") is None or (
            (not items or (not noun and not short)) and recent_round_ids is not None
            and catalog["round_id"] not in recent_round_ids):
        return kind, None, {"reason": "stale"}            # ② 快照过期（空目录也自愈）
    if not items:                                         # ③ 刚列过且确实为空
        return kind, None, {"reason": "not_found"}
    item = next((item for item in items if item["ordinal"] == index), None)
    return (kind, item, None) if item else (kind, None, {"reason": "only_one" if len(items) == 1 else "not_found"})
```

**② 里的 `(not items or (not noun and not short))` 是本卡第二个必改点**：原条件只有裸序号（无类型名、无短引用）才检查快照过期，于是"第一个**候选**"这种带类型名的说法会跳过过期检查，空目录永远自愈不了。加上 `not items` 后：**空目录无论带不带类型名都走过期自愈**，有内容的目录仍按原规则（只有裸序号才检查过期）。

四种情形各自归位：

| 情形 | 命中分支 | 行为 |
|---|---|---|
| 新会话从未列过 | ① `catalog is None` | 重列一次，再解析 |
| 上轮列过、当时为空，之后导入了数据（无论"第一个"还是"第一个数据"） | ② 空目录 + round_id 过期 | 重列 → 自愈 |
| **同一轮内**刚列过且为空 | ③ `not items` | 直接澄清，不重列 |
| 目录有 N 项、用户说第 N+1 个 | ③ 之后的 `item is None` | 直接澄清，不重列 |

**所以 `workflow.py` 不需要改。** 第一版卡在 §4② 写了 `needs_list = not catalog.get("items")`（会把已知空目录也重列），与用例 B 自相矛盾；正确解法不是给 `needs_list` 打补丁，而是**把空判据挪到过期判据之后**——`stale` 本来就重列，自愈能力白拿，改动面反而更小。

**③ 重列产生的 step 必须仍无 `tool_call_id`**（L0 的四级证据依赖这一点），不得改动。

## §5 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 纯函数：空 state + `"第一个数据"` | 返回 `reason == "stale"`，**不是 `not_found`** |
| B | 纯函数：`catalogs.candidate` 存在、`items == []`、`round_id` **属于当前最近轮次** + `"第一个候选"` | 返回 `not_found`，不触发重列，直接澄清一次 |
| B2 | 纯函数：同上但 `round_id` **不属于**当前最近轮次，且内容带类型名（`"第一个候选"`） | 返回 `stale`（带类型名的空目录也必须自愈） |
| B3 | 纯函数：目录**有 2 项**、`round_id` 过期、内容带类型名（`"第二个候选"`） | **不返回 `stale`**，按现有目录解析出第 2 项（有内容的目录保持原规则，只有裸序号才查过期） |
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
