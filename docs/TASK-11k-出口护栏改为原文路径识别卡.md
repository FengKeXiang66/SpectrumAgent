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

**③ 更关键：`SNV/SG` 与 `relative/cube` 在字符串层面同构。** 而 `relative/cube`、`private\cube`、`./cube`、`../cube`、`C:` **是现有测试明确要求拦截的**（`src-python/tests/agent/test_llm.py` L45-46 的 13 条语料）。想放行前者就必须放宽后者——那是**产品/安全取舍**，不该夹在一张修 bug 的卡里顺手做。

## §3 本卡的机制（最小、零回归）

**`_DENY_TEXT` 一个字都不改。**

只改一处：`chat()` 内，**assistant 角色**的 `content` 若命中 `_DENY_TEXT`，就把**整条 content 替换成 `[路径已隐藏]`**，然后照常发送。

| 角色 | 命中时 | 理由 |
|---|---|---|
| `assistant` | **整条替换为 `[路径已隐藏]`**，本轮照发 | 助手历史是我们自己的文本；整条替换不可能残留片段；解决自锁 |
| `user` / `system` | **硬拦**（现状不变） | 用户要立刻知道输入被拒、可改写 |
| `tools` / 工具参数 / `_NESTED_ARRAY` | **硬拦**（现状不变） | 共享规则不动，扫描能力不变 |

**明确代价**：assistant 那条消息里的其他说明会一起丢失。这是保守版本的已知取舍——本轮能继续，比整轮卡死好。

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
1) messages = _redact_assistant_paths(messages)     ← 只处理 assistant
2) digest = sha256(_json(messages))                 ← 对实际发送内容取摘要
3) if _egress_blocked({"messages": messages, "tools": tools}): raise EGRESS_BLOCKED
4) _workflow_wire(messages, tools)
```

**第 3 步之后仍可能被拦的来源**（不得在卡或文档里声称"只剩 user/system"）：user 与 system 的 content、`tools` 定义与参数、`_NESTED_ARRAY` 坐标数组。

## §7 验收

### 7.1 现有语料必须全部仍被拦（回归，13 条不动）

`test_llm.py` L45-46 那 13 条（`C:`、`D:/private/cube`、`\\nas\share\cube`、`private\cube`、`/nas/cube`、`relative/cube`、`./cube`、`../cube`、`cube.img`、`CUBE.HDR`、`training.MAT`、`[[1,2],[3,4]]`、`[ [1,2], [3,4]]`）作为 **user** 内容时全部仍返回 `EGRESS_BLOCKED`。**一条都不许改。**

### 7.2 整条脱敏（新增，核心）

| assistant 内容 | 期望 |
|---|---|
| `避开边缘/阴影的部分` | 不拦；发送内容为 `[路径已隐藏]` |
| `读取 \\nas\share\secret` | 不拦；发送内容为 `[路径已隐藏]`，且**不含** `nas`、`share`、`secret` 任何片段 |
| `E:\data\a.hdr` | 不拦；发送内容为 `[路径已隐藏]` |
| `数据集 cube-1，类 PP，指标 1.0` | 不拦；**发送内容与原文完全一致**（无命中不得改动） |

### 7.3 共享护栏回归（新增）

| 用例 | 期望 |
|---|---|
| user `打开 E:/data/a.hdr` | 仍 `EGRESS_BLOCKED`，transport 未调用 |
| tools 定义里塞 `{"description":"读取 \\nas\share\cube"}` | 仍 `EGRESS_BLOCKED` |
| 工具参数里塞 `{"path":"D:/private/cube"}` | 仍 `EGRESS_BLOCKED` |
| `[[1,2],[3,4]]`（`_NESTED_ARRAY`） | 仍 `EGRESS_BLOCKED` |

这四条证明"扫描范围与扫描能力都没变"。

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

## §9 发布说明（修正两处表述）

1. **L4**：只能确定"候选 `min_similarity` 低于入队下限 0.8"，**不足以归因于标定问题**——种子代表性、数据特性、算法行为都还需要判断。
2. **11k**：写"**计划取代** 11j 的全角方案"，不写"已取代"。落地并通过测试后再更新状态。

## §10 回滚

单 commit revert 后回到 `c56277c` 的全角方案（用户斜杠仍误拦、assistant 的 POSIX 路径仍会放行）。两个状态都不理想，本卡应尽快落地。
