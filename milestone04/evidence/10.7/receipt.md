# 10.7 集成 / 验收 / 性能实测回执

## 文件清单（逐路径；根目录 E:/AI_Agent）

- `docs/release-notes-v0.1.2.md`
- `docs/release_manifest.md`
- `milestone04/evidence/10.7/acceptance-map.md`
- `milestone04/evidence/10.7/build.txt`
- `milestone04/evidence/10.7/cargo-release-check.txt`
- `milestone04/evidence/10.7/cargo-test.txt`
- `milestone04/evidence/10.7/clippy.txt`
- `milestone04/evidence/10.7/delivery-check.json`
- `milestone04/evidence/10.7/e2e-harness-missing-import.txt`
- `milestone04/evidence/10.7/e2e-output.txt`
- `milestone04/evidence/10.7/e2e-result.json`
- `milestone04/evidence/10.7/e2e.py`
- `milestone04/evidence/10.7/flake-01.txt`
- `milestone04/evidence/10.7/flake-02.txt`
- `milestone04/evidence/10.7/flake-03.txt`
- `milestone04/evidence/10.7/flake-04.txt`
- `milestone04/evidence/10.7/flake-05.txt`
- `milestone04/evidence/10.7/flake-06.txt`
- `milestone04/evidence/10.7/flake-07.txt`
- `milestone04/evidence/10.7/flake-08.txt`
- `milestone04/evidence/10.7/flake-09.txt`
- `milestone04/evidence/10.7/flake-10.txt`
- `milestone04/evidence/10.7/flake-output.txt`
- `milestone04/evidence/10.7/flake-summary.json`
- `milestone04/evidence/10.7/flake_smoke.py`
- `milestone04/evidence/10.7/machine.json`
- `milestone04/evidence/10.7/node-test.txt`
- `milestone04/evidence/10.7/performance.json`
- `milestone04/evidence/10.7/performance.md`
- `milestone04/evidence/10.7/pytest-full-1.txt`
- `milestone04/evidence/10.7/pytest-full-2.txt`
- `milestone04/evidence/10.7/receipt.md`
- `milestone04/evidence/10.7/release-boundary-output.txt`
- `milestone04/evidence/10.7/release-boundary.json`
- `milestone04/evidence/10.7/release_boundary.py`
- `milestone04/evidence/10.7/summarize.py`
- `milestone04/evidence/seeds_20.json`
- `src-tauri/tauri.conf.json`

本次提交信息：`#04 10.7 集成验收与性能实测收官`。精确 commit hash 在提交后回执给出；本回执与清单内文件同次提交。每次 git add 只指定一个文件路径，不暂存任务卡、公司文档或整个目录。

## 测试数量与执行模式

- Python：仓库根，同一 PowerShell 调用设置 PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp，再 `.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`，默认参数，无筛选/并行。两轮各 **340 passed / 0 failed / 0 skipped**；P1=51.34s，P2=91.45s，各10条既有第三方弃用警告。P2与release编译检查并行，测试总时长不作产品性能数据。
- Flake：既有 `test_db_failure_rolls_back_rows_and_snapshot_publication` 的 False/True 两种参数，各10次；10个新pytest进程串行，每次两用例，**20/20 passed**。无断言改动、无失败后重试/跳过。按本轮门槛结清，未宣称历史根因已定位。
- Rust：`cargo test` 默认并行、无筛选/线程数覆盖，**38 passed / 0 failed**（37普通测试+1compile-fail doctest）；`cargo clippy --all-targets -- -D warnings` 零警告；额外 `cargo check --release` 通过。
- Node：现有本地Node24.19.0，内置runner默认模式，datasets与annotation两组，**31 passed / 0 failed / 0 skipped**；`npm run build`（tsc+vite）通过。
- 集成新增落点：`e2e.py`，真实source sidecar + HTTP，**56次HTTP调用全断言**；导入、空working、分割、三种提示、三种编辑、undo、validate、新建/带note新建/覆写、版本UUID overlay、队列恢复，另独立分块谱与快照oracle。此脚本不加入pytest收集，不虚增340基线用例数。flake_smoke.py仅调既有测试；summarize.py只汇总数据；release_boundary.py只做静态边界审计。

## 对应卡 §6 自验

逐条证据、测试精确名称、执行模式与状态全部列在 `acceptance-map.md`：§6.1每条功能及其超像素/快捷键/队列子断言、§6.2七条、§6.3三条、§6.4五条均有落点。人工可见性与安装环境项单独缓测，没有计为自动化通过。

- §6.1：默认20种子10入队/10拦截/19个min<0.92；入队全部min≥0.80；待确认并集64183像素。confirm/uncertain消费、erase保留、undo、三态、版本递增/覆写及note通过。所有annotation为manual/sample，scene恒0；覆写后旧第三类行和谱键消失。
- §6.2：真实快照逐像素相等；均值/std按原谱反射率独立两遍有界复算，最大绝对误差 1.471045507628332e-14，低于卡1e-10。-2不进聚合；params、pixel_count、geometry与cube→version→spectrum血缘通过；PCA独立复算沿用全量回归与10.2证据。
- §6.3：本次真实pe默认参数，保存含聚合/质量内部总耗时 0.886605–0.924080s，写事务 0.009774–0.012158s；独立validate HTTP 0.904501s；20种子扩散引擎最大 0.033137s、HTTP最大 0.066973s，满足2s候选值。完整指标、边界和10.2历史对照见performance.md/json；均为实现层实测，非固定承诺。
- §6.3内存：特征图 2,956,800 字节，含参照 5,913,600；sidecar峰值RSS 332,951,552、相对基线增量 177,418,240字节。原始float64 cube对照236,544,000字节，有界读数测试同时通过；没有全量物化原始cube。
- §6.4：缺分割错误、R14分类/上下文、UUID版本404、8MiB Rust边界等既有测试全绿；release cfg编译与六命令/ACL/锁文件审计通过。命令仍为engine_status/retry_engine/run_smoke/open_data_directory/datasets_forward/annotations_forward；无额外IPC。

## 问题 / 口径疑问

无未决口径问题，无产品逻辑或验收断言修改。脚本联调曾将Windows venv启动器PID误当服务PID、将health JSON身份误当响应头；均改按既有契约核验。最终核验前误删sqlite3导入导致独立oracle处NameError，已恢复；失败输出保留为e2e-harness-missing-import.txt。最终完整运行输出与结果分别为e2e-output.txt/e2e-result.json，只有最终通过运行用于性能记录。原头文件未识别扩展键的既有warning原样保留，没有掩盖或改读取口径。

种子本次仅入库，SHA256仍为388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2。任务卡SHA256仍为B03AEABDA6603EF2538C0CB135BD07FB4B16AD67CF872BD4F9A88B7DD86E3989；backend/__init__.py握手常量0.1.0未动；依赖声明/锁、既有功能实现未改。源头/数据文件前后hash一致。临时数据在E盘，实际临时token未进入证据、服务日志或响应。

## 就绪声明 / 缓测

10.7代码与自动化证据已就绪，停下等待科祥复核。签名/SmartScreen、干净机、长路径、reboot、#04实机UI冒烟均由科祥执行，详见acceptance-map.md末表。产品tauri.conf版本为0.1.2；manifest的v0.1.2 commit留空，安装包未生成，待tag后由负责人补。未安装依赖、未下载、未打tag/推送/操作Release。
