# 第 2 步：PyInstaller onedir

正式源文件：本目录 `build.spec`、`selfcheck_step2.ps1`、`lifecycle_regression.py`，
以及代码根 `backend/diagnostics.py` 和 `backend/__main__.py`。
这些源文件与选定的文本验收证据允许进入 Git；构建缓存、EXE、DLL、临时 GeoTIFF 不入库。

## 构建与复跑

仅使用项目已冻结的 53 包和指定解释器，不安装依赖：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m PyInstaller --noconfirm 'E:\AI_Agent\artifacts\step2\build.spec'
& 'E:\AI_Agent\artifacts\step2\selfcheck_step2.ps1'
```

自检脚本使用本机已验证的 PowerShell 7（本轮为 7.6.5）/ .NET API，
仅作为开发验收工具；运行 `app.exe` 不依赖 PowerShell 或外部 Python。
控制器使用指定 venv（也用于 dev 模式）；frozen 引擎直接以 app.exe 启动，
拥有隐藏控制台，工作目录为证据目录，PATH 仅保留 Windows 目录，不借用外部解释器。
短生命周期的注入辅助进程向引擎控制台发送真实 CTRL_BREAK / CTRL_C，
只保护辅助进程自身，不改变引擎信号处理。未实现外壳或 Job Object。
旧 NativeConsole.cs 与旧自检脚本仅留作历史证据，不再用于当前验收。

spec 锁定产物位置：`artifacts/step2/dist/app/app.exe` + `_internal/`。
移动/分发必须复制整个 `app/` 目录。数据与日志仍在 `%LOCALAPPDATA%/SpectrumAgent/`。
直接运行命令：

```powershell
& 'E:\AI_Agent\artifacts\step2\dist\app\app.exe'
```

`collect_submodules('rasterio')` 处理 Cython 层的动态导入；
`collect_data_files('rasterio')` 处理 proj.db、gdalvrt.xsd 等数据。
另外收集 uvicorn 的动态加载模块。不手动复制 rasterio DLL，也不调用额外的 DLL 收集。
本机产物中二进制分析自动生成 `rasterio.libs/`，实测 36 个 DLL 和 15 个 rasterio pyd。
不设置 GDAL_DATA、PROJ_DATA 或 PROJ_LIB；自检遇到已有变量会明确失败，不会悄悄清除。
本轮结论仅覆盖实测 wheel/锁文件/Windows 环境，不推广到其他版本的 rasterio。

## 诊断与生命周期

```powershell
& 'E:\AI_Agent\artifacts\step2\dist\app\app.exe' --selfcheck-geotiff
& 'E:\AI_Agent\artifacts\step2\dist\app\app.exe' --selfcheck-worker
```

GeoTIFF 模式在 LocalAppData 的 testdata 下每次新造样本、按指定 profile 写入并读回，
断言 CRS / 宽高 / 波段数 / transform / 数据值，然后清除样本。没有数据接入模块。
worker 模式只起一个短暂 spawn 子进程，不建任务池。入口先执行 freeze_support()，
子进程只回报自己的 PID/父 PID 并退出，断言握手未被改写。

旧 8a“Ctrl+C 优雅退出无残留已通过”的结论撤回，不再作为当前验收依据。
当前拆成两项：CTRL_BREAK immediate cleanup；CTRL_C / taskkill recovery。
dev 与 frozen 各组合至少 5 轮，按本轮 boot_id 保存全部日志和 engine_stopped 计数。
确认握手已发布后到退出判定前，脚本不删改文件；只在新场景要求中主动替换外来握手。
CTRL_BREAK 必须由 lifespan 清理，恰好一次 engine_stopped，PID/端口/握手均消失。
CTRL_C / 强杀允许残留，下一次引擎启动必须先清扫旧代并记录 stale_handshake_removed，
之后新引擎用 CTRL_BREAK 验证清理；不把这些终止记作优雅退出通过。
第一轮启动前的历史死 PID 清理、失败后的收尾均明确记为 TEST_HYGIENE_ONLY，不能用于通过判定。

## 证据与限制

根目录 selfcheck-output.txt / selfcheck-results.json 及 selfcheck-attempt1-* 是**历史**原始记录，
偶发 PASS 不能证明稳定性，旧通过结论已撤回。旧 REPORT.md / README.md / STATUS.md 和
后续用户复现脚本与日志逐字节归档于 revision-01/history，保留 FAIL、偶发 PASS、后续复现。
事实口径：frozen 与 dev 均能在 Uvicorn 完成关闭后跳过 main finally；
CTRL_BREAK 可达 ASGI lifespan，CTRL_C 与强杀可能不执行进程内钩子，不归因于 PyInstaller。
负责人提供的设计前提保持原样：CTRL_BREAK exit=3，有完整关闭序列且 lifespan 确实执行；
CTRL_C exit=1，日志停在 engine_ready，无关闭序列也无 traceback，进程内钩子不执行；
TerminateProcess / taskkill 同样没有进程内钩子。不能用本轮不同控制台注入拓扑下的
CTRL_C 清理样本改写该基线，也不能恢复“CTRL_C 稳定优雅退出”的旧结论。
当前修复分别实现旧代启动清扫与本代 lifespan 清理，main finally 只作 best-effort 兜底。
最新证据由 revision-01/latest-session.txt 指向；每次自检创建新目录，绝不覆盖旧轮次。
当前 source-manifest.json 对应修复后产物，旧清单另存 history/source-manifest-before-revision.json。
根目录 startup-measurements.json 仅属于初次构建；修复后构建的回归耗时在当前 session 中，
均不冒充干净机器冷启动。
历史工作区副本与上一 Git 提交的三个文件仅换行形式有差异，文本行一致；
两种原始字节都分别保留（history/git-5cd22b3-*），比较结果见 history-comparison.json。
revision-01/run-001 保留了本轮回归控制器读取 ANSI stderr 为 UTF-8 时的失败；
后来改为直接检查原始字节中的 ASCII 错误码，原 stderr 字节完整保留。

`startup-measurements.json` 区分正式产物首次启动 1712.879 ms 与复跑 690.567 ms。
它们是进程启动到身份匹配的 /health 200 的实测，包含轮询开销。
没有清空 OS 文件缓存或重启电脑，没有在无 Python 的干净 Windows 机器上复跑；
不能把复跑值当干净机器冷启动，也不以此声明安装包启动验收通过。
新建干净 venv 并安装锁依赖的构建尚未执行（本轮不执行安装）。

缺失 python312.dll 时 PyInstaller 原生报错包含缺失 DLL 的完整路径，退出码 -1，
无 Python traceback；系统辅助行在本机原始输出中为问号，完整保留在 missing-dll-output.txt。
DLL 在 finally 中恢复，恢复后的 SHA256 与原值一致。

原始数据解释与逐项报告见 REPORT.md。尚未开始第 3/4 步。
