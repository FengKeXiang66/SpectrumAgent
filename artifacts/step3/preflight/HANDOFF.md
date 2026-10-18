# 第 3 步执行依据（负责人 2026-10-18 状态更新）

当前执行依据为负责人本轮消息与 `artifacts/step3/prompt-final.md`。消息优先于文件中旧的关账门槛：

- 第 2 步关账项 1/3/4/5/7 直接引用既有提交，不重跑 pytest、不重归档探针、不重生成权威产物清单、不改旧原始输出。
- 第 6 项保留“待实机验证”；恢复验证、干净 VM 三段冷启动计时、断网安装延期至 setup.exe 可用后。第 2 步 STATUS/REPORT 不写“正式关闭”。
- 负责人明确放行第 3 步；每个实施检查点报告后等待确认。
- SQLite 排他锁延期到数据库里程碑；当前多实例防护将由宿主单实例插件与既有引擎 owner-alive 拒绝组成。
- FR-D13 本轮只做常驻输入框、快捷键和占位行为；上下文继承、写操作撤销、等价入口随后续数据/标注里程碑实施。
- TanStack Query/Zustand/TanStack Table 本轮延期，不替换定稿方案。

## 第 2 步既有结果引用

| 项目 | 已有提交 / 证据 |
|---|---|
| HEAD d218262 pytest，27 passed | 73421c8；artifacts/step2/revision-01/pytest-head-output.txt |
| 契约修订 | 2abb004 |
| 七份历史探针去重、哈希和风险标记 | 4b7d3be |
| VM 三件首次提交“待实机验证” | 879064e |
| 全量 product-manifest，544 文件 | bc50c3e；来源 d218262，生成器 f44e683 |
| 上轮关账准备记录 | 7b59a05 |

## 当前只读环境快照（不执行 VM 恢复或配置变更）

完整原始输出：`environment-current-output.txt`，UTC 2026-10-18T07:13:04Z，即北京时间 15:13。
Hyper-V=Enabled，vmms=Running；不再把旧快照当作当前状态。
显式 `-ComputerName localhost` 可查询 VM；未指定时本执行环境的 Hyper-V 默认主机参数报 `Value cannot be null. (Parameter 'name')`，Windows PowerShell 5.1 同样报错。

查到 Win11/Gen2/Off，启动内存 8GB，SecureBoot=On（MicrosoftWindows），来宾服务接口=True，pristine ID 与负责人提供的一致：bb3d1cac-a20d-4a60-b5ba-4090353333d7，时间 2026-10-18 14:32:24。
以下实测与负责人消息不同，保留差异供后续 VM 验收复核，不自动修改：ProcessorCount=10、Minimum=536870912、Maximum=1099511627776、TpmEnabled=False。
Copy-VMFile 双侧 SHA256 一致属于负责人提供的已完成结果，本检查点没有重做，不冒充本次独立实测。

PATH Node/npm 实测为 20.18.0/10.8.2；另有应用自带 Node 24.19.0。本检查点不安装前端依赖、不选择或切换 Node；前端阶段再明确兼容版本与安装清单。

进入本轮时已有负责人未提交改动：VM-BUILD-Win11Clean.md、build-vm.ps1、vm-ops.ps1，以及未跟踪的 deploy-win11-vhdx.ps1。它们保留原样，不混入第一笔 src-tauri 提交；当前整体 Git 干净条件不能假报通过。

## 检查点顺序

1. 当前检查点：Rust 监督器、可注入 Win32 层、确定性 stub、严格解析和日志归属测试。
2. 负责人确认后：接真实冻结引擎，定义仅 dev 读取的 SPECTRUM_ENGINE_EXE，实施真实失败场景。
3. 再确认后：Tauri 宿主、单实例插件、四态 UI、常驻对话条与固定 invoke。
4. 最后：资源暂存的两个显式模式、release 故障夹具与最终 Canonical、各 10 轮回收矩阵、两份实际 EXE manifest 和三段计时。

新增依赖仍须先列包名和用途、等确认。本检查点五个直接 Rust 依赖已获批准；Cargo.lock 与第一笔 src-tauri 代码一同归档。
