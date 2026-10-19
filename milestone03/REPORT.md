# 里程碑 #03 · 0.1.1 打包执行记录

状态：P0–P3 完成，P4–P6 待执行，P7 等负责人本机冒烟。未宣布过闸。

依据：TASK-03-打包里程碑.md 与负责人执行提示词；冲突以执行提示词为准。D1=A（仅转正 datasets_forward）、D2=产品0.1.1；握手协议版本仍0.1.0。每P独立提交，不安装新包，三份lock字节保持不变。

## P0 · #01 文档补丁

仅在获准的 `artifacts/step3/checkpoint-4/REPORT.md` 增补三项负责人裁定：记忆键为Tauri 2 NSIS标准行为（含MANUPRODUCTKEY源码行）；握手残留拍板A，不进0.1.1热修，自愈已实测两次且不以脚本删除冒充修复；不采未指认的24.146ms，以有档位/来源的211.154ms与208.095ms engine值及1292/1060/1178ms desktop值引用。既有冻结revision、原始输出、安装包未改。旧root REPORT主体为历史，不改写成新批次通过。

## P1 · 组合应用入口统一

`backend.engine.main` 改用 `spectrumagent.app.create_app`；dev_sidecar.py 原样不动。dev/release 在应用入口层共用同一create_app，解释器分别来自venv/onedir；既有debug双PID进程适配仍按#02隔离，不将它误称与release进程形态完全相同。源码入口补入src-python搜索路径；冻结由pathex收集。为P6明确要求，入口支持 `--data-root <绝对路径>`，默认LOCALAPPDATA约定及协议版本0.1.0不变。

新增3项测试验证：实际入口组合路由、数据根覆盖、拒绝相对数据根；`evidence/P1/pytest.txt` 为3 passed。预期最终pytest计数由141增至144，未减少既有测试。初次执行缺pytest临时目录父目录、随后测试直接调用内部main绕过源码bootstrap，各自失败输出保留；修正测试执行目录与入口调用方式后通过。既有TestClient弃用提示不通过装包处理。

## P2 · release 受限 IPC 与产品版本

D1=A：release handler 精确为 engine_status / retry_engine / run_smoke / open_data_directory / datasets_forward；转发模块与通用代次查询转为无条件。debug venv 收养、Win32/Job、启动路径源文件与 #02 基线逐字不变，dev handler 不变；main capability 权限集合不变，仅订正文案，cargo check 再生 capabilities schema 已归档。转发 host/端口、路由、方法、8MiB 与身份校验实现未改。

产品配置仅 version=0.1.1；协议0.1.0与三份锁保持原字节。补齐发布 UI 必要入口：取消数据面板的 import.meta.env.DEV 门控；Vite 从 tauri.conf.json 编译期注入产品版本，页面显示版本0.1.1，无需新增 Tauri 核心权限。保留模块原名 datasets_dev 以控制 diff。

`evidence/P2/` 保存 cargo check --locked --offline（exit0）、tsc --noEmit（exit0）、Vite production build 与 release-boundary.json 审计通过证据；实际 custom-protocol release 编译留待 P4，不用 debug check 冒充 release 验证。

## P3 · 新 revision 冻结与资源全量暂存

批次：`artifacts/step2/revision-20261019-m02/`。artifact_source_commit=f637fe2fe752161ceeebcae39f21de7c6fe161f9，manifest_generator_commit=ebfd09f（详见product-manifest.json完整值），两提交分离。沿用#01 batch_manifest.py生成器，扩展源码收录与嵌入源码核对到spectrumagent，保留七项硬校验原阈值；并非用旧清单冒充新包。

真实构建exit0；25个backend/spectrumagent模块嵌入代码与源码相等，无matplotlib。544文件/255,688,706B，app.exe 16,895,372B / SHA256 36e56a560c6d929690d8f4975cd73dae6a226997007d76a25dea77b49bc758e9；_internal仍543文件/238,793,334B，rasterio仍36DLL/15pyd。与封版smoke-headers批次相比，依赖只有base_library.zip顺序变化（成员内容、逐项元数据相同）；七项全部通过后生成新product-manifest。

Canonical暂存与src-tauri/resources/backend逐项全量比对544文件一致，旧ignored资源树移存.runtime供核查，未触碰旧冻结目录。build.spec仅补src-python发现路径与spectrumagent/spectral收集；collect_submodules先于Analysis，故显式加入sys.path；revision副本仅按目录深度调整ROOT。无GDAL/PROJ注入与手收DLL。PyInstaller日志实际分析工作目录为E:\AI_Agent\build\build（既有工具行为），dist位于本新revision；TEMP/TMP与缓存均E盘。依赖探针、构建原始输出及manifest见新revision，资源比对见evidence/P3。

## 后续门槛

P1统一create_app → P2转正受限IPC及发布UI → P3新revision冻结、来源/产物清单、资源全量比对 → P4 custom-protocol release/NSIS新包 → P5默认模式全量测试（≥141/22/2及clippy/tsc/vite） → P6同一自检脚本对照venv/onedir。P0–P6完成即停在等复核；负责人自行执行P7安装/首跑0.1.1/导入预览幂等/关窗/卸载数据保留。不准备VM/云电脑脚本。

缓测：签名/SmartScreen详录、干净机基线、timings.txt精确值、exit70、长路径>260、独立reboot轮、记忆键值细节。握手残留与1412继续如实记账，不互相解释未定位原因。
