# 11.3 回执

事实源：同提交 TASK-05-预处理.md，294 行，R1–R12；§2.4 / §2.5 / §2.6 / §3 / §5。

## 文件逐路径

- TASK-05-预处理.md：纳入科祥已落盘 R12 工作区版本，执行者未改卡。
- backend/paths.py：仅新增派生 preprocessed property。
- src-python/spectrumagent/preprocess/registry.py：仅 axis=null 前置分支；工作轴 None，摘要两字段 null，原非 null 校验路径不改。
- src-python/spectrumagent/preprocess/schema/__init__.py：AxisVector 与三处类型替换；新增 PcaParams/MnfParams/IcaParams/ContinuumParams，旧六模型不改。
- src-python/spectrumagent/preprocess/__init__.py：四个新算子 v1 注册及对应导入。
- src-python/spectrumagent/preprocess/operators/pca.py
- src-python/spectrumagent/preprocess/operators/mnf.py
- src-python/spectrumagent/preprocess/operators/ica.py
- src-python/spectrumagent/preprocess/operators/continuum.py
- src-python/spectrumagent/preprocess/run.py
- src-python/spectrumagent/preprocess/compare.py
- src-python/tests/preprocess/test_registry.py：仅集合字面量一行九→十三，完整相等断言保留。
- src-python/tests/preprocess/run_fixtures.py：固定合成原始 DN / 三态 label_map 夹具。
- src-python/tests/preprocess/test_decomposition.py
- src-python/tests/preprocess/test_continuum.py
- src-python/tests/preprocess/test_run.py
- src-python/tests/preprocess/test_compare.py
- milestone05/evidence/11.3/capture.py
- milestone05/evidence/11.3/capture-output.txt
- milestone05/evidence/11.3/run-evidence.json
- milestone05/evidence/11.3/ica-report.json
- milestone05/evidence/11.3/pytest-full.txt
- milestone05/evidence/11.3/authorized-existing.diff
- milestone05/evidence/11.3/receipt.md

## 测试与执行模式

全量结果见 pytest-full.txt：573 passed / 0 failed / 0 skipped；10 条既有依赖弃用警告。新增 63 项，既有 510 项保留；11.1 既有 94 项仅授权集合行扩展，其余不改。

执行模式：仓库根 E:/AI_Agent，.venv/Scripts/python.exe -m pytest，默认参数、默认执行顺序；同一 PowerShell 命令设置 PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp，运行 backend/tests src-python/tests -q。未用 pytest.exe、未增加依赖、未改 pytest 配置或过滤断言。

新增测试落点：test_decomposition.py（21）、test_continuum.py（4）、test_run.py（33）、test_compare.py（5）；数字为本次实际参数展开计数，合计 63。

最初定向执行发现 sandbox 对 pytest-current 清理路径无权限，日志保留在 .runtime/m05-11.3/pytest-targeted-sandbox.txt；以相同测试模式获准访问该本地临时目录后正常完成。此前误引未声明 psutil 已移除，复用 #04 原有 memory_bytes，未安装任何包。最终全量证据均为正常退出。

## §5 逐条自验

| 卡 §5 关键词 | 结果与证据 / 测试 |
|---|---|
| B08 三法、载荷、得分、累积方差、random_state、复现 | test_decomposition.py 的三法参数测试：投影得分数值、载荷符号、无轴摘要、两次 1e-12；ICA params 固定种子，registry.run random_state 预留不传。PCA 统一两遍协方差 eigh；MNF 统一 R12 重构。ICA 方差诊断在 meta 明标“实现层非正交重构能量口径”。|
| MNF R12 独立公式对拍、pinv | test_mnf_independent_full_r12_formula_eigenvalues_and_scores 独立算 Δ、ΣΔ、ΣN、W、C、特征值及得分；另有奇异零噪声矩阵测试。|
| B09 两方法、端点与自动顶点 | test_continuum.py 两方法固定端点/上凸包自动顶点、输出轴不变；零分母 NaN 与 zero_continuum_bands 实跑。|
| B10 逐像素输入、禁 sample_spectrum | test_compare_reuses_run_and_sql_authorizer_explodes_aggregate_reads monkeypatch backend.database.open_database，覆盖所有 connect_database 别名。先实跑拼接 SQL 并确认被 SQLite authorizer 拒绝，再运行两个配方，确认无任何该表读取。夹具故意不提供历史 spectra.npz。|
| B10 三指标、Fisher 主排序、三边界 | test_metrics_pixel_snr_quantiles_pooled_pairwise_fisher_and_three_boundaries 独立公式对拍；真实 run 复用比较测试验证按 Fisher 排序；每报告含三边界。类内量明确为 population covariance trace 的像素数加权均值（实现层口径）。零方差类仅从 Fisher 排除，原始三指标保留全部有限类。|
| 未标注降级、NaN 与零 RMS | test_zero_variance_nan_and_unlabeled_explicit_limits、test_unlabeled_real_run_only_snr_no_sample_spectrum；无标签只 SNR，含局限标注，无聚合样本；恒谱零 RMS 计 snr_nan_count，NaN 谱整条跳过并计数。|
| run 四态、failed error | test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success / test_running_state_is_committed_and_failure_error_is_as_dict：pending 落库、running 已提交、成功/失败收尾，error 与注入 DataError.as_dict 完全相等。同步执行，无后台任务。|
| B01 raw / 真分支 / 反射率量级 | test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success 监测每次 raw=True、每次 read_region 不超 block_size、禁止 to_numpy；mean/std 与原始 DN / 65535 逐像素计算对拍，非二次除 scale。float passthrough 与后续块值域分歧、reference 缺参考、预检失败无 run 另验。|
| STALE 首次 run 真触发 | test_stale_really_triggered_before_pending_and_other_version_works：删 v1 后 409、无 pending 行；v2 正常；test_run_version_dispatch_preserves_new_impl_not_builtin_name 防止按同名算子误用 v1 实现。|
| R12 换 block_size 拟合不变 | test_global_fit_independent_of_disk_block_size：Standard/MinMax/PCA/MNF/ICA 与组合链，block_size=1/7，谱均值/标准差、全部 step records、拟合参数、投影得分、指标逐元素/完整相等。逻辑行归约次序固定，磁盘块边界不进入数学拟合。|
| B05 scaler_params / 指纹重算 | test_standard_fitted_matches_global_pixel_formula_and_not_block_fit：逐波段全局参数独立对拍；常数波段三种零策略另验。test_actual_content_hash_and_annotation_version_change_fingerprint 与 test_annotation_version_fingerprint_and_fitted_recomputed：真实内容换一个字节、切标注版本/像素集后指纹变化、参数重算，换回原版本复现。源文件分别只流式哈希一次。|
| 双 artifact、路径/hash、失败无半份 | 成功仅 sample_spectra + report；相对 POSIX 路径、内容 sha256 实核；test_publication_failure_rolls_back_both_artifacts 与 test_artifact_db_insert_failure_rolls_back_rows_and_files 分别覆盖文件发布第二步失败与 DB 登记失败。失败无登记行、无残留 run 目录。|
| 血缘 | test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success 实际 JOIN cube→annotation_version→recipe_version→preprocess_run→artifact。未读历史聚合谱。|
| R10/R12 数值边界 | AxisVector 三个单波段字段在 schema 层拒绝、旧单波段 MSC reference 可用；降维缺 n_components / 0 / 大于 bands 均结构化拒绝。test_b08_run_nan_fit_exclusion_and_input_provenance_count 验三法排除 NaN、变换全 NaN、原输入数与剔除数分报。|

## 实际 run 行及内存

完整实际行（含 scaler_params 全列表、metrics、error、artifact 登记）见 run-evidence.json；数值由 capture.py 重跑生成。

固定夹具：24×5×8、uint16 原始 DN、scale_factor=65535、选中像素 110，出处 tests/preprocess/run_fixtures.py。属于实现层合成验证，**不冒充人工标注质量或真实 cube 性能**。

示例 StandardScaler run：

```json
{"id":"3eb2ee06-b046-4576-8913-132559a9407e","status":"succeeded","b01_branch":"scale","input_fingerprint":"2909b5f3e04d7fca69fe52c79c2c2bc5dcdbf37ea3c786786278a6ebb5fe03ed","annotation_version_id":"7878a304-efbe-4ba9-a7dc-48d9bffd41ae","scaler_params_first_band":{"mean":0.31156730962636203,"std":0.18607502614580135}}
```

scaler_params 为八个逐波段 mean/std 对象完整列表，取本次 standardize step meta.fitted，无替代供值路径。无 standardize 时为 SQL NULL。

ICA 复现：同夹具、同配方、block_size=1/7，实际得分最大绝对差 **0.0**（原验收 1e-12，无放宽）；暂存累计/峰值均 **7,040 bytes**（110×8×float64 8 bytes）；进程峰值 RSS **145,223,680 bytes**，测量来源 #04 已有 Windows GetProcessMemoryInfo.PeakWorkingSetSize。见 run-evidence.json / ica-report.json；finally 后无 .tmp 或 dat 残留。

实际产物字节：Standard report 3,462 / sample_spectra 1,529；ICA report 4,219 / sample_spectra 1,274。均由 capture.py 对实际产物 stat 记账，非阈值或预算。run 输入指纹用内容流式 sha256，未以 stat 冒充。

run 必填列供值：id=新 UUID；cube_id=验源成功登记 id；annotation_version_id=存在且属于 cube 的显式版本；recipe_version_id=存在且算子版本可解析的显式版本；b01_branch=B01 首块真实判据；input_fingerprint=本次源内容哈希+标注版本+所选像素数的 R3 算法；status=四态；created_at=UTC 当前时间。finished_at/error 在成功/失败收尾，scaler_params 仅来自对应 step meta.fitted；artifact id/run_id/kind/path/hash/created_at 由本次成功产物供值，同一短事务登记两份并提交 succeeded。

## 边界与停止点

无路由、Rust、前端、#04 过闸文件修改；无新增依赖。seeds_20.json SHA256 保持 388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2。公司两文档不入库。任务卡 R12 按授权随本提交入库。

本阶段无待裁定口径；完成 11.3 后停止，等待复核，不开 11.4。
