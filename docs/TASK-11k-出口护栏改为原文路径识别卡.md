# TASK-11k · 出口护栏改为「原文路径识别 + 整段脱敏」（取代 11j 的全角方案）

日期：2026-10-29　基准 commit：`c56277c`　预估：2 小时　前置：无
**本卡推翻 `c56277c` 的实现机制，保留它想解决的问题。**

## §1 为什么推翻 11j 的机制（三条实测，非推断）

| 论断 | 实测结果 |
|---|---|
| 全角转换能阻止路径外泄 | **错**。`unicodedata.normalize("NFKC", "／mnt／nas／data")` → `/mnt/nas/data`，**无损还原** |
| 11j 没有改变护栏覆盖范围 | **错**。`assistant` 的 `/mnt/nas/data` 规范化后 `_egress_blocked` 返回 **False（放行）** |
| 全角方案可以直接复用到 user | **错**。该函数同时替换 `\`，先把 `\\nas\share` 变成全角，后面的反斜杠硬拦就再也看不到原文 |

结论：**改字符外观不等于消除信息**。红线要保护的是"路径信息不外泄"，必须**在原文上识别、把整段内容抹掉**，而不是换分隔符。

同时确认两条既有缺陷（不是 11j 引入，但同一条正则导致）：
- 用户输入 `用SNV/SG做预处理` / `对比 A/B 两种配方` / `训练/测试集怎么分` → 全部 `EGRESS_BLOCKED`；
- 英文 `Note: please…` 这类 `[a-z]:` 也会被误拦（`[a-z]:` 没有要求后面跟分隔符）。

## §2 新机制（两层，各司其职）

**第一层：正则只认无歧义的路径形态**（对**所有角色**生效）

```python
_DENY_TEXT = re.compile(
    r"[a-z]:[\\/]"          # 盘符绝对路径 E:/ 或 E:\
    r"|\\\\"                # UNC 起始双反斜杠
    r"|\.(?:img|hdr|mat)\b" # 数据文件扩展名
    r"|\blabel_map\b"
    r"|/(?:[^\s/]+/)+[^\s/]*"   # POSIX 绝对路径，至少两段 /mnt/nas/data
    , re.I)
```

**第二层：assistant 文本按原文匹配整段替换为占位符**（`[路径已隐藏]`），不阻断本轮

| 角色 | 命中路径时 | 理由 |
|---|---|---|
| `user` / `system` | **硬拦**（`EGRESS_BLOCKED`） | 用户要立刻知道输入被拒，可改写 |
| `assistant` | **整段脱敏后照常发送** | 助手历史是我们自己的文本，脱敏不丢用户意图，也不会自锁 |

**11j 的 `_egress_safe_assistant` 整个删除**（不再做任何字符替换）。审计摘要仍对应实际发送内容。

## §3 允许改动的文件

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/llm.py` | 改（`_DENY_TEXT` 换正则；删 `_egress_safe_assistant`；新增 `_redact_paths`；`chat()` 内调整顺序） |
| `src-python/tests/agent/test_llm.py` | 改（11j 的 A–D 四条按新语义重写 + 新增语料用例） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行，并注明 11j 机制被取代） |

## §4 明确不做

- 不做全角/同形字符替换（已证无效）。
- 不改 `tools` 的扫描范围、不改 `_NESTED_ARRAY`。
- 不因为"`A/B` 可能是相对路径"就放弃放行——**明确接受该歧义**，见 §7。
- 不动 `state.py` 的历史构造、不动任何工具 schema。

## §5 实现要求

### 5.1 `_redact_paths(text)`

```python
def _redact_paths(text):
    return _DENY_TEXT.sub("[路径已隐藏]", text)
```

只作用于 `role == "assistant"` 且 `content` 为 `str` 的消息；**不得改动 `tool_calls` / `arguments` / `name`**。

### 5.2 `chat()` 内的顺序（写死）

```
1) 复制 messages（不改传入对象）
2) assistant content → _redact_paths
3) digest = sha256(_json(messages))      ← 对实际要发送的内容取摘要
4) if _egress_blocked({"messages": messages, "tools": tools}): raise EGRESS_BLOCKED
5) _workflow_wire(messages, tools)
```

第 4 步之后仍然拦截的，只剩 user/system 里的路径——那是**应该**拦的。

## §6 验收

### 6.1 语料表（正反双向，逐条断言）

| 文本 | 角色 | 期望 |
|---|---|---|
| `用SNV/SG做预处理` | user | **放行** |
| `对比 A/B 两种配方` | user | **放行**（接受歧义，见 §7） |
| `训练/测试集怎么分` | user | **放行** |
| `边缘/阴影` | assistant | **放行**，且发送内容与原文一致（无命中） |
| `Note: please continue` | user | **放行**（`[a-z]:` 不再误伤英文冒号） |
| `打开 E:/data/a.hdr` | user | **拦截** |
| `打开 E:\data\a.hdr` | user | **拦截** |
| `读取 \\nas\share\x.hdr` | user | **拦截** |
| `/mnt/nas/data` | user | **拦截** |
| `x.hdr` | user | **拦截** |
| `/mnt/nas/data` | assistant | **不拦**，且发送内容为 `[路径已隐藏]` |
| `读取 \\nas\share\x.hdr` | assistant | **不拦**，发送内容里**没有** `nas`、`share`、`.hdr` 任何片段 |

最后两行是本卡的核心：**整段抹掉，不是换分隔符**。

### 6.2 确定性多轮用例（不依赖模型这次用了什么标点）

```
构造：第 1 轮 assistant 回复固定含 "避开边缘/阴影"；第 2 轮发一条普通用户消息。
断言：第 2 轮的请求确实发出（transport 被调用），且 assistant 历史里的 "/" 原样保留。
```

```
构造：第 1 轮 assistant 回复固定含 "/mnt/nas/data"；第 2 轮发普通消息。
断言：请求发出；transport 收到的 assistant 内容里该路径已被整体替换。
```

这两条取代"等真实模型碰巧写斜杠"的验证方式。

### 6.3 回归

- `src-python/tests/agent` 全绿（≥442，条数以新增为准）；
- `src-python/tests backend/tests --ignore=src-python/tests/agent` 全绿（≥976）。

## §7 已知取舍（必须写进文档，不许含糊）

1. **`A/B` 与相对路径 `a/b` 无法从字符串区分。** 本卡选择放行，代价是"单层相对路径"会通过。理由：红线针对的是 NAS **绝对**路径（盘符或 UNC），这两类仍被拦截。
2. **单段 POSIX 绝对路径 `/data` 不会被拦**（正则要求至少两段）。本产品为 Windows 单机，NAS 走 UNC 或映射盘符，该形态不在威胁面内；若将来支持 Linux 需重新评估。
3. **`data/raw` 这类相对路径会通过。** 同第 1 条。
4. 以上三条必须在 `docs/` 的进度记录里写明，不允许对外承诺"所有真实路径都能拦、所有正常语句都放行"。

## §8 证据与提交

- 单 commit，`fix(agent): 出口护栏改为原文路径识别与整段脱敏`。
- 回报附：6.1 语料表的实际逐条结果（贴代码输出）、6.2 两条确定性多轮的断言与通过输出、两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §9 回滚

单 commit revert 后回到 `c56277c` 的全角方案（用户斜杠仍被误拦、assistant 的 POSIX 路径仍会放行）。两个状态都不理想，因此本卡应尽快落地而不是长期回退。
