# 里程碑02源码

不修改或覆盖里程碑01已封版exe、安装器、资源树与VM脚本。

执行测试（不需要安装包）：

```powershell
& E:\AI_Agent\.venv\Scripts\python.exe -m pytest src-python/tests -q
```

数据模型使用Pydantic dataclass；字段与JSON Schema在spectrumagent/data/schema.json。
shape恒为(lines,samples,bands)，未知wavelengths=[]，未知fwhm=null。
运行时读取器/raw选择不作为序列化字段；读取器在metadata中标注值模式和scale。
缩放模式to_numpy显式抛DataError；raw模式为只读DN memmap，保持源dtype（塑料样本为uint16）。
read_region全图属于调用方显式选择，允许；无隐式load()路径。

## #02 开发联调（仅 debug）

负责方已安装并锁定 dialog 2.8.3；不需要另装依赖。两个终端均显式设置：

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target\milestone02'
$env:TEMP='E:\AI_Agent\.runtime\milestone02-temp'
$env:TMP=$env:TEMP
```

第一终端启动 Vite：

```powershell
& 'E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe' 'E:\AI_Agent\node_modules\vite\bin\vite.js' --host 127.0.0.1 --port 1420 --strictPort
```

第二终端在 E:\AI_Agent 中启动外壳（先移除当前会话中的旧测试覆盖 SPECTRUM_ENGINE_EXE）：

```powershell
Remove-Item Env:SPECTRUM_ENGINE_EXE -ErrorAction SilentlyContinue
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' run --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --bin spectrum-agent --locked --offline
```

debug 使用 E:\AI_Agent\.venv\Scripts\python.exe，SPECTRUMAGENT_DEV_PYTHON 可覆盖绝对路径；实际 CPython PID 必须通过同 Job、创建时间与存活校验。选择目录后仅登记引用；重选同目录返回已有 ID。raw 模式随登记持久化。目录进度表示已完成目录数，单目录解析期间为不定进度，不伪造字节读取进度。

独立 HTTP 自检：`scripts/selfcheck_milestone02.py`；真实 GUI 验收脚本：`scripts/verify_m02_desktop.ps1`（需先运行 Vite，使用 E 盘隔离数据根，等待用户正常关窗）；证据复核：`scripts/audit_m02_evidence.py`。Python 脚本一律用上面的 venv 全路径。

release 不注册 datasets_forward，仍使用封版 onedir；本轮只验开发态。后续打包须复验 datasets 发布 IPC、Python 运行时差异及新增常驻 dialog 插件的安装物体积。未重冻或重打包。完整结果见 [REPORT.md](REPORT.md)。
