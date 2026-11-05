# TASK-27 算子中文名称体系卡

## 0. 一句话

为 13 个内置预处理算子建立唯一严格中文名（权威常量表，字串逐字锁定于本卡 §3）：AI 工具链输出在英文 op id 旁并列中文名、新增只读目录工具 `preprocess.operators`，前端 S06 算子链显示中文名。**op id 是唯一寻址键，零改动**；配方 JSON、数据库、fingerprint、OpenAPI 全部零迁移、零 bump version。

## 0.1 三道闸门

> 1. **工作区快照**（本卡特设，替代"干净"闸门）：开工前 `git status --short` 全文贴回报（当前有 TASK-26 未收口改动与另一条在途线，属已知状态，不是即停项）；本卡改动严格限于 §4 文件清单，**出现清单外文件即停**；清单内列明"in-flight 禁触碰"的文件出现改动即停。
> 2. **基线（2026-11-05 工作区实测，带出处）**：
>    - 前端：`node --test "src/**/*.test.ts"` = **249 tests / 249 pass / 0 fail**（实测耗时 1.5 s）。
>    - Python 分区：`PYTEST_DEBUG_TEMPROOT=<临时目录,先mkdir> .venv\Scripts\python.exe -m pytest src-python/tests/agent src-python/tests/preprocess -q` = **768 passed**（实测 210 s）。
>    - 收工门：既有用例不得变红变少，新增用例另计（768+N / 249+N，N 为本卡新增）；任何既有用例变红即停，禁止为凑数删改现有测试。
> 3. **行号锚点**：开工第一步 `grep -n` 复核本卡 §0.2 全部锚点，漂移即停上报。

## 0.2 行号锚点表（开工第一步逐条 grep 复核）

| # | 文件:行 | 锚定内容 |
|---|---|---|
| 1 | `src-python/spectrumagent/preprocess/registry.py:59-67` | `OperatorEntry` frozen dataclass（version/model/impl 三字段） |
| 2 | `src-python/spectrumagent/preprocess/registry.py:81-91` | `register()` 签名与校验（本卡**不改**此函数） |
| 3 | `src-python/spectrumagent/preprocess/__init__.py:13-31` | `builtin_registry()`：13 个算子按序注册 |
| 4 | `src-python/spectrumagent/agent/tools/workflows.py:132-141` | `run_provenance()`：`step_{i}_op` / `step_{i}_version` 键 |
| 5 | `src-python/spectrumagent/agent/tools/workflows.py:398-411` | `Workflows.recipes()`：`recipe_{i}_step_{j}_op` 键 |
| 6 | `src-python/spectrumagent/agent/tools/workflows.py:464-480` | v2 工具注册表 `tools` 列表（15 条目） |
| 7 | `src-python/spectrumagent/agent/tools/__init__.py:237-243` | `invoke()` 标量白名单（str/int/float/bool/None） |
| 8 | `src-python/spectrumagent/agent/tools/__init__.py:333-337` | v2 才调 `register_workflows`（v1 目录不动） |
| 9 | `src-python/spectrumagent/agent/llm.py:197` | wire 名映射 `"sa_" + name.replace(".", "__")`（自动，无需接线） |
| 10 | `src-python/tests/agent/test_workflows.py:50` | `len(one.snapshot()) == 10`（v1 目录锁定，**本卡不得触碰该文件**） |
| 11 | `src-python/tests/agent/test_workflow_gateway.py:75-76` | wire 名唯一性 + `[a-zA-Z0-9_-]{1,64}`（双侧同源对比，加工具不破坏） |
| 12 | `src/components/preprocess/pipeline.ts:5` | `OPERATORS` 常量：10 个 S06 开放算子（R15 exhaustive） |
| 13 | `src/components/preprocess/PipelineEditor.tsx:33-35` | 下拉 `<option>` 显示裸 op 名 |
| 14 | `src/components/preprocess/PipelineEditor.tsx:41` | `<strong>{step.op}@{step.version}</strong>` 裸英文显示 |
| 15 | `src/components/preprocess/PreprocessPanel.tsx:174-175` | 报告区 `<h3>{step.op} · …</h3>` |
| 16 | `src/components/preprocess/pipeline.test.ts:8` | `OPERATORS` deepEqual 断言（本卡在此文件**追加**断言） |
| 17 | 需求 v2.7 `.runtime/docs/光谱数据AI-Agent处理平台_需求分析与设计.txt:943-990` | FR-B01–B09 权威术语（事实源） |
| 18 | ui-v2.3 `.runtime/docs/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.txt:1512-1516` | 算子链既有文案（反射率转换 / SNV 标准正态变量 / SG 一阶导） |

## 1. 起因

用户 2026-11-05 指令（原话）："对于项目里面每一步的算子都要有对应的严格的中文名称，在 AI 调用的时候能够方便用户查看更加直观"。现状断层：算子注册表只有 `name/version/model/impl`（registry.py:59-67），无任何显示名；AI 链路 `run_provenance`（workflows.py:137-139）与 `recipes`（workflows.py:408-410）把 `snv`、`sg_derivative` 等裸英文 id 直接透给用户；前端 `PipelineEditor.tsx:41` 渲染 `step.op@version` 英文裸串。本卡为该功能的唯一权威口径。

## 2. 拍板口径

| # | 口径 |
|---|---|
| 1 | **op 英文 id 是唯一寻址键，永不改**：配方 JSON、`BUILTIN_PIPELINE` 常量比对、`input_fingerprint` 复现链、数据库全部不动 |
| 2 | **中文名是纯展示层静态常量**：不进 DB、不进 fingerprint、不改任何数值结果 → **不 bump 任何算子 version**（registry.py:89 "同名同版本不可覆盖"机制不受影响） |
| 3 | **权威对照表唯一**：本卡 §3 表为字串唯一来源；后端 `registry.py` 常量与前端 `pipeline.ts` 常量是同一张表的两处实现，由两侧测试分别逐字锁定到 §3 |
| 4 | **命名来源**：优先需求 v2.7 第 3.2 章 FR-B01–B09 术语；同一 FR 下细分算子沿 ui-v2.3 行 1512–1516 既有文案风格（缩写 + 中文） |
| 5 | **缺名兜底**：表中没有的 op（将来注册的）展示层回退显示 op id 原文；未知算子显示英文名是可接受降级，猜测式翻译不可接受 |
| 6 | **AI 链路并列双列**：`step_{i}_op`（键，照旧保留）+ `step_{i}_name`（新增中文）；工具输出契约只增不改，既有键一个不删 |
| 7 | **实现形态取最小接触面**：registry.py 采用模块级常量方案，**不改 `OperatorEntry`、不改 `register()` 签名**，既有测试零接触 |

## 3. 权威中文对照表（13 算子，字串逐字锁定，执行方无裁量权）

| # | op id | 严格中文名 | 一句话用途（summary，≤30 字） | 命名依据 |
|---|---|---|---|---|
| 1 | `reflectance` | 反射率转换 | 原始 DN 转反射率；run 前置施加，配方内禁用 | FR-B01（需求 943–948）；ui-v2.3 1512 |
| 2 | `sg_smooth` | SG 平滑 | Savitzky-Golay 多项式平滑去噪 | FR-B02（949–951）；缩写风格沿 ui-v2.3 |
| 3 | `sg_derivative` | SG 导数 | Savitzky-Golay 一阶或二阶导数 | FR-B03（953–955 原文"SG 导数"） |
| 4 | `snv` | SNV 标准正态变量 | 逐谱去均值除标准差，校正散射差 | FR-B04（957–959）；ui-v2.3 1514 既有文案 |
| 5 | `msc` | MSC 多元散射校正 | 以显式参考谱回归校正散射 | FR-B04 |
| 6 | `emsc` | EMSC 扩展多元散射校正 | 含多项式基的扩展散射校正 | FR-B04 |
| 7 | `standardize` | 标准化与归一化 | standard、minmax、area、vector 缩放 | FR-B05（961–963） |
| 8 | `crop` | 波段裁剪 | 按波长闭区间筛选波段 | FR-B06（965–967） |
| 9 | `resample` | 波段重采样 | 按目标波长轴线性或样条重采样 | FR-B06 |
| 10 | `pca` | PCA 主成分降维 | 主成分降维去相关 | FR-B08（973–975） |
| 11 | `mnf` | MNF 最小噪声分离降维 | 按信噪比排序的降维 | FR-B08 |
| 12 | `ica` | ICA 独立成分降维 | 独立成分盲源分离降维 | FR-B08 |
| 13 | `continuum` | 连续统去除 | 凸包或线性连续统归一化 | FR-B09（977–979） |

> **display_name 与 summary 的字串以上表为准逐字复制**，包括空格与标点。表序 = `builtin_registry()` 注册序 = 常量字面量顺序 = 目录工具输出顺序。

## 4. 实现

### 4.A 后端常量（registry.py，纯新增）

文件：`src-python/spectrumagent/preprocess/registry.py`。在 `OperatorEntry` 定义（59–67 行）之后、`PipelineResult` 之前，纯新增三个模块级对象（**不改动该文件任何既有行**）：

```python
# TASK-27 §3 权威对照表：op id 是寻址键，中文名仅展示层；未登记算子回退原 id。
OPERATOR_DISPLAY_NAMES: dict[str, str] = {
    "reflectance": "反射率转换",
    "sg_smooth": "SG 平滑",
    "sg_derivative": "SG 导数",
    "snv": "SNV 标准正态变量",
    "msc": "MSC 多元散射校正",
    "emsc": "EMSC 扩展多元散射校正",
    "standardize": "标准化与归一化",
    "crop": "波段裁剪",
    "resample": "波段重采样",
    "pca": "PCA 主成分降维",
    "mnf": "MNF 最小噪声分离降维",
    "ica": "ICA 独立成分降维",
    "continuum": "连续统去除",
}
OPERATOR_SUMMARIES: dict[str, str] = {
    "reflectance": "原始 DN 转反射率；run 前置施加，配方内禁用",
    "sg_smooth": "Savitzky-Golay 多项式平滑去噪",
    "sg_derivative": "Savitzky-Golay 一阶或二阶导数",
    "snv": "逐谱去均值除标准差，校正散射差",
    "msc": "以显式参考谱回归校正散射",
    "emsc": "含多项式基的扩展散射校正",
    "standardize": "standard、minmax、area、vector 缩放",
    "crop": "按波长闭区间筛选波段",
    "resample": "按目标波长轴线性或样条重采样",
    "pca": "主成分降维去相关",
    "mnf": "按信噪比排序的降维",
    "ica": "独立成分盲源分离降维",
    "continuum": "凸包或线性连续统归一化",
}


def display_name(op):
    """中文展示名；未登记算子原样返回 op id，不猜测翻译（TASK-27 §2.5）。"""
    return OPERATOR_DISPLAY_NAMES.get(op, op)
```

### 4.B AI 链路并列输出 + 目录工具（workflows.py）

文件：`src-python/spectrumagent/agent/tools/workflows.py`。

1. **顶部 import 区**（第 25 行 `from spectrumagent.preprocess.migrations import …` 旁）追加：
   `from spectrumagent.preprocess.registry import OPERATOR_DISPLAY_NAMES, OPERATOR_SUMMARIES, display_name`
2. **`run_provenance()`（132–141 行）** 循环内、`result[f"step_{i}_op"] = step["op"]` 一行之后插入：
   `result[f"step_{i}_name"] = display_name(step["op"])`
3. **`Workflows.recipes()`（398–411 行）** 内层循环、`result[f"recipe_{i}_step_{j}_op"] = step["op"]` 之后插入：
   `result[f"recipe_{i}_step_{j}_name"] = display_name(step["op"])`
4. **新增模块级 handler**（放在 `run_get` 之后、`register_workflows` 之前）：

```python
def operators(arguments):
    """TASK-27 目录工具：只读常量，按注册序输出；不返回参数 schema 或路径。"""
    result = {"operator_count": len(OPERATOR_DISPLAY_NAMES)}
    for i, (op, name) in enumerate(OPERATOR_DISPLAY_NAMES.items(), 1):
        result.update({f"operator_{i}_id": op, f"operator_{i}_name": name,
                       "operator_{i}_summary": OPERATOR_SUMMARIES[op], "operator_{i}_version": 1})
    return result
```

5. **工具注册**：`register_workflows` 的 `tools` 列表（464–480 行）中、`("preprocess.recipes", …)` 条目**之前**插入：

```python
("preprocess.operators", NoArguments, "平台预处理算子目录：算子 id、严格中文名、一句话用途与版本；只读常量，不返回参数 schema 或路径", workflows.operators, runner is not None),
```

> 只进 v2（tools/__init__.py:333–337 门控）；v1 目录不动，`test_workflows.py:50` 的 `== 10` 不受影响。wire 名 `sa_preprocess__operators` 由 llm.py:197 自动映射，满足 `[a-zA-Z0-9_-]{1,64}`。输出全为 str/int 标量，过 invoke 白名单（tools/__init__.py:237–243）。

### 4.C 前端显示（pipeline.ts / PipelineEditor.tsx / PreprocessPanel.tsx）

1. **`src/components/preprocess/pipeline.ts`**：`OPERATORS` 常量（第 5 行）之后纯新增：

```ts
// TASK-27 §3 权威对照表的前端副本；与后端 registry.py 常量逐字一致，由测试锁定。
export const OPERATOR_NAMES: Record<string, string> = {
  reflectance: '反射率转换', sg_smooth: 'SG 平滑', sg_derivative: 'SG 导数',
  snv: 'SNV 标准正态变量', msc: 'MSC 多元散射校正', emsc: 'EMSC 扩展多元散射校正',
  standardize: '标准化与归一化', crop: '波段裁剪', resample: '波段重采样',
  pca: 'PCA 主成分降维', mnf: 'MNF 最小噪声分离降维', ica: 'ICA 独立成分降维',
  continuum: '连续统去除',
};
export const operatorName = (op: string) => OPERATOR_NAMES[op] ?? op;
```

2. **`PipelineEditor.tsx`**：
   - 第 2 行 import 增补 `operatorName`；
   - 第 33–34 行下拉 `<option>`：显示文案改 `{operatorName(name)}`（`key` 与 `value` 仍为 op id，**select 机制不变**）；
   - 第 41 行 `<strong>{step.op}@{step.version}</strong>` 改为 `<strong title={`${step.op}@${step.version}`}>{operatorName(step.op)}</strong>`（主体纯中文对齐 ui-v2.3；技术键保留在悬停提示）。
3. **`PreprocessPanel.tsx`** 第 175 行 `<h3>{step.op} · …</h3>` 改 `<h3>{operatorName(step.op)} · …</h3>`（import 增补 `operatorName`）。

### 4.D 测试（新文件优先，in-flight 文件零触碰）

**禁改**：`tests/agent/test_workflows.py`、`tests/annotation/test_superpixels.py` 等当前 M/?? 状态文件（另一条工作线在途）。

1. **新文件 `src-python/tests/preprocess/test_operator_catalog.py`**：
   - 常量键集 == `builtin_registry()` 注册的 13 op 名集合（逐键比对，防两表漂移）；
   - 13 对 `(op, 中文名)` 与 13 对 `(op, summary)` 逐字 deepEqual 卡 §3 表（表内字串原样写进测试）；
   - `display_name("not_registered_op") == "not_registered_op"`（回退）；每值非空、无换行。
2. **新文件 `src-python/tests/agent/test_operator_names.py`**：
   - v1 复验：`build_registry(catalogue_version=1).snapshot()` 长度 == 10 且不含 `preprocess.operators`（**新断言**，不搬动 in-flight 的 test_workflows.py:50）；
   - v2 snapshot 含 `preprocess.operators`，其 description 非空且无路径/盘符模式；整个 v2 快照过 `_egress_blocked`（从 `spectrumagent.agent.llm` 导入，参照 in-flight test_workflows.py:56 的既有口径，但断言写在新文件里）；
   - `invoke("preprocess.operators", {})`：`operator_count == 13`、`operator_1_id == "reflectance"`、`operator_1_name == "反射率转换"`、`operator_13_id == "continuum"`；13 对 (id, name) 循环断言与卡 §3 一致；
   - `run_provenance`：内存 sqlite 建 `preprocess_recipe_version` 表插一行 snv + sg_derivative 配方（BUILTIN_PIPELINE 同款两步），传入含 `recipe_version_id` 的 row dict，断言 `step_1_name == "SNV 标准正态变量"`、`step_2_name == "SG 导数"`、`step_1_op == "snv"`（既有键与新键并列共存）；
   - `Workflows.recipes`：用 `SimpleNamespace` 伪造 `runner.recipes.list()` 返回单配方两步版本，断言 `recipe_1_step_1_name` 与 `recipe_1_step_2_name` 正确。
3. **`src/components/preprocess/pipeline.test.ts`**（该文件当前 clean，可追加）：
   - import 增补 `OPERATOR_NAMES, operatorName`；
   - `OPERATOR_NAMES` 13 键序与键值逐字 deepEqual 卡 §3（字串原样写进测试）；
   - `operatorName('not_registered_op') === 'not_registered_op'`（回退）。
4. 若 `panel.test.ts`（48–64 行源码文本 wiring 断言）因显示字串变更而红：**允许同步更新该断言**（授权非弱化：只许按新文案改 matcher，不许删除断言）。

### 4.E 文件清单（出现清单外文件即停）

| 文件 | 动作 | in-flight 状态 |
|---|---|---|
| `src-python/spectrumagent/preprocess/registry.py` | 纯新增常量+函数 | clean |
| `src-python/spectrumagent/agent/tools/workflows.py` | 3 处插入 + 1 handler + 1 注册条目 | clean |
| `src-python/tests/preprocess/test_operator_catalog.py` | 新建 | — |
| `src-python/tests/agent/test_operator_names.py` | 新建 | — |
| `src/components/preprocess/pipeline.ts` | 纯新增常量 | clean |
| `src/components/preprocess/PipelineEditor.tsx` | 3 行显示改动 | clean |
| `src/components/preprocess/PreprocessPanel.tsx` | 2 行显示改动 | clean |
| `src/components/preprocess/pipeline.test.ts` | 追加断言 | clean |
| `src/components/preprocess/panel.test.ts` | 仅当变红才同步（授权非弱化） | clean |
| `TASK-27-算子中文名称体系.md` | 本卡（备卡方已单文件提交） | 已提交 |

## 5. 明确不做（越界即停）

1. 不改任何 op id、`Step`/`Pipeline` schema、`OperatorEntry`、`register()` 签名、数据库、`BUILTIN_PIPELINE`、fingerprint；不 bump 任何算子 version。
2. 不新增 REST 端点、不动 OpenAPI 快照（目录工具只进 LLM 工具目录，走 workflows 通道）。
3. 不做算子参数级中文名（`Field(description=…)`）：算子参数当前不出现在任何 LLM 工具 schema 中（对话编排只引用已保存配方版本 id），无 AI 可见价值；将来开放对话侧自定义配方编排时另立卡。
4. 不动 v1 工具目录（`test_workflows.py:50` 的 `== 10` 锁定）；不做参数名/枚举值中文化；不引入 i18n 框架。
5. 不触碰 in-flight 文件：`test_workflows.py`、`test_superpixels.py`、`test_recycle.py`、`AnnotationWorkbench.tsx`、`superpixels.py`、`App.tsx`、`S01/S11.tsx`、`SmokePanel.tsx`、`assistant/*`、`datasets/*`、`annotation/*` 等当前 M/?? 状态文件。
6. 不为标注引擎操作（SLIC/扩散/确认/拒绝等）建中文对照表：其工具描述层已是中文（workflows.py:459–480），本卡不重复建表。
7. 不做 SAM / 自动标注相关任何内容（用户已明确分卡推进，本卡只做算子中文名体系）。

## 6. 验收表（可执行、不自指）

| # | 项 | 门 |
|---|---|---|
| 1 | Python 分区 | `PYTEST_DEBUG_TEMPROOT=<临时目录> .venv\Scripts\python.exe -m pytest src-python/tests/agent src-python/tests/preprocess -q` = **768 + N 全绿**（基线 768 实测见 §0.1；N 为本卡新增用例数，须在回报列明） |
| 2 | 前端 | `node --test "src/**/*.test.ts"` = **249 + N 全绿**（基线 249/249 实测） |
| 3 | 类型 | `npm run build`（`tsc --noEmit && vite build`）通过 |
| 4 | v1 目录不变 | 新测试断言 v1 snapshot == 10 且无 `preprocess.operators`；`preprocess.operators` 仅存在于 v2 |
| 5 | 并列双列共存 | `run_provenance` 输出同时含 `step_1_op == "snv"` 与 `step_1_name == "SNV 标准正态变量"`（新测试逐字断言） |
| 6 | 字串权威 | 两侧测试（Python + 前端）各有一张 13 对字串表，与卡 §3 逐字一致；`display_name`/`operatorName` 未知 op 回退原 id |
| 7 | egress 反证 | 新测试断言整个 v2 snapshot 过 `_egress_blocked`（新工具描述与中文名不含路径/盘符/反斜杠模式） |
| 8 | OpenAPI 无关性 | `.venv\Scripts\python.exe -m pytest src-python/tests/data/test_api.py::test_api_schema_snapshot -q` 原样通过（本卡零 API 改动的反证） |
| 9 | grep 证据 | 回报附 `grep -n "step_%i_name\|_name\b" src-python/spectrumagent/agent/tools/workflows.py` 与新键、新工具注册行的原文 |

## 7. 提交与证据

- **本卡已由备卡方单文件提交入库**（禁 `-A`）。
- 实现分两段提交，均逐文件 `git add`：
  1. 后端：registry.py、workflows.py、两个新测试文件；提交信息 `feat(preprocess): 算子严格中文名常量与 AI 链路并列输出（TASK-27 §4.A/§4.B/§4.D）`；
  2. 前端：pipeline.ts、PipelineEditor.tsx、PreprocessPanel.tsx、pipeline.test.ts（及如有 panel.test.ts）；提交信息 `feat(ui): S06 算子链中文名显示与映射常量（TASK-27 §4.C）`。
- 证据归档 `milestone27/evidence/`：`node.txt`（前端全量输出原文）、`pytest-partition.txt`（分区输出原文）、`build.txt`、`grep.txt`（§0.2 锚点复核 + §6.9 键存在证明）。
- 不 tag、不 push、不打包；远程推送归用户本人。

## 8. 即停条款

1. §0.2 任何锚点行号与实物不符：即停上报，**不得自行改写本卡**。
2. 出现 §4.E 清单外文件改动：即停。
3. 卡内未写死的口径（含中文字串与 §3 不一致、显示格式细节歧义）：一律停下问，不许自造。
4. 任何既有用例变红：即停；禁止为凑数删改现有测试。
5. 工作区 in-flight 文件（§5.5 清单）出现本卡署名改动：即停。

## 9. 修订记录

| 日期 | 内容 |
|---|---|
| 2026-11-05 | 备卡定稿：13 算子字串表锁定；常量最小接触面方案；基线实测（前端 249/249、Python 分区 768 passed）；卡单文件提交入库 |

> AI生成
