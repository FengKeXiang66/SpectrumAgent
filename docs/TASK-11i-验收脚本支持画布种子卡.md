# TASK-11i · 验收脚本支持画布种子（打通 L4）

日期：2026-10-29　基准 commit：`60b0dbd`　预估：40 分钟　前置：L1b 已落地
**顺序：本卡之后立刻由科祥重跑真实模型，L4 才有意义。**

## §1 问题：L4 在结构上不可达

`scripts/e2e_task10.py` 的 `send_message` 只发 `{"content": ...}`，全文没有任何 gesture POST。而 `annotations.propose` 无手势必然返回 `need_seed`。所以脚本永远走不到"接受候选 → 保存 → 预处理"，L4 必然红。

2026-10-29 真实模型实测（L1/L2/L3 全过，L4 红）：

```
NATIVE_TOOL_SEQUENCE: [annotations.context, annotations.ensure_labels, annotations.prepare]
done: "…请在画布上用工作区手势指认一块可信的 PP 区域…"
FAIL at L4: no new saved annotation paired with a new succeeded preprocessing run
```

**模型的最后一句是正确行为**（它没有假装识别 PP），缺的是脚本没给种子。

## §2 允许改动的文件（越界即停）

| 文件 | 动作 |
|---|---|
| `scripts/e2e_task10.py` | 改 |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行） |

## §3 明确不做

- **不改任何生产代码**（`src-python/spectrumagent/**` 一律不动），不改工具、不改判定阈值、不改 L1–L4 的通过条件。
- 不因为"L4 过不了"而放宽判据。
- 不在脚本里伪造 gesture_ref、不直接写数据库、不跳过 HTTP。

## §4 实现要求

### 4.1 发消息支持 workspace

```python
def send_message(base, token, session_id, content, workspace=None, timeout=240):
    body = {"content": content}
    if workspace:
        body["workspace"] = workspace
```

`ContentMessage` 已有 `workspace: Workspace | None` 字段（`api/agent.py` L27-29），不需要改后端。

### 4.2 新增 `--seed row,col`

给出时：**在第一条消息之后、第二条消息之前**，调用

```
POST /api/v1/annotations/{cube_id}/gestures   body {"seed": {"point": [row, col]}}
```

返回体里的 `gesture_ref` 记进报告。`cube_id` 取第一条消息事件流里**最后一条 `workspace` 事件的 `cube_id`**。

**注意（易错）**：计划审批会把 `workspace` 丢掉——`StateMachine.message` 在识别到"继续/批准"后走 `message(plan_id=..., action="approve")`，不携带 workspace。所以**承载种子的是那次 POST**（`store_gesture` 已把种子登记到会话），`propose` 在 `gesture_ref` 缺省时会回落到"最近一次手势"。workspace 仍照传（更真实），但**不要依赖它**。

### 4.3 轮次与默认文案

| 参数 | 默认 | 说明 |
|---|---|---|
| `--turns` | 给了 `--seed` 时 **3**，否则 2 | 少了走不完 |
| `--message` | 不变 | 第 1 条 |
| `--follow-up` | `继续` | 第 2 条（审批计划） |
| `--accept-message` | `接受候选，其余背景，保存后做预处理` | 第 3 条，仅 `--seed` 且 `--turns>=3` 时使用 |

`--seed` 解析：`"row,col"` 两个整数，越界或格式错直接 `parser.error`。报告里记 `seed` 与 `gesture_ref`。

### 4.4 报告增字段

`report` 增加 `"seed"`、`"gesture_ref"`、`"turns_sent"`，其余字段不动。

## §5 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | **不带** `--seed` 跑一次（用 mock provider 或真实均可） | 行为与改动前完全一致：事件序列里**没有** `annotations.propose`，L4 仍失败并给出同一句原因。证明默认路径没被破坏 |
| B | 带 `--seed 115,320`，`--turns 3` | 事件序列出现 `annotations.propose`；随后按模型行为可能出现 `apply_candidate` / `set_background` / `draft_confirm`。**L4 通过或如实打印停点**，不得改写判据 |
| C | B 的 `native_tool_sequence` 必须完整贴出 | 若模型走到 `preprocess.run_default`，报告要能看出它**是否先调过** `preprocess.recipe_ensure` / `preprocess.recipes`（这是悬了两轮的问题） |
| D | 回归 | `src-python/tests/agent` ≥438；`src-python/tests backend/tests --ignore=src-python/tests/agent` ≥976（脚本不在测试集内，但确认没误伤） |

## §6 证据与提交

- 单 commit，`test(e2e): 验收脚本支持画布种子`。
- 回报附：A 与 B 两次运行的完整事件序列（或指向 `.runtime` 的报告路径）、`native_tool_sequence`、两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

单 commit revert。回滚后脚本回到"只能验到 L3"，不影响任何生产代码与数据。
