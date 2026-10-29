# TASK-11f · L2b 比较阶段推进（小卡）

日期：2026-10-29　基准 commit：`d1d8289`　预估：20 分钟　前置：L2 已落地
**顺序：本卡先于 L2c（规则表 + protocol_version）**——它修的是 L2 留下的一个真实缺陷，改动面只有三处。

## §0 状态确认（先跑，不符即停）

```bash
git log --oneline -1                                   # 期望 d1d8289
rg -n "stages_done" src-python/spectrumagent/agent/context.py
rg -n "run_count" src-python/spectrumagent/agent/tools/__init__.py   # 期望 L292
```

期望看到 `stages_done` 只有 **两处写入**（`annotations.draft_confirm` → `annotation`+`save`；`preprocess.run_default` 成功 → `preprocess`），**没有 `compare`**。

缺陷判据探针（**必须走 `observe`，即本卡唯一获准修改的生产路径**；2026-10-29 已实测第一版，codex 复跑确认）：

```bash
.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'src-python'); sys.path.insert(0,'.')
from spectrumagent.agent import context as m
from spectrumagent.agent.task import evaluate_task
base={'annotation_version_id':'AV','last_run_id':'R1',
      'requested_stages':['annotation','save','preprocess','compare'],
      'stages_done':['annotation','save','preprocess']}

# A：生产路径 —— 比较真的跑完，经 observe 进入会话状态
st = m.observe(dict(base), 'preprocess.compare', {}, {'run_count': 2})
print('A', evaluate_task(st, {'run_status':'succeeded'}), '| stages_done', st.get('stages_done'))

# B：判据层对照 —— 手工补齐 stages_done，证明 evaluate_task 本身未被改动
control = dict(base, stages_done=['annotation','save','preprocess','compare'])
print('B', evaluate_task(control, {'run_status':'succeeded'}))
"
```

| 时机 | A（生产路径） | B（判据层对照） |
|---|---|---|
| **修复前** | `working`（`stages_done` 无 compare）—— **缺陷现场** | `succeeded` |
| **修复后** | `succeeded`（`stages_done` 含 compare） | `succeeded` |

**A 必须翻转，B 必须始终不变。** A 不翻 = 修复没生效；B 变了 = 有人动了 `evaluate_task`（越界）。

> 说明：本卡不改 `evaluate_task`，所以任何**绕过 `observe`** 的探针在修复前后输出都一样、无法证明修复有效。第一版探针直接喂手构 state，属设计错误，已按此版取代；原版输出仅作对照留档。

## §1 本卡解决的问题

**用户说"与默认配方比较"之后，任务能真正到达 `succeeded`。**

现状：`requested_stages` 值域含 `compare`，但 `stages_done` 从没有 `compare` 的写入点 → `requested <= stages_done` 永不成立 → 永远 `working`。

## §2 允许改动的文件（越界即停）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/context.py` | 改（`observe` 内**新增一个 if 块，3 行**） |
| `src-python/tests/agent/test_conversation_workflows.py` | 改（**仅 L278 那一条**加 `task_result` 断言） |
| `src-python/tests/agent/test_stages.py` | 改（新增 1–2 条单测） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行进度） |

## §3 明确不做

- **不改 `_successful()`**（`test_conversation_workflows.py` L46-50）。它是全文件共用的宽松判定，改它会影响几十条用例的语义；盲区用**用例内显式断言**补，不动公共 helper。
- 不改 `requested_stages` 的值域、不改 `evaluate_task` 的判据、不改 `preprocess.compare` 工具本身。
- 不顺手做规则表抽离或 `protocol_version`——归 L2c。

## §4 实现要求

在 `observe` 里、紧跟 `preprocess.run_default` 成功推进那段之后，新增：

```python
if tool == "preprocess.compare" and result.get("run_count"):
    state["stages_done"] = sorted(set(state.get("stages_done") or ()) | {"compare"})
```

判据说明：`preprocess.compare` 的工具出参里有 `run_count`（`tools/__init__.py` L292 构造），用它判断"比较真的产生了 run"，而不是"工具被调用过"。

测试两处：

1. `test_conversation_workflows.py` L278 现在只调 `_successful(...)` 不校验结果，改为接收返回值并断言：

```python
compared_result = _successful(_events(c.client, c.session_id, "新建仅SNV配方，与默认配方比较"))
assert compared_result["task_result"] == "succeeded"
```

**这条断言在修复前必然是红的**（就是 §0 的 `A working`），修复后才绿——它本身就是回归测试。

2. `test_stages.py` 增一条单测：`observe(state, "preprocess.compare", {}, {"run_count": 2})` 后 `stages_done` 含 `compare`；再补一条反例：`{"run_count": 0}` 时**不含**。

## §5 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | §0 探针 | **修复前 `A working` / `B succeeded`；修复后 `A succeeded` / `B succeeded`**。A 未翻转或 B 发生变化都算不合格 |
| B | L278 新断言 | 通过（修复前应红，需在回报里贴修复前那条失败输出） |
| C | `test_stages.py` 新增两条单测 | 通过 |
| D | `src-python/tests/agent` | **435 passed**（原 434 + 新增 1 条单测；若拆成两条则 436） |
| E | `src-python/tests backend/tests --ignore=src-python/tests/agent` | 仍 **976 passed** |

## §6 证据与提交

- 单 commit，`fix(agent): 比较阶段完成后推进任务状态`。
- 回报附：§0 探针**修复前与修复后两版完整输出**（A/B 两行都要，且 A 必须从 `working` 翻成 `succeeded`）、L278 那条断言**修复前的失败输出**、两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

单 commit revert。`compare` 只是多写一个 `stages_done` 成员，回滚后任务退回 `working`（原行为），无数据影响。
