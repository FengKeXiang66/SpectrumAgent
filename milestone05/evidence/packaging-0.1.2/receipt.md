# 0.1.2 冻结资源修复与重打包

2026-10-21，本机实际构建成功。安装包为 `E:/AI_Agent/artifacts/releases/0.1.2-20261021-151912-073/SpectrumAgent_0.1.2_x64-setup.exe`，297185421 bytes，SHA256 `8004FE7C97F0F344C04649A8A535346B8E8E1BACAE11B1089E2CA12BBE111498`。交付副本与 Tauri 原输出的 SHA256 相同。构建与产品实测基于 `bfa19958e9543b06e37f4061d1e2d261d8911c93` 加本次打包文件；本次三个构建脚本 SHA256 见 summary.json。

## 原因与修复

旧冻结配置只 collect_data_files("rasterio")，遗漏 spectrumagent 自带的数据。用户正式日志 `C:/Users/Administrator/AppData/Local/SpectrumAgent/logs/engine-20261021.jsonl` 三次报 `_internal/spectrumagent/annotation/catalog/plastic.json` 不存在，构造应用时迁移读目录即退出，尚未发布就绪握手。旧批次 build.spec 保留不改，当前入口为 scripts/build_release.ps1 与 scripts/backend.spec：代码收集和包数据收集分别执行；收集 spectrumagent 全部包数据，同时逐项校验当前四个 JSON 的源码哈希。已有 labels.py 的相对 __file__ 读取在正确 onedir 布局下可用，实测通过，无需改业务代码。

目录恢复不能只复制 app.exe。入口先完整冻结、真实启动自检，再保留旧 staged 目录并复制整个 onedir，逐文件字节和 SHA256 对账，随后以 custom-protocol 构建 NSIS。Tauri 资源副本的 1023 个文件与 staging 清单全等；生成 installer.nsi 的四条 File 指令证明 catalog/OpenAPI/两份 schema 都进入安装器输入，见 nsis-package-data.txt。封装后再次启动 release 资源目录实际 app.exe。没有执行安装器或改 E:/test 的现有安装。

## 结果与执行模式

- Python：624 passed、0 failed、0 skipped（原621+新3）；仓库根 `python -m pytest backend/tests src-python/tests -q`，默认参数，同条命令设置 PYTEST_DEBUG_TEMPROOT 到 E 盘，见 pytest-full.txt。十条既有依赖弃用警告保留。
- 新测试：backend/tests/test_packaging_resources.py 中 test_catalog_and_all_schema_json_are_required_frozen_resources / test_missing_catalog_blocks_packaging_before_engine_start / test_stale_or_corrupt_data_is_rejected_and_future_json_is_checked，验证完整资源、缺失拒绝、损坏与未来 JSON 的校验。
- 构建：Tauri beforeBuildCommand 的 `tsc --noEmit && vite build` 通过，Rust custom-protocol release 编译和 NSIS 封装 exit 0，见 tauri-build.txt。无 Rust/前端源码改动，未重复运行其单测；本次没有将以前的测试数字冒充重跑结果。
- 两次冻结自检：独立实际 app.exe，隔离 E 盘数据根和 TEMP，子进程 PATH 仅保留 Windows 目录，不借用开发 Python；逐次核对 bearer/boot_id/pid。四个 JSON 哈希与源码一致，21条目录、四个预置标签、内置配方存在，真实 pe 导入→默认超像素830段→扩散→少量确认→保存→预处理 succeeded，report.curves 存在。标注只是集成夹具，不代表人工质量。源文件前后哈希不变，日志无 token，结束后自己的子进程均已停止。见 frozen-smoke.json / bundled-smoke.json；完整运行日志、隔离DB/快照留在构建批次，未复制握手token入库。
- 边界审计 exit 0，见 boundary.txt。产品/握手版本仍分别为0.1.2/0.1.0；依赖声明、lock、Rust、Python业务实现、前端组件、任务卡和 release_manifest 均未修改。seeds_20.json SHA256 保持 `388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`。

第一轮 `artifacts/releases/0.1.2-20261021-151259-173/` 的冻结、自检、前端和Rust构建均成功；封装时受限沙箱禁止官方构建网络，socket 10013，整体 exit 1。日志与原安装包备份 prior-installer.exe 保留，没有把旧安装包当新产物。第二轮获准使用构建网络后同入口成功；未关闭TLS、未安装依赖、未改默认业务参数。

## 本次文件清单

- scripts/backend.spec
- scripts/build_release.ps1
- scripts/verify_frozen_backend.py
- backend/tests/test_packaging_resources.py
- docs/BUILD.md
- docs/release-notes-v0.1.2.md
- milestone05/evidence/packaging-0.1.2/boundary.txt
- milestone05/evidence/packaging-0.1.2/build-inputs.json
- milestone05/evidence/packaging-0.1.2/bundled-smoke.json
- milestone05/evidence/packaging-0.1.2/freeze.txt
- milestone05/evidence/packaging-0.1.2/frozen-smoke.json
- milestone05/evidence/packaging-0.1.2/nsis-package-data.txt
- milestone05/evidence/packaging-0.1.2/pytest-full.txt
- milestone05/evidence/packaging-0.1.2/release-result.json
- milestone05/evidence/packaging-0.1.2/summary.json
- milestone05/evidence/packaging-0.1.2/tauri-build.txt
- milestone05/evidence/packaging-0.1.2/receipt.md

安装包与运行时大文件不入库；两份公司文档、用户 .workbuddy/ 未动。实机安装态UI、签名/SmartScreen与干净机验收未执行，也未声称通过；不打tag、不push、不建Release。正确命令和产物路径规则见 docs/BUILD.md。
