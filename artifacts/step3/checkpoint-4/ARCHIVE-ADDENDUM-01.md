## Git 对象字节复核补记

297aad4 提交后，使用 git cat-file --batch 对 evidence-manifest.json 的304条记录逐一核验 Git blob 字节，发现唯一差异：nsis-install-directory-proposal.diff 工作区原始238字节被Git归一为233字节，恰好只差5个CRLF中的CR；其余303项一致。首次失败与全量诊断分别保存在 git-archive-byte-check-output.txt、git-archive-byte-diagnostics-output.txt。

补充 .gitattributes 的 checkpoint-4/*.diff -text -whitespace，并将工作区原始238字节重新加入Git。原提案、原始验收文件、原manifest和REPORT不改写。修复后复核输出另存 git-archive-byte-final-output.txt。此问题只涉及提案证据的归档换行，不涉及release exe、资源、三锁或验收行为。

本补记、后续复核收据与git状态收据属于清单中明确排除的later receipts；304文件原清单仍为唯一保字节参照。第3步未关闭；NSIS两项审批、Stopping对话条最终DOM、全仓Git干净与VM实机项仍按REPORT记录。
