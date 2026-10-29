# TASK-11L · L3a 重名数据可区分（共享显示名 + 读模式后缀）

日期：2026-10-29　基准 commit：`da50ae3`　预估：1 天　前置：无（与 L4 手动验收并行）
**可演示问题：真实库里 4 对同名数据，改完后界面上和助手列表里都能一眼区分，并且能用名字直接引用。**

## §0 状态确认与消费点清单（先跑，逐条回报）

```bash
git log --oneline -1
rg -n "class DatasetRecord" -A 4 src-python/spectrumagent/api/schemas.py          # 期望 L19-22
rg -n "dataset_i_name|safe_name" src-python/spectrumagent/agent/tools/workflows.py # 期望 L88/107/115/161/185
rg -n "\.dataset\.name" src/                                                        # 期望 8 处，见下
```

**显示名的消费点（2026-10-29 实测，必须全部覆盖，漏一个就出现"界面与助手不一致"）：**

| 位置 | 用途 |
|---|---|
| `src/components/datasets/DatasetPanel.tsx` L165 | 数据集面板标题 |
| `src/components/annotation/AnnotationWorkbench.tsx` L280 | 标注工作台标题 |
| `src/components/annotation/AnnotationWorkbench.tsx` L364 | 上一张/下一张导航 |
| `src/components/assistant/AssistantBar.tsx` L93 | 助手条"当前数据" |
| `src/components/assistant/presentation.ts` L21 | 数据集选项 label |
| `src/components/assistant/presentation.ts` L25 | 数据集选项 label（回退分支） |
| `src/components/assistant/presentation.ts` L34 | 回复文本里的可读名 |
| `src/components/modeling/InferencePanel.tsx` L57 | 推理面板数据下拉 |

助手侧消费点：`tools/workflows.py` L107（`dataset_i_name`）、L115（`describe` 的 `display_name`）、L161（`resolve` 匹配）、L185（`context` 的 `display_name`）。

**若上述行号与实物不符，在回报首段显式列出，并按内容定位，不要按数字施工。**

## §1 现场（真实库实测，非构造）

```
D8   20260804210313_15   raw=0
D12  20260804210313_15   raw=1     ← 同名，唯一区别是读模式
D9   20260804210353_75   raw=0
D13  20260804210353_75   raw=1
D10  20260804210443_152  raw=0
D14  20260804210443_152  raw=1
D11  20260804210509_189  raw=0
D15  20260804210509_189  raw=1
```

15 个数据集里 **4 对重名**，名字是采集时间戳（不可读），重名原因正是"同一源文件的不同读取模式"——TASK-11 §5.3 点名的那种情况。

现状：用户只能靠"第 8 个 / 第 12 个"区分；助手列表 `dataset_i_name` 也一模一样。

## §2 目标（本卡只做这一件）

**同名冲突时，自动追加可信的读模式后缀；界面与助手用同一个显示名。**

| 场景 | 显示名 |
|---|---|
| 名字唯一 | 原样（不加后缀，避免噪音） |
| 同名且 `raw=0` | `20260804210313_15（反射率）` |
| 同名且 `raw=1` | `20260804210313_15（原始 DN）` |

后缀只来自**可信元数据**（读模式），不推断材质、不猜批次。

**不做**：用户别名（`alias` 列）、改名接口、前端改名入口——那是 L3b，需要迁移，另开卡。

## §3 允许改动的文件

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/api/schemas.py` | 改（`DatasetRecord` 增加 `display_name: str`） |
| `src-python/spectrumagent/api/registry.py` | 改（新增显示名解析；`get` / 导入回参带上它） |
| `src-python/spectrumagent/agent/tools/workflows.py` | 改（`dataset_catalog` 用同一解析函数，替代现有 `safe_name`） |
| `src-python/spectrumagent/api/openapi.json` | **重生成**（字节级快照，必须与 schema 一致） |
| `src/components/datasets/*.tsx` | 改（新增 `displayName(record)` 帮助函数 + 替换 §0 表里 8 处取值） |
| `src-python/tests/**` | 改（新增解析函数单测 + 接口断言） |

**前端只改"显示名取值"这一类**，不改布局、不加控件。8 处替换是机械工作，但必须全覆盖——漏一处就出现界面与助手不一致。

## §4 明确不做

- 不新增数据库列、不做迁移（本卡零迁移）。
- 不改 `payload`（`extra="forbid"` + `data/schema.json` 是冻结契约，别名/显示名不能进 payload——已实证）。
- 不改 `datasets.list` 的字段名（`dataset_i_name` 保留，值改为解析后的显示名）。
- 不改 `resolve_reference` / `catalogs` 结构（L1 已就位，显示名变化自动生效）。
- 不动 v1 工具快照的其它字段。

## §5 实现要求

### 5.1 一个解析函数，两个消费者

```python
def display_names(rows):  # rows: [(id, name, raw), ...] 按 rowid 顺序
    """Append the read mode only when the base name is not unique."""
```

规则：

1. 基名 = 现有 `safe_name()` 的结果（去目录、去扩展名、截断 160）。
2. 统计基名出现次数；**只有出现 ≥2 次**才追加后缀。
3. 后缀：`raw=0` → `（反射率）`；`raw=1` → `（原始 DN）`。
4. 若追加后仍重名（理论上不会，除非同一 name + 同一 raw），回退为 `基名（原始 DN #2）` 这类带序号的稳定后缀——**不得产生新的重名**。
5. 纯函数、无 IO、可单测。

### 5.2 两个消费者

- **接口侧**：`DatasetRecord.display_name` 由 `registry` 填充；`GET /datasets/{id}` 与导入回参都要有。
- **助手侧**：`tools/workflows.py` 的 `dataset_catalog()` 里 `dataset_i_name` 改用同一函数的结果。
- **前端**：在 `src/components/datasets/` 下新增
  ```ts
  export function displayName(record: DatasetRecord): string {
    return record.display_name ?? record.dataset.name;
  }
  ```
  然后用它替换 §0 表里的 **8 处** `record.dataset.name`。**不许漏**，也不许各处自己拼。

### 5.3 openapi

`DatasetRecord` 加字段后**必须重生成** `api/openapi.json`，并与快照测试对齐。这是冻结资源，不能手改。

## §6 验收

| 编号 | 用例 | 期望 |
|---|---|---|
| A | 单测：4 对同名 + 7 个唯一名 | 唯一名**不加后缀**；4 对分别得到 `（反射率）`/`（原始 DN）`；结果**无重名** |
| B | 单测：全部唯一 | 全部不加后缀，与现有 `safe_name` 输出逐字相同（零回归） |
| C | 单测：同名且同 raw（人为构造） | 回退到带序号的稳定后缀，结果仍无重名 |
| D | 接口：`GET /datasets/{id}` | 返回 `display_name`；同名对的两条不相同 |
| E | 助手：`datasets.list` | `dataset_8_name` 与 `dataset_12_name` 不同，且与接口 `display_name` **逐字一致** |
| F | 端到端：新建会话说"有哪些数据" | 回复里 D8/D12 可区分；说"第 12 个"能选中 D12 |
| G | 前端 | 数据集面板显示带后缀的名字，与助手列表一致 |
| H | openapi 快照 | 重生成后字节级相等 |
| I | 回归 | `src-python/tests/agent` 全绿（≥453）；非 agent 全绿（≥976）；`npm run build` 通过 |

**E 与 G 是本卡的核心**：界面与助手必须是同一个显示名，不能各算各的。

## §7 证据与提交

- 建议两笔：`feat(datasets): 重名数据按读模式区分显示名` / `test(datasets): 覆盖重名与唯一名解析`。
- 回报附：A–C 单测输出、D/E 的实际返回值（贴 D8/D12 两条）、F 的 SSE 事件、openapi 重生成前后的 diff 行数、三段测试数与执行模式。
- 测试纪律：临时根指 OS 临时目录且先 mkdir；跑前确认 C 盘空闲 > 3 GB。

## §8 回滚

两笔各自 revert。无迁移、无数据变更，回滚后回到"同名不可区分"，不影响既有数据。
