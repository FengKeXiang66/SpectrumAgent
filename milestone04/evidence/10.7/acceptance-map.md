# 10.7 验收清单映射

事实源：当前 `TASK-04-标注L1.md` §6.1–§6.4（552 行；R21 采用科祥随后裁定的既有 uuid() 严格校验 + to_ascii_lowercase() + set_query）。本阶段不改卡。下列路径相对仓库根 `E:/AI_Agent`；测试名是现有测试的精确定位，不表示额外新增 pytest 用例。自动化已验项与人工缓测分开记录。

## 执行模式与证据索引

| 模式 | 实际执行与结果 | 证据（本目录内） |
|---|---|---|
| P1/P2 | 仓库根、同一 PowerShell 调用设 `PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp`；`.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`；默认参数、无筛选/并行；两轮各 340 passed / 0 failed / 0 skipped，每轮 10 条既有第三方弃用警告 | `pytest-full-1.txt`、`pytest-full-2.txt` |
| F | `flake_smoke.py`：仓库根 python -m pytest，指定 rollback 测试，默认 False/True 两种参数，每次新进程，串行重复 10 轮；20/20 passed | `flake-summary.json`、`flake-output.txt`、`flake-01.txt`…`flake-10.txt` |
| H | `e2e.py`：真实独立 source sidecar，`python -m backend --data-root <E盘隔离目录>`，真实 loopback HTTP，Bearer 与响应身份校验；默认超像素/扩散参数，无 TestClient、引擎替身或自动赋标 | `e2e.py`、`e2e-output.txt`、`e2e-result.json` |
| C | `cargo test`，默认并行，无筛选/feature/线程数覆盖；37 个单元/集成测试 + 1 compile-fail doctest = 38 passed / 0 failed | `cargo-test.txt` |
| N | Node 24.19.0 内置 runner：`node.exe --test src/components/datasets/*.test.ts src/components/annotation/*.test.ts`；默认执行，31 passed / 0 failed / 0 skipped | `node-test.txt` |
| B | `npm run build`（tsc --noEmit && vite build）；`cargo clippy --all-targets -- -D warnings`；`cargo check --release`；均退出 0，Clippy 零警告 | `build.txt`、`clippy.txt`、`cargo-release-check.txt` |
| A | `release_boundary.py`，静态逐字/配置/锁文件审计；保留六命令断言，产品版本改验 0.1.2，握手 0.1.0 不变；历史审计和历史输出未重写 | `release-boundary.json`、`release-boundary-output.txt` |
| K | 10.2 既有真实 11 cube × 五档标定，每格独立进程、默认其余参数；PCA3 另测；本次 P1/P2 重跑真实默认 PCA3/5 测试 | `../calibration/compactness.csv`、`../calibration/summary.json`、`../calibration/pca3-baseline.json`、`../10.2/calibration-checklist.md` |

C/B 的 Cargo 使用现有 `CARGO_HOME=E:/AI_Agent/.cargo-home`、`CARGO_TARGET_DIR=E:/AI_Agent/src-tauri/target/milestone03`、`CARGO_NET_OFFLINE=true`；不安装、不下载。TEMP/TMP 与测试临时根均在 E 盘。两轮全量回归与 release 检查有并发运行；H 的时延测量独立运行，不与它们重叠。P2 较 P1 更慢不能解释为产品性能退化。

## §6.1 功能（逐条）

下表 Python 路径前缀 `src-python/tests/annotation/`，Node 前缀 `src/components/annotation/`；H 对应真实 HTTP 独立证据。

| 卡内条目 | 测试 / 证据文件 / 模式 | 自验结果 |
|---|---|---|
| 迁移幂等、project_id 存在且既有行回填 | `test_storage.py::test_two_startups_backfill_existing_registry_without_replacing_payload`；P1/P2 | 通过；两次完整 app 启动，表/种子/登记 payload 比较一致 |
| 四预置标签与塑料目录 21 条、含 PS/PVC | `test_labels_api.py::test_post_three_shapes_and_tree`、`test_storage.py::test_catalog_colors_and_names_match_card`；P1/P2 | 通过 |
| 18 个规则 hex 与三预置色逐点一致 | `test_storage.py::test_catalog_colors_and_names_match_card`；P1/P2 | 通过；包括 HLS 复算与卡表比对 |
| POST labels 三种 body 成功；互斥/缺字段/缺 color_hex 422 | `test_labels_api.py::test_post_three_shapes_and_tree`、`test_missing_and_mixed_contracts`、`test_custom_missing_fields`；P1/P2 | 通过；认证与身份断言、完整端点集断言仍在 |
| schema 精确匹配、目录路径与序号、自定义 max+1、预置路径/序号 | `test_storage.py::test_custom_empty_project_sort_and_precise_schema_match`、`test_schema_and_seed_identity_survive_restart`；`test_labels_api.py::test_post_three_shapes_and_tree`、`test_unknown_project_and_non_enum_schema_fail`；P1/P2 | 通过；R13/R17 排序仍确定 |
| 超像素 n 为细分前输出；PCA3 与 PCA5 两设置均在基线范围 | `test_superpixels.py::test_real_baseline_default_parameters`（3/5 参数）；P1/P2、K、H.superpixels | 通过；H 默认 765→830；PCA3 独立基线见 K，未把细分后 n 设 ±10% |
| area_cv ≥0.10 | 同上；K CSV 的 m=0.5 行 | 通过；真实默认测试同时断言 |
| R≥1.5；PCA5 z-score、四邻域、平方欧氏均值比，约1.8/0.20 自检 | `test_superpixels.py::test_ratio_is_mean_ratio_with_fixed_pca5_reference`、`test_real_baseline_default_parameters`；P1/P2、K | 通过；引擎与标定脚本分别实现并复算，未用求和比代替 |
| d_s/τ 触发集合一致且≥1、半面积细分、只重写父区域、记录前后 n | `test_superpixels.py::test_refinement_preserves_neighbours_and_records_parent_children`、`test_bounded_reads_two_pca_passes_and_original_statistics`、`test_real_baseline_default_parameters`；P1/P2、H、K | 通过；H 报告保留 d_s、τ、父子关系与实参 |
| 超像素实际参数、特征版本与降采样 PNG | `test_superpixels.py::test_superpixel_http_report_and_no_scene`、`test_lab_forced_false_and_connectivity_all_slic_calls`；P1/P2、H | 通过；convert2lab 强制 False，不暴露请求字段；H 解码 PNG≤512 |
| scene 恒0、annotation 全 sample；场景信息沿登记 payload | `test_storage.py`、`test_superpixels.py::test_superpixel_http_report_and_no_scene`、`test_session.py::test_snapshot_replay_spectra_counts_params_and_lineage`、`test_routes.py::test_validate_save_list_uuid_overlay_note_overwrite_and_old_version`；P1/P2、H snapshot_oracles | 通过；manual 来源，未写自动/scene annotation |
| 快捷键六用例：BG0、普通1–9、非BG0拒、NULL、10拒、重复UNIQUE拒 | `test_storage.py::test_shortcut_table_check`（13 参数）与 `test_shortcut_unique_and_multiple_nulls`；P1/P2；`shortcuts.test.ts`/N | 六类均实跑通过；未绑定/越界标签仅鼠标选择 |
| 扩散阈值变化、默认0.92可复现 | `test_diffusion.py::test_single_linkage_growth_cos_uv_report_cos_s_drift_default_reproducible`；P1/P2；`test_diffusion_acceptance.py`真实 cube；H | 通过；增长 cos_uv 与报告 cos_s 分工有针对性断言 |
| 单击/框选/涂鸦均有候选 | `test_diffusion.py::test_box_half_open_hits_all_covered_superpixels_and_all_three_prompts_work`、`test_doodle_bresenham_fills_intermediate_pixels_one_pixel_wide`、`test_routes.py::test_diffuse_three_prompts_response_cos_s_queue_effective_defaults`；P1/P2、H | 通过；框半开、Bresenham 后端唯一实现 |
| 确认/修正/橡皮/多边形更新 map | `test_routes.py::test_regions_superpixel_actions_working_statistics_registered_colors`、`test_polygon_centres_even_odd_boundary_included_no_dilation`、`test_polygon_after_superpixels_overwrites_only_selected_centres`；P1/P2、H | 通过；H 另用独立矩形 oracle 逐像素验证最终快照 |
| working 可读回；刷新/切图返回不丢工作态 | `test_routes.py::test_r21_working_queue_readback_is_pure_and_contains_project_and_overlays`、`test_r21_switch_cube_recovers_isolated_queue_without_regenerating_candidates`；P1/P2；`working.test.ts`/N；H | sidecar/API 与前端逻辑已验；实际 WebView 刷新/切图的可见效果缓测 |
| 撤销≥5、栈空409、恢复后新编辑不错位 | `test_session.py::test_five_undos_deep_copy_statistics_and_edit_after_restore`、`test_routes.py::test_five_http_undos_empty_409_then_edit_stays_aligned`；P1/P2、H undo | 通过；深拷贝恢复与统计现算 |
| -2 不确定单列、overlay区分、快照仍-2、不产生annotation | `test_routes.py::test_regions_superpixel_actions_working_statistics_registered_colors`、`test_session.py::test_snapshot_replay_spectra_counts_params_and_lineage`、`test_working_memory_only_and_empty_snapshot_three_states`；P1/P2、H | API/像素/PNG 编码已验；实机视觉效果缓测 |
| 固定20种子队列三断言 | `test_diffusion_acceptance.py::test_real_cube_fixed_twenty_default_queue_three_assertions`、`test_routes_acceptance.py::test_http_fixed_twenty_default_queue_three_assertions`；P1/P2、H fixed_twenty | 默认0.92/0.80：10入队、10拦截、19个 min<0.92；所有入队 min≥0.80。文件哈希不变，未换种子 |
| confirm/uncertain 消费、erase保留、队列仅内存且隔离、pending为像素并集 | `test_diffusion.py::test_existing_session_consumes_confirm_uncertain_candidate`、`test_existing_erase_does_not_consume_queue_pending_is_pixel_union`、`test_queue_owned_by_session_cube_isolation_new_session_empty_response_copies`；`test_routes.py::test_http_candidate_consumption_and_pending_union`；P1/P2、H | 通过；H 独立重算 segments 后校验 pending 并集，不以候选像素数相加替代 |
| 换参数按像素保留已确认/-2，清候选，统计不变 | `test_session.py::test_parameter_change_preserves_three_states_clears_candidates`、`test_routes.py::test_http_resegment_clears_queue_preserves_labels_uncertain_and_statistics`；P1/P2；`working.test.ts`/N | 通过；不在前端自持 map/undo/queue |
| 保存三件与三表、新版本递增、旧版不可改 | `test_session.py::test_snapshot_replay_spectra_counts_params_and_lineage`、`test_label_tie_order_history_frozen_and_working_undo_remapped`；P1/P2、H | 通过；H v1/v2、v1 三文件 SHA 与历史映射不变 |
| 覆写仅最新、须confirm、无版本409、版本号不变、事件入note | `test_session.py::test_overwrite_conflicts_no_version_or_missing_confirm`、`test_overwrite_latest_deletes_stale_rows_updates_note_keeps_created_at`；`test_routes.py::test_no_version_overwrite_http_409`、`test_bad_bodies_geometry_mixed_geometry_400_no_side_effect`；P1/P2、H | 通过；没有历史覆写接口，历史 version 字段作为额外请求字段被拒绝；created_at 保留 |
| 覆写无脏行、每label至多一谱、annotation数=有像素label数、version更新、note可解析 | 同上；F；H snapshot_oracles | 通过；H v2 从三类改为两类再覆写，旧第三类行/谱键均消失 |
| 类均值/标准差与现算一致，容差1e-10 | `test_session.py::test_spectra_cross_row_blocks_mean_std_match_pixels_1e10`；P1/P2；H 独立两遍分块 oracle | 通过；H 精确误差记录在 snapshot_oracles，未放宽容差 |
| 质量清单与不适用显式标注 | `test_quality.py`（混合块、当前态重算、原谱、d_s/τ、合成阈值与植入离群）；P1/P2、H.validate | 通过；报告有可疑清单，“标签与聚类中心冲突、类间重叠”均为无模型阶段不适用；合成标注不作人工质量断言 |

## §6.2 数据正确性（逐条）

| 卡内条目 | 测试 / 证据文件 / 模式 | 自验结果 |
|---|---|---|
| label_map 快照逐像素回放 | `test_session.py::test_snapshot_replay_spectra_counts_params_and_lineage`；P1/P2、H snapshot_oracles | 通过；H 独立脚本构造预期 int32 map，不从保存结果反推预期 |
| 每类原谱均值/标准差分块复核 | `test_spectra_cross_row_blocks_mean_std_match_pixels_1e10`、`test_aggregate_bounded_reflectance_shared_io_no_full_cube`；P1/P2、H | 通过；H 两遍 sums/偏差平方，最多32行，经 Registry.readable(raw=False)，未复用生产聚合函数作为 oracle |
| 三态互不串、不填默认、-2排除聚合/labeled_pixels | `test_session.py::test_working_memory_only_and_empty_snapshot_three_states`、`test_snapshot_replay_spectra_counts_params_and_lineage`；P1/P2、H | 通过；H v1/v2 均保留留白与不确定区，只为实际已标类生成谱键/行 |
| params 与实际生效值一致 | `test_snapshot_replay_spectra_counts_params_and_lineage`、`test_routes.py::test_superpixels_generate_then_sync_before_response_initializes_state`；P1/P2、H | 通过；H DB params 完整等于 superpixels 响应，含 block_size/特征版本/PCA batch |
| pixel_count 直接来自 map，geometry 仅全覆盖超像素追溯 | `test_snapshot_replay_spectra_counts_params_and_lineage`；P1/P2、H | 通过；混合块不进任何 geometry，H 分别校验像素数与全覆盖超像素集合 |
| z-score 独立复算1e-6、[0,1]、均值与std范围 | `test_superpixels.py::test_resident_feature_statistics_independent_retransform`、`test_real_baseline_default_parameters`；P1/P2、K | 通过；未断言 clip 后 std 恒1/6 |
| cube→version→sample_spectrum id 血缘 | `test_snapshot_replay_spectra_counts_params_and_lineage`；P1/P2、H snapshot_oracles | 通过；各谱行 cube_id/version_id/label_id、键名与 sample_code 对位 |

## §6.3 性能（逐条）

| 卡内条目 | 证据 / 模式 | 自验结果 |
|---|---|---|
| 超像素耗时、特征字节、峰值/增量对照、有界读取 | H.superpixels；`performance.md`/`performance.json`；K；P1/P2 有界读取测试 | 实测数均列在性能记录；特征 2,956,800 字节，含参照 5,913,600；增量显著低于原始float64对照236,544,000字节。引用10.2历史值与本次值分开 |
| 细分后默认扩散候选值≤2s | H.fixed_twenty；`performance.json` diffusion_fixed_twenty | 通过；记录引擎与HTTP min/median/max，不改参数、不挑换固定种子 |
| 保存含聚合/质量总耗时，SQLite短写事务；validate单独耗时 | H.saves / H.validate；`performance.md`/`performance.json` | 已以真实pe测量；沿用10.3计时边界；三次新建/覆写均记录，旧夹具数字不冒充真机值 |

## §6.4 异常与边界（逐条）

| 卡内条目 | 测试 / 证据文件 / 模式 | 自验结果 |
|---|---|---|
| 无超像素先扩散结构化错误 | `test_diffusion.py::test_missing_superpixels_structured_without_implicit_generation`、`test_routes.py::test_missing_superpixels_http_structured_and_empty_undo_409`；P1/P2、H | 通过；真实HTTP400/SUPERPIXELS_REQUIRED，未隐式生成 |
| 已登记源移动/改动→SOURCE_CHANGED | `test_source_changed_r14.py`六项、`test_routes.py::test_http_error_envelopes_identity_and_source_changed`；P1/P2 | 通过；仅测试夹具源做删/移/变小操作，真实pe源哈希不变 |
| readable唯一包装点；未知404、原错误context、导入期FILE_NOT_FOUND；preview/band/region兼容 | `test_source_changed_r14.py`、既有 `src-python/tests/data/test_api.py` 与 reader 测试；P1/P2；`docs/release-notes-v0.1.2.md` R14条 | 通过；R14上下文/异常链与get/导入边界保持，发布记账保留 |
| 超8MiB Rust RESPONSE_TOO_LARGE | `src-tauri/src/annotation.rs`/`datasets_dev.rs` 中 `declared_and_streaming_response_limits_are_enforced`、`an_exactly_eight_mib_json_response_is_allowed`；C | 通过；Content-Length 与流式两种超限路径，恰8MiB允许 |
| release annotations_forward可用、无dev泄漏、无账号控件 | A逐字审计、B `cargo check --release`、N组件接线；六命令与ACL一致 | release配置编译与源码边界通过；实际安装包/WebView可见性仍归实机UI缓测，未宣称运行过桌面release |

## 10.4 flake 账目

F 两种参数各10次，20/20通过；随后P1/P2各340通过，零失败、零跳过。按本次重复门槛结清“可复现失败”账目；本轮未复现历史失败，因此不宣称已定位或修复其根因，也没有更改断言、加重试或跳过用例来消除失败。每次输出均保留，未来若重现应升级根因调查。

## 缓测 / 发布负责人：科祥

| 项目 | 本轮状态 | 负责人后续验证 |
|---|---|---|
| 签名 / SmartScreen | 未执行，不计自动化通过 | 对最终安装包验证签名与提示路径 |
| 干净机 | 未执行 | 最终安装包在干净 Windows 环境安装启动与握手 |
| 长路径 | 未执行实机测试 | 最终安装与数据/输出长路径场景 |
| reboot | 未执行 | 重启后启动、旧握手清理与恢复 |
| #04 实机UI冒烟 | 未执行 | S05布局/四图层/PNG实际显示、颜色/不确定/留白、首入快捷键浮层、确认/撤销/切图/刷新恢复、对话条常驻；验收实际release WebView而非逻辑测试 |
| tag / push / Release / 最终安装包哈希 | 未执行；commit与哈希留待负责人补清单 | 科祥复核后执行，`docs/release_manifest.md` v0.1.2 commit 当前留空 |

## 不变项

seeds_20.json 本次仅入库，SHA256=`388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`；源谱/头文件前后哈希不变。任务卡、backend/__init__.py、Python/Rust/Node依赖与锁文件、既有引擎/会话/前后端功能实现均未改。根目录两份公司文档继续不跟踪。所有数字均来自上述测试输出、当前H测量、历史K表或卡内参数/阈值；不把实现默认值提升为需求硬约束。
