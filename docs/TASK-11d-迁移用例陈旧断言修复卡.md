# TASK-11d · 修建模迁移用例的陈旧断言（小卡）

日期：2026-10-28　基准 commit：`794659e`　预估：15 分钟　前置：无
**顺序：本卡先于 L2 执行**（它让全量测试恢复绿，L2 才有干净的对照基线）。

## §0 状态确认（先跑，不符即停）

```bash
.venv/Scripts/python.exe -m pytest "src-python/tests/modeling/test_dataset.py::test_migration_upgrades_21_tables_repeats_without_changing_existing_schema" -q
```

期望：`1 failed`，`AssertionError: assert 22 == 21`。
**若已通过，停手回报**（说明已被别人修掉），不得自行找别的活干。

构造探针（2026-10-28 已实测，codex 复跑确认即可）：

```bash
.venv/Scripts/python.exe -c "
import sys, tempfile, pathlib
sys.path.insert(0,'src-python'); sys.path.insert(0,'.')
from unittest.mock import patch
from backend.paths import AppPaths
from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.run import RunEngine
paths = AppPaths(pathlib.Path(tempfile.mkdtemp())/'legacy')
with patch('spectrumagent.api.registry.migrate_modeling', lambda db: None):
    registry = DatasetRegistry(paths.database)
RunEngine(registry, paths)
with connect_database(paths.database) as db:
    names = sorted(r[0] for r in db.execute(\"SELECT name FROM sqlite_master WHERE type='table'\"))
print(len(names), names)
"
```

期望 22 张表，且**不含** `training_run / training_fold / metric / model_artifact / sample_target / model_registry / inference_run / inference_artifact` 任何一张。若含建模表，说明 `legacy_case` 的 patch 失效了，先回报再施工。

## §1 本卡解决的问题

这条测试真正要证明的是"迁移前不含建模表，迁移后恰好加上那 8 张，且既有表 SQL 一字不变"。它现在用 `len(before) == 21` 来表达"迁移前是旧库"——**这个数字会随任何无关的建模前表变化而失效**（当前已因多一张表而红），而它想守的性质完全没变。

修完的判据：全量非 agent 测试恢复绿，且这条测试不再依赖"迁移前恰好 N 张表"这种脆弱前提。

## §2 允许改动的文件（越界即停）

| 文件 | 动作 |
|---|---|
| `src-python/tests/modeling/test_dataset.py` | 改（**仅该用例的断言与其函数名**） |

## §3 明确不做

- **不改 `src-python/tests/modeling/conftest.py` 的 `legacy_case`**。fixture 是对的，它正确地构造了"未建模"的旧库。
- 不改任何 `migrations.py`、不改任何生产代码。
- **不把断言放宽**成 `>= 21`、`in (21, 22)`、`assert len(before)`、`pytest.skip` 或删除该断言——这些都会让测试失去意义。
- 不删 `set(after) - set(before) == {...8 张...}` 与 `all(after[name] == sql for name, sql in before.items())` 两条。
- 不动同文件其它用例。

## §4 实现要求

把 `assert len(before) == 21` 替换为"建模表缺席"断言，其余两条保持原样：

```python
MODELING_TABLES = {"training_run", "training_fold", "metric", "model_artifact",
                   "sample_target", "model_registry", "inference_run", "inference_artifact"}
assert not (MODELING_TABLES & set(before))
```

函数名去掉 `21_tables`（已确认全仓仅本文件引用该名，可安全改），改为：

```
test_migration_upgrades_legacy_schema_repeats_without_changing_existing_schema
```

`set(after) - set(before) == {...}` 那条可改用 `MODELING_TABLES` 常量，减少一处重复——**仅此一处允许的顺带整理**。

## §5 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | §0 那条单测 | 通过 |
| B | `src-python/tests/modeling` 整目录 | 全绿 |
| C | `src-python/tests backend/tests --ignore=src-python/tests/agent` | **976 passed**（原 975 + 本卡修好的 1） |
| D | `src-python/tests/agent` | 仍 **415 passed**（确认没被牵连） |

## §6 证据与提交

- 单 commit，提交信息 `test(modeling): ...`。
- 回报附：改动前失败输出、改动后通过输出、`git diff`（应 ≤ 6 行）、测试数与执行模式（四段分开写）。
- 测试纪律：临时根指 OS 临时目录且**先 mkdir**；跑前确认 C 盘空闲 > 3 GB。

## §7 回滚

单 commit `git revert`，无 DB 迁移、无数据影响。
