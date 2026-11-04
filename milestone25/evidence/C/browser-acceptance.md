# C 界面验收：合成 IPC + 实际 React App

模式：Vite 开发服务器、真实 App / S03 / S04 / S11 组件、内存合成 Tauri IPC。使用 cua_repl 浏览器工具点击和读取 DOM，截图实测宽约 832px。没有真实 NAS、业务数据库、文件删除、外部模型调用；不声称真实 NAS 连接已经通过。

原运行地址为 `http://127.0.0.1:1420/.runtime/task25/C-ui/index.html?src=smb%3A%2F%2Fqa-nas%2Fprefilled&out=smb%3A%2F%2Fqa-nas%2Ffuture`。归档夹具只将导入改为 Vite 根路径并使 html 指向归档文件，便于直接复现：

```powershell
npm run dev -- --host 127.0.0.1 --port 1420
# 浏览器打开 http://127.0.0.1:1420/milestone25/evidence/C/browser-harness.html?src=smb%3A%2F%2Fqa-nas%2Fprefilled&out=smb%3A%2F%2Fqa-nas%2Ffuture
```

1. 冷启动自动显示四个摘要，包括源失效行；失效行查看 / 标注 / 预处理全部禁用。两个查询参数显示为 UNC，源只读和输出根未启用均明示。保存后再进 S11 读取相同值。
2. 点「选择数据目录」，夹具返回三个已有目录。实际状态原文：`该路径已有数据集。本次选中 3 个（新增 0 / 已有 3）`，见 ui-active.txt / png。
3. 点「移入回收站 样品 1」，弹窗列出四类计数、两个目录、3,234 B、30 天可恢复与空间未释放。ui-before-delete-ledger.json 在确认前只含 delete_preview，无 delete；工具中对该条件作实际断言。截图 ui-delete-preview.png。
4. 点「确认移入回收站」，活跃行移除，状态显示占用未释放。再选三个目录时出现「作为全新数据集导入」已选单选项，包含新 id、从头标注、30 天、双份空间；确认后显示 `本次选中 3 个（新增 1 / 已有 2）`。
5. 选择已删除筛选，显示 1 个条目 / 3,234 B / 释放日期。点恢复再确认，因同路径已有新活跃记录，拒绝原因和「须先把新的也删进回收站，或等 30 天到期」可见，见 ui-restore-conflict.txt。
6. 进入 S11，保存的两字段、本机实际根、占用、条目日期及「NAS 路径与文件名」禁运项可见，见 ui-settings.txt / ui-settings-summary.png。
7. 点夹具「模拟引擎换代」，实际 App 换到 generation_id=2 并自动重载，新名称带第 2 代；失效源仍保留且查看按钮 isEnabled=false。打开可用样品后进入真实 S04，显示波段控件和预览；见 ui-generation-2.txt、ui-details.txt、ui-final-ledger.json。

旧代次延迟成功 / 延迟失败的精确竞态由 catalog.test.ts 的 deferred Promise 用例验证；浏览器换代是补充实测，不把即时夹具响应冒充延迟竞态证明。后端真实 SQLite / 进程重启与 LLM wire 序列化的验证在 test_project_paths.py，Rust 真实 TCP stub 验证身份与错误回显保护。
