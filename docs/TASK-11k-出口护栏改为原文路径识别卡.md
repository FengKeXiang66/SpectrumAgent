# TASK-11k（修订版）· 出口护栏：不动正则，assistant 命中即整条脱敏

日期：2026-10-29　基准 commit：`37a6cf8`　预估：1 小时　前置：无
**本卡取代 11j 的全角方案；同时撤回本卡第一版"改正则 + 片段脱敏"的设计。**

## §1 为什么推翻 11j（三条实测）

| 论断 | 实测 |
|---|---|
| 全角转换能阻止路径外泄 | **错**：`NFKC("／mnt／nas／data")` → `/mnt/nas/data`，无损还原 |
| 11j 没改变护栏覆盖范围 | **错**：assistant 的 `/mnt/nas/data` 规范化后 `_egress_blocked` 返回 **False（放行）** |
| 全角方案可复用到 user | **错**：该函数同时替换 `\`，先把 `\\nas\share` 变全角，反斜杠硬拦就看不到原文 |

## §2 为什么撤回本卡第一版（改正则 + 片段脱敏）

**① 片段替换会留残留。** 用第一版的 `_DENY_TEXT` 直接做 `sub("[隐藏]")`：

| 原文 | 替换后（残留可读） |
|---|---|
| `E:\data\a.hdr` | `[隐藏]data\a[隐藏]` |
| `\\nas\share\x.hdr` | `[隐藏]nas\share\x[隐藏]` |
| `\\nas\share\secret` | `[隐藏]nas\share\secret` |
| `/mnt/private data/report` | `[隐藏] data/report` |

**检测路径标记 ≠ 提取完整路径。** 同一个正则不能兼任两件事。

**② 收窄正则会误伤新的正常语句。** 第一版的 POSIX 分支没有起始边界：

| 文本 | 第一版结果 |
|---|---|
| `SNV/SG/MSC` | 命中 `/SG/MSC` → 误拦 |
| `A/B/C` | 命中 `/B/C` → 误拦 |
| `https://example.com/help` | 盘符分支命中 `s:/` → 误拦 |

**③ 更关键：`SNV/SG` 与 `relative/cube` 在字符串层面存在通用形态歧义。** 而 `relative/cube` 等 16 条是现有测试明确要求拦截的（`src-python/tests/agent/test_llm.py` L45-47）。想放行 `SNV/SG`，至少要处理与 `relative/cube` 的歧义——那是**产品/安全取舍**，不该夹在一张修 bug 的卡里顺手做。

（注：这不等于"必须同时放行 `private\cube`、`./cube`、`../cube`、`C:`"。它们形态各不相同，可以分别制定规则；只是这些决定都属于产品边界讨论，不属本卡。）

## §3 本卡的机制（保留既有检测规则，限定改动范围）

**`_DENY_TEXT` 一个字都不改。**

只改一处：`chat()` 内，**assistant 角色**的 `content` 若命中 `_DENY_TEXT`，就把**整条 content 替换成 `[路径已隐藏]`**，然后照常发送。

| 角色 | 命中时 | 理由 |
|---|---|---|
| `assistant` | **整条替换为 `[路径已隐藏]`**，本轮照发 | 助手历史是我们自己的文本；整条替换不可能残留片段；解决自锁 |
| `user` / `system` | **硬拦**（现状不变） | 用户要立刻知道输入被拒、可改写 |
| `tools` / 工具参数 / `_NESTED_ARRAY` | **硬拦**（现状不变） | 共享规则不动，扫描能力不变 |

**明确代价**：assistant 那条消息里的其他说明会一起丢失。例如"默认参数已确认，接下来按 SNV/SG 顺序处理"整条消失，用户下一句说"按刚才的来"时，模型可能需要重新确认。

准确表述（不得写成"零回归"）：

> 可能丢失同条助手说明，影响后续上下文理解；原始会话记录保留（`save_answer` 存原文），模型侧必要时重新确认。

正则不变只证明**检测规则**没被改写，不能证明**行为**没有回归——上面这条上下文丢失就是行为变化。

**11j 的 `_egress_safe_assistant` 整个删除**，不再做任何字符替换。

## §4 允许改动的文件

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/llm.py` | 改（删 `_egress_safe_assistant`；新增 `_redact_assistant_paths`；`chat()` 内调整顺序） |
| `src-python/tests/agent/test_llm.py` | 改（11j 的 A–D 四条按新语义重写；新增整条脱敏与共享护栏回归） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行，注明 11j 机制被取代、11k 落地） |

## §5 明确不做

- **不改 `_DENY_TEXT`**、不改 `_NESTED_ARRAY`、不改 `_egress_blocked` 的判定语义。
- **不放宽 user 侧**。`用SNV/SG做预处理` 仍会被拦——这是既有产品决定，见 §8 待决清单。
- 不实现"完整路径片段提取器"（无法可靠定边界时反而更危险）。
- 不动 `state.py`、不动任何工具 schema。

## §6 实现要求

### 6.1 `_redact_assistant_paths(messages)`

```python
def _redact_assistant_paths(messages):
    """Redact the whole assistant message when it carries a path-like token.

    Whole-message replacement, not span substitution: a marker regex cannot
    determine the span of the real path, so partial replacement leaks the rest.
    """
    safe = []
    for message in messages:
        message = dict(message)
        if message.get("role") == "assistant" and isinstance(message.get("content"), str) \
                and _DENY_TEXT.search(message["content"]):
            message["content"] = "[路径已隐藏]"
        safe.append(message)
    return safe
```

要求：复制 dict、不改传入对象、不改 `tool_calls` / `arguments` / `name`。

### 6.2 `chat()` 内的顺序（写死）

```
0) if _NESTED_ARRAY.search(_json({"messages": messages, "tools": tools})): raise EGRESS_BLOCKED
1) messages = _redact_assistant_paths(messages)     ← 只处理 assistant
2) digest = sha256(_json(messages))                 ← 对实际发送内容取摘要
3) if _egress_blocked({"messages": messages, "tools": tools}): raise EGRESS_BLOCKED
4) _workflow_wire(messages, tools)
```

**第 0 步不可省（本卡的关键顺序）。** 若先脱敏再扫描，`assistant` 同时含普通斜杠与坐标数组时（如 `a/b [[1,2],[3,4]]`），整条会被替换成 `[路径已隐藏]`，`_NESTED_ARRAY` 就再也看不到那组坐标——**"坐标数组必定硬拦"这条契约被静默改变**。虽然内容已删除、没有外发，但行为契约变了，必须用第 0 步在**原始待发上下文**上先判定。

**第 0 步只查 `_NESTED_ARRAY`，不调完整 `_egress_blocked`**——否则普通斜杠会再次造成自锁。

**第 3 步之后仍可能被拦的来源**（不得在卡或文档里声称"只剩 user/system"）：user 与 system 的 content、`tools` 定义与参数、`_NESTED_ARRAY` 坐标数组。

## §7 验收

### 7.1 现有语料必须全部仍被拦（回归，**16 条**不动）

`test_llm.py` L45-47 的参数表共 **16 条**：14 个字符串（`C:`、`D:/private/cube`、`\\nas\share\cube`、`private\cube`、`/nas/cube`、`relative/cube`、`./cube`、`../cube`、`cube.img`、`CUBE.HDR`、`training.MAT`、`[[1,2],[3,4]]`、`[ [1,2], [3,4]]`、`label_map`）+ 2 个字典（`{"points": [[1,2],[3,4]]}`、`{"label_map": [0,1]}`）。作为 **user** 内容时全部仍返回 `EGRESS_BLOCKED`。**一条都不许改。**

补充说明：`content` 为**字典**时，`_redact_assistant_paths` 的 `isinstance(..., str)` 判定不成立 → 不脱敏 → 仍由 `_egress_blocked` 硬拦。这是有意保留的。

### 7.2 整条脱敏（新增，核心）

| assistant 内容 | 期望 |
|---|---|
| `避开边缘/阴影的部分` | 不拦；发送内容为 `[路径已隐藏]` |
| `读取 \\nas\share\secret` | 不拦；发送内容为 `[路径已隐藏]`，且**不含** `nas`、`share`、`secret` 任何片段 |
| `E:\data\a.hdr` | 不拦；发送内容为 `[路径已隐藏]` |
| `数据集 cube-1，类 PP，指标 1.0` | 不拦；**发送内容与原文完全一致**（无命中不得改动） |
| 调用后传入的 `messages` 对象 | **未被修改**（`==` 原值） |
| `llm_call.prompt_sha256` | 等于**脱敏后**消息的摘要（审计对应实际发送内容，不是原文） |

### 7.3 共享护栏回归（新增）

| 用例 | 期望 |
|---|---|
| user `打开 E:/data/a.hdr` | 仍 `EGRESS_BLOCKED`，transport 未调用 |
| tools 定义里塞 `{"description":"读取 \\nas\share\cube"}` | 仍 `EGRESS_BLOCKED` |
| 工具参数里塞 `{"path":"D:/private/cube"}` | 仍 `EGRESS_BLOCKED` |
| `[[1,2],[3,4]]`（`_NESTED_ARRAY`） | 仍 `EGRESS_BLOCKED` |

这四条证明"扫描范围与扫描能力都没变"。

### 7.3b 组合用例（证明处理顺序正确，比四条独立用例更硬）

| 用例 | 期望 |
|---|---|
| assistant `a/b [[1,2],[3,4]]`（普通斜杠 + 坐标数组同时出现） | **仍 `EGRESS_BLOCKED`，transport 未调用**（第 0 步在原文上命中数组） |
| assistant content 命中路径被脱敏，但**同条消息的 `tool_calls.arguments` 含路径** | **仍 `EGRESS_BLOCKED`，transport 未调用**（脱敏不覆盖参数，第 3 步兜住） |

第二条尤其重要：它证明"整条替换 content"不会顺带放过同一消息里的工具参数。

### 7.4 确定性多轮（新增，取代"等真实模型碰巧写斜杠"）

```
第 1 轮：assistant 回复固定含 "避开边缘/阴影"（通过第一轮真实返回值构造，不是静态 chat 调用）
第 2 轮：发一条普通用户消息
断言：第 2 轮请求确实发出（transport 被调用）；transport 收到的该条 assistant 内容为 [路径已隐藏]
```

必须**真的走两轮**，不能只做一次静态 `chat()` 调用。

### 7.5 回归

`src-python/tests/agent` 全绿；`src-python/tests backend/tests --ignore=src-python/tests/agent` 全绿（≥976）。

## §8 待决清单（不在本卡范围，需单独立项）

用户侧误拦仍在，逐类决定后才能放宽。至少要回答：

| 类别 | 现状 | 待决问题 |
|---|---|---|
| `SNV/SG`、`A/B`、`训练/测试` | 拦 | 正常技术表达要不要放行？放行就等于放行 `relative/cube` |
| `relative/cube`、`data/raw` | 拦 | 相对路径算不算敏感信息？ |
| `./cube`、`../cube` | 拦 | 同上 |
| `C:`（仅盘符） | 拦 | 无分隔符的盘符引用要不要继续拦？ |
| `https://example.com` | 拦（盘符分支命中 `s:/`） | URL 是否允许？需单独定义，不能交给盘符规则偶然决定 |
| `/data`（单段 POSIX 绝对） | 拦 | 本产品 Windows 单机，威胁面内是否有此形态？ |

**在这些问题有结论之前，不改正则。**

## §9 完成口径与发布说明

**本卡的完成口径（只到这里，不得扩大）：**

> 助手历史命中既有路径规则时，整条脱敏后继续；**用户技术表达中的斜杠误拦仍待单独处理**。

不得把"整个斜杠误拦问题"标记为完成——用户侧 `用SNV/SG做预处理` 仍会被拒。

**发布说明（修正两处表述）：**

1. **L4**：只能确定"候选 `min_similarity` 低于入队下限 0.8"，**不足以归因于标定问题**——种子代表性、数据特性、算法行为都还需要判断。
2. **11k**：写"**计划取代** 11j 的全角方案"，不写"已取代"。落地并通过测试后再更新状态。

## §10 回滚

单 commit revert 后回到 `c56277c` 的全角方案（用户斜杠仍误拦、assistant 的 POSIX 路径仍会放行）。两个状态都不理想，本卡应尽快落地。
