# 里程碑 #04：标注（L1 辅助标注）

**任务卡编号**：TASK-04-标注L1
**前置里程碑**：#03 打包里程碑（已封账，release 0.1.1，含数据接入）
**定稿日期**：2026-10-20（业务口径由科祥当日拍板）
**需求依据**：需求分析与设计 v2.7（3.5 / 6.4 / 6.7）、第一阶段 UI 原型 ui-v2.3（S05）、技术选型定稿 v1.1
**能力断言背书**：scikit-image 0.26（SLIC）、scikit-learn 1.9.1（PCA）均在 `requirements-lock.txt` 内，全 CPU。2026-10-20 探针实测：skimage 0.26.0 / sklearn 1.9.1 / numpy 2.5.4 可导入并在真实 cube 上跑通 `slic` 与 `IncrementalPCA`。

---

## 1. 目标

实现标注子系统的 **L1 辅助标注**能力：机器把图像切成超像素并按光谱相似度扩散出候选区域，人只做逐块确认/修正与赋标签，最终：

- 产出**像素级标注**（label map，版本化保存）
- 自动聚合出**带标签样本光谱**（每类/每样品的均值谱 ± 标准差）——它是后续 FR-B10 配方选型、模型训练、指标验收的共同"尺子"
- 标注血缘挂接：原始立方体 → 标注版本 → 样本光谱（FR-H07 数据节点落库）

**不做自动赋标**：L1 机器只给候选区域，不给标签。库匹配、聚类命名、历史迁移、模型预标注、置信度门控均属 L2/L3，阶段二。

---

## 2. 业务口径（2026-10-20 科祥拍板，三要素）

| 要素 | 口径 | 置信度 |
|---|---|---|
| **谁来标** | **单人（研究者本人）**。无账号、无登录、无组织/权限、无多人协作；FR-E09 双人标注 + Kappa + 仲裁随阶段二 | 高 |
| **标注粒度** | **以超像素/区域为操作单位的像素级标注**，自动聚合样本级；场景级**不落 annotation 行**，仅读导入元数据透出（口径见 5.4）。不做"整图一标签" | 高 |
| **类别体系** | **项目级标签树（FR-E02，结构化、可扩展）**；内置塑料标准目录供项目选用；不做无约束自由文本 | 高 |

**塑料类别口径（含已核实事实）**：
- 科祥当前数据 `E:\高光谱数据集\plastic\` 只有 **PE / PET / PP 三类**（TASK-02 已确认 pe/pet/pp 三个子目录），阶段一塑料项目即预置这三类 + 背景。
- 塑料标准类别远不止三种。科祥列出的常用塑料类别（PE、PET、PP、PS、PVC、HDPE、LDPE、ABS、PC、PA、PTFE、PMMA、PAN、PBT、PCL、POM、PLA、TPU、PPO、PPS、SAN 等）以**随包内置"塑料标准目录"**形式提供，项目标注时按需从目录添加；未来其他数据集（非塑料）可自建标签树。
- **两处标准命名修正（化学通用名，高置信度，目录种子以此为准）**：
  1. **PS = 聚苯乙烯**（科祥单中写"聚丙乙烯"，非标准名）；
  2. **聚氯乙烯的标准缩写是 PVC**（科祥单中写"PY"，非标准缩写）。
- 需求文档 v2.7 中场景 S1 出现的 PP/PET/PS/ABS 四类是**示例项目**口径，与当前真实数据集三类不冲突——以真实数据为准，真实数据三类已核实。

---

## 3. 范围裁定（阶段权威在第 8 章路线图，不在 P 标签）

**口径说明（P0 ≠ 阶段一）**：FR-E11–E13/E15–E17/E21 虽标 P0，但 E 域总表写明"阶段一 · L1"，这些需求属于 L2/L3 链路，随阶段二交付。codex 不得因"P0 为什么不做"困惑——阶段划分以路线图为准。

### 3.1 做（#04 交付）

| FR | 需求 | 阶段一交付口径 |
|---|---|---|
| FR-E01 | 三级标注粒度 | 像素级（超像素/区域/多边形/画笔）+ 自动聚合样本级；场景级**不写 annotation 行**，仅读取导入元数据（仪器/波段/批次）透出，见 5.4 |
| FR-E02 | 标签体系管理 | 项目级标签树；枚举/布尔/连续/序数四类字段；塑料项目预置 PE/PET/PP/背景 |
| FR-E03 | 超像素预分割 | SLIC（PCA 降维后，特征口径与参数见 5.2），块内方差超阈自动细分；n_segments=800，compactness **单 cube 初值 0.5**（非红线，11 cube 标定后定稿） |
| FR-E04 | 光谱相似度扩散 | 种子一画按光谱距离扩散，**阈值实时可调并预览；初始默认 cos ≥ 0.92（默认值，非硬常数）** |
| FR-E05 | 标注版本与不可篡改 | 每次保存生成版本、可回溯；覆写二次确认（FR-D07，**仅限覆盖当前最新版本**，语义见 4.2） |
| FR-E06 | 标注质量校验 | **阶段一 lite**：标注区内光谱离群/块内高方差清单 + 完整度统计；"标签与聚类中心冲突"项无模型不适用，报告中显式标注 |
| FR-E18 | 交互式提示分割 | **P1 例外，阶段一做**：走 FR-E18 的"**或**光谱相似度扩散"路径——单击/框选/涂鸦为提示 → 光谱扩散生成候选；SAM 类模型路径（需 PyTorch/GPU）随 GPU 附加包/阶段二 |
| FR-H01 | 标注结果入库 | 像素级/样本级标注全量入库（几何、时间、source=manual） |
| FR-H07 | 数据血缘 | 标注版本节点与血缘边（cube→version→sample_spectrum）落库；血缘可视化界面不属本卡 |

### 3.2 不做（阶段二）

- **FR-E07–E17、E19–E22 全部**：主动学习、预标注 HITL、多人标注、覆盖度看板、自动化分级、库匹配、历史迁移、簇命名工作流、模型预标注、门控、复核队列、解混映射、跨立方体迁移、溯源、质量监控与自动降级。
- **FR-E14 不做独立簇命名工作流**（方法论属 L2）；超像素聚合天然服务"像素→样本聚合"，不额外开发。
- 字段预留但不实现逻辑：`annotation.source` 阶段一恒为 `manual`；`confidence`、`evidence`、`annotator_id` 恒为 NULL（ER 图字段保留，阶段二不挡路）。

---

## 4. 数据模型（先定 schema，再实现）

沿用 #02 既有模式：**raw sqlite3 + 同一数据库文件** `paths.database`（`%LOCALAPPDATA%\SpectrumAgent\db\spectrum-agent.sqlite3`），不引入新依赖（SQLAlchemy 已在 lock 但本卡沿用裸 sqlite3 以保持一致）。

### 4.1 迁移（幂等，启动时执行；迁移只增不删）

```sql
-- 项目（阶段一：仅默认项目一条；project_id 为阶段二账号体系预留）
CREATE TABLE IF NOT EXISTS project (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  note       TEXT
);

-- 标签字段（schema）：枚举/布尔/连续/序数
CREATE TABLE IF NOT EXISTS label_schema (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id),
  name       TEXT NOT NULL,
  tree_path  TEXT NOT NULL,
  field_type TEXT NOT NULL CHECK (field_type IN ('enum','bool','continuous','ordinal')),
  unit       TEXT,
  config     TEXT,                    -- JSON：连续值域 {min,max} / 序数档位 / 布尔默认值
  created_at TEXT NOT NULL,
  UNIQUE (project_id, tree_path)
);

-- 枚举值（标签）
CREATE TABLE IF NOT EXISTS label (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES project(id),
  schema_id   TEXT NOT NULL REFERENCES label_schema(id),
  code        TEXT NOT NULL,
  name        TEXT NOT NULL,
  tree_path   TEXT NOT NULL,
  color_hex   TEXT NOT NULL,
  shortcut_key INTEGER,               -- 0 仅背景；1–9 其余；>9 类超出部分留 NULL（仅鼠标点选）
  sort_order  INTEGER NOT NULL,
  is_background INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  UNIQUE (project_id, code),
  UNIQUE (project_id, shortcut_key),
  CHECK (shortcut_key IS NULL
         OR (shortcut_key = 0 AND is_background = 1)
         OR (shortcut_key BETWEEN 1 AND 9))
);

-- 标注版本（先建版本表，annotation 对它有外键）
CREATE TABLE IF NOT EXISTS annotation_version (
  id             TEXT PRIMARY KEY,
  cube_id         TEXT NOT NULL,
  version_no      INTEGER NOT NULL,
  snapshot_ref    TEXT NOT NULL,      -- 快照目录（label_map.npz / spectra.npz / label_index.json）
  n_pixels        INTEGER NOT NULL,
  labeled_pixels  INTEGER NOT NULL,
  auto_ratio      REAL NOT NULL DEFAULT 0,   -- 阶段一恒 0
  params          TEXT NOT NULL,             -- JSON：当次分割参数（n_segments/compactness/pca_components/k/block_size/特征口径版本），复现性凭据
  note            TEXT,
  created_at      TEXT NOT NULL,
  UNIQUE (cube_id, version_no)
);

-- 标注区域（**每 label 一条/版本**，不是操作日志；几何 = 该 label 全覆盖的超像素 id 集合，仅供追溯）
-- granularity 描述【记录粒度】，非操作粒度：'sample'=阶段一落库形态（每 label 每版本一条，
-- 由像素级标注聚合而来，即 FR-E01"整条平均谱一个标签"）；'pixel'=像素级明细记录（阶段一
-- 不落库，由工作态 label_map/撤销栈/快照承载，阶段二扩展）；'scene'=场景级（阶段二预留，无写入路径）
-- 'scene' 无写入路径（见 5.4）
CREATE TABLE IF NOT EXISTS annotation (
  id          TEXT PRIMARY KEY,
  cube_id     TEXT NOT NULL,
  version_id  TEXT NOT NULL REFERENCES annotation_version(id),
  granularity TEXT NOT NULL CHECK (granularity IN ('pixel','sample','scene')),
  label_id    TEXT,                   -- enum 时引用 label.id
  label_value TEXT,                   -- JSON：bool / continuous / ordinal 取值
  geometry    TEXT,                   -- JSON：{"superpixels":[...]} 或 {"polygon":[[l,s],...]}
  pixel_count INTEGER NOT NULL,
  source      TEXT NOT NULL DEFAULT 'manual'
              CHECK (source IN ('manual','library','cluster','transfer','model','unmix')),
  confidence  REAL,                   -- 预留，阶段一恒 NULL
  evidence    TEXT,                   -- 预留，阶段一恒 NULL
  annotator_id TEXT,                  -- 预留，阶段一恒 NULL
  created_at  TEXT NOT NULL,
  CHECK (label_id IS NOT NULL OR label_value IS NOT NULL)
);

-- 样本级光谱（带标签样本光谱）
CREATE TABLE IF NOT EXISTS sample_spectrum (
  id          TEXT PRIMARY KEY,
  cube_id     TEXT NOT NULL,
  version_id  TEXT NOT NULL REFERENCES annotation_version(id),
  label_id    TEXT,
  label_value TEXT,
  sample_code TEXT NOT NULL,          -- 样品标识：阶段一取数据集名（cube name）
  n_pixels    INTEGER NOT NULL,
  mean_ref    TEXT NOT NULL,          -- spectra.npz 内键名
  std_ref     TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  CHECK (label_id IS NOT NULL OR label_value IS NOT NULL)
);
```

**对 #02 表的兼容性变更（加列，不破坏既有逻辑）**：
```sql
ALTER TABLE dataset_registry ADD COLUMN project_id TEXT;   -- 回填默认项目 id
```
- 迁移启动时检测列是否存在（`PRAGMA table_info`），不存在才 ALTER；既有行回填默认项目 id。
- **每个连接都要 `PRAGMA foreign_keys=ON`**（SQLite 默认关闭；不开则 4.1 里的 `REFERENCES` 全是装饰，`annotation.version_id` 的外键形同虚设）。
- 首次启动种子：插入默认项目（`默认项目`）；为塑料项目创建 label_schema（name=`材料`、**tree_path=`材料`（单段，不含 `/`）**、field_type=`enum`）+ 四个 label（PE/PET/PP/背景，见 4.3，**tree_path 取 4.3 表值**）。种子幂等（按 code 去重）。
- **`label` 表 NOT NULL 列的写入路径覆盖（R13，三条写入路径共用；`schema_id` / `tree_path` / `sort_order` 三者均**不出现在请求体**）**：
  - **`schema_id` 定位规则**：`label_schema.tree_path` 为**单段名**（不得含 `/`；阶段一唯一值 `材料`）；`label.tree_path` 为三段 `材料/塑料/<code>`，其**第一段必须精确匹配**项目内某个 `field_type='enum'` 的 schema 的 tree_path——服务端据此自动定位 `schema_id`。理由：若 schema 自身 tree_path 含 `/`，则该 schema 永远匹配不上（取第一段后不可能等于含 `/` 的整串）。无匹配 → 422 结构化错误（提示先建对应 schema 或从目录添加）。阶段一只有 `材料` 一个 enum schema，故所有 enum 标签（预置/目录/自定义）一律归属它；多 schema 时按第一段区分，不歧义、**无默认猜测**。
  - **`tree_path` 供值**：预置=§4.3 表值写死；目录添加=服务端按 `材料/塑料/<code>` 生成；自定义=body 传入（仍须满足上条第一段匹配）。
  - **`sort_order` 供值**（同列 NOT NULL，原卡三路径皆未定义）：预置=§4.3 的 sort_order 列（BG=0/PE=1/PET=2/PP=3）；目录添加=该 code 在 §4.4 目录固定顺序中的序号（PE=1 … SAN=21，**与添加先后无关、稳定可复现**）；自定义 enum=当前项目内 `max(sort_order) + 1`（追加末尾；**项目内尚无 label 时 `max` 为 NULL，取 1**——非塑料项目的自定义场景会走到这一支）。
  - 实现上 `schema_id` 定位与 `sort_order` 取值各收敛为**一个函数**，三条路径共用，不得在别处另起一套（防规则漂移）。

### 4.2 快照文件布局（大数组不进 DB；与阶段二产物层思路一致）

```
%LOCALAPPDATA%\SpectrumAgent\annotations\<cube_id>\v<version_no>\
├── label_map.npz        # int32 (L,S)：-1=未标注(留白)、-2=人看过但给不出类(不确定)、≥0=label_index.json 中的整数下标
├── label_index.json     # {"0": "<label_id>", "1": "<label_id>", ...}
└── spectra.npz          # 每键一个 label：mean_<n>=(B,) float64、std_<n>=(B,) float64
```

- **落点与 `snapshot_ref`（R15 钉死）**：`paths.py` 增 `snapshots` property（与 db/logs/testdata 平级、随 `from_environment` 派生、**禁硬编码绝对路径、禁写源目录**）；实际路径 `<snapshots>/<cube_id>/v<version_no>/`；`annotation_version.snapshot_ref` 存**相对 `snapshots` 根的 POSIX 路径**（如 `<cube_id>/v1`），**不存绝对路径**（数据根可迁移，绝对路径会失效）。DB 短事务提交是唯一提交点；快照先写 `.tmp` 再 `os.replace`。
- 工作态（未落库）的超像素图、工作 label map 存 sidecar 内存（按 cube_id + 参数），可随时按参数重算，不依赖会被清理的 scratch（教训记录：验收只读落库快照，不读运行期临时文件）。
- **覆写语义（唯一解释，不得再分叉）**：`save` 默认**新建版本**（version_no 递增），**任何历史版本不可改**；"覆写"**仅指用当前工作态重写当前最新版本**（version_no 最大者，version_no 不变），必须携带 FR-D07 确认标记——未携带 → 409 结构化错误，携带 → 覆写事件随版本入库（**R19 钉死，修订 R17**：`annotation_version.note` 唯一承载版本事件 JSON——覆写=`{"event":"overwrite","at":"<ISO8601 UTC>","text":<用户 note 或省略>}`；新建带用户 note=`{"event":"save","at":"...","text":"..."}`；**新建且无用户 note=NULL**（R17"新建 note=NULL"相应修订）；`created_at` 保留版本首次创建时间、不随覆写改变；与旧行重写同一短事务 UPDATE。`save` body 收 `note?`（用户备注，**≤2000 字符**，超长 → 400 `INVALID_VERSION_NOTE`；请求模型 `max_length` + 应用层双重校验）；`session.save` 仅增加 `note=None` 参数与 JSON 组装，其余逻辑不动）。不存在"覆写中间历史版本"的路径（FR-E05 的"覆写二次确认"即指此，见 5.6）。
  - **覆写时的旧行处置（不写就是同版本重复行）**：在同一短事务内**先删**该 `version_id` 下的全部 `annotation` 与 `sample_spectrum` 行，**再重写**，并 `UPDATE annotation_version` 的 `snapshot_ref`/`n_pixels`/`labeled_pixels`/`auto_ratio`/`params`/`note`（**不含 `created_at`**——R19 钉死保留首次创建时间；与 10.3 实现 session.py 的 UPDATE 列表逐列一致）。快照三件先写 `.tmp` 再 `os.replace` 覆盖同名文件，避免半写状态。
  - 当前**无任何版本**时 `overwrite=true` → 409（无"最新版本"可覆写），不得静默降级为新建。

### 4.3 塑料项目初始标签（预置值）

| sort_order | code | tree_path | name | color | shortcut |
|---|---|---|---|---|---|
| 1 | PE | `材料/塑料/PE` | 聚乙烯 | `#5aa469` | 1 |
| 2 | PET | `材料/塑料/PET` | 聚对苯二甲酸乙二醇酯 | `#c98a3c` | 2 |
| 3 | PP | `材料/塑料/PP` | 聚丙烯 | `#2f7fb0` | 3 |
| 0 | BG | `材料/塑料/BG` | 背景 | `#9aa7b2` | 0（固定，不用 5） |

- **`tree_path` 说明**：四个预置 label 的 tree_path 即上表值，种子插入时按此写死（该列 NOT NULL，供值方式为"种子数据"）。BG 第一段同为 `材料` 是工程必然——阶段一只有一个 enum schema，背景必须归属某个 enum schema 才能满足 `schema_id` NOT NULL；语义上"背景非材料"的别扭记录在案，不为其增设第二个 schema（阶段二再拆）。
- 快捷键约定：**0 为背景专用**；1–9 给其余标签，项目内唯一；**超过 9 类时超出部分 `shortcut_key` 留 NULL**（仅鼠标点选，快捷键表可查/可改/可关）。0 不得分配给 `is_background=0` 的标签（4.1 **表级 CHECK** 硬约束 + 5.1 校验给友好报错，两道都在）。

### 4.4 内置塑料标准目录（随包代码种子，git 跟踪，只读）

- 位置：`src-python/spectrumagent/annotation/catalog/plastic.json`
- 内容：code、标准中文名、初始色值（可被项目覆盖）。条目：
  PE（聚乙烯）、PET（聚对苯二甲酸乙二醇酯）、PP（聚丙烯）、PS（聚苯乙烯）、**PVC（聚氯乙烯）**、HDPE（高密度聚乙烯）、LDPE（低密度聚乙烯）、ABS（丙烯腈-丁二烯-苯乙烯塑料）、PC（聚碳酸酯）、PA（聚酰胺）、PTFE（聚四氟乙烯）、PMMA（聚甲基丙烯酸甲酯）、PAN（聚丙烯腈）、PBT（聚对苯二甲酸丁二醇酯）、PCL（聚己内酯）、POM（聚甲醛）、PLA（聚乳酸）、TPU（热塑性聚氨酯弹性体）、PPO（聚苯醚）、PPS（聚苯硫醚）、SAN（苯乙烯-丙烯腈共聚物）。
- **色值生成规则（可复现，非手填）**：PE/PET/PP 沿用 §4.3；其余 18 种按目录固定顺序从 PS 起算，第 j 个（j=0..17）取色相 `hue = j × 20°`、饱和度 55%、亮度 45%，HLS→RGB 后**四舍五入**转 hex（`round(r×255)` 等）。初始色值（均可被项目内覆盖）：
  PS `#b23434`｜PVC `#b25e34`｜HDPE `#b28834`｜LDPE `#b2b234`｜ABS `#88b234`｜PC `#5eb234`｜PA `#34b234`｜PTFE `#34b25e`｜PMMA `#34b288`｜PAN `#34b2b2`｜PBT `#3488b2`｜PCL `#345eb2`｜POM `#3434b2`｜PLA `#5e34b2`｜TPU `#8834b2`｜PPO `#b234b2`｜PPS `#b23488`｜SAN `#b2345e`
- 目录色值为初始建议（项目内可改）；项目标签树从目录"选用"而非自动全量灌入（当前项目只放实际存在的类）。
  - **已知色近冲突（记录在案，不阻塞 10.1）**：生成色 `PBT #3488b2` 与 §4.3 预设 `PP #2f7fb0` 的 RGB 欧氏距离仅 **10.5**（满量程 441），叠加图上几乎不可区分。触发条件：用户在已含 PP 的项目里再从目录选用 PBT。缓解：目录色本就可被项目覆盖；10.6 前端"从目录添加"时若与已有标签色距 < 30 给出可覆盖提示（**属 10.6 范围，10.1 不实现**）。不改生成规则：偏移 10°/20° 仍是 10.5，偏移 15° 也只到 19.7，换规则解决不了根本（PP 的蓝正好落在生成色的蓝带上）。
- **目录条目入项目时的 `tree_path`**：`材料/塑料/<code>`（第一段 `材料` = 项目 enum schema 的 tree_path，阶段一固定）。从目录添加时由**服务端按此规则生成**，请求体不收 `tree_path`（该列 NOT NULL，供值方式为"服务端规则"）。
- 非塑料数据集：创建自定义 label_schema（enum/bool/continuous/ordinal），不依赖塑料目录。

---

## 5. 开发任务（按执行顺序）

### 5.1 迁移与标签/项目存储

- 新增 `src-python/spectrumagent/annotation/` 包：`migrations.py`（建表 + ALTER + 种子，幂等）、`catalog/`（塑料目录种子）、`labels.py`（LabelStore：标签树查询、从目录添加、自定义新增、schema 字段新增）。
- 项目：阶段一仅默认项目；`GET /api/v1/projects` 返回列表。项目 CRUD 不做（阶段二）。
- 新增标签的输入校验：code 项目内唯一、`tree_path` 非空**且第一段须精确匹配项目内 `field_type='enum'` 的 schema（服务端据此定位 `schema_id`，无匹配 → 422，规则见 4.1 R13）**、颜色合法 hex、快捷键 **0–9**（0 仅限 `is_background=1`）且项目内唯一、**>9 类时超出部分不分配快捷键（NULL，SQLite 的 UNIQUE 允许多个 NULL，不会冲突）**；自定义标签与目录标签走同一张表、同一份结构化登记（不产生自由文本）。快捷键越界（10 及以上）或重复 → 结构化错误。
- **`schema_id` / `sort_order` 均不出现在任何请求体**：三种 enum 标签写入路径的供值方式见 4.1 R13（预置=种子数据写死；目录添加=服务端生成；自定义=服务端按规则推导）。实现上统一走"tree_path 第一段 → enum schema"与"sort_order 取值"两个函数，不得在别处另起一套（防止两处规则漂移）。

### 5.2 超像素引擎（FR-E03）

- **取数**：必须经 `Registry.readable(cube_id)` 拿已校验的数据集对象（registry.py:134 起，逐字段比对 shape/dtype/interleave/wavelengths/fwhm，不一致抛 SOURCE_CHANGED）。**禁止自行 `read_header` 打开 hdr**，否则 6.4 的 SOURCE_CHANGED 断言无实现路径。
- **轴序（易错，务必按此）**：`SpectrumDataSet.shape` = **(lines, samples, bands)**、`shape[2]` 才是波段数（model.py:38/60）；磁盘 BIL 布局为 (lines, bands, samples)=(231,200,640)。`read_region(l0,l1,s0,s1)` 返回 **(ΔL, ΔS, B)、bands 在最后一轴**，正好喂 PCA。
- **流程**：分块有界读数（按行块，默认 32 行）→ `IncrementalPCA`（`n_components` 默认 5，按行块 `partial_fit` 后再第二遍 `transform`；**两遍都重读盘，不得缓存原始块**）→ 特征口径见下 → `skimage.segmentation.slic`。
  - 分块大小只影响 PCA **尾部**精度（PC5 与 32 行块结果相关 0.9966 @ 单批全量），**不影响分割结论**：实测 32/64/128/单批四种分块下 n=765/765/765/766、area_cv=0.177–0.183。故分块大小不是复现性风险项，但须在响应里回报实际值。
- **特征口径（compactness 的可迁移前提，改口径必须重标定 compactness）**：
  1. transform 一遍把特征图 (L,S,k) float32 填满（这张图允许驻留，见下"物化边界"）；
  2. **直接在这张驻留特征图上**按分量算均值/标准差（float64 累加）并**原地** z-score——不额外读盘，**也不用 `explained_variance_` 反推**：实测该反推与 transform 后实测 std 的相对误差在 **1e-3 量级**，且**随分块/batch 配置漂移**（32 行块 1.25e-3、64 行块 1.54e-3、128 行块 1.12e-3、单批全量 3.4e-6），属 sklearn 逐批累加的实现细节，版本间无契约，**不可当作可复现的统计量**；
  3. `clip(±3)`（防热像素/死像素把全局范围撑坏）；
  4. 线性映射到 [0,1]（即 `(x+3)/6`，clip 后区间恒定，映射无歧义）。
  skimage 0.26 的 slic 内部还会做一次全局 min-max 归一化（`slic_superpixels.py:281-291`，注释明说为让 compactness 与输入尺度无关），所以**绝对尺度不用管，但分量间相对权重由本口径决定**——这正是 0.5 这个初值绑定的对象。
- **slic 调用参数（写死，不许省）**：`n_segments=800`、`compactness=0.5`（**11 cube 标定选定值，非红线**，见下）、`channel_axis=2`、**`convert2lab=False`（强制）**、`start_label=0`。
  - `convert2lab=False` 不是卫生动作：默认 `None` 时**只要通道数等于 3 就会静默转 Lab**（`slic_superpixels.py:311-315`），而 `pca_components` 是 5.6 的暴露参数。实测 `pca_components=3` + 默认值：m=0.5 → **n=18**、m=10 → **n=193**（不抛异常、不告警）；显式 False 同参数 → 773 / 782。
- **compactness 标定值 0.5**：单 cube（pe/20260804205214_64）实测，口径如上——m=0.5 → n=765（**细分前**）、area_cv=0.182、R≈1.8（1.77–1.82，随分块浮动）；m=10 → n=782、area_cv=0.068、R≈1.07（≈规则网格，FR-E03 名存实亡）。**11 cube × 5 档全量标定确认保留 0.5**（实现层标定值，非需求硬常数）：仅此档 11/11 同时满足现有结构断言；完整实测及选定依据见 `milestone04/evidence/calibration/compactness.csv`、`summary.json`。
- 产出（工作态内存）：超像素图 `segments` int32 (L,S)、超像素数、每个超像素的**均值光谱**（按行块累积像素和与计数）、**逐波段标准差向量**（累积 sum 与 sumsq，形状 (n_super, B)）。
- **块内高方差自动细分（无歧义定义，实现与验收共用；已按实测修订过一次，勿回退）**：
  - 对超像素 s，在其**原始波段空间**（反射率 0–1，非 PCA 空间）取逐波段标准差向量 `std_s ∈ R^B`，标量 `d_s = mean_b(std_s[b])`；
  - 阈值 `τ = k × median_all(d_s)`，k 默认 3（参数化，非硬常数）；
  - 细分条件：`d_s > τ` **且** 像素数 ≥ 8（仅排除碎片）。**不得再加"像素数 ≥ 2×目标子块面积"这类体量门槛**——实测该门槛在本数据上通过数为 **0**（高方差块反而偏小：中位 174 px < 全体中位 195 px），加了等于细分永不触发；
  - 细分粒度：子块目标面积 = `目标子块面积 / 2`（目标子块面积 = 全图像素数 / n_segments），`n_sub = max(2, round(area / (目标子块面积/2)))`；在该超像素 bounding box 内重跑同一 SLIC（同特征、同 compactness），**只重写属于该超像素的像素**（bbox 内其他超像素的像素必须原样保留，否则会偷邻居），细分结果并入 segments，**记录父子关系**用于几何回写；
  - 实测（m=0.5、k=3）：τ=0.113、64/765 超阈（8.4%）；**64 个父块拆成 129 个子块（净增 65 段）**，细分后 n=830；**子块面积中位 86 px**（半格目标 92.4 px，min 11 / max 221）；另注：全部 830 段的面积中位是 191 px——**这两个数别混，86 是子块、191 是全段**；
  - 响应必须回写 `d_s`、`τ`、被细分超像素 id 列表、**细分前/后 n**，供 6.1 断言直接引用。
- **物化边界（红线 4 的具体化，别禁错对象）**：
  - **禁止**全量物化**原始立方体**：231×640×200 的 float64 是 236.5 MB，必须分块流式；
  - **允许**PCA 特征图 (L,S,k) 全量驻留——slic 是整图算法，分块喂不进去；k=5 float32 仅 2.96 MB（与原始立方体差 80 倍）。响应须回报特征图字节数与进程峰值内存。
- 输出给前端：超像素数、**实际生效参数（含 pca_components / compactness / k / 特征口径版本）**、**降采样叠加图 PNG**（≤512 边长，等高线/编号），不回传全分辨率数组。

### 5.3 扩散 / 提示分割引擎（FR-E04 / FR-E18）

- 单一扩散引擎，多种提示输入：
  - **种子画笔**（FR-E04）：种子像素/超像素集合；
  - **单击 / 框选 / 涂鸦**（FR-E18）：提示落到超像素上，取其均值谱为种子谱。
- 扩散：计算种子均值谱与各超像素均值谱的**余弦相似度 `cos_s`**（以**种子谱**为参照，全图超像素共用同一列数）；从种子超像素出发，向**与当前区域成员相邻、且该相邻对的余弦 `cos_uv` ≥ 阈值**的超像素扩散（邻接对 single-linkage，图连通 + 谱相似双条件），阈值**初始默认 0.92、实时可调、前端可预览**（标注为"默认值"，非需求硬常数）。
  - **增长邻接 = 4 邻域（R18 钉死）**：仅水平/垂直共享边界的超像素对算相邻，不用 8 邻域（与 `boundary_ratio` 同口径；角点接触会造成视觉断裂区域并扩大 single-linkage 泄漏面）。自检锚点：10.2 默认分割 pe 基线细分前 **765 段 2079 边**、细分后 **830 段 2256 边**（实施实测，逐像素双循环独立核过；**注意 R10 证据锚点的"766 段 2075 边"是另一套 segments，勿混**）。
  - **多命中提示 = 合成单候选（R18 钉死）**：框选/涂鸦/集合命中多个超像素时，取提示覆盖的**全部像素**合成一条种子谱（像素等权，即按像素数加权的超像素均值平均），初始区域 = 这些超像素的并集，产出**一个**候选；**种子成员 `cos_s` 定义为 1**（不实算），`min_similarity` 只会因增长成员低于阈值。
  - **涂鸦栅格化（R18 钉死）**：连接相邻坐标的 1 像素宽线段（Bresenham），含坐标点本身；不设线宽参数。
  - **框选区间（R18 钉死）**：半开 `[l0,l1) × [s0,s1)`，与 `read_region` 切片语义一致；初始种子集 = 区间覆盖像素命中的全部超像素。
  - **两条余弦分工写死，不得混用（R10）**：**增长判据**用 `cos_uv`（相邻两个超像素之间）；**对外报告的相似度**用 `cos_s`（对种子谱）。若增长判据也写成 `cos_s`，则区域成员的 `cos_s` 恒 ≥ 阈值，"最小相似度"变成恒真式、`queue_min_similarity` 永久休眠——这正是 R10 争议的根源。
  - **余弦一律在"原谱超像素均值谱"（200 波段反射率，已除 scale）上算，不得改用 PCA 特征**：实测两种口径结论相反——原谱口径下 20 个种子有 4–15 个候选 `min_similarity` < 0.80（下限活跃），PCA-5 特征口径下个别 cube 为 0/20（下限不触发），且区域规模退化到中位 2–18 个超像素。允许驻留 `(n_seg, 200)` 均值谱（766×200 float64 ≈ 1.2 MB，不违反红线 4）。
- 输出候选区域：超像素 id 列表、像素数、**`min_similarity` = 成员 `cos_s` 的最小值**、**`avg_similarity` = 成员 `cos_s` 的均值**（均以种子谱为参照，种子自身 `cos_s`=1 计入）、降采样叠加 PNG；不达扩散阈值的超像素不纳入（留白）。
  - 因增长按 `cos_uv` 判定、报告按 `cos_s` 计，**`min_similarity` 可以低于扩散阈值**（区域沿链漂移）——这是设计意图，不是 bug，验收会专门查这一点。
- **候选队列入队下限 `queue_min_similarity`，默认 0.80**：`min_similarity < 0.80` 的候选**不进队列**、按"不确定就留白"处理。**出处：UI 原型 ui-v2.3 S05 候选队列脚注（1711 行）**；需求正文无此数（需求层只有"低置信留白"原则）。属 **UI 层口径**，与扩散阈值（需求层场景示例）分属两层，**不得互相替代**，两者均参数化可调。
  - **它到底防什么（实测，不是推测）**：single-linkage 增长会沿链泄漏。把扩散阈值降到 0.80，区域中位规模从 ~86 个超像素涨到 **305–757**（全图 754–766），20 个种子里 **19–20 个**的 `min_similarity` < 0.80 被此下限拦掉。所以 0.80 是**增长泄漏的护栏**：扩散阈值管"相邻一步像不像"，入队下限管"整块离种子跑没跑偏"。**两者是不同层级的两道闸，不是同一阈值的上下限关系。**
  - **UI 原型队列示例的相似度谱反证了口径**：1710 行的 0.94/0.93/0.91/0.88/0.86 里，0.88 与 0.86 都**低于**扩散默认 0.92。若 `min_similarity` 恒 ≥ 扩散阈值，UI 上画不出这组数——可见"相似度"是种子参照（`cos_s`），不是邻接对参照。
- **数值常数纪律**：只允许写入有明确出处的数值（需求正文 / 场景示例 / UI 原型），且必须标注出处与层级；**无出处的常数一律禁止**。
- **候选队列状态机（唯一真源在 sidecar，前端不缓存候选）**：
  1. `diffuse` 生成候选 → 入该 cube 的**单一候选队列**（每 cube 一条队列，不按参数分叉）；队列项 = 超像素 id 集合 + 像素数 + `min_similarity` / `avg_similarity`（口径见上，种子参照）；
  2. `min_similarity < queue_min_similarity` 的候选**不入队**（该值可低于扩散阈值，故本判定在默认参数下就会真实发生，不是休眠分支）；
  3. `regions` 的 `action=confirm` 把候选写入 label map 并**移出队列**；
  4. `action=uncertain` 把该区域写入 `-2` 并**移出队列**；
  5. `action=erase` **只改 label map，不动队列**（擦除是修错，不是重新排队）；
  6. 参数变更（n_segments / compactness / pca_components）→ **清空候选队列**，label map 保留（见 5.4）；
  7. `working` 的"待确认" = 当前队列内候选的**像素并集**（去重，不重复计数）；
  8. 队列不落库、不跨会话持久；切 cube 时各 cube 队列互不影响。

### 5.4 标注会话与版本（FR-E01 / E05 / H01）

- 每个 cube 维护**工作 label map**（int32 (L,S)）：`-1` = 未标注（留白，斜纹）、`-2` = **不确定**（人看过但给不出类）、`≥0` = label_index 下标。确认候选（超像素集合→label）、画笔/多边形/橡皮直接光栅化修改、**"标记为不确定"写入 `-2`**；撤销栈（≥5 步，Z）。
  - **`label_index` 空间（R15 钉死）**：`≥0` 的下标 = **项目 label 列表按 `sort_order` 升序的下标**；`label_index.json` 的键与之一致。**已保存版本的映射不可变**——之后项目新增 label 只影响新版本的下标分配，不得改写已存 `label_index.json` 与 `label_map.npz`（否则历史版本回放错位）。
  - **撤销恢复范围（R15 钉死）**：撤销恢复 label map 的**深拷贝**（不是引用）；恢复后统计（已标/不确定/留白/各类像素数）从恢复态**现算**；撤销后的新编辑从恢复态继续，不得错位（§6.1"撤销后再编辑不错位"）。撤销栈只在内存、不落库。
  - **"样品主标签"无处落库**：5.4 末"样品主标签 = 像素数最多的 label"是**只读推导**（查询时按 label_map 统计），**不得为此自造列**（表结构以 4.1 为准）。
- **工作态归属（唯一真源，防止前端另起一份）**：工作 label map 与撤销栈都只在 sidecar 内存里，**前端不得自己维护第二份 label map 或撤销栈**；前端每次操作后通过 `GET /annotations/working` 取回降采样图与统计来重绘。撤销走 `POST /annotations/undo`，由 sidecar 出栈并重算统计。理由：两处真源必然漂移，且 6.2 的"label_map 回放逐像素相等"会失去意义。
- **超像素参数变更时的工作态**：label map 是**像素级**、与超像素 id 解耦，换 n_segments/compactness 重算 segments 后**已确认的标注保留**（按像素），只是候选选择被清空；不得因参数变更而清空或重算 label map。
- 保存版本（`save`）：
  1. 写快照目录（label_map.npz + label_index.json）；
  2. 按 label 聚合像素 → 均值谱/标准差谱（float64，按行块有界读），写 spectra.npz；
  3. 写 `annotation_version`（n_pixels、labeled_pixels、auto_ratio=0、**`params`=当次分割参数与特征口径版本的 JSON**）、**每个 label 一条** `annotation`（geometry=该 label 全覆盖的超像素 id 集合，pixel_count=label_map 统计值，source=manual）、每类 `sample_spectrum`（sample_code=cube 名）；
     - **粒度口径（勿再分叉）**：annotation 是"**区域**"语义，**每 label 每版本一条**，不是操作日志——每笔确认/每次画笔的历史**不落库**，只由撤销栈与版本快照承载。`-2`（不确定）不是 label，**不产生 annotation 行**，只存在于 label_map 与统计中；
     - **几何权威性**：超像素 id 只在 `params` 描述的那套 segments 下有意义，而 segments 不落库（4.2：工作态内存、可按参数重算）。因此 **`label_map.npz` 是唯一权威几何**，`annotation.geometry` 仅供追溯与回显，**不得作为区域重建依据**；
     - **`pixel_count` 必须由 label_map 直接统计**（该 label 的像素数），不得由 geometry 的超像素 id 反推（换参数后必然对不上）；
     - **`geometry` 的"全覆盖"定义（R15 钉死）**：只有该超像素的**全部像素**都属于此 label 时才计入其 geometry；**混合超像素（部分像素属此 label）不进任何 label 的 geometry**。理由：geometry 仅供追溯/回显，混合块记进去会让人误以为整块已标；区域重建一律走 label_map。
     - **`version_no` 规则**：新建 = 该 cube 现有 `max(version_no)+1`；覆写（overwrite=true）**version_no 不变**。
  4. 跑质量校验（5.5），结果随版本返回。
  5. **三表 NOT NULL 列的写路径覆盖（R13 纪律，随回执逐列报）**：`annotation_version` / `annotation` / `sample_spectrum` 的每个 NOT NULL 列，供值方式限三种（调用方入参 / 服务端规则 / 由 label_map 统计推导），实现时逐列核对并随回执列表；特别是 `annotation_version.params`（服务端从当次分割参数序列化）、`annotation.granularity`（阶段一恒 `'sample'`，见下）、`annotation.source`（恒 `manual`）、`sample_spectrum.mean_ref`/`std_ref`（= `spectra.npz` 内键名，键 = label_index）、`sample_spectrum.sample_code`（= cube 名）。
     - **`annotation.granularity` 取值（R16 裁定：`'sample'`）**：描述**记录粒度**而非操作粒度——落库行是像素级标注聚合后的样本级产物。三处需求实证：FR-E01（需求 671 行）"样本级（整条平均谱一个标签）"、§6.4.1（1782 行）"可由像素级标签自动聚合成样本级，**反之不成立**"、S1（417 行）"自动聚合出样本级光谱集（带标签，共 N 条）；标注版本落库"。`'pixel'` 留给阶段二真正的像素级明细记录（FR-E01"三级可共存"），阶段一不落 pixel 行；`'scene'` 阶段一无写入路径。
- 样本级：一个 cube 内按 label 各一条（**故 `annotation.granularity` 落库取 `'sample'`，R16 裁定**）；样品主标签 = 像素数最多的 label（只读推导，不自造列）。
- **场景级（口径写死，不再留解释空间）**：**阶段一不写 `granularity='scene'` 的 annotation 行**，也不写任何自动 annotation。场景信息（仪器/波段/批次）直接读 `dataset_registry.payload` 透出给 UI；`annotation.granularity` 的 `'scene'` 枚举值为阶段二预留。理由：`annotation.source` 的六个取值里没有 `auto`，而 3.2 又定死"阶段一恒为 manual"，自动落行只能 source 造假或破坏 3.2，两条路都脏；元数据本就在 payload 里，重复落行等于制造第二个真源。

### 5.5 质量校验（FR-E06 lite）

- 已确认区域内逐超像素检查：与所属 label 均值谱的距离（**R15 钉死：余弦、原谱 200 波段反射率均值谱，与 §5.3 同家族口径；"光谱角"不并立，防第二套口径漂移**）超参数阈值 → 可疑清单；**阈值参数化，默认值必须用真实 cube 实测触发率后落（可疑清单既非空也非全量），标注"实现层默认、可调"**——不得凭空写一个常数；块内高方差清单（**复用 5.2 的 `d_s`/`τ` 定义，不另立口径**）；完整度三分（**已标 % / 不确定 %（`-2`）/ 留白 %（`-1`）**、各类像素数）。
- **均值谱来源写死**：按**当前工作态 label map 现算**（与 save 聚合同一实现、同一分块读数），**不读历史 `sample_spectrum`**——否则改了标注却拿旧谱校验，结论无意义。
- `-2`（不确定）区域**不参与**离群检查（没有所属 label），只计入完整度与 working 统计。
- 报告显式标注："标签与聚类中心冲突、类间重叠"两项在无模型阶段**不适用**（不伪造结果）。
- **混合超像素的校验行为（R17 钉死）**：不跳过——对每个超像素 s 与每个在其中 ≥1 像素的 label L，取 `(s ∩ L)` 已标像素现算均值谱与 L 均值谱比余弦，低于阈值以 `(superpixel_id, label_index, pixel_count, cos)` 记入可疑清单；`-1`/`-2` 像素不进任何部分均值。理由：跳过混合块 = 恰好在"标注与分割打架"处闭眼，而那里最可能是真离群；纯多 label 块还能让工人看见边界分歧。无新参数、确定性。
- **质量校验阈值标定授权（R17）**：允许在真实 cube 上用 10.2 的 m=0.5 segments + `KMeans(n_clusters=4, random_state=0, n_init=10)` 对块均值谱聚类构造**合成标注**标定默认阈值（观测 cos 分布、按"非空且非全量"落值）；合成标注仅用于阈值行为与植入离群验证，**不得冒充人工标注、不得用于任何标注质量断言**；默认值与分布分位数随回执报。
- 可在保存时自动跑，也可独立调用。

### 5.6 FastAPI 路由（新 router，组合进 `spectrumagent.app.create_app`）

- **分割参数失配防护（R19 钉死，统一前置检查）**：`diffuse`/`regions`/`validate`/`save` 执行前，若工作态当前分割 params 与 SuperpixelEngine 缓存分割 params 不一致（换参未重新生成）→ 结构化错误 **`SEGMENTATION_STALE`（HTTP 409）**，要求先重新生成超像素；**不得静默同步到旧 segments**。`working` 端点不受此限（未生成/已生成均按现态返回）。错误码参数化：`AnnotationConflict` 的 code 可传，`ANNOTATION_CONFLICT` 与 `SEGMENTATION_STALE` 共用 409。
- `GET  /api/v1/projects`
- `GET  /api/v1/labels?project_id=`（schema + 标签值）
- `POST /api/v1/labels`（添加 schema 字段 或 从目录/自定义添加 enum 标签）——三种操作按 body 必需字段隐式区分：
  1. **从目录添加**：`{"project_id", "from_catalog": "plastic", "codes": ["PS","PVC"]}` → 201 + 创建行数组；服务端为每条生成 `tree_path = 材料/塑料/<code>` 并定位 `schema_id`（**body 不收 `tree_path` / `schema_id`**）
  2. **自定义 enum 标签**：`{"project_id", "code", "name", "tree_path", "color_hex", "shortcut_key"?, "is_background"?}` → 201 + 单行；`color_hex` 自定义时必填（无默认猜测）；**`tree_path` 第一段须精确匹配项目内 `field_type='enum'` 的 schema**（无匹配 → 422），服务端据此定位 `schema_id`（**body 不收 `schema_id`**）
  3. **添加 schema 字段**：`{"project_id", "schema": {"name", "tree_path", "field_type" ∈ enum|bool|continuous|ordinal, "unit"?, "config"?}}` → 201 + schema 行；**`schema.tree_path` 为单段名、不得含 `/`**（含 `/` 则永远无法被 label 定位，见 4.1 R13）
  - 互斥与校验：`from_catalog` 与 `code`/`schema` 不得同时出现；缺必填、混用、code 重复、hex 非法、shortcut 越界/重复、**enum 标签 tree_path 第一段无匹配 schema** → 422 结构化错误（字段级 message）。
- `GET  /api/v1/catalog/plastic`
- `POST /api/v1/datasets/{id}/superpixels`　body：`{n_segments, compactness, pca_components, force?}`；引擎内部**强制 `convert2lab=False`**（不暴露给调用方），`pca_components` 取 3 与 5 均须可用（见 6.1）
- `POST /api/v1/datasets/{id}/diffuse`　body：`{seed: {"point":[l,s]} | {"box":[l0,l1,s0,s1]} | {"doodle":[[l,s],...]}, "threshold": 0.92, "queue_min_similarity": 0.80}`；两个阈值都参数化可调（默认见 5.3），响应含候选列表（超像素 id 集合 + 像素数 + `min_similarity` / `avg_similarity` / `cos_s` 谱 + 降采样 PNG）及未入队原因统计
- `POST /api/v1/datasets/{id}/annotations/regions`　body：`{label_id?, geometry: {"superpixels":[...]} | {"polygon":[...]}, action: "confirm"|"erase"|"uncertain"}`；`uncertain` 时 `label_id` 可省（写入 `-2`）；返回新的工作态统计
  - **polygon 栅格化（R19 钉死）**：polygon geometry 转 label map 时，按**像素中心点 `(l+0.5, s+0.5)` 的 even-odd 内外判定**，中心恰在多边形边上时**计入内部**；不做边界膨胀、不设 `dilate` 参数（无出处）。与超像素集合路径（segments 命中像素并集）在同一张单值 label_map 上**后写覆盖先写**——这是请求内容决定的确定性语义，不得靠写序或膨胀凑结果。
- `POST /api/v1/datasets/{id}/annotations/undo`　撤销一步（sidecar 栈 ≥5 步）；栈空 → 409；返回新的工作态统计
- `GET  /api/v1/datasets/{id}/annotations/working`　**工作态读回**（未保存也有）：降采样 overlay PNG（已确认类色 + 不确定用问号/斜纹变体）+ 统计（超像素数、已标 %、**不确定 %**、留白 %、待确认、各类像素数）；前端重绘只认这个，不自行维护 label map。**未生成超像素时返回空统计与空图、不报错**。**R21 追加两个只读字段**：`project_id`（该 cube 所属项目，经既有 `registry.get` 通道查 `dataset_registry`）与 `queue`（与 `diffuse.queue` **同结构**，`deepcopy(state.candidates)` 含每项 overlay，空队列返回 `[]`）——编辑后/切图返回时可只读恢复右栏队列与画布候选层，**不得靠再调 `diffuse` 重建**（那会生成新候选）；**working overlay 语义不变**（候选不画进 working overlay，队列是独立字段）
- `POST /api/v1/datasets/{id}/annotations/validate`　**无 body，校验当前工作态 label map**（与 save 时的自动校验同源、同一实现）
- `POST /api/v1/datasets/{id}/annotations/save`　body：`{note?, overwrite?, confirm?}`；默认**新建版本**；`overwrite=true` 表示重写**当前最新版本**（version_no 不变），必须同时携带 FR-D07 确认标记 `confirm`——未带 → 409；试图指向历史版本 → 409（该路径不存在）
- `GET  /api/v1/datasets/{id}/annotations`（版本列表 + 当前工作进度）
- `GET  /api/v1/datasets/{id}/annotations/{version}/overlay`（降采样 PNG）——**`{version}` = `annotation_version.id`（UUID 字符串），不是 `version_no`**（R20 钉死：UUID 与表主键直连、全局唯一，`version_no` 仅用于 UI 显示与排序；`GET /annotations` 返回全列含 `id`，前端据此请求；**跨 cube 校验**：合法 UUID 但 `cube_id != {id}` → `VERSION_NOT_FOUND`(404)，不得暴露他 cube 快照）
- 统一信封/错误风格沿用 #02：DataError 结构化错误；JSON 响应大小受 Rust 侧 8 MiB 上限约束，所有图像一律降采样 PNG。

### 5.7 Rust IPC 扩展（需显式批准点）

- 新增 `src-tauri/src/annotation.rs`：沿用 `datasets_dev.rs` 的**类型化 enum** 模式（`AnnotationRequest`，`deny_unknown_fields`，目标路径由枚举变体固定，不接受自由 URL/路径），独立命令 `annotations_forward`；约束不变：仅 127.0.0.1 握手端口、GET/POST、8 MiB、响应身份头校验（boot_id/pid）、token 泄漏检查。
- **dev 与 release 双分支均注册** `annotations_forward`——**release 注册已于 2026-10-20 由科祥批准，范围仅此一条新命令，不得扩散**。命令清单从原五命令（engine_status / retry_engine / run_smoke / open_data_directory / datasets_forward）扩为六命令，capabilities 同步、ACL/schema 重新生成、release 边界审计字面量按六命令更新。
- **`AnnotationRequest` 变体表（13 个，R21 后；`deny_unknown_fields` 不变）**：

  | 变体 | 方法 | 路径 | 引入 |
  |---|---|---|---|
  | Superpixels | POST | `/api/v1/datasets/{id}/superpixels` | 10.2 |
  | Diffuse | POST | `/api/v1/datasets/{id}/diffuse` | 10.4 |
  | Regions | POST | `/api/v1/datasets/{id}/annotations/regions` | 10.4 |
  | Undo | POST | `/api/v1/datasets/{id}/annotations/undo` | 10.4 |
  | Working | GET | `/api/v1/datasets/{id}/annotations/working` | 10.4 |
  | Validate | POST | `/api/v1/datasets/{id}/annotations/validate` | 10.4 |
  | Save | POST | `/api/v1/datasets/{id}/annotations/save` | 10.4 |
  | Versions | GET | `/api/v1/datasets/{id}/annotations` | 10.4 |
  | VersionOverlay | GET | `/api/v1/datasets/{id}/annotations/{version}/overlay` | 10.4 |
  | Projects | GET | `/api/v1/projects` | R21 |
  | Labels | GET | `/api/v1/labels?project_id=<uuid>` | R21 |
  | AddLabel | POST | `/api/v1/labels` | R21 |
  | Catalog | GET | `/api/v1/catalog/plastic` | R21 |

- **路径构造分族（R21 钉死，实现要点）**：现有 `destination()`（annotation.rs:242）硬编码 `format!("/api/v1/datasets/{}/{suffix}", self.id())`，**四个新变体不属于 datasets 族、且没有 `id` 字段**，必须按变体分族构造——datasets 族 9 个沿用原逻辑；标签管理族 4 个用**固定字面量路径**，`Labels` 的 `project_id` 须经 `uuid()` 严格校验（**36 位、8-4-4-4-12 格式**，annotation.rs:144）+ `to_ascii_lowercase()` **规范化后** `set_query`（**以已验收实现为准**，annotation.rs:229/273；与 `Uuid::parse_str().to_string()` 效果等价，但卡文按实现写，R22），**不得把调用方原始字符串直接拼进 URL**（排除 `&`/`?`/`#`/`/` 注入）。Rust 原"无 query/fragment"测试口径改为"**无调用方可控 query**"，对自由 URL/host/port/path/method 的拒绝断言全部保留。
- **`AddLabel` body 上限（R21 钉死）**：现有 `MAX_RESPONSE_BYTES = 8 MiB` 只限**响应**、不限请求；`serde_json::Value` 透传前须校验序列化后大小 **≤ 64 KiB**（标签 body 远小于此），超限拒绝——否则超大 body 直接进 Python 内存。**Python 请求模型仍是业务校验唯一权威**（三种 body / 互斥 / 422 契约不变），Rust 不复制业务校验、不复制默认值。
- 前端封装为单一 annotation api client 模块（与 datasets api 同风格），禁止组件内散落 invoke。

### 5.8 前端 S05 标注工作台（阶段一最复杂组件）

- 新增 `src/components/annotation/`：`api.ts`、`types.ts`、`AnnotationWorkbench.tsx`、`canvas/`（分层画布）、`LabelPanel.tsx`、`CandidateQueue.tsx`。
- 布局按 UI 原型 S05：
  - 左栏：标签（色块 + code + 数字键）、工具（扩散/画笔/多边形/橡皮）、本图统计（超像素数、已确认 %、待确认、预计剩余）；**"预计剩余"由前端按本地确认速度估算，不进后端统计口径、不进验收**；
  - 中栏：分段切换（超像素/扩散/提示分割）+ 参数（SLIC n、compactness、阈值）、画布（图层：底图/超像素轮廓/候选高亮/已确认类色）、操作按钮（确认候选、扩散到相似区域、标记"不确定"）、上一张/下一张；
  - 右栏：候选区域队列（相似度、像素数）、已标注像素分布、"聚合为样本级标签"（保存即聚合）。
- 画布：图层 + 视口模型（沿用 UI 6.5），缩放/平移，点击/框选/涂鸦作为提示；栅格类操作走 Canvas 2D。
- 快捷键（可查/可改/可关闭，首入浮层提示）：`0–9` 选标签（0=背景；**>9 类时超出部分仅鼠标点选**）、`Enter` 确认候选、`Z` 撤销、`E/B/P` 工具、`←/→` 切换图、`Ctrl+S` 保存。
- 入口：数据集列表每项加"标注"按钮 → 打开该 cube 的工作台（阶段一不做完整左导航，做最小视图切换；S05 层级指示器 L0–L4 静态展示，当前 L1）。
- 标签管理最小 UI：标签栏"添加标签" → 目录选择（塑料目录）或自定义（code/中文名/颜色）；schema 字段管理可先做最简表单。**通道（R21）**：标签管理四个端点（projects / labels / AddLabel / catalog）经 `annotations_forward` 的**四个固定变体**到达，**不新开第七条命令**（命令总数仍六条）；前端只调 annotation api client 封装，禁止直连 sidecar（webview 拿不到端口与 token，直连不可行）。

---

## 6. 验收标准（Checklist）

### 6.1 功能

- [ ] 迁移幂等：重复启动不重复建表/种子；`dataset_registry.project_id` 存在且回填
- [ ] 塑料项目标签树为 PE/PET/PP/背景；`GET catalog/plastic` 返回 21 条（含 PS、PVC）
- [ ] `catalog/plastic.json` 18 条生成色值与 §4.4 规则表逐点一致（HLS→RGB 四舍五入转 hex）；PE/PET/PP 与 §4.3 一致
- [ ] `POST /labels` 三种 body 各成功一次；互斥混用/缺字段 → 422；custom 缺 `color_hex` → 422
- [ ] 自定义 enum 的 `tree_path` 第一段无匹配 schema → 422；目录添加生成的 label `tree_path` = `材料/塑料/<code>`、`sort_order` = 目录序号（PE=1…SAN=21）；自定义 `sort_order` = max+1；预置四 label 的 `tree_path`/`sort_order` 与 §4.3 表逐点一致
- [ ] 超像素（结构断言，全部绑定"选定 compactness 下的实测基线"，不写死 800 这个数）：
  - **n 指细分前 SLIC 原始输出**，与基线偏差 ≤10%（11 cube 标定 m=0.5、PCA-5 时 n=751–768；pe 基线 n=765 → 689–842，PCA-3 基线 n=773；来源：标定 CSV 与 pca3-baseline.json，实现层实测）；**`pca_components=3` 与 `5` 两种设置都必须满足**（3 分量必须显式 `convert2lab=False`，否则实测塌到 n=18）；细分后 n 单独记录（实测 830），**不设 ±10% 断言**（随 k 与触发率变化）
  - `area_cv ≥ 0.10`（11 cube、PCA-5：m=0.5 实测 0.176976–0.210624；m=10 为 0.067849–0.068749；PCA-3 pe 基线 0.172421；来源：标定 CSV 与 pca3-baseline.json，实现层实测）
  - **边界/内部谱距离比 R ≥ 1.5**（口径：PCA-5 z-score 特征空间、4-邻域、平方欧氏距离**均值比**；11 cube、PCA-5：m=0.5 实测 1.752193–1.830736、m=10 实测 1.013629–1.107526；PCA-3 pe 基线实测 1.623627；来源：标定 CSV 与 pca3-baseline.json，实现层实测）。R 是"FR-E03 是否退化成规则网格"的直接探针，**低于 1.5 即判超像素未按光谱切分**
    - **自检锚点**：分母必须是"段内相邻对的距离**均值**"，不是求和。本 cube 上按均值比得 **≈1.8**（分块不同在 1.77–1.82 间浮动）；若误写成求和比只得 **0.20**（差约 9 倍，因段内对数远多于跨界对）。数不对先查聚合方式，别先怀疑分割，更不得反向调参
  - 高方差细分：报告中的 `d_s > τ` 记录与超像素集合一致，**触发数 ≥ 1**（实测 k=3 触发 64/765 = 8.4%）；细分前/后 n 分别记录（实测 765 → 830）；k 为参数化默认 3，标定阶段可调，但调整须落进标定表并写明理由，**不得为了让断言通过而临时改 k**
  - 返回实际生效参数（pca_components / compactness / k / 特征口径版本）与降采样叠加图
- [ ] 场景级：导入、超像素、保存、校验任意路径执行后 `SELECT count(*) FROM annotation WHERE granularity='scene'` 恒为 0；**且落库 `annotation` 行 `granularity` 全为 `'sample'`（R16）**；场景信息经 `dataset_registry.payload` 透出
- [ ] 快捷键校验（6 用例，直接对应 4.1 表级 CHECK）：
  - 背景 `is_background=1, shortcut_key=0` → 允许
  - 普通标签 `is_background=0, shortcut_key=1..9` → 允许
  - `is_background=0, shortcut_key=0` → **拒绝**（CHECK）
  - `shortcut_key=NULL`（>9 类超出部分）→ 允许
  - `shortcut_key=10`（越界）→ **拒绝**（CHECK）
  - 项目内重复快捷键 → **拒绝**（UNIQUE）
- [ ] 扩散：种子 → 候选区域随阈值变化；默认 0.92 可复现；阈值实时改变结果
- [ ] 单击/框选/涂鸦三种提示均能生成候选（FR-E18）
- [ ] 确认/修正/橡皮/多边形编辑正确反映到工作 map
- [ ] 工作态可读回：编辑后 `GET /annotations/working` 的降采样图与统计与操作一致；**刷新/切图回来后工作态不丢**（label map 在 sidecar，不在前端）
- [ ] 撤销：`POST /annotations/undo` 连续撤 ≥5 步结果正确，栈空 → 409；撤销后再编辑不错位
- [ ] 不确定：`action=uncertain` 后该区在 label_map 中为 `-2`、`working` 单列"不确定 %"、overlay 有区分样式；快照回访后逐像素仍为 `-2`；**不产生 annotation 行**
- [ ] 候选队列（**默认参数下即须可判**，不许靠调阈值制造现象）：固定 20 个超像素种子（坐标见 `milestone04/evidence/seeds_20.json`，在 pe 基线立方体 231×640 上按 4 行×5 列均匀网格取每格中心像素，坐标记入该文件后**不得更换、不得随机重生成**）跑 `diffuse`（阈值 0.92、`queue_min_similarity` 0.80），断言 ①入队候选 ≥ 1 **且**被 0.80 拦掉的候选 ≥ 1（实测 4–15/20）；②存在候选 `min_similarity` < 0.92（证明口径未退化成恒真式）；③入队候选的 `min_similarity` 全部 ≥ 0.80。**②为 0 说明增长判据错用了 `cos_s`（见 5.3），须改实现，不得改阈值或换种子凑数**。另：confirm / uncertain 后移出队列；erase 不动队列；参数变更清队列但 label map 保留；`working` 的"待确认"= 队列内候选像素**并集**
- [ ] 参数变更：换 compactness 重算 segments 后，已确认标注与 `-2` **按像素保留**、候选清空、`working` 的已标/不确定统计不变（不得因换参数丢标注或重算 label map）
- [ ] 保存生成版本：快照三件齐全、annotation/version/sample_spectrum 行落库；再存版本号递增、旧版不可改
- [ ] 覆写语义唯一：默认 `save` 版本号递增、历史版本不可改；`overwrite=true` 未带确认标记 → 409；带标记 → 重写最新版本（version_no 不变）且覆写事件入库；指向历史版本 → 409；**无任何版本时 `overwrite=true` → 409**
- [ ] 覆写不留脏行：覆写后该 `version_id` 下 `sample_spectrum` **每 label 至多一条**、`annotation` 行数 = 本次有像素的 label 数（**每 label 一条**，无上一轮残留）、`annotation_version` 的 `n_pixels`/`labeled_pixels`/`snapshot_ref` 已更新；快照三件与工作态一致；**覆写后 `note` 可解析且 `event=="overwrite"`（R17）**
- [ ] 样本光谱：每类均值/标准差数组与按像素现算一致（容差 1e-10）
- [ ] 质量校验返回可疑清单；不适用项显式标注

### 6.2 数据正确性

- [ ] label_map 回放：快照 label map 与落库时工作 map 逐像素相等
- [ ] 样本谱 = 该 label 全部已标像素的均值/标准差（分块现算复核）
- [ ] label_map 三分语义正确：`-1` 留白（斜纹）、`-2` 不确定（人看过但给不出类）、`≥0` 标签；三者互不串、**都不被填默认标签**；`-2` 不计入 `sample_spectrum` 聚合，也不计入 `labeled_pixels`
- [ ] `annotation_version.params` 落库，且与当次实际生效参数一致（n_segments / compactness / pca_components / k / block_size / 特征口径版本）
- [ ] `annotation.pixel_count` 与该 label 在 label_map 中的像素数一致（**不得由 geometry 反推**）；geometry 的超像素 id 仅作追溯，区域重建一律走 label_map
- [ ] z-score 统计量（各 PCA 分量均值/标准差）与独立分块复算一致（容差 1e-6）；归一化后特征图取值严格落在 [0,1]（实测 min=0/max=1），各分量均值 ∈ [0.45,0.55]、std ∈ (0, 1/6]（实测 0.129–0.164，PC1 偏态被 clip 削得更多，**不可断言 std 恒为 1/6**）
- [ ] 血缘：cube → annotation_version → sample_spectrum 可按 id 串联（FR-H07）

### 6.3 性能（实测记录，不预设承诺）

- [ ] 超像素（231×640×200 = lines×samples×bands；磁盘 BIL 为 (231,200,640)）耗时记录；**回报 PCA 特征图字节数**（k=5 应为 2.96 MB）与进程峰值 RSS；峰值相对基线的增量须显著小于 236.5 MB（全量物化原始 float64 立方体的量级），以此证明未一次性物化原始立方体。（参考实测：PCA 3.2 s + SLIC 0.1 s，仅供 codex 判断量级，**不作验收阈值**）
- [ ] 扩散（**细分后** n=809–838，11 cube 在选定 compactness=0.5、k=3、PCA-5 下的标定范围；pe 基线 n=830；来源：`milestone04/evidence/calibration/compactness.csv`，实现层实测）耗时 ≤ 2 s（候选值，实测为准）
- [ ] 保存版本（含聚合）耗时记录；不长期占用 SQLite 写事务（短事务）

### 6.4 异常与边界

- [ ] 未生成超像素先扩散 → 结构化错误（提示先超像素分割）
- [ ] 源文件被移动/改动 → 沿用 #02 SOURCE_CHANGED 错误
- [ ] **`readable` 错误分类（跨里程碑唯一口径，2026-10-20 裁定）**：未登记 → `DATASET_NOT_FOUND`(404)；**已登记但源不可用/不一致 → `SOURCE_CHANGED`**（`context.source_error` 保留原始错误码，如 `FILE_NOT_FOUND`，`context.source_detail` 保留原 detail）；导入期路径错误仍为 `FILE_NOT_FOUND`（走 `candidates()`，不经 `readable`，行为不变）。包装点只在 `readable` 内部 `read_header` 一步，调用方不得各自处理。**影响面**：#02 的 `preview`/`band`/`region` 端点对"已登记但源移动/缺失"由 `FILE_NOT_FOUND` 改报 `SOURCE_CHANGED`（HTTP 400 不变，前端契约无感），随 v0.1.2 release notes 记一笔；`info` 端点走 `get()` 不受影响。
- [ ] 响应超 8 MiB → Rust 侧 RESPONSE_TOO_LARGE
- [ ] release 构建中 `annotations_forward` 可用、无 dev-only 模块泄漏；无账号体系下全程不出现登录/权限控件

---

## 7. 交付物

| 交付物 | 位置 |
|---|---|
| 迁移 + 标签/项目存储 | `src-python/spectrumagent/annotation/`（migrations.py、labels.py、catalog/） |
| 超像素/扩散/提示分割引擎 | `src-python/spectrumagent/annotation/engines/`（superpixels.py、diffusion.py） |
| 标注会话/版本/聚合 | `src-python/spectrumagent/annotation/session.py`、`quality.py` |
| FastAPI 路由 | `src-python/spectrumagent/api/annotations.py`（并在 app.py 组合） |
| Rust IPC 命令 | `src-tauri/src/annotation.rs`（dev+release 注册） |
| S05 工作台 | `src/components/annotation/` |
| 单元测试 | `src-python/tests/annotation/`（引擎、版本、聚合、迁移、错误路径） |
| **候选队列固定种子清单** | `milestone04/evidence/seeds_20.json`（20 个坐标，4 行×5 列均匀网格中心，6.1 验收用；**执行验收与独立复核不得更换、不得随机重生成**） |
| 标定表（10.2 产出） | `milestone04/evidence/calibration/compactness.csv`（行 = cube × m，列 = n（细分前）/ area_cv / R / **细分触发数** / 细分后 n / 生效参数；沿用 #03 的 `milestoneNN/evidence` 惯例） |
| 快照产物 | `%LOCALAPPDATA%\SpectrumAgent\annotations\<cube_id>\v<n>\` |

---

## 8. 依赖与阻塞

| 项 | 状态 | 说明 |
|---|---|---|
| scikit-image 0.26 / scikit-learn 1.9.1 | ✅ lock 内 | SLIC / IncrementalPCA，全 CPU |
| 裸 sqlite3 | ✅ #02 已用 | 同一 DB 文件 |
| 塑料真实数据 | ✅ 三类已核实 | PE/PET/PP，标准 ENVI |
| release 注册新 IPC 命令 | ✅ 已批准（2026-10-20） | 范围**仅** `annotations_forward`；dev/release 双分支注册，capabilities/ACL/审计字面量同步 |
| SAM 类提示分割 | ⛔ 不做 | 需 PyTorch/GPU 附加包，走扩散路径替代 |

---

## 9. 已知风险

1. **超像素在 200 维上直接跑会慢且不稳**：必须先 PCA 降维（默认 5 维），否则 SLIC 内存/耗时不可控；PCA 走增量分块、**只避免物化原始立方体**（PCA 特征图允许驻留，见红线 4，别把两者混为一谈）。
2. **阈值被当硬常数传播**：`0.92` 仅是需求文档场景 S1 的示例值（417 行，非 FR 正文），本卡写为可调默认值；`0.80` 出自 **UI 原型 S05 候选队列脚注（1711 行）**，属 UI 层口径。两者**都参数化、都必须标出处与层级**——既别把 0.92 当需求硬约束，**也别把 0.80 当"无出处伪常数"删掉**（R9 曾误判"0.80 无出处"，已勘误）。
3. **未来 GB 级立方体**：全部引擎按行块有界读 + 增量 PCA；新增维度（类别数）由项目配置驱动，色表/快捷键不写死。
4. **阶段二迁移**：新增表均带 `created_at`；`project_id` **仅**在 `project`（自身主键）/`label_schema`/`label` 三处直接存在，`annotation`/`annotation_version`/`sample_spectrum` **不冗余存 project_id**，经 `cube_id → dataset_registry.project_id` 级联获得（单链，不引入第二真源）。SQLite → PostgreSQL 平移依赖的是类型与约束可映射性，不依赖每张表都有 project_id；阶段二若需行级安全再 ALTER 回填，成本相同。`source`/`confidence`/`evidence` 字段已预留，不回填假值。
5. **`pca_components=3` 会静默触发 Lab 转换（最毒的一条，不抛异常）**：skimage 的 `convert2lab` 默认 `None`，此时"通道数 == 3"会自动 `rgb2lab`，而 `pca_components` 是暴露参数。实测真实 cube：k=3 + 默认值 → n=18（m=0.5）/ 193（m=10），显式 `convert2lab=False` → 773 / 782。**必须写死 `convert2lab=False`**，且 6.1 用 k=3 与 k=5 双设置验收，否则这条 bug 只会在"有人为了提速把 5 改成 3"时才暴露。
6. **compactness 与特征口径强耦合**：0.5 这个初值只对"逐分量 z-score → clip ±3 → [0,1]"有效（5.2）。换预处理口径必须重标定，否则会误以为参数失效。同理 `area_cv`/`R` 两个结构指标也只在该口径下标定过。
7. **`min_similarity` 的参照口径是隐藏的第二真源（R10 的核心）**：同一个"最小相似度"在两种口径下结论相反——以**种子谱**为参照时可低于扩散阈值（0.80 下限活跃，实测 4–15/20 被拦），以**邻接对**为参照时恒 ≥ 阈值（0.80 永久休眠）。R10 的"休眠参数"判断正是后一种口径的产物，按卡原文字面（`cos` 定义为种子谱 vs 超像素）确实会退化成恒真式。5.3 已把两条余弦的分工写死（增长 `cos_uv`、报告 `cos_s`，且一律在原谱上算）；6.1 用"存在 `min_similarity` < 0.92"反查口径。**改口径等于改语义，须走卡修订，不得在实现里静默选择**——静默选错会得到一个永远通过的验收项，比报错更危险。

---

## 10. 排期建议（1 人全职，codex 执行，按实测调整）

| 阶段 | 内容 | 估算 |
|---|---|---|
| 10.1 | 迁移 + 标签/项目 + 塑料目录 | 1 天 |
| 10.2 | 超像素引擎（**实交付不含扩散引擎**）；**含 11 cube × 5 值 compactness 标定（表 m×{n, area_cv, R, 细分触发数, 细分后 n} 落档，回填 5.2 / 6.1 / 6.3 的扩散规模）** | 1.5 天 |
| 10.3 | 会话/版本/聚合 + 质量校验 | 1.5 天 |
| **10.3.5** | **扩散 / 提示分割引擎（FR-E04 / FR-E18）**——§5.3 全量：`cos_uv` 增长 / `cos_s` 报告 / `queue_min_similarity` 0.80 护栏 / 原谱口径 / 候选队列状态机 8 条；**不含路由**（10.4） | 1 天 |
| 10.4 | FastAPI 路由 + 单测 | 1 天 |
| 10.5 | Rust IPC 扩展（dev+release） | 0.5 天 |
| 10.6 | S05 前端工作台 | 3 天 |
| 10.7 | 集成 + 验收 + 性能实测 | 1.5 天 |
| **合计** | | **约 11 工作日**（10.3.5 插单 +1 天，2026-10-20 科祥拍板） |

---

## 11. 红线（不可妥协）

1. **L1 机器只给候选区域，不给标签**——本卡不引入任何自动赋标（库/聚类/迁移/模型/门控一律阶段二）。
2. **标签从第一天起结构化**——不做自由文本标签；新增即登记 code/tree_path/颜色/快捷键。
3. **不新增依赖**（scikit-image/sklearn 已在 lock）；PyTorch/SAM 不进主包。
4. **大数组按行块有界读——禁的是原始立方体，不是特征图**：禁止全量物化**原始立方体**（231×640×200 float64 = 236.5 MB 量级）；**PCA 特征图 (L,S,k) 允许全量驻留**（slic 是整图算法，分块喂不进去；k=5 float32 仅 2.96 MB），但必须回报字节数与峰值内存。快照文件为大数组唯一落库形式。
5. **release 命令扩充必须显式批准**（本卡 `annotations_forward` 已获科祥批准，范围锁死为这一条）；dev-only 模块不得泄漏。
6. **不编造数值与出处**——只允许写入有出处的数，且**必须标注出处与层级**（需求正文 / 场景示例 / UI 原型）；无出处的常数一律禁止；不适用的检查项显式标注。**同一物理量的"参照口径"与数值同等重要**：`min_similarity` 的参照物（种子谱 / 邻接对）必须在卡里写死，不得由实现自行选择（见 5.3、风险 7）。

---

## 12. 修订记录（十轮复核，2026-10-20）

| 轮次 | 改动 | 依据 |
|---|---|---|
| R1 | 补 scene 口径（不落行）、修风险 4 的 project_id 表述 | 一轮复核必修 1/2 |
| R1 | 快捷键 0–9 + 0 仅背景 + >9 留 NULL；覆写语义统一为"只覆盖最新版本" | 一轮复核新发现的两处卡内自相矛盾 |
| R2 | `convert2lab=False` 写死；compactness 由 10 改单 cube 初值 0.5；红线 4 明确"禁原始立方体、允许 PCA 特征图驻留"；块内高方差给出无歧义定义 | 二轮 probe：k=3 静默塌到 n=18；m=10 退化为 13.6px 规则网格 |
| R3 | 6.1 改用 n（绑定基线）+ area_cv + **R** 三项结构断言；R 口径写死（PCA-5 z-score / 4-邻域 / 平方欧氏均值比），阈值 1.5 | 三轮双源复跑：同一口径下两实现逐格吻合（m=0.5 → 1.82，网格 → 1.07） |
| R4 | z-score 统计量改为"在驻留特征图上原地算"（否决 `explained_variance_` 反推，量级见 R5）；快捷键 CHECK 升为表级并联动 `is_background`；覆写补旧行先删后写 + 无版本时 409；6.3 扩散基线改 n≈765 | 四轮复核 4 条 + DDL 六用例复验 |
| R5 | 反推误差量级修正为"1e-3 且随分块漂移"（32/64/128/单批 = 1.25e-3/1.54e-3/1.12e-3/3.4e-6）；补"分块大小不影响分割结论"；R 加求和比 vs 均值比的自检锚点（0.20 vs 1.82）；快捷键验收展开为 6 用例 | 五轮分块敏感性 probe（n=765/765/765/766） |
| R6 | **细分门槛修正（验收可达性）**：删掉"像素数 ≥ 2×目标子块面积"，实测该门槛通过数为 0（高方差块中位 174 px < 全体 195 px）；细分粒度改 `n_sub = max(2, round(area/(目标/2)))`；6.1 明确 n 基线=细分前 765、细分后 830 不设断言；6.3 扩散基线改 830；R 锚点由 1.82 改为 ≈1.8（1.77–1.82 随分块浮动） | 六轮 probe：k=3 触发 64/765，细分后 n=830 |
| R7 | **实测数字勘误**：R6 的"+65 子块 / 子块中位 191 px"两处标签错误——65 是**净增段数**、191 是**全段面积中位**；正确为"64 父块拆成 **129 子块**、子块面积中位 **86 px**（半格目标 92.4）"；6.3 的 830 标注为"初值锚点" | 七轮复验：子块 min 11 / p25 65 / med 86 / mean 90.2 / max 221 |
| R8 | **补三处"卡未写、codex 需自造"的接口/语义缺口**：①工作态读回端点 `GET /annotations/working`（前端不得自持 label map）；②撤销端点 `POST /annotations/undo`（栈在 sidecar）；③`annotation_version.params` 记录当次分割参数，声明 label_map 为唯一权威几何、pixel_count 不得由 geometry 反推；另补"换参数不丢已确认标注" | 交转前静态审查：5.4/5.6 与 5.8 中栏图层、Z 撤销、参数面板对不上 |
| R9 | **① 出处勘误（重要）**：5.3 原写"0.80 不进队列——已核实无出处"，**实际 UI 原型 S05 候选队列脚注 1711 行明写此数**；改为承认出处、定为 `queue_min_similarity` 默认 0.80（UI 层口径，与需求层示例阈值 0.92 分属两层、不得互替）。② annotation 粒度由"每笔"改为**每 label 一条/版本**（R8 的 pixel_count 断言只在按 label 下成立），操作历史不落库。③ 补 `-2` 不确定编码全流程（UI 1693 行确有按钮）。④ 补候选队列状态机（8 条生命周期）。⑤ 小口径：预计剩余归前端、validate 无 body 校验工作态、5.5 均值谱按工作态现算、working 空态不报错 | 九轮对读 + UI/需求文档原文取证 |
| R10 | **口径缺口（比"休眠参数"更根本）**：R10 提出"默认 0.92 下所有候选 `min_similarity` ≥ 0.92 → 0.80 永久休眠"，该结论只在"`min_similarity` = 邻接对余弦最小值"时成立；按卡原文字面（`cos` 定义为种子谱 vs 超像素）确实会退化成恒真式。**修法不是加联动语义，而是写死两条余弦的分工**：增长用邻接对 `cos_uv`（single-linkage），报告用种子参照 `cos_s`，`min_similarity` 因而可低于阈值。实测（9 cube × 20 种子，原谱口径）：默认 0.92 下被 0.80 拦掉 **4–15 个/20**，下限**本来就活跃**；阈值降到 0.80 时区域中位规模由 ~86 涨到 **305–757**（全图 754–766）、**19–20/20** 被拦，这才是 0.80 的真实职责（增长泄漏护栏）。另写死"余弦在原谱均值谱上算、不得改用 PCA 特征"（特征口径下个别 cube 为 0/20，验收会抖）。6.1 验收改为**默认参数下可达**：入队 ≥1、被拦 ≥1、存在 `min_similarity` < 0.92。复核方原可达化写法区间自相矛盾（min∈(0.75,0.80) 本身 <0.80，应被拦），已改为默认参数可达断言 | 十轮 probe：pe/pet/pp 共 9 cube × 2 口径 × 3 阈值 |
| R11 | **候选队列验收种子无据**：6.1 写"固定 20 个种子"但生成规则、路径、格式均未给出，codex 会随机重生成导致不可复现。补：在 pe 基线立方体 231×640 上按 **4 行×5 列均匀网格取每格中心像素**，生成 20 个坐标写入 `milestone04/evidence/seeds_20.json`（已入 §7 交付物表），6.1 验收与独立复核**不得更换、不得随机重生成**；复跑时取同一 SLIC 输出下坐标所在超像素为种子。R10 措辞"否决复核方写法"按复核方建议改为中性表述（保留事实、去掉情绪） | 终读发现：执行期漂移风险 |
| R12 | **codex 首触即停：两个真实缺口（十查漏项）**：①§4.4 目录 18 条色值无来源——补 HLS 生成规则（hue=j×20°、sat=55%、light=45%、**四舍五入**转 hex）+ 18 值表，PE/PET/PP 沿用 §4.3；②§5.6 `POST /labels` 三形态契约未定义——补从目录添加/自定义 enum/添加 schema 的字段区分、互斥校验、422 错误结构。配套 §6.1 加两条验收（色值逐点一致 + 契约三形态各成功一次）。**复核实跑三处订正**：(a) `j` 必须**从 PS 起算**（j=0..17），若按 §4.4 全表序号读则 PS=3、色值全错；(b) 必须 `round()` 而非截断，截断得 `#b13333` 一类、每通道系统性 −1；(c) 发现 `PBT #3488b2` 与 `PP #2f7fb0` 色距仅 10.5，已在 §4.4 记录为已知冲突并划入 10.6 提示项（不改生成规则：偏移 10°/20° 仍 10.5、15° 仅 19.7）。**纪律沉淀：备卡终读八查补第 5.5 条**——"每个落盘数值（含种子数据色值/默认值）必须有来源：文档值、规则产物、或空" | codex 执行期首检：十查漏了"落盘数值来源"与"端点请求体契约" |
| R13 | **codex 二触即停：NOT NULL 列的写入来源未覆盖**：`label.schema_id` 是 NOT NULL FK，但 R12 契约的自定义 enum body 无 `schema_id`，卡内也无 `tree_path`→schema 定位规则；顺带暴露同一缺口族——预置四 label 与目录条目的 `tree_path`（同表 NOT NULL）也从未定义。补：①§4.1 种子明确 enum schema 的 `tree_path=材料`（**单段、不含 `/`**，含 `/` 则永远无法被 label 定位）+ R13 三条写入路径共用的定位规则（取 `label.tree_path` 第一段**精确匹配** `field_type='enum'` 的 schema tree_path，服务端据此定位 `schema_id`，**body 不收 `schema_id`**，无匹配 → 422）；②§4.3 预置四 label 补 tree_path 列 `材料/塑料/<code>`（BG 归 `材料` 是阶段一只有单 enum schema 的工程必然，"背景非材料"的语义别扭记录在案不另设 schema）；③§4.4 目录条目入项目 tree_path 同规则、由服务端生成（body 不收）；④§5.6 三种 body 各自标注"不收什么"；⑤6.1 加验收一条。**复核方主动扫全表补第三处**：`label.sort_order` 同列 NOT NULL 且三路径亦无供值规则（预置=4.3 sort 列 / 目录添加=目录序号 PE=1…SAN=21 / 自定义=max+1），与 `schema_id` 同源，一并纳入 R13 同块定义。**沉淀：八查补第 5.6 条**——每条 NOT NULL 列（及每个请求体缺省即无值的字段），在每条写入路径上都必须有显式供值来源（body 字段 / 服务端规则 / 种子数据，三者都不占即缺）；codex 三次即停（色值 / 请求契约 / schema 归属）全是这一条漏检；复核方按同一条规律主动扫全表，抓出第四处 `sort_order` | codex 执行期二检：十查只查了"列定义"，没查"写路径覆盖" |
| R14 | **codex 三触即停：既有实现与卡内异常口径冲突（跨里程碑）**：`Registry.readable`（registry.py:140）直接调 `read_header` 无 try/except，源文件缺失时 reader 的 `FILE_NOT_FOUND` 原样传出；而 §6.4 要求"源移动/改动 → SOURCE_CHANGED"。裁定：**卡是对的、实现没对齐**——在 `readable` 内仅包 `read_header` 一步，任何 `DataError` 统一包装为 `SOURCE_CHANGED`（`context` 带 `source_error` 原码 + `source_detail` + 原 path，`from error` 链式；先剔同名键防碰撞）；字段比对循环原样保留（其 detail"源元数据与登记记录不一致"与新文案区分）。**边界三不动**：`get()` 的 `DATASET_NOT_FOUND`(404)、导入期 `candidates()` 的 `FILE_NOT_FOUND`、reader 单测行为。**跨里程碑影响**：#02 `preview`/`band`/`region` 对"已登记但源移动/缺失"由 `FILE_NOT_FOUND` 改报 `SOURCE_CHANGED`（HTTP 400 不变），v0.1.2 release notes 记账；`info` 走 `get()` 不受影响。必加 6 项测试：删 hdr / 改名 / 换小文件（source_error 实测后断言不猜）/ 未知 id 仍 404 / 引擎缓存命中后删源再 generate 不 force / HTTP 层 preview+superpixels → 400+SOURCE_CHANGED | codex 执行期三检：实现侧漏包装，卡无需改 |
| R15 | **10.3 开令前复核：排期失实修正 + 7 钉入卡 + 1 待决**。①**排期表失实**：§10 原写 10.2="超像素 + 扩散/提示引擎"，但 10.2 实交付只有超像素+R14+标定（`engines/` 仅 superpixels.py），FR-E04(P0) 悬空；**新增 10.3.5「扩散/提示分割引擎」子阶段**（1 天，不含路由），10.2 行改"实交付不含扩散引擎"，合计 10→11 天（科祥 2026-10-20 拍板）。②**7 钉入卡**（卡未写死、codex 只能自造的点）：`label_index` 空间=项目 label 按 `sort_order` 升序下标且已存版本映射不可变；`geometry` "全覆盖"=超像素全部像素同属该 label（混合块不进任何 geometry）；质量校验距离钉死余弦+原谱 200 波段均值谱（光谱角不并立）、阈值实测后落；`paths.py` 增 `snapshots` property + `snapshot_ref` 存相对 POSIX 路径；`version_no` 新建=max+1、覆写不变；三表 NOT NULL 列逐列报供值来源（R13 纪律）；撤销恢复=label_map 深拷贝+统计现算+"样品主标签"不落库不自造列。③**待决项（阻塞 10.3 实现）**：`annotation.granularity` 卡内冲突——4.1 注释"阶段一恒为 `'pixel'`，`'sample'` 为阶段二预留" vs 5.4 末"样本级：一个 cube 内按 label 各一条"；两选项语义与后果已写进 §5.4，**待科祥拍板**（未定前不实现该列取值） | 10.3 开令前对卡审核（agent 把关） |
| R16 | **R15 待决项关闭：`annotation.granularity` = `'sample'`**。裁定依据（需求原文三处实证，agent 独立核验逐字吻合）：FR-E01（需求 671 行）"样本级（**整条平均谱一个标签**）"；§6.4.1（1782 行）"可由像素级标签自动聚合成样本级，**反之不成立**"；场景 S1（417 行）"人工确认/修正 → **自动聚合出样本级光谱集（带标签，共 N 条）；标注版本落库**"。**语义：`granularity` 描述记录粒度、非操作粒度**——阶段一操作在像素级（工作态 label_map，不落库），落库 `annotation` 行是聚合产物，取 `'sample'`；`'pixel'` 留给阶段二像素级明细记录（FR-E01"三级可共存"）；`'scene'` 无写入路径。4.1 原注释"阶段一恒为 'pixel'"系早期口径漂移，已改；§5.4 末补句；§6.1 scene 断言补"落库行全为 'sample'" | R15 待决项裁定（科祥取证 + agent 核验原文） |
| R17 | **codex 四触即停：10.3 五个口径缺口，全部裁定并取证**。① **`label_index` 并列**：`label_sort_order`（labels.py:78-85）三路径可产生并列（custom max+1 vs 目录序号，如 custom=4 与目录 PS=4），排序钉死 **`(sort_order ASC, code ASC)`**——与已发货的 `LabelStore.tree()`（labels.py:130）`ORDER BY sort_order,code` 一致，`code` 项目内 UNIQUE 构成确定全序，不依赖时钟/uuid；`label_index.json` 持久化映射，历史版本免疫。② **混合超像素**：不跳过，按 `(label ∩ 超像素)` 部分均值对查（详见 §5.5 R17 条）。③ **阈值标定授权合成标注**：真实 cube + m=0.5 segments + `KMeans(4, random_state=0, n_init=10)`，仅用于阈值行为与植入离群验证，**不得冒充人工标注/不得用于标注质量断言**。④ **覆写事件落 `annotation_version.note`**（migrations.py:58 已有该列，**不加列**）：`{"event":"overwrite","at":"<ISO8601 UTC>"}`，新建 `note=NULL`，`created_at` 不变。⑤ **授权 `migrations.py` 仅同步 R16 granularity 注释**（diff 只许注释行、零 SQL 语义变化），因 `test_ddl_matches_card_verbatim`（test_storage.py:76）逐字比对卡内 SQL 块，改卡不同步必红；该文件进逐文件 add 清单并在回执点名 | codex 执行期四检：卡未写死口径 + 卡/实现 DDL 同步 |
| R18 | **codex 10.3.5 五触即停：四处卡未写死裁定（种子参照与区域连通性）**：①**增长邻接 = 4 邻域**（与 `boundary_ratio` 同口径；角点接触致视觉断裂且扩大 single-linkage 泄漏面；锚点 **765 段 2079 边 / 830 段 2256 边** 实测，与 R10 锚点"766 段 2075 边"是两套 segments，勿混）；②**多命中提示 = 合成一条种子谱产一个候选**、像素等权（直读卡"取其均值谱为种子谱"单数）；**种子成员 `cos_s` 定义为 1 不实算**（直读"种子自身 cos_s=1 计入"）；③**涂鸦 = 相邻坐标间 1 像素宽 Bresenham**；④**框选 = 半开 `[l0,l1)×[s0,s1)`**。出处：卡 §5.3 + `boundary_ratio` 4 邻域惯例；0.80/0.92 出处不变 | codex 执行期五检：连通性与栅格化卡未写死 |
| R19 | **10.4 开令前三条裁定（polygon / note / 参数失配）**：①**polygon 栅格化** = 像素中心点 `(l+0.5,s+0.5)` **even-odd** 判定、中心恰在边上计入内部、**不做边界膨胀、不设 `dilate`**（label_map 单值，膨胀致相邻区域互相覆盖、结果依赖写序）；②**note 列语义（修订 R17）** = 唯一承载版本事件 JSON：覆写 `{"event":"overwrite","at","text"?}` / 新建带备注 `{"event":"save","at","text"}` / 新建无备注 NULL；save body 收 `note?`（≤2000 字符，超长 400 `INVALID_VERSION_NOTE`）；**授权 `session.save` 仅加 `note=None` 参数与 JSON 组装、其余逻辑不动**（实测原签名 `save(cube_id,*,overwrite,confirm)` 不收 note，§5.6 body 的 `note?` 是真空缺）；③**分割参数失配防护** = `diffuse`/`regions`/`validate`/`save` 前比对 session params 与缓存分割 params，不一致 → **`SEGMENTATION_STALE`(409)**，不得静默同步；`working` 不受限 | 10.4 开令前 agent 研判 + 科祥裁定 |
| R20 | **overlay 路径参数类型钉死（10.4 契约同步）**：`GET /datasets/{id}/annotations/{version}/overlay` 的 `{version}` = **`annotation_version.id`（UUID）**，非 `version_no`。理由：UUID 与表主键直连、全局唯一；`version_no` 仅用于 UI 显示与排序（同一 cube 内唯一、跨 cube 会撞"版本 3"）。配套：`GET /annotations` 返回全列含 `id`，前端据此请求 overlay；**跨 cube 校验**——合法 UUID 但 `cube_id != {id}` → `VERSION_NOT_FOUND`(404)，不得暴露他 cube 快照（10.4 实现已做，卡补记防被后续"优化"掉）。**契约同步两件**（10.4 提交同批）：①`test_labels_api.py:130` 的 10.1 阶段门否定断言改为肯定式完备端点集（9 个 datasets 端点全部在场，认证断言保留）；②`openapi.json` 用程序从真实 `app.openapi()` 重新生成，`test_api.py` 完整相等断言不过滤不削弱，diff 只许纯新增 | 10.4 落地时发现卡未定义项（agent 反推实现 + 科祥确认） |
| R21 | **10.6 两项接缝授权（批准面实质扩大，科祥 2026-10-20 确认）**。**缺口属实**：①`AnnotationRequest` 仅 9 变体、全为 `/api/v1/datasets/*`，projects/labels/AddLabel/catalog 四端点无 IPC 路径，webview 拿不到端口/token 无法直连 → §5.8 标签管理成死条款；②`working_view` 只返回 `{superpixel_count,params,statistics,overlay}`，无 queue/project_id，编辑后/切图返回无法只读恢复右栏队列。**授权**：①`annotations_forward` 加 4 个固定变体（Projects/Labels/AddLabel/Catalog），**命令总数仍六条**——但路径族从 `/api/v1/datasets/*` 扩到 `/api/v1/{projects,labels,catalog}`，属**批准面实质扩大**（渠道数与约束未变，比新开第七条命令更保守，故批）；②`working` 加只读 `queue`（与 diffuse.queue 同结构）+ `project_id`。**实现要点（agent 核代码发现，规格比"加 4 个分支"大）**：`destination()`（annotation.rs:242）硬编码 datasets 前缀且新变体无 `id` 字段 → **必须按变体分族构造路径**；`Labels` 的 `project_id` 须 `Uuid::parse_str().to_string()` 规范化后 `set_query`，禁原始字符串拼接；`AddLabel` 的 `serde_json::Value` 透传前须校验 ≤64 KiB（现有 8 MiB 只限响应不限请求）。**Rust 原"无 query/fragment"测试改口径为"无调用方可控 query"**，自由 URL/host/port/path/method 拒绝断言全保留。业务校验唯一权威仍在 Python（三 body/互斥/422），Rust 不复制校验与默认值。门槛：pytest 337 只增不减、cargo 35 只增不减、clippy 零警告；提交分接缝 commit + 前端 commit | 10.6 执行期即停：IPC 通道缺失 + 队列无只读源（agent 核 Rust 代码 + 科祥裁定） |
| R22 | **卡 366 行口径对齐已验收实现（tag 前事实源修正）**：R21 原写 `Labels` 的 `project_id` 用 `Uuid::parse_str(...).to_string()` 规范化，实现（annotation.rs:229/273）实际用 `uuid()` 严格校验（**36 位、8-4-4-4-12 格式**，144 行）+ `to_ascii_lowercase()`。二者**效果等价**（都产出标准小写 36 位 UUID），但**卡文按实现改写**——事实源必须与已验收实现一致，否则 v0.1.2 带病入库 | #04 收官前 agent 核实现（科祥指出卡/实现不一致） |
| 10.2 标定回填 | 55 格实测后保留 compactness=0.5（仅此档 11/11 满足既有结构断言）；仅回填 §5.2 compactness、§6.1 n/area_cv/R 基线与 §6.3 扩散规模，验收阈值不变；表、独立 R 复算脚本与汇总落档 | `milestone04/evidence/calibration/compactness.csv`、`calibrate.py`、`summary.json`、`pca3-baseline.json`（实现层实测） |

**证据锚点**（供复核抽查）：pe/20260804205214_64，231×640×200，BIL；PCA 3.2 s / evr=[0.309,0.185,0.077,0.048,0.042]；m=0.5 → n=765（细分前）、area_cv=0.182、R≈1.8；m=10 → n=782、area_cv=0.068、R≈1.07；归一化特征图均值 0.492–0.501、std 0.129–0.164、值域 [0,1]；分块 32/64/128/单批 → n=765/765/765/766、area_cv=0.177–0.183；k=3 → τ=0.113、触发 64/765、64 父块拆成 129 子块、细分后 n=830、子块面积中位 86 px（全段面积中位 191 px，勿混）。

**R10 口径锚点**（扩散/队列，与上段分割锚点分开记）：pe/20260804205214_64，n_seg=766、邻接边 2075、40 种子；**原谱口径**阈值 0.92 → `min_similarity` 0.4959–0.9835（中位 0.8312）、33/40 < 0.92、**15/40 < 0.80**（其中 1 个落在 [0.75,0.80)）；pet×4 + pp×4 各 20 种子 → 被 0.80 拦掉 7/10/13/7/10/4/13/8；阈值 0.80 → 区域中位规模 583/757/720/482/449/305/719/398 个超像素（全图 754–766）、19–20/20 被拦。**PCA-5 特征口径**（已否决，仅供对照）：阈值 0.92 → 被拦 0–4/20（pet/…_186 与 pp/…_75 为 0）、区域中位仅 2–18 个超像素。结论：口径不同结论相反，故 5.3 写死"原谱 + 种子参照"。

---

**任务卡签发人**：科祥（2026-10-20 口径已拍板；release IPC 注册 `annotations_forward` 已于当日批准）
**任务卡执行人**：codex
**复核人**：科祥（按验收 checklist 逐项确认）
