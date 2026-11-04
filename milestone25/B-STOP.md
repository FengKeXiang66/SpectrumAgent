# TASK-25 B 段即停记录

本次即停已由备卡方 eb1b25b 修卡、用户裁定解除。以下保留即停时事实，不代表当前仍阻断。已采纳活跃优先四象限、整批原子、INSERT 前复核与 REIMPORT_ACTIVE_EXISTS(409)，裁定后验证见 REPORT-B.md 与 evidence/B/reimport-ruling-targeted.txt。

当前权威卡：b6b247e；当前 HEAD 仍为该提交。A 段 9ad8268 已交付。B 段工作保留在工作区，未暂存、未提交、未 push；没有自行改卡。

阻断发生于 §3.5 的重导入条件。卡要求“recycle_bin 存在同 header_key+raw 且未 confirm_new 就 409”，同时要求确认后新建 id；已有导入又必须保留活跃记录查重行为。

复现模式：独立 Python 进程、新建合成 ENVI、真实 SQLite 外键与守卫；没有访问用户原始数据。

```powershell
$env:PYTHONIOENCODING='utf-8'
& .venv/Scripts/python.exe .runtime/task25/reimport_active_probe.py
```

步骤与实测：

1. 删除 A 进入回收站。
2. confirm_new=true 导入同路径，得到新活跃 B。
3. A 尚在回收站，再次默认导入活跃 B：409 REIMPORT_CONFIRMATION_REQUIRED。
4. 再带 confirm_new=true：返回 B 原 id，existing=true，并没有新建 id。

原文在 [reimport-active-ambiguity.txt](E:/AI_Agent/milestone25/evidence/B/reimport-active-ambiguity.txt)。这会让后续 UI 的“新建 id”确认提示与真实行为矛盾。

已请求备卡方裁定：是否先查活跃记录并正常返回已有，只有无活跃记录而同路径在回收站时才要求 confirm_new，确认后 INSERT 新 id。该建议尚未实施，不能用测试全绿代替口径裁定。

本次开工三道闸门已通过，完整基线与当前验证输出保留于 evidence/B。待裁定后继续 B 段收口；C / D 未开工。

另：本段正常改造已经造成下一段锚点漂移（例如 types.ts 合并函数 35→50、schemas.py all_datasets 35→36、registry.py 查重 156→169、INSERT 165→178、readable 200/204→214/218、api.ts 浏览 35→44）。完整 grep 原文在 [anchors-after-B.txt](E:/AI_Agent/milestone25/evidence/B/anchors-after-B.txt)，后续须由备卡方统一校准，执行方未改卡。
