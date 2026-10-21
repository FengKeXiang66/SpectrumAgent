# 11.7 TASK-05 收官回执

本阶段只新增本目录证据、追加 release notes 与卡§12 R16。产品引擎/路由/Rust/前端/既有测试/依赖/manifest零修改。提交后停等科祥复核，不打tag、不push、不建Release。

## 全量检查与执行模式

| 检查 | passed / failed / skipped（或ignored） | exit | 执行模式 |
|---|---|---|---|
| Python | 621 / 0 / 0 | 0 | 仓库根 `.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`，默认参数，同一PowerShell命令设置 `PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp`；允许清理该E盘临时目录 |
| Rust | 56 / 0 / 0 ignored | 0 | `src-tauri` 目录 `cargo test`，默认并行/default features、含unit/integration/doc；offline、TEMP/TMP在E盘 |
| node | 59 / 0 / 0 | 0 | 科祥指定托管22.22.2 `--test src/components/preprocess/*.test.ts src/components/datasets/*.test.ts src/components/annotation/*.test.ts`，内置runner默认模式 |
| TypeScript | 无诊断 | 0 | 托管Node22.22.2置PATH首位，`npx --no-install tsc --noEmit`，不下载安装 |
| clippy | 零警告 | 0 | `cargo clippy --all-targets -- -D warnings` |
| e2e | 最终完整链路通过 | 0 | 仓库根 `python milestone05/evidence/11.7/e2e.py`；真实首个pe、独立source sidecar、实际loopback HTTP、Bearer及每次响应boot_id/pid校验；真实Rust parse_request/forward探针 |
| 审计 | 七命令/dev-release/ACL/锁文件断言通过 | 0 | `python milestone03/audit_boundary.py`；原断言未修改，原11.5输出字节未变，结果另存本目录boundary.json |

三套测试数与11.6基线逐项相同（621/56/59），既有断言未改。本阶段没有新增到这些套件的单测；新增的是可独立执行的集成及证据核对脚本。Python的10条第三方弃用警告保留原输出，clippy无警告。

## 真实集成结果与口径

真实数据为 `cubes_11.txt` 首行 pe `20260804205214_64.hdr`，231×640×200；3个矩形确认区共18,000像素，标签ID由实际labels接口取PE/PET/PP。**它们是脚本合成集成区域，不代表人工标注质量**。

迁移已有 `plastic-snv-sg1`，按科祥裁定从list取内置v1，另以 `e2e-snv-sg1` 验证POST创建。SG参数仅order=1/window15/polyorder2、mode沿默认interp，不发delta。默认run只发两个版本UUID，不传block_size/guard（实际32/clip）。

已验证：标注保存→内置配方run→同指纹再run→N=3 compare→项目选用/取消且配方/历史不变；两次样本NPZ谱的最大绝对差 **0.0**；7条真实run血缘串到cube/标注版本/快照/配方版本/配方本体，且原#04样本行存在。预检负向：配方含reflectance=400 INVALID_OPERATOR_PARAMS，另一个真实cube使用本cube标注版本=404 VERSION_NOT_FOUND；预检失败不产生半份run。

两类artifact恰为sample_spectra与report：DB行、相对路径、sha256逐项对磁盘和下载内容；下载字节数=磁盘stat。**DB没有size列**，字节数仅在证据记录。report.curves存在，每类before/after与各自轴对齐，输入/输出不混用。源文件与seed内容哈希前后不变。

真实Rust探针链接已发货库并读取独立sidecar的真实握手，调用实际parse_request/forward获取report，返回已解析JSON object且无body_base64。**不冒充完整WebView invoke或supervisor代次实机验证**；后者在Rust既有单测和科祥人工清单分别覆盖。

## 性能双计时与两条触发线

来源/层级：本机实现层、CPU、默认参数、一次集成会话；计时在回归/并行构建之前完成，不构成全图全标注或跨机承诺。软件/线程/盘符信息见performance.json，CPU/架构/内存补取自运行后只读Windows CIM（environment.json），不是性能计数器。

- 单独HTTP run：内置SNV+SG1首轮 **0.587872s**、重跑 **0.579043s**，仅SNV **0.457426s**，StandardScaler **0.776162s**（显示值四舍五入六位，原精度在JSON）。
- 落库生命周期分别约0.430898/0.436152/0.314376/0.632725s，=finished_at-created_at，**从预检后开始，不冒充完整内部耗时**。触发线按HTTP全程判。
- compare N=3 HTTP总 **1.834336s**，逐配方平均成本（总/3） **0.611445s**。单配方控制run与compare内部生命周期分列，不把总/3叫作每个配方的独立HTTP span。
- 进程峰值RSS及两类产物字节数逐run已回报；单独run峰值345,026,560–346,058,752字节，为sidecar自启动累计峰值、含前序SLIC，不是run增量。此次配方无ICA，暂存字节均0；ICA暂存/清理仍由既有单测验证。
- §8风险1（单配方>30s）：**未触发，维持同步**。
- §12 R13（单run>60s或实测compare N>5）：**未触发，维持同步**。

没有调默认参数、采样上限、改用聚合谱或改同步执行来凑结果。

## 技术债结论与缓测

- forward_common：**建议下阶段用共享函数抽取**，不选宏/复杂trait；保留各typed destination/UUID/30s与300s/二进制和204差异，身份/大小/token/代次全量回归；七命令/权限/audit断言不因重构放宽。差异矩阵与方案见technical-debt.md。本阶段未改Rust。
- MSC/EMSC：算子数值与显式参考指纹已验；来源选择流程依R15 D2留阶段二。建议显式选择report.curves.before参考，但必须处理完整轴、512点抽样、有限性与来源指纹，不默认使用当前均值。
- T1摘要缺recipe_version_id：记录现状，前端当前通过get_run逐个核对新succeeded；不回改11.4。
- T2 engines=24.19.0而本次指定验收=托管22.22.2：只记录，不改声明/lock。
- 实机UI、签名/SmartScreen、干净机、长路径、重启与安装卸载由科祥执行，smoke-checklist.md全部待勾选；本回执不声称通过。

卡§5的30项及§5.1的13项全部逐条映射（43项），详见acceptance-map.md。reference文件解析/来源选择按既有授权缓建；≤0.5人日演示是接口局部性自证，不冒充人力耗时实测。

## 失败记录与更正（无静默重试）

初次核对四个接缝待裁定，原回执保留为receipt-blocked.md，已注明科祥后续裁定解除。随后三次集成尝试：

1. 探针rustc找不到spectrum_agent依赖：新脚本的dependency路径误指debug而非debug/deps；sidecar尚未启动。仅改证据构建脚本，attempt-01文件保存失败输出及runtime定位。
2. 整份JSON浮点逐位相等的新断言失败：真实Rust forward返回合法report object，但serde_json解析/重序列化后98个float末位变化，最大绝对差 **2.7755575615628914e-17**。该逐位要求超出开工令的“已解析JSON”契约。保留attempt-02；最终结构/非浮点元数据精确核对，浮点额外复用卡§5的1e-12容差。未改Rust、依赖或任何既有测试；不承诺IPC位级无损。
3. 完整重跑exit0，记录e2e-result.json；重复谱计算差0.0，与JSON传输末位差分别记账。

## 文件逐路径清单

- `TASK-05-预处理.md`：本阶段只追加§12 R16，原313行工作区字节保持不变。开工前已存在科祥/备卡Agent的§5.1 11→10与R15勘误，原样保留，不归因于本阶段自行修卡。
- `docs/release-notes-v0.1.2.md`：追加TASK-05能力、错误码、实现层口径与缓测；release_manifest.md不改。
- `milestone05/evidence/11.7/e2e.py`
- `milestone05/evidence/11.7/ipc_probe.rs`
- `milestone05/evidence/11.7/finalize.py`
- `milestone05/evidence/11.7/e2e-result.json`
- `milestone05/evidence/11.7/e2e-output.txt`
- `milestone05/evidence/11.7/performance.json`
- `milestone05/evidence/11.7/performance.md`
- `milestone05/evidence/11.7/environment.json`
- `milestone05/evidence/11.7/technical-debt.md`
- `milestone05/evidence/11.7/smoke-checklist.md`
- `milestone05/evidence/11.7/acceptance-map.md`
- `milestone05/evidence/11.7/pytest-full.txt`
- `milestone05/evidence/11.7/cargo-test.txt`
- `milestone05/evidence/11.7/node-test.txt`
- `milestone05/evidence/11.7/tsc.txt`
- `milestone05/evidence/11.7/clippy.txt`
- `milestone05/evidence/11.7/audit-output.txt`
- `milestone05/evidence/11.7/boundary.json`
- `milestone05/evidence/11.7/summary.json`
- `milestone05/evidence/11.7/receipt.md`
- `milestone05/evidence/11.7/receipt-blocked.md`
- `milestone05/evidence/11.7/attempt-01-build-result.json`
- `milestone05/evidence/11.7/attempt-01-build-output.txt`
- `milestone05/evidence/11.7/attempt-01-rustc.txt`
- `milestone05/evidence/11.7/attempt-02-json-result.json`
- `milestone05/evidence/11.7/attempt-02-json-output.txt`

提交纪律：以上逐文件add，两个公司文档不入库。seed仍为 `388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`。日志内容保留，仅规范化跟踪副本的冗余末尾空行；原始txt留在`.runtime/m05-11.7/raw-evidence-logs/`。所有本轮工具/日志仅作实现层证据；commit hash由提交后回报，避免在提交内循环自引用。
