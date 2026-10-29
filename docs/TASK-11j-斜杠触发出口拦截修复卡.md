# TASK-11j · 修「模型回复含斜杠 → 后续轮次全部 EGRESS_BLOCKED」

日期：2026-10-29　基准 commit：`ab56487`　预估：1 小时　前置：无
**优先级：高于 L4 的数据问题**——这条会让真实用户在多轮对话里直接卡死。

## §1 缺陷现场（2026-10-29 真实模型实测）

```
TURN 2  done: "…建议换一个更有代表性的 PP 区域重新指认——比如靠近目标中心的、避开边缘/阴影的部分。请再描一笔。"
TURN 3  SSE error {"code": "EGRESS_BLOCKED", "detail": "EGRESS_BLOCKED", "task_result": "failed"}
```

TURN 3 的用户消息是正常的「接受候选，其余背景，保存后做预处理」，没有任何路径内容，却被拒。

## §2 病因

`agent/llm.py` L136：

```python
_DENY_TEXT = re.compile(r"[a-z]:|\\|/[^\s/]+|\.(?:img|hdr|mat)\b|\blabel_map\b", re.I)
```

`/[^\s/]+` 的意思是「**斜杠后面跟非空白**」——本意是拦 `/home/x`、`C:/data` 这类路径。但它同时命中**中文散文里的斜杠**：TURN 2 的模型回复里有「边缘**/**阴影」，于是这条 assistant 文本进入下一轮的 history，整个 prompt 被判定为含路径 → `EGRESS_BLOCKED`。

**这是自锁**：一旦模型某轮用了斜杠，该会话之后每一轮都被拒，用户看到的是"模型坏了"。

`tools/workflows.py` 的 `comparison_notes()` 早就踩过同一个坑并打了补丁（把服务端文本里的 `/` 换成 `或`，注释写明"the unchanged egress path guard deliberately rejects"）——但那个补丁只覆盖**服务端生成**的文本，**没有覆盖模型自己写的散文**。

**中文技术语境里斜杠极常见**（`SNV/SG`、`输入/输出`、`A/B`、`训练/测试`），所以这不是边角情况。

## §3 允许改动的文件

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/llm.py` | 改（`chat()` 内、`_egress_blocked` 之前，加一次 assistant 文本规范化） |
| `src-python/tests/agent/test_llm.py` | 改（新增回归用例） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行） |

## §4 明确不做

- **不放宽 `_DENY_TEXT`**。它是安全护栏，改正则会削弱对真实路径的拦截。
- 不改 `_egress_blocked` 的判定语义、不改 `tools` 的扫描。
- 不处理 `user` / `system` 角色的文本——用户输入里真出现路径**就该拦**。
- 不在提示词里要求模型"不要用斜杠"——那是治症状，且不可靠。

## §5 实现要求

在 `OpenAICompatibleClient.chat()` 里，`_egress_blocked(...)` 调用**之前**，对**仅 `role == "assistant"` 的 `content`** 做字符替换：

| 原字符 | 替换为 | 理由 |
|---|---|---|
| `/` | `／`（全角 U+FF0F） | 视觉几乎无差别，绕开 `/[^\s/]+` |
| `\` | `＼`（全角 U+FF3C） | 同上 |

要点：

- 只改 `content` 字符串；不动 `tool_calls`、不动 `arguments`、不动 `name`。
- 就地构造新 list，**不修改传入的 `messages` 对象**（调用方还要用它算 `digest`，且不该被副作用影响）。
- 规范化后再算 `digest` 与做 `_egress_blocked` 扫描，顺序必须是：**先规范化 → 再 digest → 再扫描**。
- 函数抽成 `_egress_safe_assistant(messages)`，纯函数，可单测。

## §6 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 单测：messages 里有一条 `{"role":"assistant","content":"避开边缘/阴影"}` | `chat()` 不再抛 `EGRESS_BLOCKED`；传给 transport 的 assistant content 里 `/` 已变 `／` |
| B | 单测：`{"role":"user","content":"打开 E:/data/a.hdr"}` | **仍然抛 `EGRESS_BLOCKED`**（用户输入路径必须拦） |
| C | 单测：assistant content 里含 `SNV/SG 与 输入/输出` | 不抛；两个斜杠都被替换 |
| D | 单测：传入的 `messages` 对象在调用后**未被修改**（`==` 原值） | 通过 |
| E | 真实模型重跑（科祥执行）：`--seed 115,320 --message "对第二个数据标注 PP…"` | TURN 3 不再出现 `EGRESS_BLOCKED`；L1/L2/L3 PASS |
| F | 回归 | `src-python/tests/agent` 全绿（≥438）；非 agent 全绿（≥976） |

## §7 证据与提交

- 单 commit，`fix(agent): 模型回复中的斜杠不再触发出口拦截`。
- 回报附：A–D 四条单测的实际断言与通过输出、E 的完整 TURN 3 事件、两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §8 回滚

单 commit revert。回滚后回到"模型用斜杠即自锁"，不影响数据。
