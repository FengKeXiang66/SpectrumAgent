# 10.3 会话 / 版本 / 聚合 / 质量校验回执

## 范围与来源

事实源：用户提供的 TASK-04 R17（522 行）。执行开始与完成的文件 SHA-256 均为
`EBC8C08815F0B0938F523B898EC202E279245E9F1BA927D215E763BD6AB8ACD1`。
任务卡未由执行者修改；提交仅原样收录用户已给定的 R15–R17 修订，以保证 DDL 逐字测试与源码一同可复核。
`migrations.py` 只有 R16 granularity 注释同步，零 SQL 语义变化。

没有路由、Rust、前端或扩散引擎改动。没有新增依赖。质量校验模块没有 KMeans，也不产生标签；
KMeans 仅在获准的阈值标定测试脚本内，合成标注不保存为 annotation 行。

## 测试模式与结果

从 `E:/AI_Agent` 一条 PowerShell 命令执行：

```powershell
Set-Location -LiteralPath 'E:/AI_Agent'
$env:PYTEST_DEBUG_TEMPROOT='E:/AI_Agent/.runtime/pytest-tmp'
& E:/AI_Agent/.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q
```

默认参数；未选择测试、未跳过、未加 xdist、未加 basetemp。实际结果 **261 passed, 10 warnings in 21.48s**，
231 既有 + 30 新增（session 22、quality 8）。完整输出见 `pytest-full.txt`。
10 个 warning 均来自既有依赖的弃用提示，无安装行为。

首次定向试跑发现测试误用了不存在的 `dataset.raw`，已改为校验真实的
`metadata.value_mode == 'reflectance'`。沙箱读取已有 pytest-current 链接受限，
后续经工具审批在沙箱外运行相同 python/参数；不改测试跑法。最终全量退出码为 0。

## 新测试落点（实际用例数）

`src-python/tests/annotation/test_session.py`：

| 测试函数 | 用例数 | 核验 |
|---|---:|---|
| test_snapshot_replay_spectra_counts_params_and_lineage | 1 | 回放、1e-10、像素数、实际参数、三表血缘、sample/manual、scene=0、NOT NULL |
| test_relative_snapshot_path_three_files_and_no_source_writes | 1 | POSIX 相对路径、三件快照、原始文件不变 |
| test_aggregate_bounded_reflectance_shared_io_no_full_cube | 1 | Registry.readable 反射率、32 行界限、禁 to_numpy、save 与 quality 共享聚合 |
| test_spectra_cross_row_blocks_mean_std_match_pixels_1e10 | 3 | 1/7/32 行块、跨块累计均值和 std 与按像素计算误差 ≤1e-10 |
| test_five_undos_deep_copy_statistics_and_edit_after_restore | 1 | 六次编辑后撤销五次、深拷贝、现算统计、撤销后编辑、空栈 409 |
| test_parameter_change_preserves_three_states_clears_candidates | 3 | n_segments/compactness/pca_components 各变一次，保留三态像素并清候选 |
| test_label_tie_order_history_frozen_and_working_undo_remapped | 1 | sort_order 并列按 code、工作态按 label_id 重映射、历史映射不变 |
| test_overwrite_latest_deletes_stale_rows_updates_note_keeps_created_at | 1 | 仅最新版本、旧行先删、新行唯一、params/计数更新、note、created_at 保留 |
| test_overwrite_conflicts_no_version_or_missing_confirm | 3 | 无版本/缺 confirm 均为结构化 409 |
| test_db_failure_rolls_back_rows_and_snapshot_publication | 2 | 新建/覆写注入 SQLite 失败：DB 和三件快照恢复，无临时垃圾 |
| test_snapshot_write_failure_never_publishes_or_inserts | 1 | 注入磁盘写失败不落版本、不发布残缺目录 |
| test_working_memory_only_and_empty_snapshot_three_states | 1 | 仅不确定/留白不产生样本；新实例工作态为空；无超像素错误 |
| test_source_changed_during_save_is_not_hidden_by_working_cache | 1 | 删源后的 save 仍报 SOURCE_CHANGED，版本不落库 |
| test_save_reads_before_write_transaction_and_publishes_tmp | 1 | 每次原谱读取时另连接可 BEGIN IMMEDIATE；.tmp 三件齐全后 os.replace |
| test_cube_working_states_and_candidate_queues_are_independent | 1 | 每 cube 工作态及候选隔离，像素并集统计 |

`src-python/tests/annotation/test_quality.py`：

| 测试函数 | 用例数 | 核验 |
|---|---:|---|
| test_mixed_superpixels_partial_means_original_spectra_exclude_negative | 1 | 混合块部分均值、独立原谱余弦、-1/-2 排除、三分完整度、不适用项 |
| test_quality_recomputes_current_means_ignores_saved_sample_spectrum | 1 | 修改工作态后现算；历史谱键损坏且禁 np.load 仍可校验 |
| test_high_variance_same_definition_as_engine_current_segments | 1 | 当前 segments 的原谱 std→d_s→3×median；实际高方差触发 |
| test_default_threshold_provenance_real_cube_synthetic_behavior_only | 1 | 默认值与实测 p05 一致，来源/用途、非空非全量、植入离群行为证据 |
| test_invalid_quality_threshold_structured | 3 | 越界与 NaN 结构化错误 |
| test_bounded_aggregation_constant_spectra_stable_population_std | 1 | 跨块常数谱 std=0，无 sumsq 消减误差 |

## §6 checklist 自验

1. §6.2 label_map 回放：保存后逐像素相等，int32 和 label_index 映射一致。
2. §6.2 样本谱：float64 mean/std；按原谱像素独立计算，绝对容差 1e-10；跨行块重复核验。
3. §6.2 三态：-1/-2/≥0 各自统计；-2 不计入 labeled_pixels、annotation、sample_spectrum 或离群部分均值。
4. §6.2 params：保存 segmentation.report 的实际参数，包括 n_segments、compactness、pca_components、k、block_size、feature_version、pca_batch_size；换参数和覆写都核验。
5. §6.2 pixel_count：直接数 label_map；混合块两类的 geometry 都为空，但像素数各为 40（单测夹具），证明不从 geometry 反推。
6. §6.2 血缘：dataset_registry.id → annotation_version.cube_id/id → sample_spectrum.cube_id/version_id 逐项匹配。
7. §6.1 覆写无脏行：同一 version_id 删除两表旧行再写；有像素 label 各一行；版本号不变、旧历史版本不变；note.event=overwrite，at 为 UTC，created_at 保留，快照等于工作态。
8. §5.5 质量报告：可疑清单含 (superpixel_id,label_index,pixel_count,cos)，混合块不跳过；独立调用和保存调用一致；显式标注“标签与聚类中心冲突”“类间重叠”均“无模型阶段不适用”。
9. §6.1 粒度：测试落库 annotation 全为 sample/manual；scene 行数 0；不产生自动 annotation。
10. §6.1 工作态：五步撤销深拷贝、统计现算、继续编辑不错位；三种参数变更保留像素标签和 -2、候选清空；样品主标签仅从工作态统计推导，不加列。
11. §6.2 既有 PCA z-score 断言：本阶段未改引擎；既有测试在上述 261 项全量中继续通过。

## 三表全部 NOT NULL 列与主键供值

| 表 | 列 | 供值来源 |
|---|---|---|
| annotation_version | id（主键） | 新建 uuid4；覆写复用最新版本 id |
| annotation_version | cube_id | 调用方已登记 cube_id，经 Registry.get/readable 校验 |
| annotation_version | version_no | 服务端 max+1；覆写最新值不变 |
| annotation_version | snapshot_ref | 服务端生成 `<cube_id>/v<n>`，相对 snapshots 根、POSIX |
| annotation_version | n_pixels | 当前 label_map.size |
| annotation_version | labeled_pixels | 当前 label_map ≥0 的像素数 |
| annotation_version | auto_ratio | 卡内阶段一规则：0 |
| annotation_version | params | 本次 segmentation.report['params']，JSON 序列化 |
| annotation_version | created_at | 新建时服务端 UTC now；覆写保留首次值 |
| annotation | id（主键） | 每条聚合行 uuid4，不是编辑事件 id |
| annotation | cube_id | 同已校验 cube_id |
| annotation | version_id | 本次新建/覆写版本 id，FK |
| annotation | granularity | R16：sample |
| annotation | pixel_count | 当前 label_map 对应 label_index 直接计数 |
| annotation | source | 卡内阶段一规则：manual |
| annotation | created_at | 本次服务端 UTC 时间 |
| sample_spectrum | id（主键） | 每条聚合谱行 uuid4 |
| sample_spectrum | cube_id | 同已校验 cube_id |
| sample_spectrum | version_id | 本次版本 id，FK |
| sample_spectrum | sample_code | Registry.get 返回的 dataset.name |
| sample_spectrum | n_pixels | 共享分块聚合的对应 label 像素累计数，与 label_map 直接计数核对 |
| sample_spectrum | mean_ref | spectra.npz 的 mean_<label_index> 键 |
| sample_spectrum | std_ref | spectra.npz 的 std_<label_index> 键 |
| sample_spectrum | created_at | 本次服务端 UTC 时间 |

两张子表虽然 label_id 非 NOT NULL，但均由冻结的 label_index→项目 label.id 映射供值，满足 CHECK；label_value=NULL。
annotation 的 confidence/evidence/annotator_id 均 NULL，不造模型值。
annotation_version.note 新建 NULL，覆写为 R17 指定 JSON，与旧行重写同一事务 UPDATE。
所有连接复用 backend.database.connect_database，每连接 PRAGMA foreign_keys=ON。

## cos 阈值标定（实现层默认、可调）

出处：`quality-calibration.json`；可独立复跑：

```powershell
& E:/AI_Agent/.venv/Scripts/python.exe src-python/tests/annotation/calibrate_quality.py --output E:/AI_Agent/.runtime/m04-quality-recheck.json
```

真实 cube：pe/20260804205214_64，(231,640,200)，m=0.5、默认 PCA-5、800 目标段、32 行块、k=3，最终 830 段。
KMeans(n_clusters=4,random_state=0,n_init=10) 仅生成内存合成标注；对原谱块均值分组，比较谱是对应合成 label 的当前像素加权均值。
不得当作人工标注或标注质量结论。产品代码没有聚类赋标路径。

| 分位 | cos |
|---|---:|
| min | 0.5034724552823012 |
| p01 | 0.8030876563997569 |
| p05 | 0.8579512304124653 |
| p25 | 0.9168479519177143 |
| p50 | 0.9480581298267907 |
| p75 | 0.9722828148591671 |
| p95 | 0.9850188576232852 |
| p99 | 0.9906809361265448 |
| max | 0.9945834710577047 |

实现层选实测 p05 为默认 **0.8579512304124653**，可调；低于阈值 42/830 = 5.06024%，既非空也非全量。
植入 (superpixel_id=786,label_index=3) 被检出。所有这些数值均为本轮实现层实测，非需求硬常数。
PCA 特征图 **2,956,800 字节**；完整合成标定进程峰值 RSS **315,916,288 字节**。
该峰值包含解释器、引擎、KMeans、分块聚合与质量检查，不是原谱立方体大小；原谱读取实现及测试均限制 32 行，不调用 to_numpy。

保存耗时另见 `save-timing.json`：40×12×200 单测夹具，真实 SQLite/文件 I/O，含聚合和质量校验 **0.0204184 s**，写事务 **0.0051846 s**。
这是夹具实测，不冒充 231×640×200 实测。测试还在每次原谱读取时让另一连接成功 BEGIN IMMEDIATE，证明聚合不占写事务。

## 文件与边界

实现：backend/paths.py；src-python/spectrumagent/annotation/session.py、quality.py、migrations.py（仅注释）。
测试：src-python/tests/annotation/conftest.py、test_session.py、test_quality.py、calibrate_quality.py。
证据：本 receipt.md、quality-calibration.json、save-timing.json、pytest-full.txt。
任务卡：用户提供的 R17 原样收录，执行者未改字。

seeds_20.json SHA-256 保持 `388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`，
与根目录两份公司文档一同保持未跟踪，不入提交。按路径逐文件 git add。

无待决口径问题。10.3 完成后停止，等待复核；10.3.5 仅就绪，不开工。
