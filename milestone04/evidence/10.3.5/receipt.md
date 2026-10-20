# 10.3.5 扩散 / 提示分割回执

## 事实源与范围

已通读磁盘 TASK-04（522 行、R17，SHA-256
`EBC8C08815F0B0938F523B898EC202E279245E9F1BA927D215E763BD6AB8ACD1`）。
本轮用户随后明确下达 R18 四项裁定并要求继续；磁盘卡尚未包含 R18，执行者不自行补卡。
实现依据为卡 §5.3 / §6.1 加本轮用户的 R18 明确裁定。

实现文件只有 `src-python/spectrumagent/annotation/engines/diffusion.py`。
没有修改 superpixels.py、session.py、路由、Rust、前端或依赖；没有标签赋值或自动 annotation。
接缝读取既有 SuperpixelEngine.cache，复用其锁、SessionStore._lock / _state / set_segmentation，
直接写入既有 WorkingState.candidates；不维护第二条队列。

## 测试执行模式

从 E:/AI_Agent 一条 PowerShell 命令执行：

```powershell
Set-Location -LiteralPath 'E:/AI_Agent'
$env:PYTEST_DEBUG_TEMPROOT='E:/AI_Agent/.runtime/pytest-tmp'
& E:/AI_Agent/.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q
```

默认参数，无过滤、无并行、无额外 basetemp。实际结果：
**295 passed, 10 warnings in 27.59s**，即 261 基线 + 34 新增；本机没有 skip。
完整输出：`pytest-full.txt`。warning 均为既有依赖弃用提示，未执行安装命令。
运行经工具审批在沙箱外执行，沿用前阶段对 pytest-current 链接访问限制的处理；命令及参数不变。

初次定向测试为 30 passed / 4 failed：失败均来自同一参数化测试中我自设的比较余量
`abs(weighted-equal)>0.01`，实际差值为 0.009526270157478645；独立加权公式核验已经通过。
已改成直接验证加权公式，并用浮点容差排除等权结果。未改卡内断言、默认值或固定种子。

## 新测试落点

`src-python/tests/annotation/test_diffusion.py`（33 项）：

| 测试函数 | 用例数 | 断言 |
|---|---:|---|
| test_four_neighbour_graph_deduplicates_shared_edges_excludes_corners | 1 | 4 邻域、边去重、角接触不连通 |
| test_single_linkage_growth_cos_uv_report_cos_s_drift_default_reproducible | 1 | 邻接链增长、种子余弦报告、min 可低于两默认阈值、默认可复现且换阈值改变结果 |
| test_composite_one_candidate_pixel_weighted_seed_seed_members_defined_one | 4 | 框/涂鸦/像素集合/超像素集合合为一候选；按命中块像素数加权；所有种子成员 cos_s=1 |
| test_doodle_bresenham_fills_intermediate_pixels_one_pixel_wide | 1 | 中间像素、端点、反向、退化点、竖线；像素集合不自行连线 |
| test_box_half_open_hits_all_covered_superpixels_and_all_three_prompts_work | 1 | 半开框选边界；point/box/doodle 都生成候选 |
| test_original_means_only_pca_changes_do_not_change_spectral_result | 1 | PCA 显示特征改变不影响任何谱判定或相似度 |
| test_candidate_png_side_limit_and_pixel_count | 1 | PNG 可解码、边长 ≤512、像素数一致 |
| test_bad_prompt_structured_no_candidate | 8 | 空/混用/越界/类型/空框/不存在 id 等结构化错误 |
| test_threshold_validation_is_independent_and_structured | 4 | 非法增长阈值和队列阈值分别校验，无入队副作用 |
| test_queue_guard_default_active_separate_from_growth_no_auto_labels | 1 | 默认增长下 0.80 护栏真触发；仅改护栏不改候选；阈值不分叉队列；map/三表不自动赋标 |
| test_existing_session_consumes_confirm_uncertain_candidate | 2 | 直接走既有 edit，confirm/uncertain 消费候选并写正确像素态 |
| test_existing_erase_does_not_consume_queue_pending_is_pixel_union | 1 | erase 不动队列；重叠候选按像素并集计待确认 |
| test_existing_parameter_change_clears_single_queue_preserves_pixel_states | 3 | 三种 SLIC 参数变更均清候选，保留 label map、-2 及统计 |
| test_queue_owned_by_session_cube_isolation_new_session_empty_response_copies | 1 | 同 session 多引擎共用队列；每 cube 隔离；新 session 无候选；响应副本不污染队列 |
| test_cache_seam_reads_only_validated_resident_original_means | 1 | 仅 Registry.readable(raw=False) 验源；禁止新增 read_region/to_numpy；复用驻留原谱均值 |
| test_missing_superpixels_structured_without_implicit_generation | 1 | 未生成超像素先扩散报结构化错误，不隐式分割 |
| test_source_changed_and_unknown_id_preserve_registry_classification | 1 | 缓存不掩盖 SOURCE_CHANGED；未知 id 仍 DATASET_NOT_FOUND |

`src-python/tests/annotation/test_diffusion_acceptance.py`（1 项）：
`test_real_cube_fixed_twenty_default_queue_three_assertions`。
使用真实 pe 基线、10.2 默认分割、原始固定 20 坐标；三条队列断言、默认复现、同种子换阈值、
无自动标签及种子文件前后字节相等全部实跑。
若 seeds_20.json 缺失则明确 skip（未入库且本机缺失，禁止重生成）；真实 cube 缺失另行注明 skip。

该测试文件也是独立复跑脚本：

```powershell
& E:/AI_Agent/.venv/Scripts/python.exe src-python/tests/annotation/test_diffusion_acceptance.py --output E:/AI_Agent/.runtime/diffusion-recheck.json
```

## §6.1 / §5.3 自验结果

1. 默认阈值 0.92 可复现；固定 20 种子改为增长阈值 0.80 后，20/20 候选规模改变。
2. 单击/半开框选/1 像素 Bresenham 涂鸦都可生成候选；种子像素集合、超像素集合也通过。
3. R18 多命中：命中超像素并集为初始区域；按这些块全部像素等权合成种子均值谱；一提示一候选；种子成员 cos_s 定义为 1。
4. 邻接为水平/垂直 4 邻域。当前默认 pe 分割细分前 n=765、边=2079；细分后 n=830、边=2256。
   历史 766/~2075 锚点与当前分割并非同一张 segments。2079 已用独立逐像素双循环边集合与实现逐边精确核对。
5. 增长只用邻接对 cos_uv≥threshold；报告只用种子参照 cos_s，min/avg 包含种子；沿链漂移实测可达。
6. 所有余弦只读取 Segmentation.mean_spectra 的 200 波段反射率均值。PCA 仅供 PNG 灰度底图，不参加谱运算。
7. 队列断言①：默认参数下 **入队 10、被 0.80 拦截 10**，两者均 ≥1。
8. 队列断言②：**19/20** 候选 min_similarity<0.92，证明护栏未休眠。
9. 队列断言③：入队候选 min_similarity 全部 ≥0.80，最小 **0.8093943702234402**。
10. 每 cube 一条 SessionStore 队列；增长阈值/护栏变化不另起队列；有未入队原因计数。
11. confirm / uncertain 消费候选；erase 不消费；均直接复用既有 SessionStore.edit。
12. n_segments/compactness/pca_components 变更由既有 set_segmentation 清队列，标签及 -2 按像素保留。
13. working 待确认是队列像素并集；队列仅内存、跨 session 不保留、切 cube 隔离。
14. 生成候选不赋标签、不写 annotation/version/sample_spectrum；固定 20 默认及改阈值操作后 label_map 仍全部 -1。

## 固定 20 种子实测（实现层数据，不是新增默认常数）

完整精度、坐标、种子 id、规模、像素数、min/avg、是否入队和每次耗时见 `queue_20.json`。
以下按原 seeds 文件顺序排列；“入”=入队，“拦”=被 0.80 拦截。

| row | col | min_similarity | 结果 |
|---:|---:|---:|---|
| 29 | 64 | 0.8117080463021955 | 入 |
| 29 | 192 | 0.8093943702234402 | 入 |
| 29 | 320 | 0.4369514174170881 | 拦 |
| 29 | 448 | 0.8995713701008021 | 入 |
| 29 | 576 | 0.8353958142936784 | 入 |
| 87 | 64 | 0.7774489941409575 | 拦 |
| 87 | 192 | 0.8144889224693571 | 入 |
| 87 | 320 | 0.41031719817525525 | 拦 |
| 87 | 448 | 0.8502812853590824 | 入 |
| 87 | 576 | 0.7215686471416272 | 拦 |
| 144 | 64 | 0.8504359258678486 | 入 |
| 144 | 192 | 0.7418241268103231 | 拦 |
| 144 | 320 | 0.4116316392594652 | 拦 |
| 144 | 448 | 0.9004642378470619 | 入 |
| 144 | 576 | 0.7876719366718863 | 拦 |
| 202 | 64 | 0.7924159054434385 | 拦 |
| 202 | 192 | 0.7940137528731125 | 拦 |
| 202 | 320 | 0.46921624433458275 | 拦 |
| 202 | 448 | 0.9085547815446008 | 入 |
| 202 | 576 | 1.0 | 入 |

默认值出处与层级未变：增长 0.92=需求场景 S1 第417行示例值；
入队 0.80=UI 原型 ui-v2.3 S05 第1711行脚注，UI 层默认。两者均可调，不互相替代。
叠加 PNG 边长上限 512=任务卡约束。

## 性能及物化边界

真实 pe 默认分割 830 段；原谱均值谱 **1,328,000 字节**；PCA 特征图 **2,956,800 字节**。
独立验收进程峰值 RSS **316,166,144 字节**（包含 Python/依赖、先行超像素分割、扩散与 PNG，不是扩散增量）。
20 次默认生产调用（含验源、建图、扩散、PNG 和入队）总耗时 **0.5531471 s**，各次约 **0.0269–0.0299 s**；
均为本机本轮实测，不作为新硬阈值。引擎不读取原始立方体块，只复用驻留均值谱；测试禁止其调用 read_region/to_numpy。

## 文件与提交边界

本轮新增：

- src-python/spectrumagent/annotation/engines/diffusion.py
- src-python/tests/annotation/test_diffusion.py
- src-python/tests/annotation/test_diffusion_acceptance.py
- milestone04/evidence/10.3.5/queue_20.json
- milestone04/evidence/10.3.5/pytest-full.txt
- milestone04/evidence/10.3.5/receipt.md

任务卡、superpixels.py、session.py、公司文档及 seeds_20.json 未改。
seeds SHA-256 保持 `388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`；
两份公司文档与种子清单保持未跟踪，不入提交。仅按上述六个文件路径 git add。

无新增待决口径问题。10.3.5 完成后停止，等待复核；10.4 仅就绪，不开工。
