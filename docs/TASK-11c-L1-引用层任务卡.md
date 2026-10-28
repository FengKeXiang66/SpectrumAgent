# TASK-11c · L1 引用层（codex 任务卡）

日期：2026-10-28　代码基准：`cdda282`　上游：`docs/TASK-11b-L1-引用层设计稿.md`（P1/P2/P3 已拍板）
预估：1–2 天（后端为主）
**前置：必须先落地 L0 卡（`docs/TASK-11a-L0-可测量段任务卡.md`）。** 硬依赖是 §4.8 要改的 `src-python/spectrumagent/agent/task.py`（`CONTEXT_KEYS`）与用例 N，该文件由 L0 创建。**两卡不得并行**——否则"谁负责登记 `catalogs`/`pending_clarify` 两个键"没有唯一答案，L0 的白名单会与 L1 的新键打架。

## §0 开工前状态确认（先跑，逐条回报，不符即停并在首段说明）

**第一道闸门（顺序依赖，先于一切）**：

```bash
ls -l src-python/spectrumagent/agent/task.py
grep -n "CONTEXT_KEYS" src-python/spectrumagent/agent/task.py
```

**若 `task.py` 不存在或没有 `CONTEXT_KEYS` → 立即停手，回报"L0 未落地"，不得自行创建 `task.py`、不得扩大为执行 L0。**（2026-10-28 codex 已在 L0 未落地时正确停手一次，此闸门即把该行为固化为卡内规则。）

其余确认项：

```bash
git log --oneline -1
grep -n "_ORDINAL\|_SHORT_ID" src-python/spectrumagent/agent/context.py      # 期望 L9 / L10
grep -n "def select" src-python/spectrumagent/agent/context.py                # 期望 L37
grep -n 'recipe_{i}_' src-python/spectrumagent/agent/tools/workflows.py     # 期望 L409-411（f-string，搜不到 recipe_i_version_id 字样）
grep -n "ORDER BY code" src-python/spectrumagent/preprocess/recipes.py        # 期望 L105
grep -n 'regions"\]\[-LIMIT' src-python/spectrumagent/agent/tools/workflows.py   # 期望 L209
grep -rn "upgrade_context" src-python/                                       # 期望无输出（本卡新建）
```

**缺陷复现探针（本卡要消灭的行为，2026-10-28 已实测，codex 复跑确认）**：

```bash
.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'src-python'); sys.path.insert(0,'.')
from spectrumagent.agent import context as m
cat=[{'index':1,'id':'a'*32,'name':'sample-081','ref':'D1'},
     {'index':2,'id':'b'*32,'name':'sample-082','ref':'D2'}]
print('1', m.remember_user({'dataset_catalog':cat},'接受第二个候选').get('selected_cube_id'))
print('2', m.remember_user({'dataset_catalog':cat},'用第二个配方').get('selected_cube_id'))
"
```

期望（改动前）：两行都输出 `bbbb...`（第二个数据集）——这就是"候选/配方串线成数据"的现场。
**本卡完成后这两行必须都输出 `None`**（不得切数据），并各自留下待澄清标记。

## §1 本卡解决的可演示问题

**说"接受第二个候选"和"用第二个配方"时，数据不再被切走。**

演示动作（真实界面，不改前端）：
1. 助手页问"有哪些数据" → 回复列出 `D1 sample-081`、`D2 sample-082`；
2. 说"选第二份数据" → 右上角数据名变成 `sample-082`；
3. 说"用第二个配方" → 回复里出现"第 2 个配方：SNV（P2）"，**右上角数据名仍是 sample-082**；
4. 说"接受第二个候选"（此时只有 1 个候选）→ 回复"当前只有一个候选，是指它吗？"，数据名不变。

## §2 允许改动的文件（全称，越界即停）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/context.py` | 改（主要工作） |
| `src-python/spectrumagent/agent/workflow.py` | 改（L73 调 `upgrade_context`；把 `last_tool` 传给解析；澄清分支） |
| `src-python/spectrumagent/agent/task.py` | 改（**只改 `CONTEXT_KEYS` 一处**，见 §4.8） |
| `src-python/tests/agent/test_context_references.py` | 新建 |
| `src-python/tests/agent/test_conversation_workflows.py` | 改（补澄清与不切数据的断言） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行进度） |

**本卡不改 `agent/tools/`**：`snapshot_id` 由两侧从同一份工具出参算出（内容摘要），出参里已有的 `dataset_i_*` / `recipe_i_version_id` / `region_i_id` / `candidate_ref` 足够，不需要新字段。

**本卡相对设计稿 §8 的收窄（需科祥确认）**：前端 `candidateChoices()` / `recipeChoices()` 移到 L3。理由：序号解析的正确性由后端保证 + 回显映射（§4.7）即可在界面上看到，前端 choices 只影响展示体验，塞进本卡会让改动面翻倍。

## §3 明确不做（越界即停）

- 不改 `agent/state.py` 的 `State` 枚举、不改任何迁移、不新增表或列（`catalogs` 全部住在 `context_json`）。
- 不改 `agent/tools/` 下任何文件、不改任何工具 schema。
- 不改 `src-tauri/`、不改 `src/` 前端。
- 不做 `requested_stages`、不做阶段合法性规则表、不做版本必填注入——那是 L2。
- 不做多候选共存：`catalogs.candidate` 在 v1 最多 1 项。
- 除 §4.8 的 `CONTEXT_KEYS` 增两键外，**不改 `task.py`**：`normalize_context`、`evaluate_task`、`TASK_SCHEMA_VERSION` 一律不动。
- **不得在 `workflow.py` 的模块级 import `task`。** 现状是 `task.py` L2 模块级 `from .workflow import RECOVERABLE`、`workflow.py` 在 `generate()` 内延迟 import `task`（L64）。这个方向一旦反转就成真循环 import（L0 复核时实测可独立导入 `task`，靠的正是"延迟"）。L1 要改 `workflow.py`，容易顺手在文件头加 import——**禁止**。
- **`upgrade_context` 与 `normalize_context` 的边界（易混，写死）**：本卡**允许**在 `workflow.generate` L73 之后调用 `upgrade_context(state)`——它**只增 `catalogs` 键、不删任何键**；本卡**仍然禁止**调用 `normalize_context` 的白名单投影路径（那条会丢键，归 L2）。
- 不为了让探针变绿而在 `remember_user` 里加"找不到就退回 dataset"的兜底——那正是要消灭的行为。

## §4 实现要求

### 4.1 `catalogs` 结构

```json
"catalogs": {
  "dataset":   {"snapshot_id":"<8hex>","source":"datasets.list","round_id":"<round_id>",
                "items":[{"ordinal":1,"id":"<uuid>","ref":"D1","display":"sample-081","version":null}]},
  "candidate": {"snapshot_id":"<8hex>","source":"annotations.propose","round_id":"<round_id>",
                "items":[{"ordinal":1,"id":"c-<hex>","ref":"C1","display":"PP 候选 1","version":3}]},
  "recipe":    {"snapshot_id":"<8hex>","source":"preprocess.recipes","round_id":"<round_id>",
                "items":[{"ordinal":1,"id":"<recipe_version_id>","ref":"P1","display":"反射率基线","version":1}]},
  "region":    {"snapshot_id":"<8hex>","source":"annotations.context","round_id":"<round_id>",
                "items":[{"ordinal":1,"id":"<region_id>","ref":"R1","display":"区域 1","version":3}]}
}
```

**id 口径（易错，逐条写死）**：

| kind | `id` 取 | 来源 |
|---|---|---|
| dataset | `dataset_i_id` | `context.py` L127-131 现有逻辑 |
| candidate | `candidate_ref`（`c-` 开头） | `annotations.propose` 出参 |
| **recipe** | **`recipe_i_version_id`，不是 `recipe_i_id`** | `tools/workflows.py` L410；内置配方沿用 L407-408 已选定的固定 pipeline 版本 |
| region | `region_i_id` | `tools/workflows.py` L209-212 |

`recipe` 这一行是本次拍板的细化：用户选的是"配方的某个版本"，`run_default` 收的也是 `recipe_version_id`；把配方 id 当版本 id 绑进去会导致 `RECIPE_VERSION_NOT_FOUND`。

**`snapshot_id` = 内容摘要**：`sha256(kind + "\x1f".join(item.id) + "\x1f".join(str(item.version))).hexdigest()[:8]`。确定性、幂等、不需要服务端分配。

**保留策略**：每类最多 4 个快照，FIFO 淘汰（`catalogs[kind].history`，最近 4 个 `snapshot_id` 对应 items 的浅拷贝）。超期引用一律视为过期。

### 4.2 `active_catalog(state, last_tool)` 纯函数

按顺序取第一个命中，返回 `"dataset" / "candidate" / "recipe" / "region" / None`：

| 判据 | 返回 |
|---|---|
| `state.get("next_action") == "need_seed"` | `None` |
| `state.get("candidate_ref")` 且未被接受/拒绝 | `"candidate"` |
| `last_tool == "preprocess.recipes"` 且用户尚未选定配方 | `"recipe"` |
| `last_tool == "annotations.context"` | `"region"` |
| `not state.get("selected_cube_id")` | `"dataset"` |
| 其余 | `"dataset"` |

不落库、不改 state、可单测。

### 4.3 解析：`resolve_reference(state, content, last_tool) -> (kind, item, clarify)`

```
① 名词命中 → 定 kind：数据|数据集|份 → dataset；候选 → candidate；配方|方案 → recipe；区域|块 → region
② 裸序号（"第二个"/"第 2 个"/"序号 2"）→ 只在 active_catalog 里找
③ 短引用（D2 / C1 / P3 / R1）→ 按前缀定 kind，在该类当前快照里找
④ 都没命中 → (None, None, {"reason":"not_found"})
⑤ 命中但 active 为空/过期 → (kind, None, {"reason":"only_one"|"stale"})
```

`remember_user` 改为调它：命中 dataset → `select()`；命中 candidate → `set_candidate()`（**不调 `select()`**）；命中 recipe → `set_recipe()`（不调 `select()`）；命中 region → **不写 state**，region 只用于 §4.3 的 `resolve_arguments` 参数替换（模型从 `annotations.context` 出参已拿到 `region_i_id`，无需在 state 里再存一份）。

`resolve_arguments` 扩展（**只做序号→id 替换，不做 None 注入**，后者归 L2）：

| 工具 | 参数 | 规则 |
|---|---|---|
| `datasets.resolve` | `query` | 现状保留 |
| `annotations.apply_candidate` / `annotations.reject_candidate` | `candidate_ref` | 值匹配 `^(第?\d+个?\|[Cc]\d+)$` 时按 candidate 目录替换 |
| `preprocess.run_default` | `recipe_version_id` | 值匹配 `^(第?\d+个?\|[Pp]\d+)$` 时按 recipe 目录替换 |
| `annotations.edit_region` | `region_id` | 值匹配 `^(第?\d+个?\|[Rr]\d+)$` 时按 region 目录替换 |

已经是合法 UUID / `c-<hex>` 的值**原样透传**，不得改写。

### 4.4 `select()` 清理键拆分

现状 L42-45 一次清 11 个键（`gesture_ref`、`annotation_version_id`、`recipe_version_id`、`last_run_id`、`revision`、`candidate_ref`、`accepted_candidate_ref`、`rejected_candidate_ref`、`save_requested`、`save_denied`、`authorization_cube_id`）。

拆成常量表：

```python
CLEAR_ON_DATASET = frozenset({...11 个，逐字不变...})
CLEAR_ON_CANDIDATE = frozenset({"candidate_ref", "accepted_candidate_ref", "rejected_candidate_ref"})
CLEAR_ON_RECIPE = frozenset({"recipe_version_id", "last_run_id"})
CLEAR_ON_REGION = frozenset()
```

`select()` 继续用 `CLEAR_ON_DATASET`（行为零变化）；另加 `set_candidate()` / `set_recipe()` / `set_region()` 三个 setter，各自只清自己的子集。**禁止 setter 内部调 `select()`**。

### 4.5 `upgrade_context(state)` 惰性迁移

```
若 "catalogs" 不在 state 且 "dataset_catalog" 非空：
    catalogs.dataset = {
        snapshot_id: sha256("dataset" + ids)[:8],
        source: "legacy.dataset_catalog",
        round_id: None,                      # 有意留空 → 触发 §4.6 的过期重列
        items: [{ordinal: row["index"], id: row["id"], ref: row["ref"],
                 display: row["name"], version: None} for row in dataset_catalog]
    }
```

三条硬约束：

1. **顺序逐字沿用老 `index`，绝不重排**。老会话的"第一个数据"必须还是原来那个。
2. **`dataset_catalog` 保留为只读派生视图**，`resolve_arguments`（L182-195）与 `_readable`（`workflow.py` L25-32）继续可用。L2 再删。
3. `round_id: None` 有意为之：老会话第一次用裸序号会命中"过期重列"，刷新一次列表。

### 4.6 澄清一次（不重复追问）

`state["pending_clarify"] = {"kind": "...", "reason": "only_one"|"stale"|"not_found", "asked": false}`

`workflow.generate` 在调用 LLM **之前**处理：

- 有 `pending_clarify` 且 `asked == false` → 直接 `yield "clarify"`，把 `asked` 置 `true`，**不调 LLM**（确定性，省一次调用）；
- 有 `pending_clarify` 且 `asked == true` → **不再问**，保持当前选择不变，回复"仍未确定，保持当前选择"，并清掉 `pending_clarify`。

这条同时是"不重复追问"的实现机制，验收用例 F 专测。

### 4.7 回显映射（P2 硬约束）

凡是由序号解析成功并改变了 state 的，回复里**必须**出现映射，格式固定：

- 数据：`已选第 2 份数据：sample-082（D2）`
- 配方：`第 2 个配方：SNV（P2）`
- 候选：`第 1 个候选：PP 候选 1（C1）`
- 过期重列：`已刷新列表，第 2 个现在是 sample-082（D2）`

由控制器生成这段文本（不交给模型自由发挥），确保"用户能直接核对序号"。

### 4.8 登记新键（与 L0 卡的交界，必做）

本卡往 state 里加 **2 个新键**：`catalogs`、`pending_clarify`（`last_tool` 只作函数入参，不落 state；`region_ref` 不加，见 §4.3）。

因此必须同步：

1. `src-python/spectrumagent/agent/task.py` 的 `CONTEXT_KEYS` 增加这 2 个键（**这是本卡允许改 `task.py` 的唯一一处**，不得顺手改 `normalize_context` 或 `evaluate_task`）。
2. L0 卡 §5 用例 H 的"实际写入 ⊆ `CONTEXT_KEYS`"是**单向包含**，因此加键不会让 H 变红；但要确认 L0 的正则扫描路径也能覆盖 `catalogs` 的写入点——若 H 的扫描只认 `state["..."]` 字面赋值，用 `state.update(...)` 或 `state["catalogs"][kind] = ...` 的写法可能漏检，**本卡必须用 `state["catalogs"] = ...` 的整体赋值形式**，让 H 扫得到。

## §5 验收用例

| 编号 | 用例 | 期望 |
|---|---|---|
| A | §0 的两行探针 | 改动后都输出 `None`，且 state 里出现 `pending_clarify` |
| B | "选第二份数据" | `selected_cube_id` 切到 D2；`CLEAR_ON_DATASET` 全部清掉 |
| C | 已有 `annotation_version_id` 时说"用第二个配方" | `recipe_version_id` 绑定字母序第二；**`annotation_version_id` 仍在**、`selected_cube_id` 不变 |
| D | 已有 `annotation_version_id` 时说"接受第二个候选"（只有 1 个） | `selected_cube_id` 不变、`annotation_version_id` 仍在；产生 `pending_clarify(reason="only_one")` |
| E | 同上，用户再说"就是这个" | 候选被接受，`annotation_version_id` 仍在 |
| F | `pending_clarify.asked == true` 后用户仍说"第二个" | **不得再问**；state 不变；回复含"保持当前选择" |
| G | `active_catalog == None`（`next_action="need_seed"`）时说"第二个" | 澄清一次，**不落到 dataset** |
| H | 老会话（只有 `dataset_catalog`、无 `catalogs`）调 `upgrade_context` | 生成 `catalogs.dataset`，`ordinal` 与老 `index` 逐字相等，`round_id is None`，`dataset_catalog` 仍在 |
| I | 老会话升级后说"第二个" | 命中过期重列，回复含"已刷新列表"；不得按旧序号静默解析 |
| J | `resolve_arguments` 传入合法 `c-<hex>` | 原样透传，不被改写 |
| K | `resolve_arguments` 传入 `"第二个"` 给 `apply_candidate` | 按 candidate 目录替换为真实 `candidate_ref` |
| L | 单测：`active_catalog` 六条判据各一条 | 全绿 |
| M | 单测：`snapshot_id` 幂等 | 同一 items 调两次得同一 id；items 变一个则变 |
| N | `CONTEXT_KEYS` 已含 `catalogs`、`pending_clarify`；L0 用例 H 仍绿 | 两条都过（H 是单向包含，加键不应变红） |
| O | 回归 | `src-python/tests/agent` 分段跑全绿（见 §6） |

## §6 证据产物与提交方式

- **逐文件提交**，禁 `git add -A` / `git add .`。建议三笔：`context.py`+测试 / `workflow.py` / 文档。
- 回报必须附：`§0` 逐条结果（含改动前后两版探针输出）、每文件 diff 摘要、测试数与执行模式、界面演示四步的截图或事件序列、未做项与偏离项、行号与实物不符处。
- **用例 F（不重复追问）与用例 I（老会话重列）必须贴实际 SSE 事件序列**：事件名 + 顺序 + 关键字段（`pending_clarify.reason`、`asked`、是否发生重列、回复文本里"已刷新列表"的位置）。**不接受只写"通过"**——这两条是状态机行为，最容易被实现成"再问一次"或"静默解析"却让断言表面变绿。
- 测试纪律：本机全量 pytest 会被 safe-delete hook 拦，必须分段跑
  `cd E:\AI_Agent && .venv/Scripts/python.exe -m pytest src-python/tests/agent -q`；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

三笔 commit 各自 `git revert`。`workflow.py` 引用 `context.py` 的新函数，回滚顺序：先 `workflow.py` 再 `context.py`。无 DB 迁移；`catalogs` 是新增键，老代码读到会忽略，回滚不会丢数据。

## §8 完成后向 TASK-11 §11 追加一行

`L1 完成于 <commit>，三类序号互不串线；老会话惰性迁移已验（用例 H/I）；前端 choices 移至 L3。`

**遗留跟踪项（落 L3 卡时必须核到）**：`src/components/assistant/presentation.ts` 的 `candidateChoices()` 与 `recipeChoices()` 两个函数尚未创建，需在 L3 卡的文件清单里显式列出，并写明它们复用 `datasetChoices()`（L11-26）"从最近一条对应工具的 step 出参重建序号"的模式。不列就会漏。
