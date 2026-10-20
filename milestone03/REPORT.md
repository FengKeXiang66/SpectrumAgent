# 里程碑 #03 · 0.1.1 打包执行记录

状态：P0–P6 完成，等复核；P7 等负责人本机冒烟。未宣布过闸。

依据：TASK-03-打包里程碑.md 与负责人执行提示词；冲突以执行提示词为准。D1=A（仅转正 datasets_forward）、D2=产品0.1.1；握手协议版本仍0.1.0。每P独立提交，不安装新包，三份lock字节保持不变。

## P0 · #01 文档补丁

仅在获准的 `artifacts/step3/checkpoint-4/REPORT.md` 增补三项负责人裁定：记忆键为Tauri 2 NSIS标准行为（含MANUPRODUCTKEY源码行）；握手残留拍板A，不进0.1.1热修，自愈已实测两次且不以脚本删除冒充修复；不采未指认的24.146ms，以有档位/来源的211.154ms与208.095ms engine值及1292/1060/1178ms desktop值引用。既有冻结revision、原始输出、安装包未改。旧root REPORT主体为历史，不改写成新批次通过。

## P1 · 组合应用入口统一

`backend.engine.main` 改用 `spectrumagent.app.create_app`；dev_sidecar.py 原样不动。dev/release 在应用入口层共用同一create_app，解释器分别来自venv/onedir；既有debug双PID进程适配仍按#02隔离，不将它误称与release进程形态完全相同。源码入口补入src-python搜索路径；冻结由pathex收集。为P6明确要求，入口支持 `--data-root <绝对路径>`，默认LOCALAPPDATA约定及协议版本0.1.0不变。

新增3项测试验证：实际入口组合路由、数据根覆盖、拒绝相对数据根；`evidence/P1/pytest.txt` 为3 passed。预期最终pytest计数由141增至144，未减少既有测试。初次执行缺pytest临时目录父目录、随后测试直接调用内部main绕过源码bootstrap，各自失败输出保留；修正测试执行目录与入口调用方式后通过。既有TestClient弃用提示不通过装包处理。

## P2 · release 受限 IPC 与产品版本

D1=A：release handler 精确为 engine_status / retry_engine / run_smoke / open_data_directory / datasets_forward；转发模块与通用代次查询转为无条件。debug venv 收养、Win32/Job、启动路径源文件与 #02 基线逐字不变，dev handler 不变；main capability 权限集合不变，仅订正文案，cargo check 再生 capabilities schema 已归档。转发 host/端口、路由、方法、8MiB 与身份校验实现未改。

产品配置仅 version=0.1.1；协议0.1.0与三份锁保持原字节。补齐发布 UI 必要入口：取消数据面板的 import.meta.env.DEV 门控；Vite 从 tauri.conf.json 编译期注入产品版本，页面显示版本0.1.1，无需新增 Tauri 核心权限。保留模块原名 datasets_dev 以控制 diff。

`evidence/P2/` 保存 cargo check --locked --offline（exit0）、Vite production build 与 release-boundary.json 审计通过证据；tsc在P2通过，完整复跑输出另见P5/tsc.txt；实际 custom-protocol release 编译留待 P4，不用 debug check 冒充 release 验证。

## P3 · 新 revision 冻结与资源全量暂存

批次：`artifacts/step2/revision-20261019-m02/`。artifact_source_commit=f637fe2fe752161ceeebcae39f21de7c6fe161f9，manifest_generator_commit=ebfd09f（详见product-manifest.json完整值），两提交分离。沿用#01 batch_manifest.py生成器，扩展源码收录与嵌入源码核对到spectrumagent，保留七项硬校验原阈值；并非用旧清单冒充新包。

真实构建exit0；25个backend/spectrumagent模块嵌入代码与源码相等，无matplotlib。544文件/255,688,706B，app.exe 16,895,372B / SHA256 36e56a560c6d929690d8f4975cd73dae6a226997007d76a25dea77b49bc758e9；_internal仍543文件/238,793,334B，rasterio仍36DLL/15pyd。与封版smoke-headers批次相比，依赖只有base_library.zip顺序变化（成员内容、逐项元数据相同）；七项全部通过后生成新product-manifest。

Canonical暂存与src-tauri/resources/backend逐项全量比对544文件一致，旧ignored资源树移存.runtime供核查，未触碰旧冻结目录。build.spec仅补src-python发现路径与spectrumagent/spectral收集；collect_submodules先于Analysis，故显式加入sys.path；revision副本仅按目录深度调整ROOT。无GDAL/PROJ注入与手收DLL。PyInstaller日志实际分析工作目录为E:\AI_Agent\build\build（既有工具行为），dist位于本新revision；TEMP/TMP与缓存均E盘。依赖探针、构建原始输出及manifest见新revision，资源比对见evidence/P3。

## P4 · custom-protocol release / NSIS

真实 `npm run tauri -- build --features custom-protocol ... -- --locked --offline` 执行，beforeBuildCommand自动tsc+Vite，外壳重新编译成功（1m31s）；首次bundle因套接字os error10013退出1。原输出完整保留。随后同特性、--no-binary-patching仅重试bundle成功exit0；详细日志证明HEAD经微软fwlink 302→微软CDN 200、proxy:None，未关闭TLS、未安装依赖。既有工具缓存逐文件SHA相等复制到本轮target；NSIS两SHA1锚点吻合，WebView2载荷复用。实际Cargo fingerprint features=[custom-protocol]、未含test-probes。

交付：`artifacts/milestone03/SpectrumAgent_0.1.1_x64-setup.exe`，287,410,501B，SHA256 `93c717284866562b8986bd1ad06bdcdb11d0adeb0fa7b47bfcb1646fc21888e7`；相对#01的287,156,790B增加253,711B（合计引擎/前端/IPC/dialog-rfd变化，不将合计增量冒充dialog单独归因实验）。交付副本与bundle源逐字节一致。旧artifacts/step4/setup.exe仍d8492536完整SHA，未改动。

外壳11,413,504B / SHA256 8b4426a513b66a724e10d626bebbaecdb6a31e8e28f1d52c468bebd0e9ad519e；release资源544文件逐项匹配新批次manifest。NSIS生成脚本保留Programs目录守卫、currentUser/offlineInstaller和原模板，产品version0.1.1；release根的exe集合仅spectrum-agent.exe，无probe/stub。两exe的RT_MANIFEST与SHA绑定，均longPathAware/asInvoker/CommonControls6；>260路径功能测试仍缓测。

签名分列：setup.exe=NotSigned；外壳exe=NotSigned；引擎exe=NotSigned；WebView2载荷=Valid/Microsoft。SmartScreen警告可能出现，实际警告详录缓测，不称签名链完整。构建命令/退出码、工具缓存逐项SHA、生成NSIS脚本、fingerprints、dist全量SHA与候选绑定均在evidence/P4，未运行安装器或P7。

## P5 · 最终源码默认全量测试

2026-10-20（本地时区）执行，六项命令全exit0。pytest backend/tests src-python/tests -q：144 passed（6.26s，141基线+P1入口/数据根/非法相对路径3项）；10个既有弃用提示保留。Cargo test --locked --offline：默认并行22 passed（21常规+1 compile_fail文档测试），无--test-threads，RUST_TEST_THREADS未设置；包含真实venv双PID Job回收/陈旧握手自愈。Node --test：2 passed。tsc --noEmit：exit0。cargo clippy --all-targets -- -D warnings：exit0。vite build：exit0；重建后dist三个文件全量SHA与P4入包时相同。

完整命令/原始输出逐项在 `evidence/P5/pytest.txt`、`cargo-test-default.txt`、`node-test.txt`、`tsc.txt`、`clippy.txt`、`vite.txt`；默认模式与E盘环境见environment.json，逐项exit码见results.json，计数与dist复算见summary.json。没有使用串行cargo结果替代默认并行。

## P6 · 同一 HTTP 契约 venv / onedir 对照

仅参数化既有scripts/selfcheck_milestone02.py，以SPECTRUMAGENT_SELFCHECK_EXE指定冻结app.exe，缺省仍dev_sidecar；SPECTRUMAGENT_SELFCHECK_RESULT保存JSON。两侧均清除PYTHONPATH、使用非源码临时工作目录和显式--data-root，只构造2×3×4小样本，不访问plastic源数据。dev_sidecar保持原样。验证器verify_acceptance.py只比较已有输出及清单，不另建HTTP用例。

两侧退出0：health200、无token401、首次import200/imported1、重复existing1/imported0且同id、raw波段全6值与DN一致、raw=false覆盖全6值与DN/65535一致、3×2 PNG SHA相同、并行3次导入单id、源文件大小/mtime_ns/SHA读取前后不变。三错误均HTTP400：缺文件顶层FILE_NOT_FOUND；坏头与超大文件保留原子批次顶层IMPORT_BATCH_INVALID，items分别HEADER_INVALID/SIZE_MISMATCH；实际声明48B/实长49B被拒。未改API错误信封迎合测试。

完整health/401/import/raw/scaled/preview/三错误共9类响应逐字段相等，另外比较幂等summary、PNG SHA与并发结果。仅排除每boot的身份值、导入UUID、临时路径、elapsed/uptime；health body及获授权datasets响应的boot_id/pid已先与本次握手校验。两侧JSON日志各24行、token命中0。venv launcher4260/实际CPython18232；onedir spawn_pid=实际PID=26080。P6脚本收尾强制终止与删除临时目录明确为测试卫生，不据此声称产品正常关窗/Job/握手清理通过；产品dev Job证据在P5集成测试，release安装态清理留P7。

`evidence/P6/venv-output.txt`与`onedir-output.txt`为完整原始输出（含全部JSON体）；各result.json保留各侧结果。runtime-comparison.json/comparison-output.txt归档同源新manifest和9类响应对照。最终复核：三锁字节不变、旧sealed step2证据全量hash不变、#01 setup仍d8492536；资源与release资源各544文件全量吻合，新shell/setup/dist仍绑定P4。

## 验收自评与范围说明

| 项目 | 自评 | 证据 |
|---|---|---|
| P0 三项负责人裁定 | 完成 | 获准旧REPORT补丁，未采未指认计时 |
| P1 组合应用入口 | 完成 | P1三测试、P3嵌入源码、P6冻结HTTP |
| P2 release五命令/ACL/隔离 | 完成 | evidence/P2/release-boundary.json、P4特性fingerprint |
| P3 新manifest/旧revision不变/资源 | 完成 | 新revision七校验、源/产物清单与P3全树比对 |
| P4 新0.1.1 NSIS | 完成 | evidence/P4/release-candidate.json，副本SHA一致 |
| P5 默认全量测试 | 完成 | 144 / 22(含1文档) / 2，六命令全exit0 |
| P6 venv/onedir | 完成 | 同一脚本、9类完整响应与数值/PNG一致 |
| P7 负责人本机核心链 | 待负责人执行 | 安装前无旧版→默认路径安装→非白窗/Ready/0.1.1→11项导入/预览/重复新增0→关窗→卸载留数据 |
| 负责人独立复跑与过闸 | 等复核 | 本报告不代替负责人验收 |

实现补齐：P1增加--data-root以满足P6；P2取消发布UI的DEV门控并从唯一产品配置注入版本显示；P3 collect_submodules前补src-python路径，revision副本仅调整ROOT层级。这些为任务目标所需最小改动，未扩权限/依赖/协议。Cargo/npm包版本仍0.1.0以保持锁字节不动，产品与UI为0.1.1；握手/OpenAPI仍0.1.0。第一次bundle的10013及P1两次测试准备失败原样保留，最终输出另存；未擦除失败证据。P5 summary仅作计数/用途说明，不将相对路径拒绝描述为HTTP结构化错误。

完整变更文件清单见CHANGES.md（含新revision与原始证据）。各P分别提交；P3按来源→生成器→清单三笔同范围提交，artifact_source_commit与manifest_generator_commit分开。安装包为ignored构建产物，证据/清单已入库。新revision与milestone03/evidence已补齐.gitattributes的-text规则，保留原始输出换行字节，evidence-byte-audit.json逐项核对暂存区；最终提交后git status复核存档，除两份负责人公司文档外，无未跟踪、无修改。

## 后续门槛

P1统一create_app → P2转正受限IPC及发布UI → P3新revision冻结、来源/产物清单、资源全量比对 → P4 custom-protocol release/NSIS新包 → P5默认模式全量测试（≥141/22/2及clippy/tsc/vite） → P6同一自检脚本对照venv/onedir。P0–P6完成即停在等复核；负责人自行执行P7安装/首跑0.1.1/导入预览幂等/关窗/卸载数据保留。不准备VM/云电脑脚本。

缓测：签名/SmartScreen详录、干净机基线、timings.txt精确值、exit70、长路径>260、独立reboot轮、记忆键值细节。握手残留与1412继续如实记账，不互相解释未定位原因。
