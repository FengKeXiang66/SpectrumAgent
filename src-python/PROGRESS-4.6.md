# 里程碑 #02 · 4.6 前序阻塞快照

**更新（2026-10-19）**：下述两个前置均已由负责人批准并完成；4.6 现已实现、验证，完整交付与自评见 [REPORT.md](REPORT.md)。以下保留当时状态，不能作为当前状态引用。

2026-10-19。此文件是进行中记录，不是里程碑验收通过报告。

## 已完成且已提交

| 子任务 | 提交 | 内容 |
|---|---|---|
| 4.1 | f7876c5 | Pydantic 数据模型、JSON Schema、有界读取、raw-only memmap |
| 4.2 | 6c450ea | spectral ENVI 封装、读前精确大小校验、只读 plastic 验证脚本 |
| 4.3 | d058ad4 | 共用字段规范化的 JSON/TXT 二进制解析器 |
| 4.4 | d19c879 | 缺 interleave、包裹/平铺 JSON 兜底及共享大小校验 |
| 4.5 | bb7cc6f | 原子、幂等、持久化引用登记及有界 API/预览 |

真实 plastic 11 个样本逐文件完整输出见 `tests/evidence/plastic-11.txt`：11/11；测试不依赖该绝对路径，也不复制或修改采集文件。

## 本轮已执行验证

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m pytest backend/tests src-python/tests/data -q --basetemp .runtime/m02-tests/4.6-regression
& 'E:\AI_Agent\.venv\Scripts\python.exe' scripts/selfcheck_milestone02.py
& 'E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe' node_modules/typescript/bin/tsc --noEmit
& 'E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe' --test src/components/datasets/types.test.ts
```

- Python：141 passed，10 warnings，5.62s，原始输出 `tests/evidence/4.6-python-regression.txt`。
- 开发入口独立 HTTP：health 200、无 token 401、登记/重复登记、raw 默认与 scaled 覆盖、3×2 PNG、缺文件 400、3 路并发 + health 200；日志 21 行合法 JSON、凭证匹配 0。原始输出 `tests/evidence/4.6-live-http.txt`。
- 直接 Popen 自检的 finally 强制回收和临时目录移除是**测试卫生，不是产品 Job 或握手清理通过依据**。该脚本明确标记 supervisor_acceptance 尚待身份裁定。
- 当前已写组件的 TypeScript 类型检查退出 0；Node 单测 2/2，输出 `tests/evidence/4.6-ui-unit.txt`。
- Rust 新增 TCP stub 测试已写，**尚未编译执行**；不得记为通过。
- 原生目录选择、实际 debug Tauri→sidecar→列表/Canvas、关窗回收：**未验证**。

warning 来自现有 Starlette/httpx TestClient 及 spectral/NumPy 弃用提示；没有据此安装任何新 Python 包。早先 4.5 失败诊断出现过测试凭证 repr，原始诊断隔离在 .runtime，入库诊断副本明确标记脱敏；本轮未据此宣称历史诊断零泄漏。

## 前置一：负责方安装 dialog

仅声明 Rust `tauri-plugin-dialog = "=2.8.3"` 与 npm `@tauri-apps/plugin-dialog = "2.8.3"`；截至本记录，两份 lock 未更新、node_modules 插件目录不存在。Codex 没有执行安装或 fetch。

负责方安装完成后，先审计 lock 新增项全部归属于 dialog/rfd/fs 三棵树，再实现插件注册及选择器。预计数量不是通过依据，以实际 lock/依赖树为准；审计、两份 lock 与 4.6 同笔提交。Python lock 必须不变。

## 前置二：venv launcher 双 PID（新实测阻塞）

原始输出见 `tests/evidence/4.6-python-process-probe-host.txt`：

```text
explicit_interpreter=E:\AI_Agent\.venv\Scripts\python.exe
spawn_pid=28612
actual_python_pid=26420
ProcessId=28612, ParentProcessId=30520, ExecutablePath=E:\AI_Agent\.venv\Scripts\python.exe
ProcessId=26420, ParentProcessId=28612, ExecutablePath=C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe
launcher_exit=0
```

同一次 tasklist 的另两个 Python PID（14212/30520）是探针驱动本身，不是引擎递归。初次 HTTP 自检对 `handshake.pid == Popen.pid` 的断言失败，保留于 `tests/evidence/4.6-live-http-pid-failure.txt`；后续 HTTP 自检只证明 API 可运行，不能抹掉此身份阻塞。

现有监督器以 CreateProcess PID 验握手；已批准方案只准替换启动方式。因此需负责人补裁定后才能改变身份校验，当前没有实施双 PID 放行。

提交审批的方案：仅 debug source-Python 分支允许握手指向**同一 Job 内**实际 Python PID，用该 PID 的 GetProcessTimes 校验创建时间；外壳仍持有/等待 launcher，Job 关闭回收两者。增加身份不符/非本 Job/创建时间不符与实际关闭回收测试；release 单 PID 逻辑不动。不以忽略 PID、只检查端口或自行换解释器绕过。

## 已写但未完成的 4.6 内容

- 结构化 datasets_forward：固定 localhost/已核验握手端口，编译期操作枚举、GET/POST 路由集合、8MiB 限额、身份先于状态/正文校验、无代理/重定向、工作线程、返回前核对代次；防凭证明文及 JSON 转义反射。
- main.json 授权仅为声明；release handler 保留原四命令列表；datasets_forward 函数及模块仅 cfg(debug_assertions)。没有改变 release resolver/Job 启动行。
- 单一前端 API 出口；目录进度、幂等列表合并、缩略图与 Canvas 组件；尚未接入 App/原生选择器。
- 尚未执行依赖审计、完整 Rust 构建/clippy、桌面联调；4.6 尚未提交完成。

## 留待后续打包里程碑

dev 使用指定 venv 3.12.13，release 使用封版 onedir；datasets 的 release IPC 尚未设计/注册。后续成品须复验新增路由、插件体积与运行时差异。本轮不重冻、不重打包，不修改 #01 安装包、resources/backend、artifacts/step4、VM 脚本与已封版证据。
