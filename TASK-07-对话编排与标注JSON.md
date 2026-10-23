# TASK-07 对话编排（D 域地基）与标注 JSON + 训练 MAT 任务卡

> 里程碑 **#07**。事实源：需求文档（FR-D01~D13、FR-E01~E10、FR-A08/A13、FR-H07/H09、FR-L10）+ UI 原型（S01 助手屏、S05/S06）+ 技术选型定稿 v1.1（LLM 网关唯一出口）+ D 域编排讨论摘要（2026-10-22）+ 2026-10-22/23 与科祥的两轮设计讨论。
> 本卡由备卡 Agent 起草（2026-10-23），**待科祥确认 §10 后转 codex**。一次只开一个子阶段（§5）。
> 基线（2026-10-22 实测）：Python **681 passed**｜Rust **58 passed**｜node **74 passed**｜tsc exit 0。回归跑法照抄：`cd <仓库根> && .venv/Scripts/python.exe -m pytest backend/tests src-python/tests`，`PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp` 与命令同条书写。

---

## 0. 背景与动机（先读，不要跳过）

### 0.1 本卡直接针对的现存漏洞：多边形顶点 100% 丢失

实测代码路径（2026-10-23 核）：

1. `api/annotations.py:67` `PolygonGeometry` 早就接收多边形顶点（REST 入口在）；
2. `polygon_mask()`（:83-96）已实现，口径为 **R19：像素中心 + even-odd + `inside | on_edge`**（边界像素计入，无膨胀）；
3. 但 `session.py:197 edit()` **只接收布尔掩码**——顶点在这一步被丢弃；
4. `_aggregate_rows()`（:334-349）写进 `annotation` 表的 geometry 只有 `{"superpixels": [...]}`，且只记录"整个超像素被标成同一类"的几何——**手画多边形连一条 region 记录都不会留下**（R4 起 DB 行 geometry 改 `region_ids` 指针，见 §3；本条描述 R4 前现状）。

结论：现在保存一次标注再打开，只能看到一张位图，**原多边形永久不可再编辑**（拖顶点微调不可能）。本卡的标注 JSON 主文档正是针对此漏洞：JSON 是几何原始语义的唯一保存处。

### 0.2 三级真相源（缺一不可，不许合并）

| 层 | 角色 | 消费者 |
|---|---|---|
| JSON（草稿/确认版） | **编辑真相**：顶点、source、confidence、region 边界 | 人（画布/对话编辑） |
| `label_map.npz` | **计算真相**：有损但确定性 | 预处理（实测 `preprocess/run.py:152-167` 从 `snapshot_ref` 读；指纹含 `annotation_version_id`）、统计 |
| MAT | **导出物**：给 MATLAB/外部训练脚本 | 平台内部任何计算**禁止读取**（红线 6，否则指纹全变） |

绑定不变量：**确认版 JSON 栅格化结果与冻结 `label_map.npz` 逐像素 bit-exact**——这是唯一能证明"JSON 没写坏"的验证条件。

### 0.3 已知限制（红线直接结果，非缺陷，不得在本卡"顺手修复"）

**草稿态跑不了预处理**：`preprocess/run.py:152` 只认 `annotation_version` 快照，草稿无版本号。"边标边看预处理效果"做不到——这是"标注前置于预处理"（v2.5 定版）与指纹血缘的直接结果。想做须另开草稿态试算通道，会破坏指纹血缘，**本卡明确不做**。

---

## 1. 范围裁定

### 1.1 做（阶段一）

| 项 | 内容 | 依据 |
|---|---|---|
| G1 | **LLM 网关（唯一出口）**：OpenAI 兼容 httpx 薄客户端 + `LLMClient` 抽象 + 配置/凭据 + 禁运字段拦截 + 全量留痕 + token 计量 | 定稿 v1.1（FR-L10）；D 域摘要 §3.2/§3.4 |
| G2 | **自研编排状态机**：`IDLE→PARSE→CALL_TOOL→INTERPRET→DONE` + `CLARIFY/HUMAN_CHECK/ERROR` 分支 | D 域摘要 §3.3（定稿明选"自研状态机 + OpenAI 兼容协议"，不选 LangChain） |
| G3 | **SKILL 版本化契约**：system prompt + 工具清单 + 示例 + mock 回归探针 | 2026-10-23 讨论结论 |
| G4 | **SSE 流式端点 + 前端常驻对话条（S01 最简）** | FR-D13；UI 原型 S01 |
| G5 | **标注 JSON 主文档**：草稿/确认两态；`polygon`/`pixel_set` 二形态几何；来源 + 置信度 | 2026-10-22/23 讨论；FR-E01/E05/E08/E16 |
| G6 | **栅格化规则 + JSON↔label_map 互锁** | #04 既有机制延伸（label_map 为唯一权威几何不变） |
| G7 | **训练 MAT 生成**：标注确认时同步产出，**原料态 DN**（B01 前）+ 标签 + 输入指纹 | 2026-10-22 讨论结论；FR-H09 精神 |

### 1.2 不做（明确禁止，不要"顺手加"）

- C 域建模（PLS 等）、F 域训练实验、H 域检索/RAG——后续里程碑。
- E 域 L2/L3 全自动标注（库匹配全链、黄金验证集、修正率降级）——阶段二。
- 多步依赖 **DAG 规划**：本卡只做线性 tool_call 序列（上限见 §2.2）。
- 本地模型（Ollama/LM Studio）联调：`LLMClient` 抽象为其留位，阶段一冒烟只验云端。
- Rust 侧任何 LLM 逻辑：全部在 sidecar（Python）内。
- MAT 压缩选项、zlib/npz 替代格式：`do_compression=False` 钉死（§2.5）。
- 草稿 JSON 的中间版本历史：只确认版冻结（§2.4）。
- **版本恢复为草稿**（从确认版 `annotation.json` 载回 draft）：JSON 化后天然可做，但阶段一范围已满，**明确不做**，防实现期顺手加。
- 替用户预置任何厂商 base_url/key：默认未配置状态（§2.1）。

### 1.3 输入前提（已有，不改）

- #04：标注会话、`label_map.npz` 三件套快照、`label_index.json`（R15：下标 = 项目 label 按 sort_order 升序）、-1/-2 语义、`ReadableRows` 有界读。
- #05：`preprocess_run` 输入 = cube + annotation_version；`readable(raw=True)`；`input_fingerprint` 算法；artifacts 只落 `sample_spectra` + `report`。
- #06：标注画布（几何手势采集面）。
- `backend/paths.py` AppPaths 模式；`main.rs:194` 七个 IPC forward 命令与 4.6 forward 基建（身份校验/8MiB 限额/路由白名单）。

---

## 2. 业务口径（钉死，照抄不得发挥）

### 2.1 LLM 网关（G1）

- **客户端零新增依赖**：不引 `openai` 包，用已锁定 `httpx==0.28.1` 裸调 `{base_url}/chat/completions`（协议面就 chat/completions 一个端点 + models 可选）。理由：定稿"OpenAI 兼容协议"本就不锁定厂商；PyInstaller 冻结避重依赖（D 域摘要 §3.1 同理由）。
- **`LLMClient` 抽象**（`agent/llm.py`）：`chat(messages, tools, *, stream=False) -> ChatResult`；`ChatResult` 含 `content`、`tool_calls[{id, name, arguments_json}]`、`usage{prompt_tokens, completion_tokens, total_tokens}`、`finish_reason`。云端/本地同一协议可插（本地 = base_url 指向 Ollama/LM Studio）。
- **配置分层**：`llm_settings` 表存 `base_url / model / temperature / max_tokens / timeout_ms`（非敏感）；**默认全部为空 = 未配置**，禁预置厂商地址（禁"落盘数值无来源"）。**API key 不落任何盘**：设置屏填入 → 仅 sidecar 进程内存持有（模块级容器，不写 db/日志/产物），重启失效重填（备卡裁定；keyring 包未锁定，新增依赖路线见 §10-1）。
- **禁运字段拦截**（FR-A13 + 定稿）：出域 payload 只含白名单重建上下文——数据集 id、类 code、指标数字、工具名。**NAS 路径、文件名、label_map 内容、坐标数组一律不进 messages**。发送前 deny 扫描：命中盘符/反斜杠/正斜杠路径形态/`.img|.hdr|.mat` 文件名/**坐标数组形态（序列化文本中 `[[` 开头的嵌套数组，即 `[[int,int],...]` 像素坐标对）** → `EGRESS_BLOCKED`，网络零发出（测试用 mock transport 断言未调用），`llm_call` 记 `status='blocked'`。**扫描是兜底不是主防线**——主防线是 §2.3 出参白名单（工具回灌内容根本不产生坐标；R7：R1 起"约束写了坐标数组、扫描只查路径"就是洞，无工具返回几何故未暴露，`sample_pixels` 是第一个触发的）。
- **留痕**：`llm_call` 每次调用一条（model / tokens / latency / status / tool_names / error）。**消息全文不落库，只存 sha256**（"全量留痕"指调用记录全量，非内容全量——本地单用户库亦无必要存全文）。
- **token 计量**：取响应 `usage`；本地模型无 usage → 记 `null`，**禁填 0、禁估算**（探针口径：分不清就说不确定）。
- **传输失败**：超时/断网 → `LLM_TRANSPORT`，状态机进 `ERROR` 复位 `IDLE`；禁静默重试（重试必须经状态机显式分支且至多 1 次）。

### 2.2 编排状态机（G2）

- 五态三分支照 D 域摘要原文：`IDLE → PARSE（调 LLM 选工具）→ CALL_TOOL（校验+执行算子+打溯源）→ INTERPRET（结果回灌 LLM 翻人话）→ DONE`；分支 `PARSE→CLARIFY`（参数缺失主动反问，**禁取默认值蒙混**）/ `CALL_TOOL→HUMAN_CHECK`（人在环）/ `→ERROR`（复位）。
- **`HUMAN_CHECK` 触发类**：FR-D07 四类（删除数据、覆写标注、发布模型、超长任务）+ 本卡新增一类：**标注版本确认**（draft_confirm）。确认前不执行。
- **单消息 tool_call 上限 N=8**（备卡裁定；场景 S1 约 5–6 步，8 留余量；超出拒第 9 个并 `TOOL_SEQUENCE_LIMIT`）。线性序列，禁 DAG。
- **每步落库** `agent_step`：含 `arguments_json`（过校验后的参数）、`result_digest`（sha256）、`result_summary`（短摘要，大对象不落库）、`status`。**被 schema 拒的 tool_call 也落 step**（`status='rejected'`）——防"被拒调用无痕"，回归探针靠它断言。
- **红线物理保障**：tool_call 落地前必须过 Pydantic 校验（D 域摘要 §3.2 原文）。

### 2.3 SKILL 契约（G3）

- **`skill_version` 表只增不改**（对齐 #05 配方版本化纪律）：**内容列 `UPDATE` 一律禁止**；唯一允许的 `UPDATE` = 状态迁移，完整迁移集 = `draft→active` / `draft→retired` / `active→retired`（R8 勘误：:96"切换"语义要求 `active→retired`，原"仅 `draft→active/retired`"不闭合）；**retired 为终态**（禁 retired→任何状态）；active 全局唯一（部分唯一索引或应用层断言+测试）。
- **激活**：阶段一全局唯一 active；两个操作语义钉死（R8）：① **`activate(v)`**：仅 `draft→active`；**若已有 active 存在则失败**（active 唯一约束，禁自动替换——防误切换）；② **`switch(v)`**（显式切换，即"切换 = 新版本 active、旧 retired"的落地）：**同一事务内**旧 active→retired + 新 draft→active，原子（任一失败整体回滚，禁出现零 active 或双 active 的中间态）。会话创建时快照 `skill_version_id`。**无 active skill 时拒绝创建会话**（禁造默认 skill——skill 全文是种子数据，来源=本卡规格，防实现期手填）。
- **工具清单来源**：只封装既有/本卡新增的 **service 层函数**（datasets/annotations/preprocess 的 Python service），不经 Rust IPC 自绕。首批工具（对齐命令面，不发明新能力）：

  | 工具 | 底层 | 本卡状态 |
  |---|---|---|
  | `datasets.list` / `datasets.describe` | 已有 datasets service | 包 schema |
  | `annotations.draft_get` / `draft_add_region`（入参 `op="add"|"uncertain"|"erase"`：`uncertain`/`erase` 禁传 `class_code`/`confidence`、geometry 仅 `gesture_ref`；`add` 必填 `class_code`） / `draft_select_candidates` / `draft_confirm` | §2.4 新增 | 新增 |
  | `preprocess.run` / `preprocess.compare` | #05 已有 | 包 schema |
  | `training_mat.export` | §2.5 新增 | 新增 |
  | `settings.llm_get` | §2.1（无 key） | 新增 |

- **几何禁入（本卡最核心红线工程化）**：工具入参 schema **不得包含自由坐标/谱值字段**。LLM 可传：类 code/名称、方法枚举、数量上限、region_id、version_id 引用。几何只允许两个产源：①`draft_select_candidates(class, method, params)`——算法（SLIC/SAM 扩散）在工具内确定性生成；②用户画布手势（前端采集，工具收 `gesture_ref`）。LLM 传坐标数组 → schema 无此字段 → `TOOL_ARGS_INVALID` 拒 + step rejected。
- **工具出参白名单（R7，堵“结果回灌”洞）**：§2.2 INTERPRET 的“结果回灌 LLM”所回灌的内容 = 工具执行的 `result_summary`，**只允许标量 + 枚举 + 计数字符串**（id、code、计数、状态、版本号、纯文字提示）；**`sample_pixels` / `bbox` / region 几何 / `document` 原文 / 任何 `[[int,int],...]` 坐标数组形态一律剔除**。冲突信息给 LLM 的只有 `conflict_count` + 纯文字提示（“存在 N 处跨类重叠，请在画布上处理”）；**位置数据只走 REST 响应给前端**（§4.1），不进 messages。`draft_get` 回灌摘要 = `{cube_id, revision, n_regions, n_classes, updated_at, estimated_mat_bytes}`（全标量；§10-2 定稿：体积数字让 LLM 能在对话里主动提醒导出大小，符合白名单）；**完整 document 只走 REST 响应**（前端画布要用，LLM 不感知几何）。几何禁入从此覆盖入参 + 出参两侧。
- **工程保障**：一个测试静态扫描 `skill_version.tools_json`，断言无坐标/谱值类字段名（`points|coords|polygon|spectra|values|bands`）——schema 层强制，不靠 prompt 叮嘱；**出参侧同一纪律**：回灌摘要的构造有对应断言（见回归探针 ⑦）。
- **初始 skill（version_no=1）种子数据**：`system_prompt` / `tools_json` / `examples_json` 由本卡规格生成，内容钉死（R8 落定稿正文，codex **照抄、禁改一字**；验收人工对读）：角色=光谱平台编排助手；红线条款（只编排不产数 / 坐标谱值禁传 / 不确定就反问 / 结论带溯源(算子·版本·run_id) / 只说 id 不说路径）；工作流知识（标注→预处理→建模顺序不回退；S05 五步：超像素→扩散→逐类确认→聚合→保存；配方对比话术）。`system_prompt` 定稿正文（上述要点的逐条落文，每条可回溯）：

  > 你是光谱数据处理平台的编排助手。你只编排既有能力，不产生任何数值结果。
  >
  > 红线（每次回复遵守）：
  > 1. 只编排不产数：所有数值由平台算子和工具产生，你禁止估算、编造或复述未经工具返回的数字。
  > 2. 坐标与谱值禁传：你不得传递任何坐标数组、像素谱值或几何参数；标注区域由画布算法或用户手势产生。
  > 3. 不确定就反问：参数缺失或意图不明时向用户提问，禁止取默认值替用户决定。
  > 4. 结论带溯源：涉及算子、预处理配方或数据版本的结论，必须附算子名、版本号与 run_id。
  > 5. 只说标识不说路径：对话中只出现数据集、区域、版本的 id，禁止出现文件路径。
  >
  > 工作流知识：
  > - 处理顺序不回退：标注 → 预处理 → 建模，按此顺序推进，不跳步、不反向。
  > - 标注五步（S05）：超像素分割 → 扩散 → 逐类确认 → 聚合 → 保存。
  > - 配方对比：基于 preprocess.compare 的返回逐项说明各配方的指标差异与适用场景，结论带算子名与版本号。

  `tools_json` = 本节首批工具表（:99-105）的序列化快照（工具名 + 入参 schema + 描述；LLM 可传字段仅限 :107 白名单）。`examples_json` = **`[]`**（阶段一不预置对话示例——卡无示例正文来源，按八查⑤.5 显式留空、禁实现期自行编写；将来确需示例时随 skill v2 只增不改进入）。**禁实现期另起措辞**。（"配方对比"一条原卡只有标签无正文，由备卡方代拟补缺，溯源见 §12 R8；科祥可单独拍板替换该句，不影响其余定稿。）
- **回归探针（mock，不烧 token）**：mock `LLMClient` 回放固定 tool_call 序列，至少 6 条：①正常链路（选工具→执行→解读）；②参数缺失→CLARIFY 反问（禁默认值）；③LLM 传坐标→schema 拒 + step rejected；④覆写标注→HUMAN_CHECK 确认前不执行；⑤禁运字段→EGRESS_BLOCKED 且 transport 零调用；⑥多步序列按序执行、第 9 个被拒；⑦**出参白名单（R7）**：`draft_confirm` 冲突场景 + `draft_get` 场景下，回灌 LLM 的 messages 序列化文本**不含 `[[` 坐标数组形态**、不含 `points|polygon|sample_pixels|bbox` 字段名（禁运扫描看不见坐标，这条是直接防线）。真实模型冒烟归科祥本机（§8/§10-3）。

### 2.4 标注 JSON（G5/G6）

- **两态**：`annotation_draft`（每 cube 一条活草稿，mutable）+ 确认时走 #04 既有 `annotation_version` 保存路径；快照目录由三件套扩为**四件套**：`label_map.npz` / `label_index.json` / `spectra.npz` / **`annotation.json`（新增）**。
- **JSON schema（钉死）**：

```json
{
  "schema_version": 1,
  "cube_id": "uuid-string",
  "classes": [{"index": 0, "code": "PP", "name": "聚丙烯", "color": "#RRGGBB"}],
  "regions": [
    {"region_id": "r-0001", "op": "add", "class_index": 0,
     "geometry": {"type": "polygon", "points": [[x, y], "..."]},
     "source": "manual|algorithm|library|migration|model",
     "confidence": "high|medium|low",
     "created_at": "iso8601"},
    {"region_id": "r-0002", "op": "uncertain",
     "geometry": {"type": "polygon", "points": [[x, y], "..."]},
     "source": "manual",
     "created_at": "iso8601"},
    {"region_id": "r-0003", "op": "erase",
     "geometry": {"type": "polygon", "points": [[x, y], "..."]},
     "source": "manual",
     "created_at": "iso8601"}
  ],
  "raster_rule_version": 1
}
```

- `geometry.type ∈ {polygon, pixel_set}`：**polygon** = 用户手画（扫描线 even-odd 填充，边界像素以中心点在内为准）；**pixel_set** = RLE 行游程 `{"rows": [[row, start, length], "..."]}` + `segments_fingerprint`（分割参数指纹，来源 #04 segments 参数纪律）——算法候选（`draft/candidates`）与 legacy 超像素确认（§4.2）共用此形态；**不可手改**（要改必须先转 polygon——备卡裁定）。
- **`op` 字段（R4 新增，R5 收敛为三值，与 #04 `action ∈ {confirm, erase, uncertain}` 一一对应）**：`"add"`（默认，省略即 add）= 标注归属某类，**必填 `class_index` + `confidence`**；`"uncertain"` = 人看过给不出类（栅格化 → -2）；`"erase"` = 显式擦回空白（→ -1）。**`uncertain`/`erase` region 无 `class_index` / `confidence` 字段**（schema 层禁携带——二者都不归属任何类；这也消除了 R4 版“uncertain 携带 class_index”的歧义）；`source` 仍必填（三态都是人的动作）。
- `confidence ∈ {high, medium, low}` **只表达确定性分档**（R5 起不再兼职表达“无类别”——那是 `op:"uncertain"` 的职责）；`op:"uncertain"` ↔ label_map **-2**；`op:"erase"` ↔ **-1**（有记录地显式留白）；**无任何 region 覆盖** ↔ **-1**（从未标注，无记录）——erase 与无记录 label_map 同值、审计语义不同（前者可追溯“这里曾被擦过”），uncertain 与二者均不同值。
- 类表 `index` = `label_index.json` 下标（#04 R15：项目 label 按 sort_order 升序），**不得另起一套**。
- **栅格化 = 纯函数** `rasterize(annotation_json, shape) -> label_map int32`：①**polygon 分支必须调用既有 `polygon_mask()`（`api/annotations.py:83`，R19 口径：像素中心 + even-odd + `inside | on_edge` 边界计入，无膨胀），禁止重写扫描线**（重写必差边界一整圈像素，bit-exact 永远失败）；②pixel_set RLE 直接展开；③**跨类重叠不静默覆盖**——**每次栅格化从零构建**（document 整篇重写、纯函数全量计算；禁增量缓存/跨次“维护”——写“维护”会诱导 codex 做增量状态，改类时必错）：**`label_map` 与 `owner`/`conflict` 两图并行维护、互不派生**——label_map 的每个像素由**最后一个覆盖它的 region 的 `op` 直接决定**（add→class_index / uncertain→-2 / erase→-1，**不经过 owner 图**）；`owner`（每像素当前 add 归属类）与 `conflict`（该像素是否有 ≥2 个不同类 add 覆盖且未被清除）**仅用于冲突统计，任何情况下不参与 label_map 赋值**（R6：若实现成“先算 owner 最终归属、再从 owner 生成 label_map”，uncertain 的 -2 与 erase 的 -1 都表现为 owner 空、无法区分 → **-2 全部退化成 -1** → §2.4“uncertain 与二者均不同值”当场失效、bit-exact 失败）；`op:"add"` 写入时若 `owner` 已是**不同类** → 标 `conflict`；`op:"uncertain"/"erase"` 清除该像素的 `owner`/`conflict` 标记；**`conflict` 一旦置位仅 erase/uncertain 可清除，重复 add（同类或不同类）均不清除**（用户需先擦后画——必须写明，否则前端会以为“重画盖住”能解冲突）；**最终 `overlap_conflicts = count(conflict & (label_map >= 0))`，是最终状态统计、不是累加**（R5：否则用户用 erase 擦掉重叠部分后 conflicts 不降——死锁与删 region 之前同型）；`overlap_conflicts > 0` **不许确认**（`OVERLAP_UNRESOLVED`，HITL 四种修法都必须能解锁：删 region / 改类 / erase 擦重叠 / uncertain 标不确定）；④同类重叠合并；⑤**`op:"erase"` = 显式擦回空白**：其 geometry 覆盖像素的 label_map 置 **-1**、owner/conflict 标记清除，按 regions 数组序**后写覆盖先写**——因此 erase **能消除**既有重叠冲突；⑥-1/-2 语义：`op:"uncertain"` → -2（无类）；`op:"erase"` → -1（有记录显式留白）；无 region 覆盖 → -1（从未标注）。
- **`raster_rule_version` 历史函数永不删除**：定为常量 1，但 v1 栅格化函数（含 `polygon_mask` 引用）必须作为冻结实现保留——将来改规则（v2）时，旧确认版 JSON 重放仍走 v1 函数，结果不变。回归测试断言：同一确认版 JSON 永远 bit-exact（跨版本升级后仍成立）。
- **工作态初始化改为 JSON 派生**（`SessionStore._state()`，session.py:153-159 现状是 `np.full(-1)`）：有 `annotation_draft` → 读 JSON 栅格化出 label_map 作为工作态；没有才建全 -1。**禁止出现"JSON 有标注、画布全空白"或内存与 JSON 两套主数据**。
- **undo 双回滚**（现状 session.py:134/211/224：undo 栈只存 `label_map.copy()`，纯内存 maxlen=5）：改为存 **(document_json, label_map) 成对快照**——撤销必须同时回滚 JSON 与位图，否则几何与位图脱节，下一次任何写操作会把撤销结果覆盖回去。
- **classes 一致性校验（确认时）**：`classes[].index` 必须与确认时生成的 `label_index.json`（#04 R15：项目 label 按 sort_order 升序）逐项一致，**不一致直接拒确认**（`LABEL_INDEX_MISMATCH`）；`code/name/color` 允许随项目 label 表刷新快照（显示值），但 `index` 错位零容忍。
- **互锁不变量（验收锚点）**：`确认版 JSON + 栅格化规则 → label_map` 与冻结的 `label_map.npz` **逐像素 bit-exact**（不是容差）。JSON→label_map 单向权威；反向仅审计。
- **草稿写路径**：`annotation_draft.document_json` 由工具层维护——每次几何编辑整篇写入，**单条 UPDATE 在 `BEGIN IMMEDIATE` 事务内完成、失败回滚**（DB TEXT 列，无文件临时态；勿写成"临时文件+rename"），JSON Schema 校验不过不落盘；`schema_version`/`raster_rule_version` 为常量 1（禁配置化）；`cube_id` 来自 datasets 存在性校验；`updated_at` 服务端 timestamp。
- **确认版 `annotation.json` = 规范化副本（钉死）**：写入快照的不是草稿原文，而是规范化后的副本——`classes` 按确认时的项目 label 表刷新（显示值）、`regions` 原样拷贝、`raster_rule_version` 保持 1；**草稿原文不动**。bit-exact 重放的基准永远是快照内这份规范化副本（classes 刷新不影响栅格化，因 index 已校验一致）。
- **对话编辑入口**：`draft_add_region` 等只收 region 引用/类/方法（几何禁入原则）；坐标由算法或手势提供；**LLM 从不构造 document_json 原文**。

### 2.5 训练 MAT（G7）

- **触发**：标注版本确认时同步生成（confirm = HITL 动作，天然审批点）；另提供手动重建入口（源数据变化后）。
- **内容（原料态）**：`spectra float32 (n, B)` = **B01 前的原始 DN**（`readable(raw=True)`，与 #05 run 预检同口径，R11）；`labels int32 (n,)`（**仅 ≥0**；-1/-2 不进）；**`rows` / `cols` int32（各 n 个）**——后续空间-光谱模型（patch 提取）必需，成本 8n 字节（PE cube 全标 147,840 像素约 1.2 MB，相对 118 MB 谱矩阵约 1%）；**`source_dtype`** = 实际读取数组的 `dtype.str`（保留字节序，如 `'<u2'`；DN 原为 uint16 转 float32 无损，原为 float64 则有损——必须写清，否则复现时数值对不上无从查起。注意：与 registry `SOURCE_CHANGED` 的 dtype 口径**有意不同**——`SpectrumDataSet` 校验器把 dtype 归一为 `.name`（model.py:56，丢字节序）属预存在缺口，不在本卡范围）；`label_index`（类 code 列表）；`wavelengths`（hdr 有则 float64 (B,)，无则空数组 + `has_wavelengths=false`）；元数据 dict：`cube_id / annotation_version_id / input_fingerprint / n_spectra / n_bands / n_classes / dtype_note="raw_dn_pre_b01" / schema_version / created_at`。
- **`labels` / `label_index` 语义钉死（防训练类别错位）**：`labels` **保留项目原始 index（可能不连续**——用户只标了 0 和 3 时 labels 里就没有 1、2）；`label_index` 存**项目全表快照**（与确认时 `label_index.json` 完全一致）。理由：与 label_map 语义同源、与 #04 R15 一致；下游要压缩到 0..k-1 自己压，**平台不替用户重映射**（禁第二套下标）。
- **`rows`/`cols` 轴序钉死**：`row` = line 索引、`col` = sample 索引，均 **0-based，与 label_map 同轴序**（不是 x/y 几何坐标；与 BIL/BSQ 读取的 (lines, samples, bands) 轴序一致）。
- **同步生成 + 性能门（维持同步，不预留异步死分支）**：confirm 同请求内同步生成（HITL 动作天然审批点）。量化依据（milestone05/evidence/11.7/performance.md 实测）：#05 单配方全图 pass 落库生命周期 0.31–0.63s（PE cube [231,640,200]、已标 18000 像素、`BoundedInput.lines()` 每行块都 `readable()` 全图读一遍再筛，即已含全图 IO）；MAT 相对增量只有 memmap 写盘 + savemat，**预计 PE cube 全标 2–5s、1000×1000×200 全标（800MB）5–10s，距 30s 门有 6–15 倍余量**。12.7 记录实测值即可；**若实测 >30s，回来重议异步方案（另出补丁），本卡不预插 pending 分支**（对齐 #05 "§8 风险1（单配方 >30s）：未触发，维持同步"的同款处置）。
- **禁烤预处理**：MAT 不含任何 B01/SNV/SG 产物。预处理在下游按配方施加——理由：多配方对比共用一份原料（FR-B10）、CV 每折重拟合预处理参数（需求"防泄漏"条明文）、#05 禁全量物化红线、fit-on-apply 指纹复现语义、FR-H07 血缘（原始立方体→标注版本→配方→实验→模型）。
- **生成方式**：按 label_map 筛选 → 有界行块读（复用 #04 row_blocks 模式）→ 累积写**临时 memmap `.npy`**（`<exports>/<cube_id>/<version_id>/.tmp/`）→ `scipy.io.savemat` 一次性落盘 → `finally` 删临时目录；`do_compression=False`（钉死，保速度与确定性）；峰值内存 O(B)。
- **落点**：`AppPaths.exports` 新增 property（`root/"exports"`，与 snapshots/preprocessed 平级，`create_directories` 同步）；文件 `<exports>/<cube_id>/<annotation_version_id>/training_mat.mat`；**可重算可清理**（FR-A08 精神）。
- **MAT 是导出物不是计算输入**：预处理/未来训练的权威输入始终是 (cube, label_map)；测试断言 preprocess run 不读 exports 目录（防下游反过来依赖 MAT 导致指纹全变）。

---

## 3. 数据模型（DDL 草稿 + NOT NULL 写路径覆盖）

> 纪律（八查⑤.6）：每条 NOT NULL 列在每条写入路径上都必须有显式供值来源——限三种：body 字段 / 服务端规则 / 种子数据。三者都不占即缺，不许留空。

```sql
-- G1：LLM 配置（非敏感；key 不在此表）
CREATE TABLE IF NOT EXISTS llm_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL              -- 设置屏保存 body；首次启动服务端播种空值(base_url/model/temperature/max_tokens/timeout_ms)
);
-- 供值：value 全部来自 PUT /settings/llm 的 body 或启动播种（播种值=空串=未配置，禁预置厂商）

-- G1：调用留痕（每次调用一条；消息全文不落库，只存 sha256）
CREATE TABLE IF NOT EXISTS llm_call (
  id                TEXT PRIMARY KEY,
  session_id        TEXT,          -- agent_session.id；系统级调用记 NULL（status 维持四值枚举不前缀，系统级仅以 session_id=NULL 标识）
  model             TEXT NOT NULL, -- 响应回读（请求用的 model，发送前已知）
  prompt_sha256     TEXT NOT NULL, -- 服务端：发送前对 messages 计算
  tool_names        TEXT,          -- 服务端：本次请求 tools 名列表 JSON（无工具调用记 NULL）
  prompt_tokens     INTEGER,       -- 响应 usage；无 usage 记 NULL（禁 0 禁估算）
  completion_tokens INTEGER,       -- 同上
  total_tokens      INTEGER,       -- 同上（响应 usage 原值，禁由 prompt+completion 派生填写；§2.1 ChatResult.usage 三字段与 DDL 对齐，2026-10-23 勘误补入）
  latency_ms        INTEGER NOT NULL, -- 服务端计时
  status            TEXT NOT NULL, -- ok|blocked|transport_error|http_error
  error             TEXT,
  created_at        TEXT NOT NULL   -- 服务端 timestamp()
);

-- G2/G3：会话与步骤
CREATE TABLE IF NOT EXISTS agent_session (
  id              TEXT PRIMARY KEY,
  title           TEXT,           -- 服务端规则：首条用户消息截断 40 字；禁 LLM 生成后回写
  skill_version_id TEXT NOT NULL REFERENCES skill_version(id), -- 创建时取当前 active；无 active 拒绝创建
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_step (
  id              TEXT PRIMARY KEY,
  session_id      TEXT NOT NULL REFERENCES agent_session(id),
  seq             INTEGER NOT NULL,   -- 服务端自增（会话内）
  tool            TEXT NOT NULL,      -- LLM 返回的 tool_call.name
  arguments_json  TEXT NOT NULL,      -- 过 Pydantic 校验后的参数；rejected 路径供值：{"_raw_sha256":…,"_raw_truncated":…}（原文截断上限 4KB，大对象禁入）
  result_digest   TEXT,               -- 执行结果 sha256；rejected 记 NULL
  result_summary  TEXT,               -- 服务端短摘要；大对象禁入
  status          TEXT NOT NULL,      -- ok|rejected|human_check_pending|error
  latency_ms      INTEGER NOT NULL,
  created_at      TEXT NOT NULL
);

-- G3：SKILL 版本（只增不改；内容 UPDATE 禁止，仅状态迁移 draft→active / draft→retired / active→retired，retired 终态）
CREATE TABLE IF NOT EXISTS skill_version (
  id            TEXT PRIMARY KEY,
  version_no    INTEGER NOT NULL,     -- 服务端自增
  name          TEXT NOT NULL,
  system_prompt TEXT NOT NULL,        -- 种子数据：来源=本卡 §2.3 规格
  tools_json    TEXT NOT NULL,        -- 种子数据：工具清单快照（几何禁入字段扫描对象）
  examples_json TEXT NOT NULL,        -- 种子数据：来源=本卡 §2.3
  status        TEXT NOT NULL,        -- draft|active|retired；active 全局唯一（断言+测试）
  note          TEXT,
  created_at    TEXT NOT NULL
);

-- G5：标注草稿（每 cube 一条活草稿）
CREATE TABLE IF NOT EXISTS annotation_draft (
  cube_id            TEXT PRIMARY KEY REFERENCES dataset_registry(id),
  revision           INTEGER NOT NULL,            -- 禁 DEFAULT：忘写直接报错（八查⑤.6 显式供值，不靠默认兜底）；服务端自增，写入带 CAS（见下）
  document_json      TEXT NOT NULL,   -- 单条 UPDATE，BEGIN IMMEDIATE 事务内原子（DB TEXT 列无文件临时态）；schema 校验不过不落盘
  schema_version     INTEGER NOT NULL,-- 常量 1（禁配置化）
  raster_rule_version INTEGER NOT NULL,-- 常量 1（禁配置化；v1 栅格化函数永不删除）
  updated_at         TEXT NOT NULL    -- 服务端 timestamp()
);
-- 并发 CAS 三条规则（缺一不可）：
--   ① 创建：revision 从 0 起，INSERT 时写 revision=1；
--   ② 更新：UPDATE annotation_draft SET document_json=?, revision=revision+1, updated_at=? WHERE cube_id=? AND revision=?，
--      影响行数 0 → DRAFT_REVISION_CONFLICT（HTTP 409）；
--   ③ 禁 INSERT OR REPLACE / ON CONFLICT DO UPDATE——两者都会把 revision 重置为默认值 1，客户端持旧值反而写成功，CAS 反向失效。
-- 动因：画布与对话可同时编辑同一 cube，last-write-wins 会静默丢更新。

-- G7：训练 MAT（一版标注一份）
CREATE TABLE IF NOT EXISTS training_mat (
  id                    TEXT PRIMARY KEY,
  cube_id               TEXT NOT NULL,                        -- 服务端：confirm 入参
  annotation_version_id TEXT NOT NULL UNIQUE REFERENCES annotation_version(id), -- 服务端：confirm 产物
  relative_path         TEXT NOT NULL,                        -- 服务端生成（POSIX 相对，对齐 snapshot_ref 纪律）
  sha256                TEXT NOT NULL,                        -- 落盘后计算
  n_spectra             INTEGER NOT NULL,                     -- 生成时统计
  n_bands               INTEGER NOT NULL,                     -- 生成时统计
  n_classes             INTEGER NOT NULL,                     -- 生成时统计（= label_index 全表条目数，非 labels 中 unique 数）
  input_fingerprint     TEXT NOT NULL,                        -- 复用 #05 算法(dataset_id|源哈希|annotation_version_id|样本像素数)
  created_at            TEXT NOT NULL
);
```

**#04 快照目录三件套 → 四件套**：`annotation/session.py` save 路径增加 `annotation.json` 写入。**patch 自洽**：`tests/annotation/test_session.py:306` 现断言快照目录恰为三件套，必须同步改为四件套（**不许弱化断言**，只许加成员——按"#07 后新保存版本恰为四件套"的粒度断言，#07 前三件套旧版本回放兼容见 §4.2）；`test_session.py:90` 同理。

**#04 `annotation` 表与 JSON region 的关系（钉死，R4 定 / R5 补边界）**：`annotation.geometry` 改存 `{"region_ids": [...]}`——指向快照内确认版 `annotation.json` 的 region id 列表（**每 label 一行/版本**粒度不变；`session.py:334-349 _aggregate_rows` 原 superpixels 几何不再写 DB——多边形时代空几何列表会误导审计）。`pixel_count` 仍**只以 label_map 为准**（现状纪律不变）。`confidence` 列 **#04 已预留**（`annotation/migrations.py:79` `confidence REAL -- 预留，阶段一恒 NULL`，同表还有 evidence/annotator_id 预留列）——**不需要加列、也不需要迁移**；每 region 的 confidence 以 JSON 为准，DB 行不做聚合（防"落盘数值无来源"）。

**DB 行的承载边界（R5 钉死，防 codex 试插后撞 CHECK）**：① DB 行的 `region_ids` **只含 `op:"add"` region**（只有 add 有 label 归属）；**`op:"uncertain"`/`op:"erase"` region 不落 DB 行、只存在于 JSON**——`annotation` 表有 `CHECK (label_id IS NOT NULL OR label_value IS NOT NULL)`（`annotation/migrations.py:83`），uncertain/erase 无 label，插不进去；审计链 = `DB 行 → region_ids → JSON add region`，uncertain/erase 只能从 JSON 侧反查（DB 是摘要不是全量，如实记账）。② DB `source` 列 CHECK 枚举为 `('manual','library','cluster','transfer','model','unmix')`——**不含 `algorithm`**（`migrations.py:77-78`，#04 既有约束不改）。**DB 行 source 恒 `'manual'`，语义重定义为"该行由人工确认（confirm = HITL 动作）落库"**——此属性恒成立，无需发明枚举映射；**不采用 `algorithm→cluster` 之类有损映射**：映射对应关系无出处（违反八查⑤.5），且每 label 一行是聚合粒度，一个 label 混合 manual+algorithm region 时"行的 source"无法由 region 确定性导出。region 级真实溯源（含 algorithm）只在 JSON；混合溯源 DB 粒度无法承载是**如实记账的已知有损**。**审计以快照内 JSON 为权威，DB annotation 行 = 指针 + 计数摘要**（不选"DB 保持 superpixels 现状、审计只认 JSON"：空几何列表比指针更糟）。

---

## 4. 改动清单（逐文件，不要扩大范围）

### Python（sidecar）

| 文件 | 动作 | 内容 |
|---|---|---|
| `backend/paths.py` | 改 | 新增 `exports` property + `create_directories` 同步 |
| `spectrumagent/agent/migrations.py` | 新增 | §3 **七张**新表 DDL + 幂等 `migrate(db)`（照抄 `annotation/migrations.py` 模式：DDL 字符串 split 逐条执行 + 种子播种 llm_settings 空值；禁 `INSERT OR REPLACE`）；接线点 = `api/registry.py:87` `DatasetRegistry.__init__` 内现有 `migrate(db)` 调用处（:14 是 import 行，别找错）；**新 DDL 注释禁含 ASCII 分号 `;`**——迁移实现按 `DDL.split(";")`（`annotation/migrations.py:109`）按 ASCII 分号切语句，注释里一个 ASCII 分号就把语句切碎成语法错误（全角"；"不触发，但也别用） |
| `spectrumagent/agent/__init__.py` | 新增 | 包 |
| `spectrumagent/agent/llm.py` | 新增 | `LLMClient` 抽象 + OpenAI 兼容 httpx 实现 + 禁运扫描 + mock transport |
| `spectrumagent/agent/state.py` | 新增 | 五态三分支状态机 |
| `spectrumagent/agent/tools/__init__.py` | 新增 | 工具注册（Pydantic 入参 schema + handler） |
| `spectrumagent/agent/tools/annotations.py` | 新增 | draft_get / draft_add_region / draft_select_candidates / draft_confirm |
| `spectrumagent/agent/tools/preprocess.py` | 新增 | 包 #05 run/compare schema |
| `spectrumagent/agent/tools/training_mat.py` | 新增 | export 工具 |
| `spectrumagent/agent/skill.py` | 新增 | skill_version 播种/激活/只增不改 |
| `spectrumagent/agent/mat.py` | 新增 | MAT 生成（有界读 + memmap 临时 + savemat） |
| `spectrumagent/agent/raster.py` | 新增 | 栅格化纯函数：polygon 分支**调用** `annotations.polygon_mask`（R19），pixel_set RLE 展开，overlap 检测；v1 函数冻结永不删 |
| `spectrumagent/annotation/session.py` | 改 | ① save 路径四件套（+`annotation.json`，`_write_snapshot` :322 扩展，`read_version` :351 同步）；② confirm 入口挂 MAT 生成；③ `_state()` :153 初始化改 JSON 派生（§2.4）；④ `edit()`/`undo()` 双轨回滚（§2.4）；⑤ 确认时 classes 一致性校验（§2.4） |
| `spectrumagent/api/agent.py` | 新增 | `POST /api/v1/agent/sessions`、`POST /api/v1/agent/sessions/{id}/messages`（SSE）、`GET /api/v1/agent/sessions/{id}/steps` |
| `spectrumagent/api/settings.py` | 新增 | `GET/PUT /api/v1/settings/llm`（PUT 禁收 key；**GET 响应加 `has_key: bool`**——§10-1 定稿：不新增端点、不回显 key，重启后 false 但配置仍在）；`PUT /api/v1/settings/llm/key`（仅内存） |
| `spectrumagent/api/annotations.py` | 改 | ① draft **六个** REST 端点（GET draft / POST regions / POST candidates / **POST** regions/{id} / POST confirm / GET training-mat，契约见 §4.1）；② **既有三个写端点（`/datasets/{id}/annotations/regions|undo|save`）改 draft 驱动**——Rust 九 operation 与前端零改动，详见 §4.2 |
| `spectrumagent/app.py` | 改 | 挂三个新 router |

### Rust（src-tauri）

| 文件 | 动作 | 内容 |
|---|---|---|
| `src/main.rs` | 改 | `generate_handler!` 增加 3 个 forward 命令（备卡裁定：`agent_forward` / `settings_forward` / `annotations_draft_forward`——按 4.6 forward 基建复用度可收敛，禁止超出 3 个） |
| `src/*.rs`（forward 实现） | 新增/改 | 复用 4.6 模式：身份先于状态/正文校验、路由白名单、8MiB 限额、无代理/重定向 |
| `src-tauri/permissions/autogenerated/` | 重新生成 | 新命令 capability |

### 前端（src/）

| 文件 | 动作 | 内容 |
|---|---|---|
| `src/components/assistant/` | 新增 | 常驻对话条最简组件（S01）：输入框 + SSE 消费 + 工具执行摘要气泡 + HUMAN_CHECK 确认卡片 |
| `src/components/annotation/`（既有 S05 画布页） | 改 | confirm 确认卡片显示 `estimated_mat_bytes`、**超 2GB 弹二次确认**（§10-2 定稿；两条 confirm 路径——REST 与 LLM→HUMAN_CHECK——的确认卡片均在前端渲染，闸放前端一处覆盖两者；2GB 阈值来源=§10-2 决策记录，非实现期手填） |
| 既有页面布局 | 改 | 对话条常驻底部（最小侵入，禁改既有页面结构——补丁自洽） |

### 测试（与实现同子阶段提交，禁后补）

- `src-python/tests/agent/`：llm 网关（mock transport）/ 状态机三分支 / skill 只增不改 / 工具 schema 几何禁入扫描 / 6 条 mock 回归探针
- `src-python/tests/annotation/`：draft CRUD + 原子写 + schema 拒绝；栅格化用例（凹多边形、孔洞、跨行 RLE、跨类重叠）；互锁 bit-exact；四件套断言更新
- `src-python/tests/mat/`：内容断言（DN 原料 / labels≥0 / rows-cols / source_dtype / wavelengths 两形态 / 元数据）/ UNIQUE 重建 / 峰值内存 / exports 禁作计算输入
- `src-tauri/tests/`：3 个 forward 命令白名单与限额（对齐 4.6 测试模式）
- `src/**/*.test.ts`：对话条 SSE 消费与 HUMAN_CHECK 卡片

### 4.1 接口契约（draft 六端点，codex 据此开工；错误码对齐 #04/#05 DataError 风格）

> **路径前缀说明（R4）**：新端点挂 `/api/v1/annotations/{cube_id}/draft/...`，与 #04 legacy `/api/v1/datasets/{id}/annotations/...` **故意不同**——新前缀走新 `annotations_draft_forward` 命令白名单（只有 POST/GET 两种方法），物理上不可能误触 legacy 九路由审计面；legacy 路由一字不改（`annotation.rs:287` "Keep the nine audited dataset routes" 注释纪律）。

| 端点 | body | 响应 | 错误码 |
|---|---|---|---|
| `GET /api/v1/annotations/{cube_id}/draft` | — | `{cube_id, revision, document, schema_version, raster_rule_version, updated_at, estimated_mat_bytes}`；无草稿返回 `document=null, revision=0, estimated_mat_bytes=0`（**REST 响应含完整 document 给前端画布；回灌 LLM 的 `draft_get` 摘要只含标量** `{cube_id, revision, n_regions, n_classes, updated_at, estimated_mat_bytes}`——出参白名单见 §2.3，document 含全部 region 几何、LLM 不感知几何）。**`estimated_mat_bytes` = `count(label_map>=0) × n_bands × 4`**（§10-2 定稿：GET draft 内对该 document 做一次栅格化后计数，rasterize 纯函数无 IO；前端打开画布即拿到，confirm 确认卡片显示、超 2GB 弹二次确认——体积必须点在确认**前**拿到，写进 confirm 响应已晚） | `DATASET_NOT_FOUND`(404) |
| `POST /api/v1/annotations/{cube_id}/draft/regions` | `{revision, op?（默认 add）, class_code, geometry:{type:"polygon",points} 或 gesture_ref, confidence?}`（**无 `source` 字段**——服务端强制 manual、不接受传值，body 出现即隐性矛盾，R5 删；`op=uncertain/erase` 时禁传 `class_code`/`confidence`） | `{revision, region_id, statistics}` | `TOOL_ARGS_INVALID`(400) / `DRAFT_REVISION_CONFLICT`(409) / `LABEL_NOT_FOUND`(400) |
| `POST /api/v1/annotations/{cube_id}/draft/candidates` | `{class_code, method, params}`（method=SLIC/谱扩散，params 对齐 #04 SuperpixelRequest/DiffuseRequest） | `{revision, region_id, geometry_type:"pixel_set", preview_statistics}` | `TOOL_ARGS_INVALID`(400) / `SUPERPIXELS_REQUIRED`(400) / `DRAFT_REVISION_CONFLICT`(409) |
| `POST /api/v1/annotations/{cube_id}/draft/regions/{region_id}` | `{revision, ...patch 字段}`（**patch 白名单：`class_code` / `geometry` / `confidence` / `deleted`**；`region_id`/`created_at`/`source` 不可改——source 是溯源，改了就是血缘造假） | `{revision, region_id}` | `REGION_NOT_FOUND`(404) / `DRAFT_REVISION_CONFLICT`(409) / `TOOL_ARGS_INVALID`(400) |
| `POST /api/v1/annotations/{cube_id}/draft/confirm` | `{revision, overwrite?, note?}` | `{version_id, version_no, snapshot_ref, training_mat_id?, overlap_conflicts:0}`（`training_mat_id` **可空**：MAT 失败时 `null` + `mat_error`，见补充约定） | `DRAFT_REVISION_CONFLICT`(409) / `OVERLAP_UNRESOLVED`(409，**带冲突计数+位置**，见补充约定) / `LABEL_INDEX_MISMATCH`(400) |
| `GET /api/v1/annotations/{cube_id}/versions/{version_id}/training-mat` | — | `application/octet-stream`，`Content-Disposition: attachment; filename="training_mat.mat"`（对齐 #05 `sample_spectra.npz` 下载先例 `preprocess.rs:305`） | `VERSION_NOT_FOUND`(404) / `MAT_NOT_FOUND`(404) |

**端点补充约定**：

- **删 region**：走 **POST** `{revision, deleted: true}`（R4：与 legacy 面统一只用 POST/GET 两种方法——`annotation.rs:288-301` 九个 operation 方法硬编码只有 POST/GET，:287 注释明说保持不动，不为删一个 region 引入第三种 HTTP 方法；且"六端点"在 POST 下才自洽，POST+PATCH 同路径会算成七个）——写入时从 `regions` 数组物理移除（document 整篇重写，无软删状态）。**必须有删除入口**：否则用户误画一个大区压住别的类时，除了改 class 别无他法，confirm 将永久停在 `OVERLAP_UNRESOLVED`。
- **`source` 强制规则（防伪造溯源）**：画布路径（POST regions 的 polygon）`source` 服务端强制 `"manual"`、**不接受客户端传值**；算法路径（POST candidates）强制 `"algorithm"`。`confidence` 默认：manual → `high`、algorithm → `medium`（阶段一不做置信度分档——分档阈值又成"落盘数值无来源"）；**`op=uncertain/erase` 的 region 无 `confidence` 字段**（禁传，传了 `TOOL_ARGS_INVALID`）。
- **`class_code` → `class_index` 转换**：服务端按项目 label 表（sort_order 升序，R15）解析，客户端禁传 index；解析不到 → `LABEL_NOT_FOUND`(400)。
- **confirm 的原子边界 = 四件套提交**：MAT 失败**不回滚已确认版本**，响应 `training_mat_id=null` + `mat_error=<原因>`，走 §2.5 手动重建入口补生成（MAT 是可重算导出物，版本才是权威）。
- **`OVERLAP_UNRESOLVED` 必须带位置（R6）**：**REST 409 响应** context = `{conflict_count, sample_pixels, bbox}`——`sample_pixels` 为 conflict 像素按 **(row,col) 字典序前 20 个**（确定性选取规则，禁随机抽样），`bbox` 为 `{min_row, min_col, max_row, max_col}`；对齐 #04 DataError context 先例（如 `FILE_NOT_FOUND` 带 path）。理由：conflict 图栅格化时已算出，返回位置近零成本；只返回计数会让用户“知道有冲突但找不到、修不了”，HITL 流程卡死。**回灌边界（R7）**：同一错误经 §2.2 INTERPRET 回灌 LLM 时**只给 `conflict_count` + 纯文字提示**（“存在 N 处跨类重叠，请在画布上处理”）；`sample_pixels`/`bbox` 只进 REST 响应体给前端，不进 messages（§2.3 出参白名单——坐标数组不出域，红线 4）。
- **几何禁入对 REST 同样生效**：`draft/regions` 的 polygon 来自画布采集、`candidates` 来自算法；REST 层与工具层共用同一 schema（`geometry` 仅 `polygon`/`gesture_ref` 两种合法入参，禁自由坐标数组透传——`gesture_ref` 为服务端会话内引用）。
- 所有写端点带 `revision` 做 CAS；冲突一律 409 让客户端重取，**禁服务端合并**。
- confirm 走 HITL：`overwrite=true` 或已有版本时要求显式确认（对齐 #04 `AnnotationConflict` 语义）。

### 4.2 既有三个写端点的 draft 驱动改造（#04 兼容，Rust/前端零改动，R4 新增）

**背景（P0-B，三轮复核中最重要的发现）**：#06 画布全部经 `annotations_forward` 九 operation 调用（前端 `src/components/annotation/api.ts` 零 URL 直连，`regions/undo/save` 均在其中）。若三个写 handler 仍直改内存 label_map，则 confirm 时：走 JSON 栅格化 → **画布刚画的多边形丢失**；走内存 label_map → 快照内 `annotation.json` 与 `label_map.npz` 不一致 → **bit-exact 互锁必败**。两条路都坏，且是必然而非偶然。故三个 handler 内部全部改为 draft 驱动：

| 既有端点 | 现状（2026-10-23 实测） | 改为 |
|---|---|---|
| `POST /datasets/{id}/annotations/regions` | `sessions.edit(mask)` 只改内存 label_map（`api/annotations.py:195-200`） | **先写 draft JSON**（按下方 action 映射表）→ 栅格化 → 更新工作态 label_map；工作态始终是 JSON 的派生 |
| `POST /datasets/{id}/annotations/undo` | `sessions.undo()` 弹内存整图副本（:202-205） | 与 §2.4 同一 **(document_json, label_map) 成对双回滚**路径 |
| `POST /datasets/{id}/annotations/save` | `sessions.save()` 写三件套（:216-220，`_write_snapshot` :322-332） | **= confirm 的内部实现，但不生成 MAT**：draft 栅格化 → 四件套 + version 行 + aggregates/quality（现状逻辑不变）；confirm = save + MAT + HITL |

**action → region 映射表**（legacy `AnnotationRegionRequest` = `{label_id, geometry: Superpixels|Polygon, action: confirm|erase|uncertain}`；Rust 契约冻结，**无 source/params 字段**，本卡不改 Rust）：

| legacy action + geometry | draft region（R5：action→op 恒等，不再翻译） |
|---|---|
| confirm + polygon | `op:"add"`：`class_index` ← `label_id` 按项目 label 表 sort_order 解析（R15），geometry = polygon 顶点**原样**，`source="manual"`（服务端强制），`confidence="high"`（默认） |
| confirm + superpixels | `op:"add"`：class_index 同上，geometry = `pixel_set`（RLE，由 `segments ∩ ids` 掩码生成）+ `segments_fingerprint` ← 当前分割参数（`state.params`），source/confidence 同上 |
| uncertain | `op:"uncertain"`：geometry 两种形态同上，`source="manual"`，**禁带 class_index/confidence**（R5 依据：#04 `session.py:207-208` 的 uncertain 分支根本不校验 `label_id`——`AnnotationRegionRequest.label_id` 可空（`annotations.py:72`），强行解析必 400；且"给不出类"携带 class_index 语义矛盾） |
| erase（polygon 或 superpixels） | `op:"erase"`：geometry 两种形态同上，`source="manual"`，**禁带 class_index/confidence** |

**溯源口径（钉死）**：legacy 路径 `source` 恒 `"manual"`——legacy 入口不携带扩散/算法参数（#04 Rust 契约无此字段），无法区分"画布点选超像素"与"扩散候选确认"；算法候选的完整溯源请走新 `draft/candidates` 路径（source 强制 `"algorithm"` + params 入参）。DB `annotation.source` 恒 `'manual'` 与此一致（§3）。

**旧版兼容**：`read_version` 对 #07 之前的三件套快照（无 `annotation.json`）返回 `document=None`，旧版本回放不回归；四件套断言只约束 #07 之后新保存的版本（区分新旧快照的粒度，不是弱化断言）。

**无 draft 时的 save**：按空 document 处理（`regions: []`，classes 按确认时 label 表刷新）——与现状全 -1 工作态行为一致。

**save 后 draft 保持活草稿**（可继续编辑、可再次确认为新版本）——与 #04 "save 不清工作态"语义一致；"版本恢复为草稿"仍不做（§1.2）。

---

## 5. 开发任务（子阶段，一次只开一个；每子阶段独立可验）

| 子阶段 | 内容 | 出口条件 |
|---|---|---|
| **12.1** | LLM 网关：`llm.py` + `llm_settings` + `llm_call` + 禁运扫描 + mock transport | mock 全链路通；禁运/超时/usage 缺失三态有测试 |
| **12.2** | SKILL 契约：`skill_version` + 播种 + 激活 + 工具注册框架 + 几何禁入 schema 规范 | 初始 skill v1 播种；schema 扫描测试过；无 active 拒建会话 |
| **12.3** | 状态机 + `agent_session`/`agent_step` + CLARIFY/HUMAN_CHECK/ERROR + SSE 端点 | 三分支测试过；step 全落库含 rejected |
| **12.4** | 6 条 mock 回归探针 + 前端常驻对话条（S01 最简） | 探针全过（不烧 token）；node/tsc 过 |
| **12.5** | 标注 JSON：**第一件事先写 rasterize 不变量测试（实现前落盘，R6 测试先行）**：① 幂等（同一 JSON 两次栅格化逐像素相同）；② `-2` 存在性——**同一像素先 `add` 后 `uncertain` 覆盖，最终必须 -2 而非 -1**（R7：这是“从 owner 派生 label_map”实现的专用回归锚——纯 uncertain 场景该实现靠特判也能过、测不出来；erase 无法用最终值测，-1 与无覆盖同值，其正确性靠 JSON 记录审计）；③ polygon 分支与 `polygon_mask` 逐像素一致；④ regions 数组重排后结果允许变（顺序敏感是已知属性，**不做“交换律”断言**，如实记录）；再写 `annotation_draft` + schema + draft REST + 栅格化纯函数 + 互锁测试 + **既有 regions/undo 端点 draft 驱动**（§4.2 映射表） | 四条不变量测试先行落盘（②须为混合序列锚）+ draft CRUD + 原子写 + bit-exact 互锁 + **legacy action→region 映射（含 erase/uncertain）过测** |
| **12.6** | confirm 四件套 + overlap 仲裁 HITL + 训练 MAT（exports + DDL + savemat 流式）+ **save = confirm 内部实现（四件套、无 MAT）** | confirm→四件套→MAT 全链过；旧三件套断言已同步；**legacy save 四件套 / 不产 MAT / #07 前旧版回放兼容过测** |
| **12.7** | 集成 + 验收清单 + 性能实测（MAT 生成耗时/体积、对话端到端延迟）+ 冒烟归科祥 | §6 全绿；本机冒烟（云端 key 由科祥填） |

**A/B 拆分决定（§10-6 定稿，原为选项）**：12.1–12.4 = **里程碑 A = v0.2.0**（编排地基，约 7.5 工作日）；12.5–12.7 = **里程碑 B = v0.3.0**（标注 JSON + MAT，约 5.5 工作日）。各自**独立过闸、独立 tag、独立 manifest 行**——B 卡住时 A 已可交付冒烟，拆分的意义才成立；压成一个 v0.2.0 则 B 卡 A 也发不出。B 不依赖 A 的工具层可独立验收（REST 直调），但 confirm 的 HITL 语义与 A 的 HUMAN_CHECK 同源——若拆，B 先用 REST 确认、A 完成后把 confirm 接入状态机（补一条集成测试）。

---

## 6. 验收标准（逐条可验；自报测试数必须带执行模式，复核一律默认参数复跑）

**G1 网关**
- [ ] mock transport 下完整链路：消息 → tool_call → Pydantic 校验 → 执行 → 溯源 → 解读 → SSE 流式返回
- [ ] 禁运字段：payload 含盘符/反斜杠/路径形态/`.img|.hdr|.mat` 文件名 → `EGRESS_BLOCKED`；mock 断言 transport 零调用；`llm_call.status='blocked'`
- [ ] API key 禁落盘：设 key 后跑全流程，转储 sqlite + 扫 logs/artifacts/exports，**零命中 key 字符串**
- [ ] usage 缺失（本地模型形态）→ tokens 记 `NULL`，禁 0 禁估算（断言）
- [ ] 换模型 = 改 `llm_settings` 三键 + 内存 key，代码零改动：同一 mock 序列换 base_url/model 断言行为逐字节一致
- [ ] **`has_key` 状态（§10-1 定稿）**：`GET /settings/llm` 响应含 `has_key: bool` 且**任何响应/日志/DB 路径不回显 key 本体**；设 key 后 true；**重启后 `has_key=false` 但 `base_url/model` 等配置仍在**（内存 key 与 db 配置分离，两边都验）
- [ ] 传输超时 → `LLM_TRANSPORT` → ERROR → IDLE；无静默重试（断言重试计数 ≤1 且经显式分支）

**G2 状态机**
- [ ] 参数缺失 → CLARIFY 反问，**禁取默认值**（断言未执行工具）
- [ ] 覆写标注/删除数据 → HUMAN_CHECK，确认前工具零执行
- [ ] 单消息 tool_call 按序执行；第 9 个被拒 `TOOL_SEQUENCE_LIMIT`
- [ ] 每步落 `agent_step`（含 digest）；被 schema 拒的调用也落（`status='rejected'`，`arguments_json` 为 `{"_raw_sha256","_raw_truncated"}` 截断 ≤4KB，禁为空禁塞原文）
- [ ] tool_call 落地前过 Pydantic 校验（拒调用不进 handler——断言 handler 调用次数）

**G3 SKILL**
- [ ] `skill_version` 只增不改：内容 `UPDATE` 一律拒绝；状态迁移仅 `draft→active` / `draft→retired` / `active→retired`（retired 终态）；`activate` 遇已有 active 失败（禁自动替换）；`switch` 同事务原子（旧 retired + 新 active，禁零/双 active 中间态）；active 全局唯一（并发激活第二个失败）
- [ ] 会话快照 `skill_version_id`；skill 退役后老会话回放不受影响
- [ ] 工具 schema 静态扫描：`tools_json` 无 `points|coords|polygon|spectra|values|bands` 类字段
- [ ] LLM 传坐标数组 → `TOOL_ARGS_INVALID` + step rejected（mock 回放）
- [ ] 6 条 mock 回归探针全过（§2.3 列举），**不产生任何真实网络调用**
- [ ] 初始 skill v1 三字段（system_prompt/tools_json/examples_json）与 §2.3 规格逐条对应（验收时人工对读）

**G5/G6 标注 JSON**
- [ ] draft CRUD：创建/读/加 region/改 region/删 region（`deleted:true`）；JSON Schema 校验不过 → 拒绝且不落盘
- [ ] 并发编辑：10 次并发写 → **成功数 + `DRAFT_REVISION_CONFLICT`(409) 数 = 10，且 revision 单调递增**（原"无半篇 JSON"断言在 DB TEXT 存储下永真，已换）
- [ ] **revision CAS**：带旧 revision 写 → `DRAFT_REVISION_CONFLICT`(409)；不带 revision 写 → 400（禁隐式 last-write-wins）；UPDATE 必须 `revision+1`，禁 `INSERT OR REPLACE`/`ON CONFLICT DO UPDATE`（断言：同 revision 重放第二次必 409）
- [ ] **patch 白名单**：`class_code/geometry/confidence/deleted` 可改；改 `source`/`region_id`/`created_at` → 400（血缘不可伪造）
- [ ] **source 强制**：画布路径（#04 legacy `regions` 端点与新 `draft/regions`）region 的 `source` 恒为 `"manual"`（客户端传别的值被忽略/拒）；算法路径（`draft/candidates`）恒为 `"algorithm"`
- [ ] 栅格化用例：凹多边形、带孔多边形、跨行 RLE、pixel_set 与 polygon 混合、同类重叠合并
- [ ] **on_edge 口径**：构造边界用例（顶点落在像素中心/边上），断言栅格化与 `polygon_mask()` 输出逐像素一致（防重写扫描线）
- [ ] 跨类重叠：检出 `overlap_conflicts>0` 时 confirm 被拒（409 `OVERLAP_UNRESOLVED` 带计数+位置：`sample_pixels` 前 20 + `bbox`）；删掉冲突 region 后可确认（删除入口可达性）
- [ ] **rasterize 不变量四条（12.5 测试先行，R6/R7）**：① 幂等（同 JSON 两次栅格化逐像素相同）；② `-2` 存在性（**混合序列锚**：同像素先 add 后 uncertain 覆盖必须 -2、不得退化 -1——owner 图不得参与 label_map 赋值；纯 uncertain 场景测不出该 bug）；③ polygon 分支与 `polygon_mask` 逐像素一致；④ regions 数组重排后结果允许变（顺序敏感如实记录，不做交换律断言）
- [ ] **互锁**：快照内**规范化副本** `annotation.json` 栅格化结果与 `label_map.npz` **逐像素 bit-exact**（草稿原文未被改动）
- [ ] **v1 栅格化函数保留**：跨代码版本升级后，同一确认版 JSON 重放仍 bit-exact（冻结函数回归测试）
- [ ] **工作态 JSON 派生**：有 draft 的 cube 打开工作台 → label_map 与 JSON 栅格化一致（非全 -1）；重启（重取 state）后仍一致
- [ ] **undo 双回滚**：编辑→撤销→JSON 与 label_map 同时回到前态（断言 document 与 label_map 成对）
- [ ] 四件套：快照目录断言同步为四件套（旧断言已更新未弱化）；#04 既有标注回放测试不回归
- [ ] **legacy 路径 draft 驱动**（§4.2）：经 `annotations_forward`（op=regions/undo/save）编辑后，draft JSON 含对应 region/erase 记录；重开工作台（`_state` 重新派生）label_map 与 JSON 栅格化一致——**画布新画不丢、bit-exact 不破**
- [ ] **legacy save = confirm 内部实现**：产出四件套（#07 后新版本）、**不生成 MAT**（exports 无新文件、`training_mat` 无新行）；#07 前三件套旧版本 `read_version` 回放返回 `document=None` 不回归
- [ ] **三值 op 语义**：`add` → class_index（必填 class_code + confidence∈{high,medium,low}）；`uncertain` → -2（禁带 class/confidence）；`erase` → -1（禁带 class/confidence）；三态与 #04 action 一一对应；`uncertain`/`erase` region 不落 DB 行（§3 承载边界）
- [ ] **重叠冲突 = 最终状态统计（R5 防死锁）**：add A + add B 重叠 100 像素 → `overlap_conflicts=100`、confirm 拒；**追加 erase region 擦掉重叠部分 → conflicts=0、confirm 放行**（先 add 后 erase 同像素 → -1，后写覆盖先写）；uncertain 覆盖重叠部分同样解锁（该像素 -2 不计入）；删 region / 改类 / erase / uncertain 四种 HITL 修法均须实测可解锁
- [ ] -1/-2 语义：`uncertain` region → -2；无记录 → -1（构造用例断言）
- [ ] 类 index 与 `label_index.json` 一致（禁第二套下标）；**classes 一致性**：index 错位 → confirm 拒 `LABEL_INDEX_MISMATCH`；code/name/color 刷新不拒
- [ ] **预计体积前置（§10-2 定稿）**：`GET /draft` 响应 `estimated_mat_bytes` = `count(label_map>=0) × n_bands × 4`（构造用例手算对拍，含空草稿=0、部分标注、全图标注三态）；前端 confirm 确认卡片显示该值、**超 2GB 弹二次确认**（12.4 验收）；`draft_get` 回灌摘要带该标量（探针 ⑦ 顺带断言 messages 含体积数字、且仍不含几何）

**G7 训练 MAT**
- [ ] confirm 即生成：`training_mat` 一行 + 文件存在 + sha256 与记录一致
- [ ] 内容断言：spectra 与 `readable(raw=True)` 逐元素相等（**DN 原料，未经 B01**）；labels 仅 ≥0；wavelengths 有/无两形态；元数据字段齐全（含 `dtype_note="raw_dn_pre_b01"`）
- [ ] **labels/label_index 语义**：构造"只标了 index 0 和 3"的用例 → MAT labels 中只有 {0,3}（不重映射），`label_index` = 项目全表快照；`n_classes` = 全表条目数
- [ ] **rows/cols 轴序**：与 label_map 同轴序 0-based（断言 rows/cols 反查 label_map 值 = labels）
- [ ] **source_dtype**：取实际读取数组 `dtype.str`（含字节序，如 `'<u2'`）；uint16 源断言转 float32 无损
- [ ] **confirm 失败语义**：MAT 生成失败 → 版本已确认（四件套在）、响应 `training_mat_id=null` + `mat_error`；手动重建后 `training_mat` 行出现（无半份登记）
- [ ] **禁作计算输入**：preprocess run 全链路不读 exports 目录（路径探针/monkeypatch 断言）
- [ ] 重建：删旧文件+删旧行+重生成，UNIQUE 不冲突；临时目录 `finally` 清理（失败路径也验）
- [ ] 有界：大 label_map 下生成峰值内存 O(B)（记录实测；mock 大图可过）
- [ ] MAT 大小/耗时记入 12.7 性能记录（参照 #05 实测 0.31–0.63s/配方全图 pass；>30s 回来重议，不预留异步分支）

**全局**
- [ ] 回归全绿：`cd <仓库根> && .venv/Scripts/python.exe -m pytest backend/tests src-python/tests`（基线 681 + 新增）；`cargo test`（58 + 新增）；`node --test`（74 + 新增）；`tsc --noEmit` exit 0；clippy `-D warnings`
- [ ] 禁运扫描对**所有**出域 payload 生效（含 system prompt 里的路径泄露——扫描 messages 全体）；扫描规则含坐标数组形态（`[[` 嵌套数组）
- [ ] **工具出参白名单（R7）**：mock 探针（§2.3 探针 ⑦）跑 `draft_confirm` 冲突场景与 `draft_get`，断言回灌 LLM 的 messages 序列化文本**不含 `[[` 坐标数组形态**、不含 `points|polygon|sample_pixels|bbox|document` 字段名；`sample_pixels`/`bbox` 只出现在 REST 响应（前端可达、LLM 不可达）
- [ ] 审计脚本重跑（4.6 边界脚本）通过：新 forward 命令未扩大攻击面

---

## 7. 红线（违反任何一条即打回）

1. **LLM 只编排不产数值**（总红线）：所有数值来自确定性算子/服务端统计；LLM 输出只做意图与参数传递。
2. **几何/谱值禁入 LLM 工具入参**：schema 层强制（无字段可传），不靠 prompt 叮嘱。
3. **tool_call 落地前必过 Pydantic 校验**：拒调用不进 handler。
4. **禁运字段不过不发**（FR-A13）：路径/文件名/坐标数组不出域；网络零发出可断言。
5. **API key 禁落任何盘**：db/日志/产物/转储都不行；仅进程内存。
6. **label_map 是下游计算的唯一权威几何**：预处理/训练/统计的唯一几何输入是 `label_map`（含从 `annotation_version.snapshot_ref` 读的冻结快照）；**草稿态工作态由 JSON 栅格化派生属编辑面内部转换，不构成下游计算输入**（JSON→label_map bit-exact 是这条转换的正确性保证）；MAT 永不作任何计算输入。
7. **MAT 原料态**：禁把任何预处理产物烤进 MAT；禁设压缩/替代格式。
8. **SKILL / 会话 / 步骤记录只增不改**（状态迁移除外）。
9. **标注前置于预处理不回退**（v2.5 定版）：confirm 是预处理的输入前提。
10. **不预置厂商、不硬编码 key、不造默认 skill**：一切配置与种子数据有显式来源。
11. **栅格化 polygon 分支只许调用 `polygon_mask`（R19），禁止重写扫描线**：重写必坏 on_edge 口径与 bit-exact 互锁；v1 栅格化函数冻结永不删。
12. **草稿并发编辑禁 last-write-wins**：`revision` CAS，冲突 409 让客户端重取，禁服务端静默合并。

---

## 8. 排期（估时，供排期参考；实际以 codex 实测为准）

| 子阶段 | 估时 |
|---|---|
| 12.1 网关 | 2 天 |
| 12.2 SKILL + 工具框架 | 2 天 |
| 12.3 状态机 + SSE | 1.5 天 |
| 12.4 回归探针 + 前端对话条 | 2 天 |
| 12.5 标注 JSON | 2 天 |
| 12.6 confirm + MAT | 2 天 |
| 12.7 集成验收 + 冒烟 | 1.5 天 |
| **合计** | **约 13 工作日**（A 7.5 = v0.2.0 / B 5.5 = v0.3.0，拆两里程碑已定稿） |

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 云端 LLM 工具调用遵循度因厂商而异（参数严守/多步稳定） | 换模型后行为漂移 | mock 回归探针先过；真实冒烟归科祥本机；换模型先过探针再切 |
| keyring 包未锁定，key 只能内存持有 | 重启重填，体验差 | §10-1 拍板；内存方案零依赖、零泄露面 |
| MAT 体积 n×B×4B（如 100 万像素 × 200 波段 ≈ 800MB） | 磁盘/传输压力 | exports 可重算可清理（FR-A08）；阈值策略 §10-2；下载走既有 forward 限额通道 |
| pixel_set RLE 大区域 JSON 膨胀 | draft 读写变慢；**GET draft 可能顶穿 8MiB forward 限额**（n_segments=5000 时 RLE 可达 MB 级） | draft 大小记入 12.7 性能记录；超限需分页或 RLE 预览截断（记入风险，不禁生成） |
| S01 对话条是首个对话组件，易蔓延成"重做前端" | 范围失控 | 最简实现清单钉死（§4 前端）；禁改既有页面结构 |
| 3 个新 forward 命令扩大 IPC 攻击面 | 安全回退 | 复用 4.6 基建（身份/白名单/限额/无代理）；审计脚本重跑 |
| confirm 同时写四件套 + MAT，失败中途状态不一致 | 半份产物 | 失败不登记半份（对齐 #05 failed 纪律）：**快照目录（四件套）与 MAT 文件**同一"先临时后 rename、finally 清理"协议；draft 是 DB TEXT 列、无文件临时态（§2.4） |

## 10. 决策记录（七项定稿，2026-10-23；依据复核方终审建议值，拍板后转 codex）

1. **API key 存储 = (b) 内存持有 + 状态显示（定稿）**：key 仅 sidecar 进程内存持有（模块级容器，不写 db/日志/产物），重启失效重填；零新增依赖（keyring 路线不采纳）。落地：`GET /api/v1/settings/llm` 响应加 `has_key: bool`（**不新增端点**、不回显 key）——§4 `settings.py` 契约同步；§6 加验收“重启后 `has_key=false`、配置（base_url/model 等）仍在”。
2. **MAT 大小策略 = 确认前显示预计体积 + 超 2GB 二次确认（定稿；落地方式经复核修正）**：体积必须在**用户点确认之前**拿到——“确认卡在 confirm 前、响应在 confirm 后”，写在 confirm 响应里已经晚了（文件都写完了）。落地：**`GET /api/v1/annotations/{cube_id}/draft` 响应加 `estimated_mat_bytes`**（§4.1）= `count(label_map>=0) × n_bands × 4`（GET draft 内对该 cube 的 document 做一次栅格化后计数；rasterize 是 §2.4 纯函数、无 IO，对比 MAT 生成的全图 IO 可忽略）。前端打开画布即拿到，confirm 确认卡片显示该值、超 2GB 弹二次确认；两条 confirm 路径（REST / LLM→HUMAN_CHECK）的确认卡片均在前端渲染，**闸放前端一处覆盖两者**；后端不设硬阈值（这是 UX 二次确认门，不是配额门）。**连带好处**：该字段是标量，`draft_get` 回灌 LLM 时可带（符合 §2.3 白名单），LLM 能在对话里主动提醒“此标注导出约 1.8GB”——这才是 LLM 真正有用的地方，比它去猜几何强。
3. **冒烟云端 = DeepSeek（定稿）**：key 由科祥本机填入，双方均不经手落盘；§2.1 httpx 直连（不经 Rust forward）；换模型只改 `llm_settings` 三键 + 内存 key。
4. **tool_call 上限 N=8（定稿）**：口径 = 单条 LLM 响应的 tool_calls 数（非整会话步数），超出拒第 9 个并 `TOOL_SEQUENCE_LIMIT`。
5. **草稿不要中间历史（定稿）**：只确认版冻结；§1.2:60 已有条款。硬理由：history 表与 `revision` CAS 会打架（历史条目也需 CAS，否则回滚又出现 last-write-wins）。
6. **拆 A/B 两个里程碑（定稿）+ 版本号**：§5“拆分选项”改“决定”——12.1–12.4 = **里程碑 A = v0.2.0**（编排地基，用户可感知的“能对话编排”）；12.5–12.7 = **里程碑 B = v0.3.0**（标注 JSON + MAT）。各自**独立过闸、独立 tag、独立 manifest 行**——B 卡住时 A 已可交付冒烟，拆分的意义才成立；别把 A+B 压成一个 v0.2.0（那样 B 卡则 A 也发不出）。拆分的真正理由不变：**12.5 改 `session.py` 工作态语义是全卡最高风险点**，与 LLM 网关混编，bit-exact 挂了分不清是栅格化问题还是 mock 序列问题。
7. **draft_get 引用可达性 = 维持留 12.2（定稿）**：解法方向已记录（摘要加 `regions:[{id,class_code,op,pixel_count}]` 限量 N 条 + `truncated`，全符合白名单）；纸面推演已到顶，由 codex 在 12.2 写工具清单撞上“draft_get 到底返回什么”时的实测反馈定，本卡不预决。

## 11. 开工状态

- **§10 七项已定稿（2026-10-23），可转 codex**；一次只开一个子阶段；每子阶段出口条件过闸才开下一个。
- **里程碑切分（§10-6 定稿）**：A = 12.1–12.4 → 过闸后 tag **v0.2.0**；B = 12.5–12.7 → 过闸后 tag **v0.3.0**；各自独立 manifest 行。**版本号唯一来源 = `src-tauri/tauri.conf.json` 的 `version`**（现为 0.1.3；`build_release.ps1:6` 从它取，产物目录/安装包名/build-inputs 全用）——发布 A 时先把它改 `0.2.0` 再打包打 tag，B 同理改 `0.3.0`；漏改则产物目录是 `0.1.3-<stamp>`，与 tag 和 manifest 行全部错位。
- 提交纪律：逐文件 `git add`，禁 `-A`/`.`；本卡落盘后**立即提交入库**（教训：TASK-06 卡曾长期未入库、P1-2 记账的教训在 R7 收尾时原样重演——TASK-06/07 两卡直到 2026-10-23 才补入库；此后改版仍遵守“落盘即入库”）。
- **转 codex 时的两条硬提醒**：① 12.5 第一件事**不是写实现**，是先落盘 rasterize 四条不变量测试（§5:378），其中“同一像素先 add 后 uncertain 必须 -2”是防“从 owner 派生 label_map”坏实现的唯一有效锚；② §10 第 7 项（draft_get 引用可达性）留给 codex 在 12.2 提问时定，不要现在替它决定。
- 冒烟（真实 LLM、安装包）归科祥本机执行。

## 12. 修订记录

| 轮次 | 日期 | 内容 |
|---|---|---|
| 定稿 | 2026-10-23 | §10 七项拍板定稿（依据复核方终审建议值）：① key 内存持有 + `GET /settings/llm` 加 `has_key: bool`（不新增端点）；② **预计体积落地方式修正**——原写“confirm 确认卡/响应需带预计体积”混淆了确认前/后（确认卡在 confirm 前、响应在 confirm 后，体积必须点在确认前拿到），改落 **`GET /draft` 响应 `estimated_mat_bytes`**（`count(label_map>=0)×n_bands×4`，纯函数栅格化计数无 IO），前端 confirm 卡片显示 + 超 2GB 二次确认（两路径闸在前端一处）；标量故 `draft_get` 回灌可带、LLM 可对话提醒体积；③ DeepSeek；④ N=8 维持；⑤ 不要历史（§1.2 已有条款）；⑥ **拆 A/B 定稿 + 版本号 A=v0.2.0 / B=v0.3.0** 独立过闸/tag/manifest；⑦ 引用可达性维持留 12.2。联动：§2.3 回灌摘要、§4 settings 契约与前端表、§4.1 GET draft、§5 拆分决定、§8 排期、§6 两项新验收、§11 开工状态。**§11 追加（同日复核 P1）**：版本号唯一来源提醒——`src-tauri/tauri.conf.json` 的 `version`（现 0.1.3，`build_release.ps1:6` 从它取），发布 A/B 前先改再打 tag，防产物目录与 tag/manifest 错位 |
| 勘误 | 2026-10-23 | 12.1 开工时 codex“首触即停”报两处规格冲突，均属实（卡自身不一致，非实现问题），裁定并改卡：① **`llm_call` 补 `total_tokens INTEGER`**（可空，无 usage 记 NULL，禁由 prompt+completion 派生）——§2.1 ChatResult.usage 定义三字段而 §3 DDL 只有两列，向 §2.1 对齐；移交 prompt 的“usage 三字段落库”因此成立；② **删 `session_id` 注释里的 `system:` 前缀**——status 维持 `ok|blocked|transport_error|http_error` 四值枚举，系统级调用仅以 `session_id=NULL` 标识（前缀会破坏枚举等值查询）。两处均为 DDL 注释/列级勘误，不动任何已定稿口径 |
| R1 | 2026-10-23 | 初稿：范围 G1–G7；网关/状态机/SKILL/标注 JSON/MAT 五项口径钉死；DDL + NOT NULL 写路径覆盖；子阶段 12.1–12.7；验收/红线/排期/风险/待确认。依据：2026-10-22/23 两轮讨论 + D 域摘要 + 定稿 v1.1 + #04/#05/#06 实现事实 |
| R2 | 2026-10-23 | 独立复核修订（复核方逐条实测代码后采纳七条 + 三项补充）：① 新增 §0 背景与动机（实测：手画多边形顶点现存 100% 丢失——`PolygonGeometry` api/annotations.py:67 收顶点、`polygon_mask` :83-96 R19 口径、但 `session.py:197 edit()` 只收布尔掩码、`_aggregate_rows` :334-349 只写 superpixels）；② §2.4 栅格化 polygon 分支**必须调用 `polygon_mask`（R19：像素中心+even-odd+`inside|on_edge`），禁重写**；③ §2.4 `_state()` 初始化改 JSON 派生（现状 session.py:159 `np.full(-1)`）；④ §2.4 undo 改 (document_json, label_map) 成对回滚（现状 :134/211/224 只回滚位图）；⑤ §3 `annotation_draft` 加 `revision` + CAS 409；⑥ §4.1 补 draft 六端点接口契约表；⑦ §2.4 classes 一致性校验（index 错位拒 confirm）；⑧ §2.5 MAT 加 `rows`/`cols`/`source_dtype` + 同步生成性能门（>30s 改异步 pending）；⑨ §0.3 记录"草稿态跑不了预处理"为已知限制；⑩ v1 栅格化函数永不删除 |
| R3 | 2026-10-23 | 第二轮复核修订（十项，全部实测核实后采纳）：① 红线 6 限定"下游计算"口径（JSON 派生工作态属编辑面内部转换，消除与 §2.4 的自相矛盾）；② §4 "四个端点"→"六个（见 §4.1）"；③ `training_mat` 删 `status`/pending 死分支——量化依据：milestone05/evidence/11.7/performance.md 实测 #05 单配方全图 pass 落库 0.31–0.63s（已含全图 IO，`BoundedInput.lines()` 每行块全图读），MAT 增量预计 2–10s，距 30s 门 6–15 倍余量，对齐 #05 "未触发、维持同步"处置，>30s 回来重议；④ revision CAS 补三条规则（INSERT revision=1 / UPDATE 必须 revision+1 / 禁 OR REPLACE 与 ON CONFLICT DO UPDATE——否则 CAS 反向失效）；⑤ §4.1 补删 region（PATCH `deleted:true`，解除 OVERLAP_UNRESOLVED 死锁）+ patch 白名单（source 不可改，血缘防伪造）+ source 强制规则（manual/algorithm，不接受客户端传值）+ confidence 默认 + class_code→index 服务端解析 + confirm 原子边界=四件套（MAT 失败不回滚版本，training_mat_id=null+mat_error）；⑥ §2.5 钉死 labels 保留项目原始 index（不重映射）+ label_index 全表快照 + n_classes=全表条目数 + rows/cols 与 label_map 同轴序 0-based + source_dtype 取 `dtype.str`（保留字节序，与 registry `.name` 口径差异已注明，model.py:56 预存在缺口不在本卡范围）；⑦ §2.4 "临时文件+rename"改 DB 事务措辞（DB TEXT 列无文件临时态）+ 确认版 annotation.json 定为规范化副本（classes 刷新、regions 原样、草稿原文不动）；⑧ rejected 路径 arguments_json 供值（_raw_sha256+_raw_truncated ≤4KB）；⑨ §1.2 加"版本恢复为草稿：不做"；⑩ §9 风险表补 8MiB forward 限额；⑪ §6 换掉永真断言（并发 10 次=成功+409，revision 单调递增） |
| R4 | 2026-10-23 | 第三轮复核修订（六项，逐条实测核实后采纳；其中 P1-3 的"confidence 无列"经核实不属实——`annotation/migrations.py:79` 已有预留列，改按"指针+摘要"方案落）：① **P0-A 方法统一 POST**：§4:277 与 §4.1:316 的 PATCH→POST（依据 `annotation.rs:288-301` 九 operation 方法硬编码只有 POST/GET、:287 注释保持不动、:579 测试断言方法；"六端点"在 POST 下自洽）；② **P0-B 新增 §4.2**——既有 regions/undo/save 三 handler 改 draft 驱动（Rust/前端零改动）：regions→先写 JSON 再栅格化、undo→双回滚同路径、**save=confirm 内部实现但不生成 MAT**；补 action→region 映射表（含 **erase → `op:"erase"` region**，R4 设计的显式减法语义：栅格化置 -1、不参与跨类冲突检测、无 class/confidence 字段）、legacy source 恒 manual 的溯源口径、#07 前三件套旧快照 read_version 返回 document=None 兼容、无 draft 时 save 按空 document、save 后 draft 保持活草稿；③ §4:263 "六张"→"七张"并修正迁移落点（实际无 backend/migrations.py；按域模式新增 `spectrumagent/agent/migrations.py`，在 `api/registry.py:14` 现有 migrate 调用处接线）；④ §3:224 去 `DEFAULT 1`（八查⑤.6：NOT NULL 列显式供值，不靠默认兜底）；⑤ §3 补 `annotation` 表与 JSON region 关系钉死（geometry 改 `{"region_ids":[...]}` 指针、pixel_count 仍只以 label_map 为准、confidence 预留列不动、DB source CHECK 无 `algorithm` 的已知口径差如实记账、审计以快照 JSON 为权威）；⑥ §4.1:311 `training_mat_id?` 可空 + §9:443 措辞限定"快照目录与 MAT 文件"同一协议。联动：§2.3 工具表 draft_add_region 加 `op` 入参、§2.4 schema/rasterize 补 erase 口径、§5 12.5/12.6 出口条件、§6 补 legacy 三条验收、§10 补录复核方六项拍板意见（含 DeepSeek 代理问题的事实修正：LLM 直连不经 Rust forward） |
| R5 | 2026-10-23 | 第四轮复核修订（两个 P0 + 四条 P1 + 两条 P2，逐条实测核实；触发原因 = R4 引入 `op`/erase 新机制却未重跑不变量检查，两个新 P0 全是漏检）：① **P0-1 冲突统计改最终状态**（原"erase 不参与冲突检测"致 erase 擦不掉重叠 → confirm 死锁，与删 region 之前同型）：栅格化维护 `owner`/`conflict` 两图，`overlap_conflicts = count(conflict & (label_map >= 0))` 是最终统计非累加；erase/uncertain 清除覆盖像素的归属与冲突标记 → 四种 HITL 修法（删/改类/erase/uncertain）都能解锁（§2.4 ③⑤⑥、§6 验收）；② **P0-2 `op` 收敛三值**（add/uncertain/erase，与 #04 action 一一对应）：依据 `annotations.py:72` `label_id` 可空 + `session.py:207-208` uncertain 分支不校验 label_id——R4 版"uncertain=add+confidence:uncertain 带 class_index"会 400 且语义矛盾；`confidence` 枚举删 `uncertain` 值只留 high|medium|low（确定性分档不兼职表达无类别）；③ **P1-1 DB source 不搞有损映射**：复核方建议 `algorithm→cluster` 映射——不采纳（枚举对应关系无出处违八查⑤.5，且每 label 聚合粒度混合多源时行的 source 无法确定性导出）；改为语义重定义"DB 行 source 恒 manual = 该行由人工确认（confirm=HITL）落库"（属性恒成立无需发明）+ 混合溯源是如实记账的有损、审计链 JSON 反查；④ **P1-2 DB 承载边界**：`region_ids` 只含 add region；**uncertain/erase 不落 DB 行只存 JSON**（`annotation` 表 CHECK label_id/label_value 至少其一非空，`migrations.py:83`——复核方写的 :87 是 registry.py migrate 调用行，又一处行号错）；⑤ **P1-3 迁移接线点 :87**（R4 写的 :14 是 import 行，实测 `DatasetRegistry.__init__` 内 :87）；⑥ **P1-4 新 DDL 注释禁 ASCII 分号**（迁移实现 `DDL.split(";")` 按 ASCII 分切，`migrations.py:109`；卡内 DDL 自查无 ASCII 分号于注释）；⑦ **P2**：§4.1 draft/regions body 删 `source`（服务端强制不接受传值，body 出现即隐性矛盾）改带 `op?`；§3:230 document_json 注释统一"单条 UPDATE 事务内原子" |
| R6 | 2026-10-23 | 第五轮复核修订（1 P0 + 2 P1，全是给 R5 新增机制补语义定义、未新增字段/图/端点；触发原因仍是不变量重查——R5 引入 owner/conflict 两图却未查“图与 label_map 的关系”）：① **P0-新 label_map 赋值路径钉死并行维护**：R5 只写“维护 owner/conflict 两图”，未说 label_map 是否由 owner 派生——若实现成“先算 owner 最终归属再从 owner 生成 label_map”，uncertain 的 -2 与 erase 的 -1 都表现为 owner 空、无法区分 → **-2 全部退化成 -1 → bit-exact 当场失败**。改为：**label_map 与 owner/conflict 并行维护、互不派生**，label_map 每像素由最后一个覆盖 region 的 op 直接决定（add→class_index / uncertain→-2 / erase→-1，不经 owner 图）；owner/conflict 仅用于冲突统计；“维护”改“**每次从零构建**”（document 整篇重写，禁增量缓存诱导）；② **P1-新1 conflict 清除条件补全**：conflict 一旦置位**仅 erase/uncertain 可清除**，重复 add（同类或不同类）均不清除、用户需先擦后画（写明否则前端以为“重画盖住”能解冲突）；③ **P1-新2 OVERLAP_UNRESOLVED 409 必须带位置**：context = `{conflict_count, sample_pixels（(row,col) 字典序前 20，确定性）, bbox}`——只返回计数会让用户“知道有冲突但找不到、修不了”；④ **测试先行兜底（方法论转变）**：12.5 第一件事先写 rasterize 不变量测试四条（幂等 / -2 存在性 / polygon 分支与 polygon_mask 逐像素一致 / regions 重排结果允许变即顺序敏感如实记录不做交换律断言），纸上穷举不变量有天花板，属性测试兜底“还没想到的不变量” |
| R7 | 2026-10-23 | 第六轮复核修订（三条，全部属**同一数据流边界族**——R6 新增 `sample_pixels`/`bbox` 响应字段经 §2.2 INTERPRET 回灌 LLM 撞红线 4；**判据细化：新增响应字段也算新增机制**，R6“未新增字段”的自我声明因此不准确，终止判据从“新增字段/图/端点”扩为“新增任何机制含响应字段”）：① **工具出参白名单**（§2.3 新增整段）：INTERPRET 回灌 LLM 的 `result_summary` 只允许标量+枚举+计数字符串，`sample_pixels`/`bbox`/region 几何/`document` 原文/`[[int,int],...]` 坐标数组一律剔除；冲突给 LLM 只有 `conflict_count`+纯文字提示；位置数据只走 REST 给前端；`draft_get` 回灌摘要 = `{cube_id, revision, n_regions, n_classes, updated_at}` 全标量。工程保障：出参侧构造断言 + 回归探针 ⑦（messages 序列化文本不含 `[[`、不含 `points|polygon|sample_pixels|bbox`——禁运扫描只查路径形态看不见坐标，扫描是兜底、白名单是主防线）；② **禁运扫描补坐标数组形态**（§2.1：`[[` 嵌套数组形态入扫描规则，作兜底）；③ **12.5 -2 测试改混合序列锚**（§5/§6：同像素先 add 后 uncertain 必须 -2——纯 uncertain 场景“从 owner 派生”实现靠特判也能过、测不出，断言会空转）。联动：§4.1 GET draft 行区分 REST/回灌、OVERLAP_UNRESOLVED 回灌边界、§6 新增出参白名单验收项。**同族末遍扫描结论：无残留**——全卡几何/坐标 56 处逐条过，只四类（JSON schema/DDL 存储面、REST 前端面、显式禁令、栅格化纯函数），`examples_json` 种子措辞不含几何示例、`draft_get` 描述已标回灌边界。**停止条件达成：R7 三条全属数据流边界族、无新族问题，此后停止改卡，新发现归入 12.5 不变量测试兜底**。**收尾追加（同日，复核方终审确认九处全部到位 + 独立扫描无残留后）**：§10 新增第 7 项——"引用可达性"边界（`draft_get` 回灌摘要不含任何 region_id，跨轮对话的改/删在 LLM 侧不可达；解法方向 = 摘要加 `regions:[{id,class_code,op,pixel_count}]` 限量+truncated，全符合白名单；**不现在改卡，留 12.2 由 codex 实测反馈时定**）；§11 补转 codex 两条硬提醒（12.5 先落不变量测试再写实现；§10-7 不替 codex 预决） |
| R8 | 2026-10-23 | 12.2 开工时 codex"首触即停"报两处**卡自身不闭合**（未改一码即停，纪律按设计生效），裁定并改卡：① **状态迁移集不闭合**——:95 仅允许 `draft→active/retired`，:96"切换 = 新版本 active、旧 retired"却要求 `active→retired`。裁定：迁移集补 `active→retired`、retired 终态；激活拆两个操作——`activate(v)` 仅 draft→active 且**遇已有 active 失败**（禁自动替换防误切换），`switch(v)` = 同一事务内旧 active→retired + 新 draft→active 原子切换（"切换"语义落地，禁零/双 active 中间态）；② **种子正文缺口**——:110 要求"配方对比话术"与 examples_json 但全文无正文来源（examples_json 仅 4 处提及字段本身、指标名 SNR/Fisher 卡内零出现）。裁定：`system_prompt` 落**定稿正文**（逐条对应 :110 原要点枚举+"禁取默认值"§6:400+S05 五步原名，codex 照抄禁改一字，验收人工对读）；"配方对比"原只有标签无正文，**备卡方代拟一句**（成分 = :110 mandated 主题 + 红线4 算子·版本 + 工具表 preprocess.compare :103；科祥可单独拍板替换，不影响其余定稿）；`examples_json` = **`[]`**（八查⑤.5 显式留空，禁实现期自行编写，将来随 skill v2 只增不改进入）。联动：§3:219 DDL 注释、§6:407 验收行同步；均不动任何已定稿口径 |
