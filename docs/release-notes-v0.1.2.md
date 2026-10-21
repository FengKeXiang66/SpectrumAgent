# v0.1.2 release notes

阶段一 L1 标注交付，发布操作待科祥执行。产品版本为 0.1.2，sidecar 握手兼容版本仍为 0.1.0。验收记录见 `milestone04/evidence/10.7/acceptance-map.md`；尚未打 tag、推送或创建 Release，安装包签名、干净机与实机 UI 冒烟仍待负责人执行。

## 标注能力（TASK-04 10.1–10.6）

- 项目与结构化标签存储、塑料目录、快捷键校验；标签可从目录添加、自定义，或登记 schema 字段。
- 分块 IncrementalPCA 与 SLIC 超像素、原谱高方差细分；compactness 经真实数据标定，响应回报实际参数、特征图字节数和进程峰值内存。原始立方体不全量物化。
- 单击、框选、涂鸦提示及原谱邻接对余弦扩散，只产生候选区域，由用户确认标签。候选队列按种子参照相似度设置独立入队护栏；不自动赋标。
- 内存工作态支持确认、不确定、擦除、撤销与队列恢复；参数变更按像素保留标注并清空候选。
- 保存版本生成 label map、标签映射和每类均值/标准差快照，按 label 聚合样本谱；默认新建版本，显式确认才覆写最新版本，保留首次创建时间并登记备注事件。
- 质量校验使用当前工作态原谱均值，报告可疑区域、高方差块与三分完整度。“标签与聚类中心冲突、类间重叠”在无模型阶段不适用；合成标注标定仅验证阈值行为。
- FastAPI 标注路由与受限 `annotations_forward` IPC 在 dev/release 双分支注册；路径、方法、身份和响应体大小受约束。R21 补齐项目、标签与塑料目录通道。
- S05 工作台提供标签管理、画布提示与人工编辑、候选队列、快捷键和版本保存；工作态与撤销栈由 sidecar 维护。预计剩余时间仅本地估算。底部全局对话条保留。

默认参数与出处：扩散阈值 0.92 来自需求场景 S1 示例，队列护栏 0.80 来自 UI 原型 S05 脚注，均为可调默认值；超像素 compactness=0.5 来自 10.2 的 11 cube / 55 格标定。质量余弦默认阈值及合成标定分布见 `milestone04/evidence/10.3/quality-calibration.json`（实现层默认、可调）。

## R14 跨里程碑错误契约

- R14 跨里程碑修正：#02 的 preview、band、region 对“数据集已登记，但源文件移动、缺失或不可用”的错误码，由读取器原始码（如 FILE_NOT_FOUND）统一改为 SOURCE_CHANGED；HTTP 状态仍为 400。响应 context 保留 source_error、source_detail 和读取器原 path。
- 包装仅发生在 Registry.readable 的 read_header 调用处。未知数据集仍返回 DATASET_NOT_FOUND（404）；导入期路径错误仍为 FILE_NOT_FOUND；info 仅查询登记记录，行为不变。
- #04 superpixels 共用该规则，包括命中引擎缓存后对源文件的重新验证。

依据：TASK-04 §6.4、§12 R14（2026-10-20）。

## 发布前缓测

签名/SmartScreen、干净机、长路径、重启以及实际桌面 UI 冒烟由科祥执行。自动化 HTTP 集成与逻辑层测试不能替代这些项目；详见 10.7 验收映射。

## 光谱预处理（TASK-05）

- B01 反射率三分支算子及 guard/NaN 记录；run 前置读取原始 DN，当前支持 scale/passthrough，白/暗参考文件解析仍缓建，不重复除 scale。B02 SG 平滑、B03 按 band index 的一/二阶导数，窗口/阶数校验；B04 SNV、显式参考谱 MSC/EMSC 算子。S06 不开放 MSC/EMSC，参考来源选择留阶段二。
- B05 StandardScaler/MinMax/面积/L2 四法，fit-on-apply 参数与输入指纹随 run 记录；B06 闭区间裁剪、线性/样条重采样、越界 NaN 以及相邻间隔中位数 FWHM **代理值**提示。波长轴与谱条数契约随流水线传递。
- B07 全局配方库、只增版本、项目只读选用关联；内置 `plastic-snv-sg1` 为 SNV→SG一阶（order1/window15/polyorder2），B01 为数据集特定前置步、不入配方。取消选用仅删除关联，不删除配方。
- B08 PCA/MNF/ICA 确定性降维与最小分量占比展示，random_state 与载荷定向可复现；ICA 的重构能量口径明确标注为非 PCA 方差分解。B09 上凸包/端点线性连续统去除；不等同像素去背景或 ROI 筛选。
- B10 对比作用于标注快照选中的**逐像素 B01 反射率**，不读取历史 sample_spectrum 聚合谱代替；报告逐像素 SNR 四统计量、类间距离、类内方差和 Fisher 主排序。数值公式/噪声估计为 TASK-05 §2.5/§2.6 的实现层口径；显式披露三边界：SNR 跨算子类型不可比，零方差/单样本类排除 Fisher 且不加 epsilon，类间原值不可跨配方比较。未标注仅 SNR并标注局限，LLM不参与数值计算或选优。
- 十二个 FastAPI 操作与第七条受限 IPC 命令 `preprocess_forward` 在 dev/release 注册。固定loopback/握手端口、类型化目的地、UUID、身份头、代次、8MiB及token护栏；预处理同步请求超时300s。报告通过IPC仍为解析后的JSON，样本谱NPZ才使用base64二进制包装。
- S06 提供合法算子链与当前轴维护、配方保存/新版本/项目选用、真实终态run、前后类均值曲线与Fisher对比。曲线在最终执行遍有界采集，拟合遍不污染；每类≤512点确定性等距索引抽样，null断线。传输超时后通过runs摘要及新run详情核对真实状态，并保留手动恢复入口。坏波段剔除、去背景/仅ROI、历史Kappa、每步预览标注阶段二/不适用。

关键错误契约：`OPERATOR_VERSION_STALE`（409，仅声明的 name@version 不存在）、`INVALID_OPERATOR_PARAMS`（400，字段级信息）、`NORMALIZATION_DEGENERATE`（400）、`SOURCE_CHANGED`（400，已登记源变化）。IPC 对非法标识返回 `INVALID_DATASET_ID` / `INVALID_RUN_ID` / `INVALID_RECIPE_ID` / `INVALID_PROJECT_ID` 结构化信封；`ARTIFACT_TOO_LARGE`、`RESPONSE_TOO_LARGE`、`SENSITIVE_RESPONSE` 与 `STALE_RESPONSE` 保持各自边界，不以传输中断推断服务端run失败。

11.7 真实 pe HTTP 全链路、真实 Rust parse_request/forward 探针、逐像素对比性能和全量回归证据位于 `milestone05/evidence/11.7/`。标注区域为脚本集成夹具，不代表人工标注质量；Rust探针不冒充完整WebView invoke。单次本机性能不是跨机承诺，30s采样议题与R13异步议题分别判定，默认参数未调整。

实机UI冒烟、签名/SmartScreen、干净机、长路径与重启仍待科祥执行，见 `milestone05/evidence/11.7/smoke-checklist.md`。安装包最终commit/hash和发布归档待科祥构建后回填 `docs/release_manifest.md`；本阶段不改manifest、不打tag、不push、不创建Release。

## 0.1.2 冻结资源打包修复

修复旧冻结配置仅收集rasterio数据、遗漏spectrumagent包内JSON的问题；缺失plastic.json会在数据库迁移阶段导致sidecar退出，尚未发布就绪握手。当前统一入口为 `scripts/build_release.ps1`（见 `docs/BUILD.md`），使用新的 `scripts/backend.spec` 收集当前包内数据并核对所有JSON的源码哈希。安装包封装前后均实际启动冻结后端，验证身份、标签/目录与真实pe的标注和预处理链路；自检失败即停止，保留旧资源与旧安装包。源码测试不再作为冻结包启动通过的替代证据。产品版本0.1.2与握手兼容版本0.1.0保持不变；此修复未改业务数值或源数据。

## S05 画布显示（TASK-06）

preview 的默认映射有意由全量程 min/max 改为 `stretch=auto` 的有限值联合2/98分位映射。`stretch=none` 保留旧min/max与uint8截断，单波段继续用原png_gray编码，支持旧调用方按需保持旧显示。接口默认 `size=preview` 保留，S05 显式请求 `size=full`。显示参数不进入标注工作态或数据库，不改变 regions/undo/save/validate 语义。
