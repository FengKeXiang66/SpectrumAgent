# 10.2 标定复跑

在仓库根目录用现有 Python 环境执行：

```powershell
& E:\AI_Agent\.venv\Scripts\python.exe milestone04/evidence/calibration/calibrate.py
& E:\AI_Agent\.venv\Scripts\python.exe milestone04/evidence/calibration/summarize.py
```

calibrate.py 从 E:\高光谱数据集\plastic\ 发现全部 11 个 hdr，断言 pe3/pet4/pp4，记录 cubes_11.txt。每个 cube 按开工令的 0.2/0.5/1/2/10 五档运行；每格独立进程，防止进程历史峰值混入本格，完整输出 compactness.csv 共 55 行。临时 registry 与其他临时文件默认在 E:\AI_Agent\.runtime\m04-recheck\calibration\，脚本显式设置 TEMP/TMP/tempfile.tempdir 到该目录。

取数全经 Registry.readable(raw=False)。PCA 默认 32 行、5 分量，batch_size=32×samples；每次读取的源映射只存活于该次行块读取，不将原始光谱块跨迭代驻留。PCA 使用可丢弃的读缓冲区原地中心化，copy=False 只控制临时副本，不改变批次、浮点精度或算法。transform 后的 float32 特征填满，再从该驻留图测 float64 累加的 mean/std，原地 z-score、clip±3、映射 [0,1]。

表中 n/area_cv/R 均针对细分前 segments；触发数和 n_after 单独记录。k=3、n_segments=800、block_size=32、特征口径版本及显式 SLIC 标志随每行落盘，数值来源为卡 §5.2 与开工令。

R 的两份实现分别位于引擎 boundary_ratio 和标定脚本 independent_ratio：固定 PCA-5 的 clip 之前 z-score 特征、水平/垂直四邻域、逐对平方欧氏距离的均值比。脚本逐格与引擎复算对比；sum_ratio_diagnostic 仅用于排查“求和比”误写，不作为 R。

内存数值单位均为字节。baseline_rss_bytes 与 peak_rss_bytes 取 Windows GetProcessMemoryInfo 的 WorkingSetSize/PeakWorkingSetSize，peak_rss_delta_bytes=peak-baseline；不清空工作集，不通过抬高基线来降低增量。feature_bytes 为用于 SLIC 的特征图本身；resident_feature_bytes 另计 pre-clip z-score 参照图，允许驻留依据为卡 §11.4。全量原始 float64 cube 的对照量为 231×640×200×8=236,544,000 字节。

summarize.py 检查网格完整性、版本和实参，并按现有 §6.1 的 n/area_cv/R/细分断言汇总各档通过数；不会为选参修改验收阈值。summary.json 为本次表的派生结果。选择依据及实际内存范围另见 ../10.2/calibration-checklist.md。

PCA=3 的回归另行运行；R 仍使用独立的 PCA-5 参照图，分割特征与参照特征不混用。独立进程补测记录在 pca3-baseline.json，不混入默认 5 分量的 55 行标定表。

源代码提交：fa44fe8af3ef0374154a91a539b3d98b6af02412。固定 seeds_20.json 与本阶段标定无关，未读取其中坐标进行选参，也未修改或重生成。
