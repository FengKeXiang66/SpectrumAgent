# TASK-06 §6 验收映射

执行模式、完整命令、原始输出以各子项D1–D7回执及summary.json为准。R10/R11及用户对§6.6a的更正已闭环：无波长轴仍按索引分散正常搜索，只有候选不足或无合法组合才走三分位，fallback=true。

| §6 | 测试/证据 | 状态与口径 |
|---|---|---|
| 1 / 1.1 | test_none_png_matches_head_minmax_truncation_byte_for_byte；performance.py 的 legacy_none_png_sha256；scope-check.json | HEAD a052b33 与当前真实PE none-PNG SHA256完全相同；png_gray AST未改，默认size仍preview，默认stretch改auto |
| 2 / 2.1 | test_manual_rgb_channel_order_metadata_and_dimensions_match_gray；final-manual-rgb.png；final-performance.json | 顺序保留、band=R、波长回填；同size灰度/RGB同尺寸，full为640×231；preview尺寸另测 |
| 3 | test_rgb_joint_mapping_no_second_stretch_or_independent_noise_amplification | auto/none均联合范围，低方差B通道不放大到满量程 |
| 4 | 同上逐像素手算；test_rgb_nonfinite_is_excluded_and_maps_black | 直接联合映射后组装，无第二次拉伸 |
| 5 / 5.1 / 5.2 | test_real_pe_feature_determinism_dispersion_corr_and_candidate_shape；test_feature_corr_shape_assertion_catches_wrong_index_space；final-performance.json | 实现内强制候选矩阵形状断言；三次一致、分散约束、两两max相关<0.75；完整B×B带波段索引的独立交叉复算一致；不把具体自动band写成测试期望 |
| 6 / 6.1 | test_feature_*；test_rgb_constant_or_all_nan_is_black；test_rgb_nonfinite_is_excluded_and_maps_black | R11：候选不足、无合法组合、常量corr NaN置0、B<3结构化400、三分位重复兜底均测；无波长轴按索引分散搜索且fallback=true（用户确认实现正确并修正§6.6a，无代码变更） |
| 7 | test_region_mean_matches_numpy_all_pixels_and_half_open_bounds；test_region_mean_keeps_partial_nan_pixels_and_marks_only_all_nan_bands；final-performance.json | 逐像素算术均值对拍atol=1e-9；不剔除像素，部分NaN也传播null，nan_bands按§2.5只列全NaN列；真实PE绝对误差见原始JSON |
| 8 | test_point_spectrum_uses_scaled_source_even_when_registered_raw；test_point_spectrum_exposes_nonfinite_null_without_changing_region_endpoint；final-performance.json | 1×1、强制raw=False（含登记raw=True），NaN/Inf→null，旧region仍NON_JSON_VALUES |
| 9 | display.test.ts 的LUT四组测试；D5.md代码审查 | 默认恒等、边界/16间距、RGB共表、alpha保留、参数跨模式保留；拖动不发IPC为代码审查，不冒充浏览器自动化 |
| 10 | performance.py final；performance.txt / final-performance.json；两张final PNG | 真实独立sidecar+loopback HTTP，手动RGB<100ms、auto特征/PNG缓存冷<1500ms；未清OS页缓存，源哈希在计时前读取；单机观测非跨机承诺 |
| 11 | pytest-full.txt / cargo-full.txt / node-full.txt / tsc.txt / clippy.txt / audit-boundary.txt | 默认全量681 Python /58 Rust（含doctest）/74 node；tsc、clippy -D warnings、audit exit0；未改audit脚本 |
| 12 | summary.json；D1–D7回执；baseline-*.txt | pytest均-m pytest，从仓库根，环境变量正斜杠；每次首次空E盘目录，无safe-delete拦截；Python无沙箱，其他默认沙箱，未证明“必须无沙箱” |

本轮没有执行实机WebView交互冒烟，不声称通过。没有新增全波段伪彩、导数/SG显示、反差对比、坏波段/坏像元功能，也不改标注编辑接口或SessionStore。需求文档回写归备卡方。
