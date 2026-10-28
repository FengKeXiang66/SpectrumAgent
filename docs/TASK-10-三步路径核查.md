# TASK-10 · 三步脱困路径对照核查

> 核查对象：用户提供的「AI 编排零基础三阶段脱困路径」（看懂 → 跑通闭环 → 定点复制）
> 核查时间：2026-10-28
> 方法：全部结论均来自本机代码与真实运行库实证，非照抄原提案
> 结论一句话：**三步里的"看懂"和"定点复制"项目已经满足，"跑通闭环"这一步的设施齐了但从未真跑过——卡在 v2 没发布，而不是卡在你不懂。**

---

## §0 核查总表

| 步骤 | 提案要求 | 项目现状 | 判定 |
|---|---|---|---|
| 第一步 · 看懂 | 只读 3 个文件，建立 session → message → plan → tool_call → step | 3 个文件都在，但规模比提案预设大；**另有两个提案没提的核心文件**（`context.py` 195 行、`workflow.py` 263 行）才是 v2 的实际大脑 | **部分满足（需补两份地图）** |
| 第二步 · 跑通最小闭环 | 对话 → LLM 规划 → 工具调用 → 算子 → SSE 轨迹，助手页右侧可见 | SSE 事件、轨迹渲染、step 落库、真实模型配置**全部就绪**；但真实模型**从未调用过 v2 的任何工具**，实测跑的是 v1 | **设施满足 / 验证未做** |
| 第三步 · 定点复制 | 新功能 = 一个 Pydantic schema + 一个 handler + 一行注册 | 完全成立：注册表统一、schema 统一 `extra="forbid"`、v2 的 15 个业务工具就是这个模式 | **满足** |
| 四条硬规矩 | ①一次一单元 ②不改状态机 ③含四要素 ④数值只来自算子 | ①③④已在代码结构中强制；②**无机制保障**，纯靠自觉 | **3/4 满足** |

---

## §1 第一步「看懂」：三个文件在，但提案漏了 v2 的两个大脑

### 1.1 提案点名的三个文件（实测行数）

| 文件 | 行数 | 职责（实证） |
|---|---|---|
| `src-python/spectrumagent/api/agent.py` | **94** | SSE 入口。`make_router()` L58、`create_session()` L64、`message()` L78、`steps()` L90 |
| `src-python/spectrumagent/agent/state.py` | **552** | 状态机。`State` 枚举 L41、`AgentStore` L101、`StateMachine` L285、`_dispatch()` L330 |
| `src-python/spectrumagent/agent/tools/__init__.py` | **338** | 工具注册表。`ToolInput` L17（`extra="forbid"` L18）、`ToolRegistry` L191、`register()` L198、`build_registry()` L264 |

> 提案说 `api/agent.py` 只有 95 行——实测 94 行，基本准确。

### 1.2 但提案漏了两个文件，而它们才是 v2 真正在跑的部分

工作区里有一整套 **未提交** 的 v2 实现（`git status` 显示 `??`）：

| 文件 | 行数 | 职责 | 为什么提案必须补上 |
|---|---|---|---|
| `agent/context.py` | **195** | 任务记忆（对象引用、授权、候选/配方绑定） | `user_reference()` L14、`ordinal()` L25、`select()` L37、`remember_user()` L54、`observe()` L116、`resolve_arguments()` L182 |
| `agent/workflow.py` | **263** | 连续 observe-act 执行循环 | `generate()` L62 起，循环体 L133+ |
| `agent/tools/workflows.py` | **489** | 15 个业务工具 | `register_workflows()` L461，工具表 L473-487 |

**不读这两个文件，"看懂 Agent" 只能看懂 v1，而 v1 正是实测打转的那套。**

### 1.3 提案的「5 个概念」在 v2 下不够用

提案列 `session → message → plan → tool_call → step`。v2 实际还有三个必需概念：

| v2 概念 | 落点 | 为什么必需 |
|---|---|---|
| **turn**（一个用户意图跨多个 round） | `agent_round.turn_id`；`state.py:164 turn_rounds()` | 用户一句话可能引发多轮工具执行；`done` 只表示"这一轮工具跑完"，不等于业务完成 |
| **task state**（任务状态） | `agent_session.context_json` | 实测 3 个会话该字段**全空**——v1 从不落任务状态，这正是"反复重问"的根因 |
| **budget / gate**（预算与人审门） | `workflow.py` 的 `MAX_WORKFLOW_BATCHES` / `MAX_WORKFLOW_STEPS` / `plan_check` / `human_check` | 防止自由循环与不可逆写入 |

**结论：第一步不是"已完成"，而是"已完成 70%"——补上 `context.py` + `workflow.py` 两张地图即可。**

---

## §2 第二步「跑通最小闭环」：设施全齐，验证从未做

这是最关键的一节。逐项实证：

### 2.1 设施就绪（四项全部通过）

| 设施 | 证据 |
|---|---|
| SSE 事件类型完整 | `src/components/assistant/sse.ts:7-13`：`step`（含 seq/tool/status/result_summary）、`clarify`、`human_check`、`plan`、`workspace`、`done`、`error` |
| 前端轨迹渲染 | `AssistantBar.tsx:13` 渲染 step 文本；`AssistantBar.tsx:87-88` 把 step 分流到日志区；`presentation.ts:12` 对 `datasets.list` 做折叠 |
| step 真实落库 | 表 `agent_step`（列：session_id/round_id/seq/tool/arguments_json/result_digest/result_summary/status/latency_ms）**实测 13 行** |
| 真实模型已接通 | `llm_settings`：`base_url=https://api.siliconflow.cn/v1`、`model=deepseek-ai/DeepSeek-V4-Flash`、`egress_enabled=1`；`llm_call` 表 **28 条**真实调用记录（带 prompt_tokens/completion_tokens/latency_ms） |

**也就是说：如果你现在打开助手说一句话，模型会真的调 DeepSeek，轨迹会真的显示。**

### 2.2 但——真实模型调用的**全部是 v1 的 10 个工具**

对 `llm_call.tool_names` 做全表去重，三个会话的工具目录**完全一致**：

```
datasets.list, datasets.describe, annotations.draft_get,
annotations.draft_add_region, annotations.draft_select_candidates,
annotations.draft_confirm, preprocess.run, preprocess.compare,
training_mat.export, settings.llm_get     ← 共 10 个，全部 v1
```

v2 特征工具命中数：

| 检索模式 | 命中 |
|---|---|
| `workflows.` | **NONE** |
| `sa_` | **NONE** |
| `context.` | **NONE** |
| `datasets.resolve` / `annotations.prepare` / `annotations.propose` / `preprocess.recipes` | **NONE** |

**v2 的 15 个业务工具，一次都没有被真实模型调用过。**

### 2.3 根因（已在第一轮定位，此处补充确认）

| 环节 | 事实 | 位置 |
|---|---|---|
| v2 代码未提交 | `git status`：`?? agent/context.py`、`?? agent/workflow.py`、`?? agent/tools/workflows.py` | 工作区 |
| v2 skill 从未发布 | 运行库 `skill_version` 只有 v1（`initial-orchestrator`），**v2 (`conversation-workflows-v2`) 零记录** | 运行库 |
| 老会话永久锁死 v1 | `ensure_workflow_skill()` 只在 `api/agent.py:66-69` 建会话时调一次；`agent_session.skill_version_id` 有不可变触发器 | `skill.py:141-161` |
| 发布包不含 v2 | 0.4.0 的 `app.exe`(PYZ) 有 `agent.state`/`agent.llm`（v1），**无** `agent.context`/`agent.workflow`/`tools.workflows` | 发布产物 |
| 开发/发布是两套产物 | `engine_path.rs`：`#[cfg(debug_assertions)]` 才读 `SPECTRUM_ENGINE_EXE`，release 走 `resolved_resource` | `src-tauri/src/engine_path.rs:14-26` |

> **注意**：`_workflow_enabled()`（`state.py:290`）的判据是"工具目录里有没有 `annotations.prepare`"。既然库里 skill 只有 v1，**这个判据永远为 False**，v2 代码路径在真实会话里一行都没进过。

### 2.4 现有测试不能替代真实验收

| 脚本/测试 | provider | 结论 |
|---|---|---|
| `scripts/e2e_task07.py` | `httpx.MockTransport`，文件头自述 "mock provider ... no real provider network" | 只证明设施通 |
| `src-python/tests/agent/test_conversation_workflows.py` | `WorkflowProvider` 假 provider + L55-56 `monkeypatch` 主动 `raise AssertionError("Acceptance tests must not call a real provider")` | 只证明边界守得住 |
| `llm_call` 真实记录 | 真模型，但工具目录全是 v1 | 证明 v1 能调通，不证明 v2 |

**判定：第二步的"跑通"从未发生。缺的不是设施，是发布 + 一次真实模型验收。**

---

## §3 第三步「定点复制」：完全成立，模式已固化

### 3.1 「一个 schema + 一个 handler + 一行注册」确有其事

`ToolRegistry.register()` 签名（`tools/__init__.py:198`）：

```python
def register(self, name, arguments, description, handler=None, *,
             human_check=False, gpu=False, estimate_ms=None): ...
```

v2 的 15 个业务工具就是纯一行式（`tools/workflows.py:489`）：

```python
for name, arguments, description, handler, ready in tools:
    registry.register(name, arguments, description, handler if ready else None)
```

### 3.2 schema 强制已经是全局默认

`tools/__init__.py:18`：

```python
model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
```

**所有工具参数继承自 `ToolInput` → 自动 strict + 禁止多余字段 + 禁止 inf/nan。** 提案的"schema 校验（extra=forbid）"这一条不需要额外做，已经在基类里。

### 3.3 四要素覆盖率

| 要素 | 状态 | 证据 |
|---|---|---|
| schema 校验 | ✅ 全局强制 | `ToolInput` L18 + `validate_schema()` L114 + `validate_snapshot()` L140 |
| 前置条件检查 | ✅ | 每个 `*Arguments` 的 validator；`workflow.py` 的 `_authorized()` L19、`_readable()` L25 |
| 结果摘要 | ✅ | `_run_summary()` L247；`registry.register(..., handler)` 返回经 `ResultSummary` 白名单过滤 |
| step 落库 | ✅ | `AgentStore.add_step()` L257 / `finish_step()` L271 |

### 3.4 唯一缺口：没有现成的「新增一个工具」填空模板

`.runtime/` 下有 21 份 codex 备卡（`codex-12.1` … `codex-135`，最大 44KB），**但它们都是里程碑任务卡，不是可复用的工具开发模板**。

- 最新的 `codex-135-prompt.txt` 结构是：§0 状态确认 → §1 范围与边界 → §2 需求与文书锚点 → §3 数据现状实证 → …
- 这是「做一项功能」的卡，**不是「加一个工具」的卡**。

**提案承诺的"可复用 codex 定点开发 prompt 模板（含新增一个工具的标准填空格式）"目前不存在，需要新建。**

---

## §4 四条硬规矩的机制化程度

| 规矩 | 现状 | 依据 |
|---|---|---|
| ① 一次只改一个文件 / 一个工具，先给 schema 再写实现 | ✅ 由工具注册结构天然隔离 | `register()` 一行式 + 每个工具独立 Pydantic 类 |
| ② 不许改状态机 / 不许加新依赖 / 不许改表结构 | ❌ **无机制保障** | 仓库无 CI 门禁、无 `AGENTS.md`/`CONTRIBUTING.md`、无 pre-commit hook |
| ③ 每个工具含 schema 校验 / 前置检查 / 结果摘要 / step 落库 | ✅ 代码结构强制 | 见 §3.4 |
| ④ 数值只能来自算子 | ✅ 双层强制 | `llm.py:140 _egress_blocked()` 出域扫描 + `tools/__init__.py` 标量白名单 |

> ② 是唯一的软约束。当前靠 codex 备卡散文约束，属于"人治"。**补一份 `AGENTS.md` + 一个 CI 脚本即可变成"法治"。**

---

## §5 你现在到底该做什么（按依赖排序，不是按难度排序）

依赖关系是硬约束：❶ 不做完，❷ 无意义；❷ 不做完，❸ 验不了。

### ❶ 发布 v2（约半天，纯工程，零设计）

这是**唯一的阻塞点**。四个动作：

1. 逐文件 `git add`（禁 `-A` / `.`），提交 20 项改动 + 3 个新文件
2. 补**存量会话迁移路径**：老会话 `skill_version_id` 不可变 → 需在 `api/agent.py` 建会话时或启动自检时，让老会话指向 v2（否则库里 3 个会话永远 v1）
3. **启动自检发布 v2**：`ensure_workflow_skill` 只在建会话时调一次 → 需在应用启动时也调
4. **加可核对的运行信息**：会话接口返回 `skill_version_id` + 工具目录版本 + 构建标识；界面显示"当前编排 v2"。这样以后不用再靠文件时间戳猜版本

**验收**：新会话 `skill_version_id` 指向 `conversation-workflows-v2`；`llm_call.tool_names` 里出现 `annotations.prepare` / `datasets.resolve`。

### ❷ 真实模型验收（约 1 天）

- 现有假 provider 测试**保留**（它们验证边界）
- 新增**真模型**端到端脚本，走真实 HTTP，不再 mock
- 场景必须覆盖：单标注、标注后预处理、切换数据、**"第二个候选"**、**"第二个配方"**、重名数据、失败恢复、缺少材质依据
- 统计指标：任务完成率、重复追问次数、无进展轮次、错误对象写入、伪完成、协议泄漏

### ❸ 补三份"你指挥 codex 用的契约"（约 1 天）

| 交付物 | 作用 | 状态 |
|---|---|---|
| **Agent 状态机地图** | 你能看懂、能验收 codex 的产出 | **缺** |
| **codex 定点开发 prompt 模板**（新增一个工具的填空格式） | 消灭 vibe coding 的自由发挥空间 | **缺** |
| **AGENTS.md + CI 门禁** | 把规矩②从"散文"变成"法治" | **缺** |

---

## §6 一个必须说清的边界

**"PP，其余为背景"无法纯靠对话闭环到终态。**

- 谱相似扩散是从**种子**出发传播相似性，**不判定材质是不是 PP**（`annotation/engines/diffusion.py`）
- SLIC 只做超像素，**不识别 PP**
- v2 的 `annotations.propose` 无手势时返回 `need_seed` 而**拒绝编造**——这是**正确行为**，不该改

要闭环到终态，必须补至少一种可信依据：

1. 已验证的材料分类模型
2. 适配数据的参考光谱库
3. 系统生成候选 → 用户在对话里指认"这个是 PP"（**这个最现实**，且 `annotations.propose` + `apply_candidate` 已经准备好了承载它）

**助手此时只该补问这一项**（请指认一个 PP 候选），而不是重问数据集、类型、全部参数。这条要写进提示词的"禁止重复追问"规则。

---

## §7 结论

| 问题 | 答案 |
|---|---|
| 项目满足三步路径了吗？ | **看懂 70% / 跑通 0% / 定点复制 100%** |
| 你现在的混乱是什么造成的？ | **不是不懂，是项目里最好的那套代码（v2）从未被发布和验收过**——你看到的混乱是 v1 的真实表现，v2 修好了但没上线 |
| 你需要学 LangChain / LangGraph 吗？ | **不需要**，需求文档 L1893/L2386-2388 已写死：自研状态机 + OpenAI 兼容工具调用协议，不引框架 |
| 你现在最该做什么？ | **❶ 发布 v2**——这是零设计、纯工程、半天的工作，且它是后面两件事的前提 |
| 你需要自己写多少代码？ | **接近零**。v2 的 947 行已经在工作区躺着了，你要做的是"让它生效 + 验它 + 给 codex 划边界" |

**下一步建议**：先做 ❶。我可以帮你把发布 + 迁移 + 启动自检 + 运行信息这条链一次做完，做完你就能在助手页看到 v2 的真实轨迹——那时"看懂"这件事会自然发生，不需要额外读代码。
