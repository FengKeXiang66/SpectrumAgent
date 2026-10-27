# TASK-07b 编排助手运行时质量补丁（D 域对话编排）

> 派生自 TASK-07，针对用户实测 transcript（2026-10-27）暴露的三个运行时硬伤。
> 事实源：用户粘贴的 1–28 轮真实对话、`src-python/spectrumagent/agent/{state,llm,skill,tools/__init__}.py`、`src/components/assistant/{AssistantBar.tsx,sse.ts}`。
> 本卡由复核方（codex 路径）起草，待科祥确认后实施。一次只落一个修复点。

---

## 0. 实测三硬伤（来自 transcript）

| 现象 | 用户感受 |
|---|---|
| 已确认实体（数据集 ID 等）下一轮忘光 | 「这编排的效果一点也不好」 |
| 工具日志 inline 喷「n. datasets.list · ok · count:15 · dataset_ids:…」 | 对话流被内部日志淹没 |
| 已说「请你自动帮我执行标注过程」，下一轮仍退回确认 | 过度确认、不肯动手 |
| 「2. LLM_HTTP：LLM_HTTP」裸错误码 | 报错不可读，且疑似后端抖动 |

---

## 1. 根因定位（代码实证）

| 硬伤 | 根因 | 落点 |
|---|---|---|
| 上下文丢失 | PARSE/INTERPRET 只把**当前轮** content 喂 LLM，已完成轮次从不读回（DB 有 `agent_round`/`agent_step` 但不回灌） | `state.py:270`（PARSE）、`state.py:356`（INTERPRET） |
| 工具日志回显 | `step` 事件被 `entryText` 当对话条目内联渲染，且 `result_summary` 原始 dict 透传（`datasets.list` 在 `tools/__init__.py:267` 返回 `dataset_ids` 长串） | `AssistantBar.tsx:11`、`sse.ts:83`、`tools/__init__.py:267` |
| 过度确认 | `annotations.draft_confirm` 标 `human_check=True`（`tools/__init__.py:308`），`state.py:342-348` **代码无条件**闸；用户授权指令在独立轮，因上下文丢失（R1 前）未被读取，且代码闸不查既往授权 | `tools/__init__.py:308`、`state.py:342` |
| 裸错误码 | 错误事件按 `code：detail` 直接渲染，内码未转文案 | `AssistantBar.tsx:16`、`llm.py:215/256` |

---

## 2. 设计反转声明（重要，须评审）

**R10（TASK-07 `migrations.py:48` DDL 注释）原为：「落盘≠回灌，往轮仍不回灌 LLM」。**

本次 R1 **有意反转**该规则为：「已完成轮次（status='done'）回灌 LLM，作为 PARSE 与 INTERPRET 的上下文前缀，上限 10 轮」。

理由：
1. 无历史设计依赖「工具结果是唯一真相」，但用户**跨轮实体/意图**（确认过的数据集、明确的 auto-execute 授权）并不存在于单轮工具结果里，导致丢失。
2. 反转后 LLM 能看到既往 `user_message` + 工具调用 + 工具结果，实体与授权指令自然延续。
3. 设上限 10 轮防止上下文无限增长；长会话超出部分丢弃最早轮次。
4. 风险：上下文体积增大、可能把早期错误信息带入。已用上限 + 仅取 `done` 轮对冲。

`migrations.py:48` 注释同步改写，避免卡面与代码自相矛盾。

---

## 3. 修复方案

### R1 上下文回灌（主因，必修）

- 新增 `AgentStore.rounds(session_id, *, exclude_round_id=None, limit=None)`：取 `status='done'` 轮次，按 seq 排序，可排除当前轮、可截断。
- 新增 `StateMachine._history_messages(version, exclude_round_id=None)`：对每轮拼装 `[user_message, assistant(tool_calls), tool 结果…]`。
- PARSE（`:270`）：`messages = [system, *history, user(content)]`。
- INTERPRET（`:356`）：`messages = [system, *history(exclude=当前轮), user(round.user_message), *当前轮工具]`。

### R2 工具日志折叠（体验，必修）

- `AssistantBar.tsx`：把 `step`/`error` 事件移出主对话 `<ol>`，渲染为折叠 `<details>「执行日志 (N)」`。
- `sse.ts scalarText`：对单值字符串 > 50 字符截断加 `…`，消除 `dataset_ids` 长串喷流。
- **不动 `reduceChat` 数据模型**，故 `sse.test.ts` 数据层断言零改动。

### R3 auto_confirm 授权跳过闸（体验，必修）

- `migrations.py`：`ALTER TABLE agent_session ADD COLUMN auto_confirm INTEGER NOT NULL DEFAULT 0`（PRAGMA 守卫，幂等）。
- `StateMachine` PARSE：检测授权短语（含「自动执行」/「自动帮我执行」/「无需确认」/「不用确认」）→ `set_auto_confirm(1)`；撤销短语（「恢复确认」/「需要确认」/「不要自动」）→ `set_auto_confirm(0)`。
- `state.py:342` human_check 闸、`state.py:297` plan_check 闸：当 `auto_confirm=1` 时跳过确认，直接执行/放行。
- 默认 0，既有 human_check / plan_check 测试不受影响；仅授权后生效。

### R4 错误码转友好文案（体验，必修）

- `sse.ts` 新增 `friendlyError(code, detail)`：映射 `LLM_HTTP/LLM_TRANSPORT/http_error/transport_error/TOOL_FAILED/AGENT_FAILED/AGENT_STORAGE/INVALID_REQUEST/SESSION_NOT_FOUND` 为中文；未知码回退 `code：detail`。
- `reduceChat` 的 `state.error`（`:78`）与 `AssistantBar` error 条目均走 `friendlyError`。
- `sse.test.ts:79` 期望文案同步改为友好文本。

---

## 4. 验证

- `src-python/tests/agent/test_state.py`：改写 `second_turn_has_no_history` 为断言历史被注入；新增 `auto_confirm` 绕过 human_check/plan_check 测试。
- `node --test src/components/assistant/`：`sse.test.ts` 数据层不变，仅 `:79` 改友好文案。
- 全量：`cd <根> && .venv/Scripts/python.exe -m pytest src-python/tests/agent`、`node --test src/components/assistant/`。

## 5. 风险与回滚

- R1 反转 R10，若上下文过大导致 LLM 调用成本上升：调小 `limit`。
- R3 授权为会话级粘性：误触授权后可用撤销短语或新会话复位。
- 回滚：本卡单 commit，必要时 `git revert` 对应提交。
