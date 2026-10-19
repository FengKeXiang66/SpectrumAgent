# 里程碑 #02：数据接入（Data Ingestion）

**任务卡编号**：TASK-02-数据接入  
**前置里程碑**：#01 地基演示（已封账）  
**定稿日期**：2026-10-19（基于当日探针实测）  
**能力断言背书**：venv `spectral` 0.25 实测通过（标准 ENVI）+ 边界矩阵构造测试通过（三种非标准场景）

---

## 1. 目标

实现 SpectrumAgent 对高光谱数据文件的读取能力，支持：
- **P0**：标准 ENVI 格式（`.hdr` + `.img`/`.raw`/`.bin`）— 用 `spectral` 库
- **P0**：纯二进制 + 独立头文件（`.bin` + `.json`/`.txt`）— 自研解析器（numpy memmap）
- **P1**：非标准 ENVI 边界 case（缺 interleave、ENVI5 JSON、头声明 vs 实际大小不符）— 自研兜底

血缘链位置：数据接入 → 标注(L1) → 预处理 → PLS/指标 → 入库 → 检索 → Agent

---

## 2. 采集端样本集（已确认）

**来源**：科祥提供 `E:\高光谱数据集\plastic\`
- 三个子目录：`pe/`（聚乙烯）、`pet/`（聚对苯二甲酸乙二醇酯）、`pp/`（聚丙烯）
- 格式：**标准 ENVI**，`.hdr` + `.img`
- 规格一致：640×231×200 像素，BIL 交错，data type=12（uint16），小端序，offset=0
- 波段范围：881.85–1714.13 nm（近红外）
- reflectance scale factor = 65535
- 文件大小验证：59,136,000 B = 640×231×200×2 ✅

**spectral 实测结果**：`envi.open_image()` 成功，shape=(231,640,200)，类型 `BilFile`，`read_band()` 返回 (231,640)，值域 0.0–1.0（已除 scale factor）。

**2026-10-19 全量复核（11/11 通过）**：open 1.7–7ms、read_band ≤37ms；read_band / read_pixel / read_subregion 返回值与 numpy memmap 直读的 DN/65535 逐值相等；BIL memmap 布局为 (lines=231, bands=200, samples=640)。

---

## 3. 能力断言（基于 2026-10-19 探针实测）

| 断言 | 实测结果 | 对 #02 的影响 |
|---|---|---|
| spectral 0.25 可读标准 ENVI（BSQ/BIL/BIP） | ✅ 通过（塑料数据集验证） | 标准格式全由 spectral 覆盖，自研解析器只兜底 |
| spectral 缺 interleave 字段 | ❌ 不支持，报 MissingEnviHeaderParameter | 自研解析器必须实现默认 interleave 策略 |
| spectral 支持 ENVI 5 JSON 头 | ❌ 不支持，报 FileNotAnEnviHeader | 自研解析器必须覆盖 JSON 头解析 |
| spectral 校验头声明 vs 实际文件大小 | ❌ 不校验，静默忽略多余字节 | 自研解析器必须实现大小校验，发现即报 |
| spectral 读数精度分层（2026-10-19 实数勘误） | `read_band`/`read_bands` → **float64**（已除 scale factor）；`load()` → **float32**（已除）；`asarray()` → **uint16 原始 DN memmap**（未除，逻辑索引 (lines,samples,bands)，与 numpy memmap 直读逐值相等） | raw=True 直接用 `img.asarray()`，不必自写 memmap；卡片旧文"uint16→float32"作废 |
| spectral 扩展名限制 | ⚠️ 必须给 `.hdr`，直开 `.img` 失败 | API 封装层做 hdr→img 自动关联 |
| spectral shape 约定 | (lines, samples, bands) | 文档写清楚，避免 (samples, lines, bands) 混淆 |

---

## 4. 开发任务（按执行顺序）

### 4.1 数据模型与接口定义（先定 schema，再实现）

定义 `SpectrumDataSet` 数据类（Python，sidecar 层）：
- 字段：`name`, `shape` (L×S×B), `dtype`, `interleave`, `wavelengths` (nm 列表), `fwhm` (可选), `data_path`, `header_path`, `metadata` (dict)
- 方法：`read_band(i)`, `read_pixel(l,s)`, `read_region(l0,l1,s0,s1)`, `to_numpy()`
- 必须支持**延迟加载**（lazy）：大文件不一次全读进内存
- **返回契约（2026-10-19 裁定，codex 4.1 问询答复）**：`to_numpy()` 仅在 raw 模式可用——返回原始 DN 的 np.memmap（uint16、逻辑索引 (lines,samples,bands)、**未除 scale factor**、零拷贝视图）；默认缩放模式下 `to_numpy()` 必须**显式报结构化错误**，禁止隐式分配整个立方体。红线"禁止全量读取"禁的是**隐式全量**，不禁调用方显式 `read_region(全图)`（有界接口、调用方知情）。**不实现懒缩放视图类**（非 ndarray、下游 np.asarray/库调用会静默物化或破裂，契约污染）。缩放读数一律走 read_band / read_bands / read_pixel / read_subregion 等有界接口。验收用例：缩放模式 `to_numpy()` 抛错；raw 模式返回 `isinstance(x, np.memmap)` 且值 == DN 原值。

### 4.2 ENVI 标准格式接入（P0，spectral 封装）

实现 `EnviReader` 类：
- 输入：`.hdr` 路径（自动关联同目录 `.img`/`.raw`/`.dat`）
- 内部：调用 `spectral.open_image()`
- 输出：`SpectrumDataSet` 实例
- **精度策略**：
  - 默认模式：返回 spectral 的缩放 reflectance（read_band/read_bands → float64，load() → float32）
  - `raw=True` 模式：直接用 `img.asarray()`（uint16 memmap，逻辑索引 (lines,samples,bands)，已实测与 numpy memmap 直读逐值相等），返回 DN 原值并显式标注"未除 scale factor=65535"
- API 细节（2026-10-19 真实样本实测）：
  - `envi.open_image()` / `spectral.open_image()` 必须传 `.hdr`（直传 `.img` 报 FileNotAnEnviHeader）；数据文件名与头不一致时用 `envi.open(hdr, image=<数据路径>)`
  - `read_bands([...])` 返回 (lines, samples, n)，**波段在最后一轴**
  - `read_pixel(row, col)` 参数 = (lines 下标, samples 下标)，返回全部波段
  - `read_subregion((r0,r1),(c0,c1))` 返回全波段立方体 (lines, samples, bands)；显式索引用 `read_subimage(rows, cols, bands)`
  - 取值入口：`img.nbands`、`img.metadata['reflectance scale factor']`、`img.bands.centers`；塑料数据 `map_info=None`（无地理参考）
- 异常处理：文件不存在、头格式错误、数据大小不符 → 结构化错误信息（非抛裸异常）

### 4.3 纯二进制 + 独立头文件接入（P0，自研解析器）

实现 `BinaryReader` 类：
- 输入：数据文件路径 + 头文件路径（JSON 或简化 TXT）
- **字段词汇表统一为 ENVI 标准字段名**（域内标准；采集端未来的头文件只可能是 ENVI 衍生），JSON 与 TXT 共用同一套 schema 和同一个键规范化器（键名大小写 / 空格 / 下划线不敏感，brace list 解析与 classic ENVI 路径共享，不写两套）。*（2026-10-19 勘误：卡片原 JSON 示例的 `shape`/`dtype` 词汇作废，以本节为准。）*
- JSON 头 schema（示例）：
  ```json
  {
    "samples": 640,
    "lines": 231,
    "bands": 200,
    "data_type": 12,
    "interleave": "bil",
    "byte_order": 0,
    "header_offset": 0,
    "wavelengths": [881.85, 886.03],
    "scale_factor": 65535,
    "data_file": "sample.bin"
  }
  ```
- 简化 TXT 头语法（UTF-8；`#` 起始为注释行；空行忽略；`key = value` 两侧空白任意；brace list `{a, b, c}` 可跨行，ENVI classic 风格）：
  ```
  # comment
  samples = 640
  lines   = 231
  bands   = 200
  data_type = 12
  interleave = bil
  byte_order = 0
  header_offset = 0
  wavelength = {881.85, 886.03, ...}
  reflectance scale factor = 65535
  data file = sample.bin
  ```
- 规范化与校验规则（TXT/JSON/ENVI5 三路共用）：
  - 必填：`samples`/`lines`/`bands`/`data_type`，任一缺失 → 结构化错误
  - `interleave` 可缺省 → 默认 `bsq` + 警告日志；取值 `bsq`/`bil`/`bip`（大小写不敏感）
  - `data_type`：ENVI 码 1–15（1=uint8/byte、2=int16、3=int32、4=float32、5=float64、12=uint16、13=uint32、14=int64、15=uint64；探针实测 1/2/3/5/12/13 可读）**或**字符串别名（`uint16`/`<u2`/`int16`/`float32` 等）→ 归一为 numpy dtype
  - `byte_order`：`0`/`1` 或 `little`/`big`（不敏感）；`header_offset`：≥0 整数，默认 0
  - `wavelengths`/`fwhm`：数字列表，存在时长度必须 == `bands`，否则结构化错误
  - `scale_factor`：正数，可选；`data_file`：可选，脱离同基名的数据文件名（相对头文件目录解析）
  - 未知键：收入 metadata + 警告，不致命
  - 数据文件解析顺序：显式路径参数 > `data_file` 键 > 同基名候选扩展名（`.bin`/`.raw`/`.dat`/`.img`/`.bsq`/`.bil`/`.bip`/无扩展名）> 结构化错误
  - **大小校验（红线）**：读前比对 `header_offset + samples×lines×bands×itemsize` vs `os.path.getsize(数据文件)`，不符即结构化错误，禁止静默
- 内部：numpy memmap 读数据文件（或经共用 schema 层归一化后由 SpectrumDataSet 管理）
- 输出：`SpectrumDataSet` 实例（接口与 EnviReader 完全一致）
- 单元测试 fixture：JSON 头+.bin（bil/uint16 已知值回读相等）；TXT 头+.bin（bsq/float32）；TXT 含注释 / 跨行 brace list / 空白变体；JSON 字符串 dtype 别名；缺必填键 / 波长长度不符 / 大小不符 → 结构化错误；interleave 缺省 → bsq+警告；`data_file` 脱离命名可解析

### 4.4 非标准 ENVI 边界兜底（P1）

实现 `FallbackEnviReader`：
- 缺 interleave：默认按 BSQ 解析，日志警告（与 4.3 同策略）
- ENVI5 JSON 头：ENVI 5 头文件惯例为 JSON、标准字段集中于顶层 `header` 对象内；解析以此为主路径，**同时容忍同一批键出现在顶层**（防版本漂移，不得因字段位置包裹形式不同而解析失败）。字段名走 4.3 同一规范化器；`data type` 接受 ENVI 数字码或字符串别名；其余顶层键（如 `coordinate system string`）收入 metadata。fixture 需覆盖 header 包裹式与扁平式两种写法，均须读通
- 大小校验：读取前比较 `header声明大小` vs `os.path.getsize(数据文件)`，不符即报（与 4.3 同一校验函数）
- 兜底链：`EnviReader` 失败 → `FallbackEnviReader` → 仍失败 → 报错

### 4.5 FastAPI 端点暴露

sidecar 新增路由：
- `POST /api/v1/datasets/import`（2026-10-19 契约裁定）：
  - 请求体：`{"path": "<文件或目录绝对路径>", "raw": false, "data_path": "<可选，头文件配对用>"}`；`raw` 为该数据集的**默认读模式，随登记落库**
  - 文件与目录**统一响应信封**：`{"datasets": [{"id": "<uuid>", "dataset": { SpectrumDataSet 元数据 }, "existing": false}], "summary": {"total": n, "imported": a, "existing": b}}`
  - 目录递归（深度不限）收集 `.hdr`/`.json`/`.txt` 伴随头，每个能解析出数据文件的头登记为一个数据集；基名冲突用父目录名消歧
  - **整批原子**：先全量解析校验（仅头文件 + 大小校验，不做全量读），任一无效 → HTTP 400，错误体列出**全部**无效项（路径 + 原因），且不登记任何数据集；空目录同样 400 显式报错
  - **幂等**：同一规范化路径 + 同一 raw 模式已登记 → 返回既有 `id`（`existing: true`），不建重复记录
  - 导入 = 登记引用 + 元数据解析：**不复制、不移动、不修改源文件**（源目录只读红线的延续）
- `GET /api/v1/datasets/{id}`：获取已导入数据集信息
- `GET /api/v1/datasets/{id}/preview`：返回缩略图 / 单波段预览（PNG base64）
- `POST /api/v1/datasets/{id}/band/{i}`：读取指定波段数据（JSON 数组，小区域）；band/region 端点支持可选 `raw` 覆盖（默认用数据集登记模式）

**dev 联调入口（2026-10-19 裁定）**：#02 开发期需带新路由的后端做前后端联调，封版 app.exe 不动、本轮禁止重冻/重打包。方案：Rust 侧**仅 `#[cfg(debug_assertions)]` 分支**支持以本机 venv Python 直接启动 sidecar（默认 `E:\AI_Agent\.venv\Scripts\python.exe`，env var 可覆盖，代码内显著标注 dev-only），复用既有握手/端口/Job 监督机制、协议不变；release 构建路径逻辑零变化，不改 tauri.conf.json 的 resources/externalBin 配置、不碰 `resources/backend`；该分支不得向 release 引入任何新依赖。API 模块与单元测试可先于外壳独立完成；dev（venv）与 release（onedir）的运行时差异记为已知开发期差异，由后续打包里程碑在成品上复验。

**dev IPC/ACL 扩展（2026-10-19 裁定）**：datasets 转发需新增命令 `datasets`。边界：① invoke_handler 注册 cfg 双分支，**release 分支保持原 4 命令逐字不变**（以 diff 为证）；② 转发器为固定功能：目标仅 `127.0.0.1:<握手端口>`、路由白名单仅 `/api/v1/datasets/*`、方法白名单 GET/POST、响应大小上限（超限结构化报错）、响应校验 boot_id/pid 防伪；③ ACL 条目（main.json 的 `allow-datasets-forward`）为声明性，**真正的授权边界是 handler 注册**——release 不注册即无从调用；权限文案同步更新，不得顺手放宽其他项；④ release 形态的 datasets IPC 推迟到打包里程碑决定（已记账），本轮 dev-only；⑤ 前端对 `datasets` 的调用统一封装为一个 api client 模块，禁止组件内散落 invoke（可审计）。

### 4.6 前端 UI 适配

- 文件选择器（`@tauri-apps/plugin-dialog` 2.8.3，`open({ directory: true, multiple: true, filters: [...] })`，多选/目录；capability 仅加 `dialog:allow-open`，2026-10-19 批准）
- 导入进度条（大文件读取）
- 数据集列表页（名称、维度、波段范围、缩略图）
- 单波段预览（Canvas 2D 渲染灰度图）

---

## 5. 验收标准（Checklist）

### 5.1 功能验收

- [ ] `EnviReader` 能读塑料数据集全部样本，shape/dtype/wavelengths 正确
- [ ] `EnviReader` 的 `raw=True` 返回 uint16 DN，值域 0–65535
- [ ] `BinaryReader` 能读构造的纯二进制样本（与 ENVI 同一数据，不同头格式）
- [ ] `FallbackEnviReader` 能处理三种边界 case（缺 interleave、JSON 头、大小不符报错）
- [ ] FastAPI 端点返回 JSON schema 稳定（字段名、类型、空值语义不变）
- [ ] 前端能选文件 → 导入 → 列表展示 → 单波段预览，全程无白屏/卡死

### 5.2 性能验收

- [ ] 读取 59MB 数据集（塑料样本）metadata 耗时 ≤ 500ms（只读头）
- [ ] 读取单波段（231×640）耗时 ≤ 100ms
- [ ] 内存占用：懒加载模式下，不触发全量数据读取
- [ ] 并发：同时导入 3 个数据集不阻塞 sidecar

### 5.3 数据正确性验收

- [ ] spectral 读取结果与 numpy memmap 直读结果对比，reflectance 值一致（容差 1e-5）
- [ ] shape 转换正确：spectral (lines,samples,bands) → 前端展示 (samples,lines) 不转置错误
- [ ] 波长列表顺序与波段索引一一对应

### 5.4 异常验收

- [ ] 文件不存在 → HTTP 400 + 结构化错误
- [ ] 头格式损坏 → HTTP 400 + 结构化错误
- [ ] 数据大小不符 → HTTP 400 + 结构化错误（不静默忽略）
- [ ] 超大文件（>2GB）→ 内存不爆炸（验证 memmap 生效）

---

## 6. 交付物

| 交付物 | 位置 | 说明 |
|---|---|---|
| `SpectrumDataSet` 数据模型 | `src-python/spectrumagent/data/` | Pydantic dataclass |
| `EnviReader` / `BinaryReader` / `FallbackEnviReader` | `src-python/spectrumagent/data/readers/` | 解析器实现 |
| FastAPI 路由 | `src-python/spectrumagent/api/datasets.py` | REST 端点 |
| 前端数据集管理页 | `src/components/datasets/` | React + Canvas 2D |
| 单元测试 | `src-python/tests/data/` | 覆盖全部 reader + 边界 case |
| 构造测试样本 | `src-python/tests/fixtures/` | 标准 ENVI + 三种边界 + 纯二进制 |
| API 文档 | 自动从 Pydantic schema 生成 | 供前端对接 |

---

## 7. 依赖与阻塞

| 依赖项 | 状态 | 说明 |
|---|---|---|
| spectral 0.25 | ✅ 已装（venv） | 标准 ENVI 读取 |
| numpy | ✅ 已装 | memmap + 数组操作 |
| Pydantic | ✅ 已装 | 数据模型 + API schema |
| 前端文件选择器 | ⏳ 待实现 | Tauri dialog API |
| 采集端真实样本 | ✅ 已确认 | 塑料数据集，标准 ENVI |

---

## 8. 已知风险

1. **spectral 精度损失**：uint16 → float32 转换中，超过 2²⁴ 的 DN 值会丢精度。塑料数据集 scale factor=65535，最大值 65535 < 2²⁴，安全。但未来若遇到更大 scale factor 或 32-bit 数据，需切换 raw 模式。
2. **大文件内存**：塑料数据集 59MB 较小，未来若遇到 GB 级数据，memmap 是底线，但前端预览生成缩略图时可能仍需全量扫描——需设计采样策略（每 N 行取一点）。
3. **前端渲染性能**：231×640 单波段 = 147k 像素，Canvas 2D 直接渲染无压力。但 200 波段全量预览（伪彩合成）需降采样。

---

## 9. 排期建议

| 阶段 | 内容 | 估算 |
|---|---|---|
| 9.1 | 数据模型 + EnviReader | 1 天 |
| 9.2 | BinaryReader + FallbackEnviReader | 1 天 |
| 9.3 | FastAPI 端点 + 单元测试 | 1 天 |
| 9.4 | 前端 UI（导入 → 列表 → 预览） | 2 天 |
| 9.5 | 集成测试 + 性能调优 | 1 天 |
| **合计** | | **6 工作日** |

（基于 1 人全职，codex 执行速度参考 #01 实际耗时调整）

---

## 10. 红线（不可妥协项）

1. **任何文件读取不得静默失败** — 大小不符、格式错误必须显式报错
2. **大文件必须懒加载** — 不允许 `read()` 全量读进内存
3. **前端不得直接操作文件路径** — 所有文件操作经 Tauri API → sidecar，禁止浏览器端 `fs`
4. **数据模型 schema 必须带 JSON Schema** — 供 LLM Agent 后续步骤理解数据结构

---

**任务卡签发人**：待科祥确认  
**任务卡执行人**：codex（GPT-6.1 Sol）  
**复核人**：科祥（按验收 checklist 逐项确认）
