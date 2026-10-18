# 第 2 步当前状态

正式 onedir 已构建，当前完整自检 1–7、8a、8b 及单 worker 均 PASS。
主报告见 REPORT.md；完整原始输出见 selfcheck-output.txt。
首次自检 8a 曾失败，原始记录保留在 selfcheck-attempt1-*；
历史握手出现原因未定位，详细说明见 README.md。
首次产物进程启动到 /health 200 为 1712.879 ms；复跑为 690.567 ms。
干净机器冷启动未验证。未安装依赖，未开始第 3/4 步。

---

以下为上轮最小探测时的历史记录，不代表当前状态。

## 历史：最小 onedir 探测完成，正式构建待确认

尚未编写正式 build.spec，尚未构建 backend app.exe，未开始第 3/4 步。
本目录内 probe/pid_probe.spec 是 PyInstaller 为最小探针自动生成的 spec，
不是 backend 的 build.spec。未安装包，未修改 requirements-lock.txt 或 backend 代码。

## 已执行的先行探测

10 行源码：probe/pid_probe.py。
实际执行的构建命令：

```powershell
& 'E:\AI_Agent\.venv\Scripts\python.exe' -m PyInstaller --onedir --name pid_probe --distpath 'E:\AI_Agent\artifacts\step2\probe\dist' --workpath 'E:\AI_Agent\artifacts\step2\probe\build' --specpath 'E:\AI_Agent\artifacts\step2\probe' --noconfirm 'E:\AI_Agent\artifacts\step2\probe\pid_probe.py'
```

通过 computer-use 在资源管理器中双击 pid_probe.exe。
独立终端 tasklist 实测 1 个 pid_probe.exe，PID=28668。
只读 AttachConsole + ReadConsoleOutputCharacterW 得到原始控制台文本 28668。
双击时的 tasklist 与控制台读取结果保存在 probe/process-probe-output.txt、
probe/doubleclick-console.json。首次脚本读取空 stdout 出错后已修复空值判断。

随后对同一个 exe 直接 Start-Process，实测 spawn_pid=21060、
os.getpid() stdout=21060，tasklist 仍仅 1 个 pid_probe.exe。
该轮完整命令与输出见 probe/spawn-probe-output.txt。
所有探针进程均已回收，最后 tasklist 输出：

```text
INFO: No tasks are running which match the specified criteria.
```

本机这个最小 onedir 探针没有观察到独立 bootloader 父进程。
backend 打包后的进程数仍须重新实测，不能用此探针代替。
Job Object / KILL_ON_JOB_CLOSE 未验证；依本轮要求，未写 Job Object 代码。

## 只读环境探测

完整原始输出见 environment-probe-output.txt：

```text
pyinstaller=6.22.3
pyproj_spec=None
shapely_spec=None
rasterio_CRS=EPSG:4326
rasterio_pyd_count=15
sibling_lib_dirs=['E:\\AI_Agent\\.venv\\Lib\\site-packages\\rasterio.libs']
rasterio_geotiff_samples=[]
rasterio_dynamic_libs=[]
rasterio_proj_db=[('E:\\AI_Agent\\.venv\\Lib\\site-packages\\rasterio\\proj_data\\proj.db', 'rasterio\\proj_data')]
rasterio_data_dirs=['E:\\AI_Agent\\.venv\\Lib\\site-packages\\rasterio\\gdal_data', 'E:\\AI_Agent\\.venv\\Lib\\site-packages\\rasterio\\proj_data']
```

## 需确认的约束

1. 当前 53 包不含 pyproj、shapely。它们分别提供独立坐标变换、几何运算，
   当前 backend 不使用；现有 rasterio.CRS.from_epsg(4326) 已实际返回 EPSG:4326。
   现有依赖可以支撑本轮引擎，却不能收集两个不存在的包。
   请确认本轮仅对 rasterio 落实二进制/数据收集；若必须加入另外两包，
   应先确认新增依赖及版本，再更新锁文件，不能自行安装。
2. 已验收的 backend/README.md 约定强杀遗留握手由后续外壳核验并清理；
   当前 handshake.py 由正常退出 finally 清理。本轮又要求强杀单独 app.exe
   后无残留握手，同时禁止外壳/Job Object。本路径未验证。
   若要求强杀后自动清理，需要批准额外存活的清理机制，会改变进程模型；
   若保持原契约，本轮应如实记录强杀后的握手状态，脚本的精确清理单独报告。
   不会把脚本收尾删除握手记成引擎自动清理通过。
3. 安装的 rasterio 目录内没有 .tif 样本；用户承诺提供的真实样本尚未收到。
   正式 GeoTIFF 验证前需有样本（用户样本或确认可用的 rasterio 官方测试数据）。

## 正式第 2 步八项检查状态

| 项 | 状态 |
|---|---|
| 1. cmd 直接启动 backend app.exe、tasklist | 未执行（仅先行最小探针完成） |
| 2. 冻结态 health / smoke / 401 / 分块 curl | 未执行 |
| 3. 冻结态握手全文 | 未执行 |
| 4. 冻结态 JSON 日志样本 | 未执行 |
| 5. 冻结态 GeoTIFF CRS/宽高/波段 | 未执行 |
| 6. 移除 DLL 的可读错误 | 未执行 |
| 7. 包体积与冷启动毫秒数 | 未执行；最小探针体积/耗时不冒充引擎数据 |
| 8. 任务管理器强杀后进程/握手 | 未执行 |

原任务的冻结态 multiprocessing worker 自检也未执行。
build.spec、selfcheck_step2.ps1、正式 dist 尚未产出。此检查点不宣称第 2 步通过。
