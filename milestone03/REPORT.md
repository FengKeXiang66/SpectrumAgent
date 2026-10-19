# 里程碑 #03 · 0.1.1 打包执行记录

状态：P0 完成，P1–P6 待执行，P7 等负责人本机冒烟。未宣布过闸。

依据：TASK-03-打包里程碑.md 与负责人执行提示词；冲突以执行提示词为准。D1=A（仅转正 datasets_forward）、D2=产品0.1.1；握手协议版本仍0.1.0。每P独立提交，不安装新包，三份lock字节保持不变。

## P0 · #01 文档补丁

仅在获准的 `artifacts/step3/checkpoint-4/REPORT.md` 增补三项负责人裁定：记忆键为Tauri 2 NSIS标准行为（含MANUPRODUCTKEY源码行）；握手残留拍板A，不进0.1.1热修，自愈已实测两次且不以脚本删除冒充修复；不采未指认的24.146ms，以有档位/来源的211.154ms与208.095ms engine值及1292/1060/1178ms desktop值引用。既有冻结revision、原始输出、安装包未改。旧root REPORT主体为历史，不改写成新批次通过。

## 后续门槛

P1统一create_app → P2转正受限IPC及发布UI → P3新revision冻结、来源/产物清单、资源全量比对 → P4 custom-protocol release/NSIS新包 → P5默认模式全量测试（≥141/22/2及clippy/tsc/vite） → P6同一自检脚本对照venv/onedir。P0–P6完成即停在等复核；负责人自行执行P7安装/首跑0.1.1/导入预览幂等/关窗/卸载数据保留。不准备VM/云电脑脚本。

缓测：签名/SmartScreen详录、干净机基线、timings.txt精确值、exit70、长路径>260、独立reboot轮、记忆键值细节。握手残留与1412继续如实记账，不互相解释未定位原因。
