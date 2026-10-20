# 10.2 标定回填与内存验收回执

R14 与引擎代码已先提交：fa44fe8af3ef0374154a91a539b3d98b6af02412。本次随后单独完成 55 格标定、PCA-3 独立补测、任务卡授权回填与最终回归；未进入 10.3。

## 文件清单（相对于 E:\AI_Agent，逐路径）

先前 R14/引擎提交：

- TASK-04-标注L1.md
- docs/release-notes-v0.1.2.md
- src-python/spectrumagent/api/registry.py
- src-python/spectrumagent/api/annotations.py
- src-python/spectrumagent/api/openapi.json
- src-python/spectrumagent/app.py
- src-python/spectrumagent/annotation/engines/__init__.py
- src-python/spectrumagent/annotation/engines/superpixels.py
- src-python/tests/annotation/test_labels_api.py
- src-python/tests/annotation/test_superpixels.py
- src-python/tests/annotation/test_source_changed_r14.py
- milestone04/evidence/calibration/calibrate.py
- milestone04/evidence/10.2/pytest-r14.txt
- milestone04/evidence/10.2/r14-checklist.md

本次标定回填提交：

- TASK-04-标注L1.md
- milestone04/evidence/calibration/README.md
- milestone04/evidence/calibration/cubes_11.txt
- milestone04/evidence/calibration/compactness.csv
- milestone04/evidence/calibration/summary.json
- milestone04/evidence/calibration/summarize.py
- milestone04/evidence/calibration/pca3-baseline.json
- milestone04/evidence/10.2/calibration-run.txt
- milestone04/evidence/10.2/calibration-checklist.md
- milestone04/evidence/10.2/pytest-final.txt

## 执行模式与测试数

最终完整回归：231 passed、0 skipped、10 条第三方弃用警告，20.22 秒（pytest-final.txt 实测）。与用户指定跑法一致：仓库根 E:\AI_Agent，同一 PowerShell 调用设 PYTEST_DEBUG_TEMPROOT=E:\AI_Agent\.runtime\pytest-tmp，然后 E:\AI_Agent\.venv\Scripts\python.exe -m pytest backend/tests src-python/tests -q；无筛选、无并行、无额外 pytest 参数。231=202 既有+23 超像素+6 R14。六项测试名称与断言逐项见 r14-checklist.md。

标定：现有 Python 环境、真实 11 cube、CPU、每格独立进程、默认 n_segments=800/pca_components=5/k=3/block_size=32；仅 compactness 按开工令网格变化。无数据替身、无安装或依赖变化。临时 registry/文件只在 E 盘。calibrate.py 与 summarize.py 可独立重跑，步骤见 calibration/README.md。

## 对应卡 §6 自验

1. §6.1 超像素结构：55/55 格完成；m=0.5 时 11/11 cube 同时满足现有 n/area_cv/R/细分断言。其余四档通过数均为 0，故保留默认 compactness=0.5，没有修改断言阈值。PCA-5 细分前 n=751–768，area_cv=0.1769761260–0.2106243543，R=1.7521929475–1.8307364422；触发数 55–71，细分后 n=809–838（来源：compactness.csv/summary.json，实现层实测）。
2. §6.1 双设置与强制参数：PCA-5 pe 基线 n=765→830、触发64；PCA-3 pe 基线 n=773→839、触发63、area_cv=0.1724213897、R=1.6236270632。两者 n 均在 689–842，R≥1.5、area_cv≥0.10；SLIC 所有全局/局部调用强制 convert2lab=False、enforce_connectivity=True，channel_axis=2/start_label=0，未暴露到 API（来源：CSV、pca3-baseline.json、test_lab_forced_false_and_connectivity_all_slic_calls）。
3. §6.1 细分：按原谱 std 向量均值 d_s、tau=k×median(d_s)、d_s>tau 且像素≥8；n_sub 半面积公式不变，仅改父区域像素，邻居 id 逐像素原样保留，父子关系返回。统计与触发集合在实跑测试中直接对位；未加体量门槛，未为验收调 k。
4. §6.1 R 防误写：引擎与脚本独立实现固定 PCA-5 pre-clip z-score/四邻域/平方欧氏距离均值比；55 格逐一复算一致。pe 基线 R=1.8282458263，求和比诊断值=0.2013874494，与卡的约1.8/0.20锚点一致。PCA-3 分割的 R 仍以 PCA-5 作参照，不将3分量分割特征改作参照。
5. §6.1 响应与场景：POST superpixels 返回实参（含 block_size、pca_batch_size、k、特征口径版本）、d_s/tau、细分前后数与父子关系、降采样 PNG≤512；不返回全分辨率数组。启动/导入/分割后 scene 行仍为0，无自动赋标或 annotation 写入。
6. §6.2 特征：两遍独立行块读取、不缓存原始块；原地统计、z-score、clip±3、映射[0,1]。独立 transform 复算统计误差≤1e-6；真实基线 PCA-3/5 的 min/max=0/1、分量均值[0.45,0.55]、std在(0,1/6]。原谱均值/std 聚合另有像素直接计算对照。源读取仅用 Registry.readable(raw=False)，全部读数经 read_region。
7. §6.3 默认PCA-5内存：feature_bytes=2,956,800；另计 pre-clip 参照，resident_feature_bytes=5,913,600。55 个独立进程的峰值 RSS=308,936,704–310,222,848字节，较各自基线增量=176,656,384–177,893,376字节；最大增量为原始float64 cube对照236,544,000字节的75.2052%（低24.7948%）。单元总耗时3.4316–5.8294秒。来源：CSV/summary.json，实现层实测；耗时不当作固定承诺。
8. §6.3 PCA-3补测：feature_bytes=1,774,080，含独立PCA-5参照的驻留特征总量6,504,960字节；峰值RSS=333,590,528字节、基线132,558,848字节、增量201,031,680字节。它额外运行PCA-5参照提取，因此单列，不能拿默认5分量的177.89MB替代此配置。来源：pca3-baseline.json，实现层实测。两配置的源读取均逐行块限界，未物化原始立方体；内存证据同时给出OS峰值与有界读取测试，未清空工作集或抬高基线。
9. §6.4 R14：六项全绿，read_header 失败包装 SOURCE_CHANGED，保留原码/detail/path/异常链；字段比对、get()、导入 candidates() 与 reader 既有行为保持。未知id HTTP404，已登记源不可用 HTTP400。v0.1.2 release notes 已记账。
10. §6中扩散/会话/保存/质量校验/Rust/前端项本阶段不适用，未实现或声称已验；§6.3仅授权回填扩散规模，未测扩散耗时。不运行桌面/VM人工冒烟。

## 回填与纪律

任务卡由505行变506行：仅修改§5.2 compactness标定描述、§6.1 n/area_cv/R实测基线、§6.3扩散规模，并在§12追加“10.2 标定回填”行；其余段落已逐段比对不变。验收阈值、余弦口径及所有其他条款未改。

不新增依赖、不安装、不下载、不打tag、不推远端、不操作Release。固定种子未改、未生成，SHA256仍为388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2；两份公司文档与固定种子不入库。

未决口径问题：无。10.2交付完成，停在此阶段等待科祥复核；不抢跑5.3或10.3。
