# 11.1 算子框架

范围：TASK-05 §2.1 / §2.2 / §2.2.1 / §2.6 / §5，含开工令 R7、R8 裁定。只处理调用方传入的 `(n_spectra,bands)` 谱矩阵，不读文件、不写 DB、不保存配方、不生成对比指标。波长轴是 `run(..., wavelengths=...)` 的只读随行数据，本阶段所有算子保留其长度和顺序。

`builtin_registry()` 每次创建独立注册表；`registry.entries` 为 `{name: {version: OperatorEntry}}`。注册用 `register(name, version, ParamsModel, impl)`，参数模型必须为 `extra="forbid"` 的 Pydantic BaseModel。`entry.params_schema` 直接取 `model_json_schema()`，执行只用同一模型 `model_validate`；无 JSON Schema 解释器或新增依赖。模型默认值也随校验后的 step params 返回。

`parse_pipeline(dict_or_json)` 校验固定的 `steps/op/version/params` 字段与各步参数；`run(spectra,pipeline,*,wavelengths=None,random_state=None)` 执行并返回 `PipelineResult(spectra,wavelengths,steps)`。random_state 为后续随机算子保留参数位，本阶段算子不使用随机数。每步记录 `{op,version,params,meta}`；纯矩阵返回得到空 meta，二元组返回的 meta 规范化为严格 JSON 值。谱矩阵里的 NaN 不会转成零，只有 meta 的非有限标量转为 null。

| name | version | params_schema 摘要 |
|---|---:|---|
| reflectance | 1 | 必需 hdr；可选 branch=reference/scale/passthrough、white_reference/dark_reference 向量；guard=clip/keep/error，默认clip |
| sg_smooth | 1 | 必需 window 正奇数、polyorder 非负且严格小于window；mode=interp/mirror/constant/nearest/wrap，默认interp |
| sg_derivative | 1 | 同SG；必需order=1或2；delta不在参数表，内部固定1.0 |
| snv | 1 | zero_std=zeros/nan/error，默认zeros；std固定ddof=0 |
| msc | 1 | 必需有限reference一维向量，长度须等于bands，无默认当前数据均值 |
| emsc | 1 | 同MSC；polynomial_order非负整数，默认2 |

上述默认值来自卡 R6 与开工令；SG 严格小于边界按 R7 开工令，Pydantic/系数记录/散射退化按 R8 开工令执行。SG 的五种 mode 取本机 SciPy savgol_filter 已支持的枚举；mode=constant 使用该函数既有默认边界常数，不新增配方参数或默认值。

B01 的 `params.hdr` 接受原始 hdr 字段字典（字段名复用既有 ENVI key_name 规范化），应保留原始 scale 字段是否存在，不能拿读取器补出的默认 scale_factor 充作 hdr 判据。`white reference` / `dark reference` 只用于匹配判据；已解析的参考向量通过两个 reference 参数提供，文件解析归后续 run 层。可选 branch 只是核验声明，不能覆盖 hdr 判据；多判据/无判据分别报 AMBIGUOUS_REFLECTANCE_INPUT / UNKNOWN_REFLECTANCE_INPUT。nan_bands 计输出矩阵中 NaN 元素数，negative_clipped 计实际置零的负值元素数（keep不裁剪，计数为0）。不裁剪大于1的值，不引入epsilon。

SG 数值计算复用 SciPy。当前环境 interp 边缘最小二乘会拒绝 NaN：有非有限值时，内部仍走同一 SG 卷积，边缘仅对有限的完整拟合窗口调用 interp；不可拟合边缘传播 NaN，不填充/插值缺失值。完整有限输入直接调用原始 SciPy 路径；窗口与polyorder错误在调用前结构化拒绝。

MSC/EMSC 复用 np.linalg.lstsq；设计矩阵依次为 ref、常数、t的一至p次幂，t为波段序号映射[0,1]。秩不足报 SCATTER_MODEL_DEGENERATE(400)，含design_rank/expected_columns。NaN输入行在LAPACK调用前检出，该行输出NaN，nan_spectra计行数；已拟合行a恰为0或NaN时输出NaN，zero_scale_count计数，不使用近零阈值。

参考谱与系数的SHA256均取C-contiguous float64 bytes；系数矩阵形状为(n_spectra,设计列数)，NaN输入行对应系数行保留NaN，哈希覆盖这些行。meta只给coefficients_shape/coefficients_sha256，不内联系数，不写reference_source；参考来源与全量系数artifact留后续阶段。SNV无参考谱，因此reference_sha256/reference_len为null；MSC/EMSC无std归一化，因此std_ddof为null、zero_std_count为0。

注册同名同版本会拒绝覆盖；不同version同时保留旧impl。只有声明的name@version不存在时抛OPERATOR_VERSION_STALE(409)。删除旧实现仅在验收测试中模拟，没有生产退役/配方持久化接口。

测试位于 `src-python/tests/preprocess/`：B01判据/guard/NaN、SG窗口/阶数/mode/单位、散射公式与R8边界、全链解析执行、多版本、JSON-safe、逐元素1e-12复现、新算子局部注册演示。演示验证扩展所需改动局限于一个小模型/纯函数/注册；没有用测试耗时冒充“≤0.5人日”的人力实测。

## 11.1 自验回执

实跑模式：仓库根 E:/AI_Agent，同一PowerShell调用设置 `PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp`，执行 `.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`，默认参数、无筛选/并行。结果434 passed、0 failed、0 skipped，42.50s、10条既有第三方弃用警告；其中既有340+本次94。完整本机输出在 `.runtime/m05-11.1/pytest-full.txt`，不纳入功能源码提交。以下数字为本轮实现层实跑记录，不是算子性能承诺。

| 卡§5关键词 | 新测试落点（src-python/tests/preprocess/） | 结果 |
|---|---|---|
| B01三分支、R6补充 | test_reflectance.py | 三公式/分支记录、双判据错误、三guard、NaN传播通过 |
| B02、R7严格边界 | test_savgol.py | 偶数/阶数越界在SciPy前拒绝，五种mode、窗口/阶数可复现；NaN局部传播通过 |
| B03、R6补充 | test_savgol.py | 一/二阶多项式导数按band_index，非均匀波长轴保持，delta未知键拒绝 |
| B04、R6/R8补充 | test_scatter.py | ddof=0、零方差三策略、显式reference、MSC/EMSC公式与lstsq、秩/NaN/恰零a/系数指纹通过 |
| 算子框架全链R5 | test_registry.py::test_registered_schema_parse_execute_and_invalid_params_full_chain | 注册→JSON解析→逐步执行→字段级校验错误闭环通过 |
| 算子级确定性R5 | test_registry.py::test_operator_level_determinism_1e12_without_mutating_inputs | 六个内置算子同输入两次谱误差≤1e-12，meta相等，输入不被修改 |
| 算子版本R4 | test_registry.py::test_same_name_multiversion_retained_and_stale_only_when_absent | v1/v2共存、各自复现；显式模拟删v1后仅v1报409，v2正常 |
| 新增算子演示 | test_registry.py::test_new_operator_demo_is_local_registration_without_framework_changes | 新模型+纯函数+注册在测试内闭环，不改框架；工时口径由源码局部性供复核 |
| 算子返回结构R6/R8 | test_registry.py、test_scatter.py | 两种返回形态、np.float64/ndarray meta转换、strict JSON序列化、系数仅形状/哈希通过 |

四个边界独立实跑结果：多判据=AMBIGUOUS_REFLECTANCE_INPUT；无判据=UNKNOWN_REFLECTANCE_INPUT；偶数窗口=INVALID_OPERATOR_PARAMS（steps.0.params.window）；polyorder==window=INVALID_OPERATOR_PARAMS（steps.0.params.polyorder）。首轮77过/1失败暴露本机SciPy interp对NaN拒绝的行为；实现已补显式窗口传播，最终新增94与全量434均通过，没有削弱断言。

本轮不改任务卡/依赖/既有源码，不安装依赖。R7/R8以科祥开工令为依据（卡补丁由科祥落盘）；系数artifact、参考来源回填、配方存储、比较、路由、Rust、前端均留各后续阶段，不在本提交实现。
