# TASK-11b · L1 引用层设计稿（评审稿，未落卡）

日期：2026-10-28　代码基准：`cdda282`　前置：L0 卡（`docs/TASK-11a-L0-可测量段任务卡.md`）
本文只给设计，不含实现步骤；审完再落 L1 卡。

## 1 目标与边界

**目标**：让"第几个"永远解析到用户实际看到的那个对象，且切换一类对象不清掉另一类的成果。

**不做**：多候选共存、无种子候选生成、严格零画布、跨会话任务、任意配方参数编辑。前端不做"严格同快照校验"，只做 choices 复用（见 §8）。

## 2 现状实测（四类目录，实际只有一份半）

| 类型 | 存在哪 | 谁生成序号 | 缺陷 |
|---|---|---|---|
| dataset | `context_json.dataset_catalog`（`context.py` L123-133） | 后端从 `datasets.list` 出参的 `dataset_i_*` 拼 | 有目录、无 `snapshot_id`、无类型标签 |
| candidate | 内存 `_previews`（`tools/workflows.py` L251-254）+ `state.candidates` 队列 | 无 | **没有编号目录**；`propose` 每次清空全部预览（L283）→ 同时最多 1 个 |
| recipe | 每次 `preprocess.recipes` 现算，不持久化 | 后端按 `recipes.list()` 顺序 | `recipes.list()` 是 **`ORDER BY code`**（`preprocess/recipes.py` L105）→ "第二个配方"= 字母序第二，与界面视觉顺序可能不同 |
| region | `annotations.context` 出参 `region_i_id`（`workflows.py` L209-212） | 后端 `enumerate(document["regions"][-50:], 1)` | 序号 1 = **最近 50 条里最早的那条**，与画布倒序直觉相反 |

**一个好消息**：前端 `src/components/assistant/presentation.ts` L11-26 的 `datasetChoices()` 也是从**最近一条 `datasets.list` 的 step 出参**重建序号。所以界面与助手在数据列表上**本来就同源**，不需要新通道——只需给这份出参加 `snapshot_id` 并持久化。这条把 L1 的前端工作量从"三处都改"降到"给候选/配方加两种 choices"。

## 3 `catalogs` 结构

```json
"catalogs": {
  "dataset":   {"snapshot_id": "d3f81a2c", "source": "datasets.list", "round_id": "<round>",
                "items": [{"ordinal": 1, "id": "<uuid>", "ref": "D1", "display": "sample-081", "version": null}]},
  "candidate": {"snapshot_id": "c71e0b93", "source": "annotations.propose",
                "items": [{"ordinal": 1, "id": "c-<hex>", "ref": "C1", "display": "PP 候选 1", "version": 3}]},
  "recipe":    {"snapshot_id": "a2d90f14", "source": "preprocess.recipes",
                "items": [{"ordinal": 1, "id": "<recipe_version_id>", "ref": "P1", "display": "反射率基线", "version": 1}]},
  "region":    {"snapshot_id": "9b4c7e21", "source": "annotations.context",
                "items": [{"ordinal": 1, "id": "<region_id>", "ref": "R1", "display": "区域 1", "version": 3}]}
}
```

四条约定：

1. **`snapshot_id` 由内容摘要决定**：`sha256(kind + "\x1f".join(item.id) + "\x1f".join(str(item.version)))[:8]`。确定性、幂等、不需要服务端分配。同一份内容重复 list 得到同一 id，用户跨轮引用不会失效。
2. **`ordinal` 由服务端固定**，等于出参里的 `dataset_i_*` / `recipe_i_*` / `region_i_*` 下标，前端展示必须照抄，不得自己排序。
3. **保留最近 4 个快照**（每类），FIFO 淘汰。超出即视为"该引用已过期"，解析时明说而不是猜。
4. **`version` 是对象版本**（候选的 draft revision、配方的 `version_no`、区域的 revision），用于"这一版"的解析与失效判断。

## 4 `active_catalog`：停点决定解析范围

`state["active_catalog"]` 不是持久字段，是**每次解析前由停点算出的派生值**：

| 停点判据（按顺序取第一个命中） | active |
|---|---|
| `next_action == "need_seed"` | `None`（要画布指认，没有可编号对象） |
| `candidate_ref` 存在且未被接受/拒绝 | `candidate` |
| 最近一步是 `preprocess.recipes` 且用户尚未选定 | `recipe` |
| 最近一步是 `annotations.context` | `region` |
| `selected_cube_id` 为空 | `dataset` |
| 其余 | `dataset` |

写成纯函数 `active_catalog(state, last_tool)`，可单测，不进 state、不落库。

## 5 解析规则

```
用户话 → ① 名词命中？ → 按名词定 kind（数据/数据集/份 → dataset；候选 → candidate；
                            配方/方案 → recipe；区域/块 → region）
       → ② 裸序号（"第二个"）？ → 只在 active_catalog 里找
       → ③ 短引用（D2 / C1 / P3 / R1）→ 按前缀定 kind，全局找
       → ④ 都找不到 → 问一次（明确列出候选名称），不回落、不猜
```

三条硬规则：

- **裸序号永不回落到 dataset**。`active_catalog` 为空或找不到时，回复"当前没有可选择的候选项，你是指数据列表里的第 N 个吗？"，由用户确认一次。
- **快照过期先重列**：若 `catalogs[kind].round_id` 不属于当前 session 的最近一轮，且用户用了裸序号 → 先重跑一次对应的只读工具（`datasets.list` / `preprocess.recipes` / `annotations.context`），用新快照解析，并在回复里说明"已刷新列表"。这是"重启后老会话失忆"的正解，不靠猜旧序号。
- **`select()` 只被显式的数据选择调用**，候选/配方的切换走各自的 setter，不走 `select()`。

## 6 `select()` 清理键拆分

现状 `context.py` L42-45 一次性清 11 个键，是"切数据"的正确行为，但被候选/配方复用就成灾难。拆成四张表：

| 动作 | 清 | 保留 |
|---|---|---|
| 切 dataset（`select()`） | 全部 11 个（现行为不变） | — |
| 选/拒 candidate | `candidate_ref`、`accepted_candidate_ref`、`rejected_candidate_ref` | `annotation_version_id`、`recipe_version_id`、`last_run_id`、`revision` |
| 选 recipe | `recipe_version_id`、`last_run_id` | `annotation_version_id`、`candidate_ref`、`revision` |
| 选 region | 无（当前无对应 state 键） | 全部 |

`select()` 的 11 键清单保持逐字不变，只是把"清哪些键"抽成常量表，供另两种 setter 引用自己的子集。

## 7 迁移：老会话怎么不失忆

老会话的 `context_json` 里是 `dataset_catalog: [{index,id,name,ref}]`，没有 `catalogs`。

**方案：读取时惰性升级（read-time upgrade），不写迁移脚本、不停机、不过迁移闸。**

`normalize_context(context)` 增加一条纯函数升级：

```
若 "catalogs" 不在 context 且 "dataset_catalog" 非空：
    catalogs.dataset = {
        snapshot_id: sha256("dataset" + ids)[:8],
        source: "legacy.dataset_catalog",
        round_id: None,                      # 标记为"来源未知"，触发 §5 的快照过期重列
        items: [ {ordinal: row["index"], id: row["id"], ref: row["ref"],
                  display: row["name"], version: None} for row in dataset_catalog ]
    }
```

三条关键约束：

1. **顺序逐字沿用老 `index`，绝不重排**。老会话的"第一个数据"必须还是原来那个。重排 = 静默换对象。
2. **`dataset_catalog` 保留为只读派生视图**（= `catalogs.dataset.items` 的投影），供 `resolve_arguments`（`context.py` L182-195）与 `_readable`（`workflow.py` L25-32）继续工作。L2 再删，L1 不删。
3. **`round_id: None` 是有意的**：老会话升级后第一次用裸序号，会命中 §5 的"快照过期先重列"，刷新一次列表。这一步会改变序号映射，所以必须在回复里明说"已刷新列表，第 N 个现在是 X"，**不能静默**。

升级在 `store.save_context` 之前由调用方执行（L1 不把它接进运行时写入路径，理由同 L0：运行时投影风险大）。实际接法是 `workflow.generate` L73 读到 state 后调一次 `upgrade_context(state)`，只做"加 catalogs 键"，不删任何键。

## 8 前端契约（L1 只做最小）

- 复用 `presentation.ts` 的 `datasetChoices()` 模式，新增 `candidateChoices()` / `recipeChoices()`，数据源同样是"最近一条对应工具的 step 出参"。
- 三种 choices 的 `index` 一律取服务端出参下标，**前端不得自行排序**（当前 `datasetChoices` 已按 index 排序，符合）。
- L1 **不做**"界面与助手严格同快照校验"（需要前端回传 snapshot_id，属 L4 收紧项）。若界面因筛选显示的列表与服务端快照不一致，L1 的兜底是：解析前先重列（§5 第二条），因此助手侧永远基于刚刷新的列表。

## 9 验收（三条句子 + 反例）

| 句子 | 期望 |
|---|---|
| 选第二份数据 | 切换 `selected_cube_id`，清空候选/配方/版本（现行为） |
| 接受第二个候选（此时只有一个） | **澄清一次**："当前只有一个候选，是指它吗？"；不切数据、不清 `annotation_version_id` |
| 用第二个配方 | 绑定 `recipe_version_id` = 字母序第二；**不切数据**、不清标注版本 |

反例：

- 拒绝候选后再说"用第二个配方" → 候选的拒绝状态保留，只换配方。
- 老会话（无 `catalogs`）说"第二个" → 先重列并说明，不得直接按旧 `dataset_catalog` 猜。
- `active_catalog = None`（等种子）时说"第二个" → 问一次，不得落到 dataset。

**D1 的精确化（需确认）**：v1 同时只有 1 个候选，"接受第二个候选"的正确行为是**澄清一次**而不是"接受第二个"。这一句从"要能接受"改成"要能澄清"，才是可断言的。

## 10 需拍板的三个点

- **P1** 快照保留 4 个是否够？建议 4（够覆盖"上上轮展示过的那份列表"），超期一律视为过期并要求重列。
- **P2** §7 约束 3 的"重列后必须明说"要不要做成硬约束（回复里必须出现"已刷新列表"）？建议硬约束——否则用户不知道序号变了。
- **P3** §9 表格第二行改成"澄清一次"，是否同意？不同意就必须把多候选共存提前到 L1，工期 +2~3 天。

## 11 风险

1. **`region` 序号方向**（§2 表末行）与画布直觉相反。L1 只做"目录存在"，**不修方向**；修它要动 `annotations.context` 出参顺序，属 L2。
2. **`recipe` 序号是字母序**。若产品希望按"最近使用"排序，得先定排序口径——L1 沿用现状（`ORDER BY code`），不引入新排序。
3. **老会话升级后第一次裸序号会重列**，用户会看到序号变化。这是有意为之（§7 约束 3），但要写进发布说明。
4. **`_previews` 在内存**：进程重启后候选引用全失效。L1 不持久化预览（几何数据量大且属服务端所有），只保证"失效时明确说失效"，不假装还有。
