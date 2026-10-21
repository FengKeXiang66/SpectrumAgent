# 11.6 · TASK-05 §5.1 十三条对位

执行模式：node 使用科祥给定的托管 **22.22.2**；仓库根 `node --test src/components/preprocess/*.test.ts src/components/datasets/*.test.ts src/components/annotation/*.test.ts`，默认 runner、无 DOM/浏览器替身。Python 在仓库根以 `python -m pytest backend/tests src-python/tests -q` 默认参数运行，同一命令设置 `PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp`。Rust 在 `src-tauri` 目录默认并行 `cargo test`。类型检查为托管 Node 在 PATH 首位时 `npx --no-install tsc --noEmit`（不下载安装）。

| §5.1 顺序 / 关键词 | 实现和可执行自验 | 证据 / 结论 |
|---|---|---|
| 1 算子链合法编排 | `PipelineEditor.tsx` 上移/下移/删除/重复；`pipeline.test.ts` 的目录、空链、move/delete/repeat 用例；保存与 run 在非法/未保存草稿时禁用 | `node-test.txt`；通过 |
| 2 参数面板 | SG 奇数、严格 polyorder<window、导数 1/2、mode；SNV 三策略、标准化四法；crop/resample、三降维必填维数、连续统两法。`pipeline.test.ts` 正反例全链校验。reflectance 不开放；MSC/EMSC 明示阶段二 | `node-test.txt`；按卡逐名枚举实现。明列名单实际为 10 项（13 注册名减 B01/MSC/EMSC）；未添加卡外第 11 个名字、未改卡 |
| 3 变轴链 | `axisAfter`、`compilePipeline` 纯函数；crop 闭区间、每个 source 用当前轴、target 取起止点数生成；无初始轴与降维后无轴均拒绝轴操作 | `pipeline.test.ts` 的纯函数、crop→resample→crop、无轴用例；通过 |
| 4 前后曲线 | `run.py` 只在最终遍开启 before；`CompareChart` 同画布上下两栏，只画后端数组、空值分段、不插值；图例从 label_index→id→后端 code/颜色；缺失回退 id 前 8 位；无轴明确 band index | `test_curves.py` 四项；`pipeline.test.ts` 的曲线断线；`panel.test.ts` 的图例/接线；`curves-sample.json` 真实 pe run；通过 |
| 5 指标后端供值 | `MetricsView` 展示 SNR 四统计量及计数、类间/类内/Fisher、excluded_classes；boundaries/limitations/source 原文。未标注时后端不存在的标签指标不生成 | `panel.test.ts` 的接线测试、11.3/11.4 全量既有测试；`pytest-full.txt`；通过逻辑验收 |
| 6 B08 最小展示 | 三法占比与累计占比列表；ICA 使用“分量重构能量占比”标题并显示后端 variance_definition 原文 | `panel.test.ts` 接线测试；通过逻辑验收 |
| 7 配方保存复用 | 具 code/name/description/note；create / get / add_version 分别对接，历史无覆写入口；后端库按 code 排序；INVALID_REQUEST 原信封并提示检查重复 code | `api.test.ts` 的 create/get/add_version；`panel.test.ts` 错误及接线；11.4 既有版本/重复 code 测试仍绿；通过 |
| 8 项目选用 | 项目取 `annotations.projects()[0]`，显示名；select/deselect/list 三路，取消只变关联 | `api.test.ts` 三变体与 204；`panel.test.ts` 接线；11.4 既有幂等 DELETE 测试不动；通过 |
| 9 run 提交状态 | 标注 UUID 取 `annotations.versions(cube)` 下拉；无版本禁用；只发两 UUID；真实 run 四态、失败 error/error.detail 原文 | `api.test.ts` 投影与防 extras；`panel.test.ts` 接线；`pytest-full.txt` 既有四态验收；通过 |
| 10 超时恢复 | 提交前记录摘要 id；TRANSPORT/网络/超时后自动 list_runs，查新 succeeded 的 get_run 详情匹配 recipe_version_id；找不到保持“尚未判定失败”并保留手动刷新；不把业务错误当超时 | `panel.test.ts` 的 recovery、transport、submit TRANSPORT 三项实际执行 stub transport；通过 |
| 11 配方对比 | 明确多选版本，compare 投影；按后端 ranking 原序显示、Fisher=null 不入表并说明；boundaries/selection 原文 | `api.test.ts` compare；`panel.test.ts` 接线；既有 B10 数值/排序验收不改；通过逻辑验收 |
| 12 唯一出口 | `api.ts` 单一 `preprocess_forward` client；12 个 op 明确投影；组件无 invoke/fetch/URL/端口/token | `api.test.ts` 12 项逐变体精确请求与 extras 隔离；`panel.test.ts` 静态接线；通过 |
| 13 测试与构建基线 | Python 621/0/0；Rust 56/0/0；node 59/0/0；tsc exit 0；既有测试断言零修改 | `pytest-full.txt`、`cargo-test.txt`、`node-test.txt`、`tsc.txt`；通过 |

D1 特别验收：`test_collect_before_defaults_false_and_stays_empty` / `test_final_pass_collects_b01_class_sums_counts_and_unlabeled` / `test_global_fitting_passes_never_pollute_before` / `test_curves_json_axes_sampling_nan_and_class_contract`。分别覆盖 False 不累计、B01 原谱类和计数与未标注 -1、Standard/PCA/MNF/ICA 多遍拟合不累计、JSON 独立 in/out 抽样与全 NaN after=null。NaN 仍由原 `json_safe` 转 null，未修改算子、拟合、指标或版本逻辑。

实机 UI 冒烟由科祥执行；此表不把 node 逻辑测试等同于实机 UI 通过。坏波段剔除、去背景/仅 ROI、历史 Kappa、每步预览，以及 MSC/EMSC 参考谱来源，界面均明确阶段二/不适用。
