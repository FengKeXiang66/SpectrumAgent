本目录保留所有中间记录，不回写旧输出。

| 目录/文件 | 含义 |
|---|---|
| evidence-20261018-155624-671746 | 首轮启动前清单排序比较失败；未启动真实引擎 |
| canonical-readonly-difference-output.txt | 只读核对，544 文件缺失/额外/变化均为 0，只有顺序不同 |
| evidence-20261018-155712-784511 | 第一轮真实联调完成；尚未补强逐次失败归档、原始字节和脱敏前 token 扫描 |
| evidence-20261018-155929-723334 | 补逐次失败快照、bootloader stderr 原字节、创建到迁移计时；token 扫描仍只覆盖脱敏副本 |
| evidence-20261018-160118-937634 | 增加脱敏前原始日志 token 扫描；文本归档换行仍有二次转换 |
| evidence-20261018-160306-056134 | **最终依据**。补启动前 EOF 与原始增量 SHA；保留原始换行；16 个 final 片段与日志原文件逐字节一致 |
| original-log-audit-output.txt | 首个临时审计命令按 GBK 读 UTF-8 receipt 失败 |
| original-log-audit-fixed-output.txt | 正式 audit_evidence.py 显式 UTF-8，原始片段/闭合增量 SHA 全部一致 |

中间 receipt 的 passed 表示当时脚本断言通过，不能替代最终原始字节与 token 证明。最终以 REPORT.md、verification-receipt.json 及最终依据目录联合核验。

运行入口是 selfcheck_checkpoint2.ps1（默认离线构建），会实际启动冻结引擎并在 LocalAppData 准备握手夹具；发现未知握手立即拒绝。失败先落盘内部日志；收尾只清理本轮已知握手、已知进程及 E 盘 target 内专用副本。测试卫生不作为生命周期通过依据。

重放原始字节审计使用项目 .venv 的 python.exe 执行 audit_evidence.py，并传最终依据目录。它只读运行日志、按保存的起止偏移核验；审计输出已存在时拒绝覆盖。若要重复审计，应使用独立证据副本/新输出位置，不能覆盖既有审计。
