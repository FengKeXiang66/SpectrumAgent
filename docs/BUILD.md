# Windows 0.1.2 安装包构建

在 PowerShell 中，从仓库根执行当前入口。以下为本机已验证的 PowerShell 7 路径，无须依赖 PATH：

```powershell
Set-Location E:\AI_Agent
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File .\scripts\build_release.ps1
```

若 PowerShell 7 已在 PATH，也可写 `pwsh -NoProfile -File .\scripts\build_release.ps1`。

脚本使用已有 `.venv`、仓库 `.toolchains/node24.19.0-npm10.8.2`、Rust 和本地 NSIS/WebView2 工具缓存，不执行依赖安装。Cargo 使用 `--locked --offline`。不要把 `milestone03/build_release.ps1` 或历史 `artifacts/step2/*/build.spec` 当作当前入口；它们绑定旧冻结批次或旧数据收集范围，保留作历史记录。

Cargo离线不等于安装器封装离线：Tauri的WebView2离线运行时封装仍可能访问官方地址查询版本或准备构建工具。请在有该网络访问权限的终端运行；不必关闭TLS校验或修改依赖。受限沙箱出现socket 10013时，脚本会停止并保留完整日志。

流程依次为：

1. 在 `artifacts/releases/0.1.2-<时间戳>/` 创建新批次，调用 `scripts/backend.spec` 冻结当前 Python。`collect_submodules` 收代码，`collect_data_files("spectrumagent")` 另收 catalog/schema/OpenAPI 等包内数据；不再只收 rasterio 数据。
2. 校验当前包内全部 JSON 与源码 SHA256 一致；真实启动冻结 `app.exe --data-root <隔离目录>`，子进程PATH仅保留Windows目录，不借用开发Python。核对就绪身份、projects/labels/21条目录、内置配方，以及真实pe的超像素→扩散→确认→保存→预处理成功与曲线报告。测试区域只是集成夹具，不代表人工质量。
3. 保留旧 `src-tauri/resources/backend`，完整复制本次onedir并逐文件对账，禁止只复制app.exe或把新旧目录叠加。
4. 通过 Tauri CLI 自动执行 `tsc --noEmit && vite build`，以 `custom-protocol` release 构建NSIS；同名旧安装包先备份。
5. 再次启动 release资源目录下实际后端，执行相同冻结冒烟，检查生成NSIS脚本包含plastic.json，最后复制安装包到本次批次并输出字节数/SHA256。

任一步失败，入口抛错停止，不把上一轮安装包当成新交付。完整日志和 `release-result.json` 位于本次批次，最终安装包路径由最后一行 `SUCCESS:` 给出：

```text
E:\AI_Agent\artifacts\releases\0.1.2-<时间戳>\SpectrumAgent_0.1.2_x64-setup.exe
```

该文件是安装包；单独拷贝外壳spectrum-agent.exe不包含Python运行时。构建与冻结HTTP验证不等同于签名、干净机或完整安装态UI验收；这些仍须实机检查。脚本不会安装程序、不修改正式用户数据、不打tag、不push，也不修改release manifest。

只检查一个已有冻结后端时：

```powershell
& .\.venv\Scripts\python.exe .\scripts\verify_frozen_backend.py assets --directory '<完整app目录>'
& .\.venv\Scripts\python.exe .\scripts\verify_frozen_backend.py smoke --exe '<完整app目录>\app.exe' --output 'E:\AI_Agent\.runtime\frozen-check-唯一目录'
```

smoke目录必须不存在；脚本用实际进程创建时间核对自己的子进程，结束后回收它，仅在隔离目录写数据库、快照和日志。真实pe路径取 `milestone04/evidence/calibration/cubes_11.txt` 首行，源文件只读且前后哈希校验。
