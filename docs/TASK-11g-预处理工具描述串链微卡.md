# TASK-11g · 预处理工具描述串成一条链（微卡）

日期：2026-10-29　基准 commit：`4d569b0`　预估：10 分钟　前置：L2b 已落地
**顺序：本卡先于真实模型验收**——它改的是模型看到的文字，不改行为。

## §1 本卡解决的问题

L2 删掉隐式默认后，`run_default` 要求显式版本。但模型在工具目录里看到的**三条描述互不指路**：

| 工具 | 现描述 | 问题 |
|---|---|---|
| `preprocess.recipes`（L480） | "发现可用配方、最新版本、算子名与版本以及默认配方…" | 没说要拿哪个字段（`recipe_i_version_id`）喂给谁 |
| `preprocess.recipe_ensure`（L481） | "…登记后返回版本，**供 compare 比较**" | **把用途写成了只给 compare 用**，把 run_default 排除在外 |
| `preprocess.run_default`（L482） | "必须显式指定标注版本与配方版本；省略由控制器注入，仍缺则拒绝" | 没说这两个版本从哪来 |

结果：模型要么凭空编版本、要么反问用户、要么放弃。替身测试全绿是因为替身"知道"这条路。

**本卡只做一件事：让三条描述互相指路，并写出确切字段名。**

## §2 允许改动的文件（越界即停）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/agent/tools/workflows.py` | 改（**仅 L480–L482 三行描述字符串**） |
| `docs/TASK-11-对话标注与预处理实现方案.md` | 改（§11 追加一行进度） |

## §3 明确不做

- 不改任何处理逻辑、不改 schema、不改参数类型或默认值。
- 不改其它任何工具的描述。
- 不动 `run_default` 的 `need_version` 分支。
- 不写新测试（描述是字符串，用 §5 的快照证据验，不写断言描述文本的测试——那种测试只会变成改一次修一次）。

## §4 三条新描述（逐字照抄，不得改写）

```python
("preprocess.recipes", NoArguments, "列出可用配方及其最新版本；返回 recipe_i_version_id 供 run_default 绑定或 compare 使用，不要求用户提供 UUID", workflows.recipes, runner is not None),
("preprocess.recipe_ensure", RecipeArguments, "显式选择固定模板 raw 反射率基线、snv、snv_sg1；登记后返回 recipe_version_id，供 run_default 运行或 compare 比较", workflows.recipe_ensure, runner is not None),
("preprocess.run_default", DefaultRunArguments, "必须显式指定 annotation_version_id 与 recipe_version_id：前者取 annotations.context 的 latest_annotation_version_id，后者取 preprocess.recipes 的 recipe_i_version_id 或 preprocess.recipe_ensure 的返回值；缺一即返回 need_version 拒绝，不采用库中最新或内置默认；返回真实指标和溯源", workflows.run_default, runner is not None),
```

## §5 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 工具目录快照 | 三条描述与 §4 逐字一致（贴 `registry.snapshot()` 里这三条的 `description` 原文） |
| B | 启动自检 | `ensure_workflow_skill` 因 `tools_json` 变化产生**新 skill 版本**（`skill_version_no` +1）；贴前后值 |
| C | 新建会话 | 新建会话绑定到新版本；**已有会话保持旧绑定**（这是 append-only 设计，不是缺陷，需在回报里说明实测结果） |
| D | 回归 | `src-python/tests/agent` 全绿（≥436）；`src-python/tests backend/tests --ignore=src-python/tests/agent` 全绿（≥976） |

## §6 证据与提交

- 单 commit，`docs(agent): 串起预处理工具描述` 或 `feat(agent): ...` 均可，二选一，不混。
- 回报附：三条描述原文、`skill_version_no` 前后值、新旧会话绑定实测、两段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

单 commit revert。回滚后 skill 版本不退回（append-only），但旧版本仍在，可切换。
