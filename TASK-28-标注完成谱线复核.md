# TASK-28 标注完成谱线复核卡

> **状态**：功能提交 `b41bf10` 已落（仅 §4 清单内 8 文件），门 1–16 通过，门 17 按 v1.5 判据裁定后可关闭；未 push / tag / 打包。**本卡是执行阶段唯一权威口径**；`需求总结-标注完成谱线复核.md` v2.2（`3059c45`）是需求输入材料，执行方以本卡为准，不得回去按需求总结自行解释或重开已定案项。
> **修订 v1.1（2026-11-05，独立复核后）**：把「大 n_segments 的 Python 侧封顶」明确写为**本卡不做、延后另立卡、执行方不得自行发挥**（见 §3.4 / §6 门 13 / §7 条款 10 / §8）；补记本卡顺带修复现状潜在 HTTP 500 缺陷（**此补记已由 v1.4 修正作废**：源谱 NaN 被 `row_blocks` 阻断，不存在该缺陷）；修正两处引用行号。**D1–D8、v2.2 四项口径、FR-E23、基线数字一律不重开。**
> **修订 v1.2（2026-11-05，开工闸门首触即停后）**：修正 §0.1 Python 基线命令——原固定名 `sa-gate-28-annotation` / `sa-gate-28-data` 加 `New-Item -Force` 会复用备卡方实跑遗留的**非空**目录，与「全新临时根」口径冲突。改为 **GUID 唯一根 + 去掉 `-Force` + 存在性断言**；明确已有同名目录属已知状态、不复用不删除、不构成即停项；明确**耗时是记录值不是断言值**、`.config/git/ignore` 权限 warning 属环境噪声。D1–D8、四项口径、FR-E23、17 道门、基线计数一律不变。
> **修订 v1.5（2026-11-05，门 17 即停后）**：功能提交 `b41bf10` 仅含 §4 清单内 8 文件，门 1–16 通过；门 17 因收工时 `artifacts/step2/` 出现 14 个 `M` 即停。备卡方只读核实：14 项**全部**满足「未进功能提交 / `git diff --cached` 为空 / `git diff --ignore-cr-at-eol --quiet` 退出 0 / `git ls-files --eol` 为 `i/lf w/crlf attr/-text` / mtime 均为 2026-10-18」，即**索引(LF)与工作区(CRLF)的固有行尾不一致在索引 stat 缓存替换后暴露**，HEAD 未变、工作区字节未变、staged = 0。裁定为**已知行尾/索引可见噪声，不计入「清单外文件改动」**，门 17 据此关闭；这 14 项**不恢复、不改写、不提交、不进本卡任何提交**，保持现状交需求方后续决定。D1–D8、四项实现口径、FR-E23 / P1、接口契约、门 1–16、基线计数一律不重开。
> **修订 v1.4（2026-11-05，实现前 NaN 契约冲突停工后）**：明确 §6 门 8 的 NaN 输入构造口径与上游拒绝规则衔接。源谱非有限输入由 `row_blocks`（`superpixels.py:59-66`）在 yield 前抛 `NON_FINITE_SPECTRA`，经 `app.py:82-85` 映射为 **HTTP 400**，属既有设计、本卡不改不放宽；门 8 拆为 **8A**（上游拒绝规则保持，期望 400）与 **8B**（返回边界转换契约，注入非有限值验证转 `null` 且 HTTP 200）。**同时修正 v1.1 补记的错误断言**：「含 NaN 波段 → cos 为 NaN → 500」被 `row_blocks` 阻断，不成立；统一转换改定性为**防御性契约**而非「修复现状活 bug」。`cos` 为 NaN 的 UI 分支标注为当前不可达。D1–D8、v2.2 四项实现口径、FR-E23 / P1、§3 接口契约主结构、§4 清单、基线计数一律不重开。
> **修订 v1.3（2026-11-05，Python 基线失败即停后）**：**v1.2 的 C 盘 GUID 唯一根口径作废**。根因经对照实验坐实为 **Windows MAX_PATH 260 路径长度限制**，非代码回归：C 盘 `%TEMP%`（41 字符）+ 32 位 GUID 后缀（+33）把 `.../app/annotations/<uuid>/v1.<GUID>.tmp` 推到 262 字符，`os.mkdir` 报 `FileNotFoundError: [WinError 3]`。改为 **E 盘 `.runtime/` 下短根（8 位随机后缀，根长约 34 字符）**，保留「全新 + 独立进程 + 无 -Force + 存在性断言」。42 项失败判为环境假失败，不计入收工门、不得据此改测试或放宽断言。D1–D8、四项口径、FR-E23、接口契约、17 道门、基线计数（249 / 391+2 / 106）一律不变。
> **事实源**：需求 v2.7 `artifacts/step3/requirements-v2.7.txt`；ui-v2.3 `.runtime/docs/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.txt`。归档 v2.6 / ui-v2.2 禁止引用。
> **行号时效**：本卡全部行号为 2026-11-05 **工作区在途状态**（34 M + 7 untracked）实测值。提交或回滚都会漂移，**开工第一步逐条 grep 复核 §0.2，漂移即停上报**。

---

## 0. 一句话

在 S05 标注工作台新增「谱线复核」tab：**扩展既有** `POST /api/v1/datasets/{identifier}/annotations/validate` 的响应，吐出每个已标注超像素的均值谱与类参考谱；前端按 band index 叠加展示、可疑优先，用户目视判读后在视图内直接 erase，剔除后重拉刷新。**零新增端点、零 Rust、零 openapi 改动、零版本副作用、零自动剔除**。

## 0.1 三道闸门

1. **工作区快照闸门**（本卡特设，替代「干净」闸门）：开工前 `git status --short` 全文贴回报。当前实测 **34 M + 7 untracked = 41 项**，其中 `src/components/annotation/types.ts`、`AnnotationWorkbench.tsx`、`annotation.css` 有未提交改动（JSON 投影状态徽章），`src/components/annotation/annotationStatus.ts` 为未跟踪新增。本卡**在这些在途改动之上追加**，禁止 `reset` / `checkout` / 覆盖 / 回滚任何在途改动；出现 §4 清单外文件改动即停。清单内「in-flight 禁触碰」文件出现**回滚或内容丢失**即停。**v1.5 收工实测为 48 M + 7 untracked**：34 项原有在途改动内容未变，新增 14 项 `artifacts/step2/` 为行尾/索引可见噪声（判定见 §6 门 17），7 个 untracked 未变。
2. **基线闸门（2026-11-05 实测，带出处）**：
   - 前端（逐字双层 glob）：`node --test "src/**/*.test.ts"` = **249 tests / 249 pass / 0 fail**（1809.68 ms）。**防呆**：单层 glob `node --test "src/*/.test.ts"` 实测 **0 tests**（0 用例假绿），用错即验收无效，禁用。
   - Python 两分区，各自**独立 python 进程 + 全新 E 盘短根**（PowerShell 5.1 逐字；v1.3 经长短根对照实验与 `test_confirm_routes.py` 单文件 11 passed 验证，**全分区计数由执行方在其独立回合实跑**）：
     ```
     $tmp = Join-Path 'E:\AI_Agent\.runtime' ("t28a-" + [guid]::NewGuid().ToString("N").Substring(0,8)); if (Test-Path -LiteralPath $tmp) { throw "临时根已存在: $tmp" }; New-Item -ItemType Directory -Path $tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT = $tmp; & .venv\Scripts\python.exe -m pytest src-python/tests/annotation -q
     $tmp = Join-Path 'E:\AI_Agent\.runtime' ("t28d-" + [guid]::NewGuid().ToString("N").Substring(0,8)); if (Test-Path -LiteralPath $tmp) { throw "临时根已存在: $tmp" }; New-Item -ItemType Directory -Path $tmp | Out-Null; $env:PYTEST_DEBUG_TEMPROOT = $tmp; & .venv\Scripts\python.exe -m pytest src-python/tests/data -q
     ```
     **两条命令逐字使用；不得加 `-Force`、不得把两个分区写进同一条 pytest 命令**（safe-delete 钩子 unlink 预算耗尽会杀 anyio portal）。备卡方实跑基线：**annotation 391 passed + 2 skipped**、**data 106 passed**，合计 **497 passed / 2 skipped**。
     **临时根口径（v1.3 定案；v1.2 的 C 盘 GUID 唯一根作废）**：
     - **根路径长度硬约束**：Windows MAX_PATH = 260，annotation 测试会创建 `.../pytest-of-Administrator/pytest-0/<test>-runtime/app/annotations/<uuid>/v1.<GUID>.tmp` 深层目录。实测旧 C 盘固定根下该路径 **229 字符**（安全）；v1.2 的 C 盘 GUID 根下 **262 字符**（加 `label_map.npz` 达 276），`os.mkdir` 抛 `FileNotFoundError: [WinError 3]`。对照实验：长根（96 字符）跑 `test_confirm_routes.py::test_overlap_locations_and_four_arbitrations[erase]` = **1 failed / WinError 3**；**E 盘短根（34 字符）跑同一测试 = 1 passed / EXIT=0**。因此临时根必须落在 `E:\AI_Agent\.runtime\` 下、**根路径总长 ≤ 40 字符**；超 40 即停上报。
     - 「全新」= 运行前目录不存在、创建时为空（`Test-Path` 断言 + 无 `-Force` + 8 位随机后缀）。两分区前缀分别 `t28a-` / `t28d-`，各自独立进程。若 `throw` 命中（随机碰撞），换一次重跑即可，不算失败。
     - **v1.2 造成的 42 项失败判为环境假失败**：`annotation` 分区 349 passed / 42 failed / 2 skipped（EXIT=1）全部源于路径超长，失败项集中在 save / snapshot / projection 类深层目录创建；`data` 分区 106 passed 不受影响。**不计入收工门、不得据此改源码、改测试或放宽断言**；基线计数仍为 391+2 / 106。
     - 备卡方实跑遗留的 C 盘 `sa-gate-28-annotation` / `sa-gate-28-data` 两目录（非空）及 v1.2 生成的 C 盘 GUID 目录均属已知状态，**不构成即停项**：不复用、不删除、不清空、不改名，也不得用作 `PYTEST_DEBUG_TEMPROOT`。`.runtime/` 已被 gitignore，新建根不污染工作区。
     - **禁用 `PYTEST_DEBUG_TEMPROOT=` 空值**；临时根必须真实存在（先 New-Item 再赋值）。
     - **耗时是记录值，不是断言值**：卡内 1809.68 ms / 313.82 s / 10.29 s 均为备卡方当日实测记录，机器负载会造成波动（已出现 1657 ms、800.669 ms、250.32 s、9.06 s、20.37 s 等读数）。**唯一断言是 pass / fail / skip 计数**（249 / 0、391 / 2、106），耗时不参与「与卡不符」判定。
     - `warning: unable to access 'C:\Users\Administrator/.config/git/ignore': Permission denied` 与 `StarletteDeprecationWarning` 属已知环境噪声，与代码错误分开陈述，不计入失败。
     - **safe-delete 预算（备卡方本回合实测）**：`PYTHONPATH` 注入的 safe-delete 钩子有 **50 次 unlink / 回合**预算，同一对话回合内累计多次 pytest 会触发 `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":50,"threshold":50,"scope":"turn"}`，使后续 fixture setup 变成大量 `E`（典型目标是 `pytest-of-Administrator/pytest-0/.lock`）。这是**验证环境的回合预算耗尽，不是代码回归、不是基线失败**：出现时应换一个干净的回合 / 进程重跑，不得据此改源码、改测试或放宽断言。执行方在其独立回合按本卡命令实跑不受备卡方回合计数影响。
   - **收工门**：既有用例不得变红变少，新增另计（`249+Nf` / `497+Np` / `2 skipped` 不变）；任何既有用例变红即停，禁止为凑数删改现有测试。环境噪声（`StarletteDeprecationWarning`、文件锁 warning）与代码错误分开陈述。
3. **行号锚点闸门**：开工第一步 `grep -n` 复核 §0.2 **全部 34 条**锚点，漂移即停上报，禁止按偏移推算。第 33 / 34 条为 v1.4 新增（上游非有限拒绝链），若前 32 条已在本卡开工时核验通过，只需补核这两条，不必重跑全表。

## 0.2 行号锚点表（开工第一步逐条 grep 复核）

| # | 文件:行 | 锚定内容 | 本卡动作 |
|---|---------|----------|----------|
| 1 | `artifacts/step3/requirements-v2.7.txt:1273` / `:1357` | FR-E22（E 域末条目）/ FR-G08（G 域末条目） | 事实源，不改 |
| 2 | `.runtime/docs/…高保真原型.txt:31, 332, 408-413` | S05 = 标注工作台；S05 映射 `FR-E01~E10 · E14` | 事实源，不改 |
| 3 | `src-python/spectrumagent/annotation/quality.py:15-19` | `cosine`：NaN 不抛错返回 `float('nan')` | 不改 |
| 4 | `quality.py:22-50` | `validate` 全实现（`:32-35` comparisons 循环） | 改，见 §3 |
| 5 | `quality.py:36` | `suspicious = [item for item in comparisons if item["cos"] < threshold]`，共享 dict 引用 | **严禁改动** |
| 6 | `quality.py:41-42` | `d_s = std.mean(axis=1)` / `tau = k*np.median(d_s)` | 不改计算，输出层转换 |
| 7 | `src-python/spectrumagent/annotation/session.py:38-42, 62` | `Moments(count, mean, m2)`；`pixels.mean(axis=0)` | 不改（故不吐 nan_bands） |
| 8 | `session.py:78-110` | `aggregate_spectra` 有界累积，`parts` → `(超像素, 标签)` | 不改，复用同一累积器 |
| 9 | `session.py:279-285` | `SessionStore.validate` 不传 aggregates、自行重算 | 不改 |
| 10 | `session.py:346-350` | save 内 `validate(..., aggregates=aggregates)` | 不改（双通道同源） |
| 11 | `session.py:257` | `edit` → `drafts.add` 写 annotation_draft（CAS revision） | 不改 |
| 12 | `session.py:440-450` | `_write_snapshot` 只写 labels 级 mean/std | 不改 |
| 13 | `src-python/spectrumagent/api/annotations.py:353-356` | 独立只读 validate 端点（`Depends(no_body)`、无 response_model） | **不改路由形态** |
| 14 | `src-python/spectrumagent/api/datasets.py:145-146` | `isfinite→None` 序列化范本 / `nan_bands` 由原始像素直算 | 只借前半，不改 |
| 15 | `src-python/spectrumagent/api/openapi.json:1496-1527` | validate 响应 schema `{}` | **不改文件** |
| 16 | `src-python/tests/data/test_api.py:211-214` | openapi 逐字节断言 | 不改，收工须通过 |
| 17 | `src-python/tests/annotation/test_quality.py:53` | `comparisons[0]["cos"]` 跨通道断言 | 不改、不重定位 |
| 18 | `src-python/tests/annotation/test_session.py:153` | no-full-cube 有界读取测试先例 | 仿写新增用例 |
| 19 | `backend/app.py:61-68` | `FastAPI` 未指定 `default_response_class` → 正常响应走 `JSONResponse`（`allow_nan=False`） | 不改 |
| 20 | `src-python/spectrumagent/preprocess/registry.py:40-56` | `json_safe`（docstring：metadata only，`:56` 对非白名单类型抛 TypeError） | **不复用**，见 §3.3 |
| 21 | `src-python/spectrumagent/annotation/engines/superpixels.py:142, 261` | `sums/counts[:,None]` 空块产生 NaN；n_segments 上限 65535 | 不改 |
| 22 | `src-tauri/src/annotation.rs:10` | `MAX_RESPONSE_BYTES = 8 MiB`（所有转发响应通用） | 不改 Rust |
| 23 | `src-tauri/src/annotation.rs:49-50, 107` | `AnnotationRequest` `deny_unknown_fields` 严格枚举 + `Validate` 变体 | 不改 Rust |
| 24 | `src/components/annotation/types.ts:57-62, 73-74, 76` | `Comparison` / `Quality` / `Saved` 引用 Quality / `color_hex` | 追加字段 |
| 25 | `src/components/annotation/api.ts:19, 60` | `requests.validate` / `annotationClient.validate` | 不改 |
| 26 | `src/components/annotation/AnnotationWorkbench.tsx:257, 259` | edit 前后 `setQuality(null)` | 不改语义，剔除后重拉 |
| 27 | `AnnotationWorkbench.tsx:388-390, 411, 424, 426, 450` | tab 框架 / wavelengths / onBlockErase / 校验按钮 | 挂 tab、复用通道 |
| 28 | `AnnotationWorkbench.tsx:452-453` | `item.cos.toFixed(6)` 与 `τ=` 消费点 | 加空值兜底 |
| 29 | `src/components/preprocess/pipeline.ts:72-81` | `curveRuns` 纯函数（null / 非有限断线） | 只 import，不改 |
| 30 | `src/components/preprocess/CompareChart.tsx:20-23, 33-35, 38` | 共享 low/high 范本 / 波长优先 x 映射 / `curveRuns(values)` 调用形态 | 只借共享 y 轴，不改文件 |
| 31 | `src/components/preprocess/panel.test.ts:59` / `pipeline.test.ts:58` | 三项正则锁定 / 三段断线规则 | 不改，收工须通过 |
| 32 | `src/components/annotation/display/DisplayToolbar.tsx:49, 51-56` | 波长优先 axis（D6 禁止复用）/ null 断线 | 不改 |
| 33 | `src-python/spectrumagent/annotation/engines/superpixels.py:59-66` | `row_blocks`：任何非有限输入在 yield 前抛 `NON_FINITE_SPECTRA` | **不改**（门 8A 的上游拒绝规则依据） |
| 34 | `src-python/spectrumagent/app.py:82-85` + `api/annotations.py:32` | `DataError` 无 `status_code` 且路径不在 `LABEL_PATHS` → **HTTP 400** | 不改（门 8A 期望码依据） |

---

## 1. 起因与 FR 挂靠

标注完成后只有余弦相似度数字可看（`quality.py:32-35` 已把 `moments.mean` 算在手边却只吐 cos），操作者需要「眼见为实」逐块目视判读并剔除异常标注。v2.2 已核实现状：`aggregate_spectra.parts` 的数据现成、独立只读 validate 端点现成、前端「校验当前工作态」按钮现成，缺的只是**响应吐出曲线 + 前端画出来 + 视图内剔除联动**。

**FR 挂靠定案：新增 `FR-E23`（P1）**。依据：v2.7 E 域止于 FR-E22（`:1273`）、G 域止于 FR-G08（`:1357`）；FR-E06（`:1172-1176`）是自动检测+可疑清单，FR-G02/G03（`:1333-1340`）属建模结果展示域，FR-C10（`:1033`）是 P2 算法层离群检测——**语义均不同，无既有条目可挂靠**。P1 理由：FR-E06 已覆盖 P0 自动质量校验，本项为人工目视增强，不阻断阶段一交付。**本卡不改事实源文档、不改 ui-v2.3 的 S05 映射**，仅在此登记编号。

屏位：**S05 标注工作台内**（ui-v2.3 固定 11 屏、无空余屏号，「独立屏」被事实源排除）。

## 2. 拍板口径（全部定案，执行方无裁量权，出卡前一律不重开）

### 2.1 D1–D8

| # | 定案 |
|---|------|
| D1 | 默认按标签分组叠加 + 类参考谱对照线，可切逐块勾选查看 |
| D2 | 参照线画（与 cos 同源，`aggregates.labels[label].mean`） |
| D3 | 视图内直点触发 erase（复用 `onBlockErase` 通道） |
| D4 | S05 工作台新 tab（挂 `AnnotationWorkbench.tsx:388-390` 框架） |
| D5 | 手动入口，与「校验当前工作态」按钮（`:450`）同构 |
| D6 | 横轴 **band index**，hover/轴标注显示波长；**禁止复用波长优先坐标映射** |
| D7 | 一期只画已确认（`labels >= 0`，`session.py:98`），-2 本来就不进 parts |
| D8 | F4 独立 JSON 复查入口 = 二期另立卡，本期不含 |

### 2.2 v2.2 四项实现口径

| # | 定案 |
|---|------|
| ① | **非有限值统一转 `null`**：在 `quality.validate` **返回边界递归做一次**，覆盖 `comparisons[].cos`、`comparisons[].mean`、`references[].mean`、`high_variance.d_s`、`high_variance.tau`；禁止只修 `cos` 或 `mean`。验收门写「两通道均 200、不出现 500」 |
| ② | **NaN cos 块不算可疑，不改 `quality.py:36`**：视作「余弦无法定义」而非「与类参考谱不像」；视图置于展示末尾并单独标注「余弦无法定义」，用户仍可目视判读与剔除。**v1.4 补注**：上游 `row_blocks` 拒绝非有限输入、`cosine` 零范数抛 `UNDEFINED_COSINE`，故 `cos` 为 NaN 的分支**当前不可达**，属防御性 UI 设计；不得为触发它而放宽上游检查或伪造谱线 |
| ③ | **排序放前端**：后端 `comparisons` 保持 `sorted(aggregates.parts.items())` 原序；前端展示按 cos 升序（可疑优先），`cos === null` 排末尾 |
| ④ | **前端复用边界**：只可 import `curveRuns` 纯函数，不得改 `CompareChart.tsx:38` 的调用形态；横轴自建 band index；多曲线**共用 y 轴**以 `CompareChart.tsx:20-23` 为范本，`DisplayToolbar.tsx:44-48` 的 `SpectrumReadout` 单条自缩放不可照搬 |

### 2.3 工程红线（继承自 v2.2 §7）

1. 内存红线：大数组禁止全量物化，逐行块有界读取（`row_blocks` / `Registry.readable`，`session.py:96` 为范本）。
2. 光谱口径：固定当前状态原始反射率，不受预处理管线影响。
3. 8 MiB 转发上限是**所有转发响应通用**，非 catalog 专属；`n_segments` 合法上限 65535，parts 条数 =（超像素 × 标签）组合数，按实际 n_segments 实测体积。
4. n_segments 三处现状：engine 200（`superpixels.py:29`）、api 请求模型 800（`api/annotations.py:56`）、前端 200（**未提交在途改动，HEAD 为 800**）。本卡不动三处；开工时若在途改动已提交/回滚须重新核对。
5. 源目录零改动；数据集删除/重导入等既有行为不变。
6. JSON label 直接用类码（PE/PET/PP），映射恒等默认，不新增命名变换。
7. 审计只增不改。
8. 测试变更须授权同步、非弱化；不得改动 `panel.test.ts:59` 与 `pipeline.test.ts:58` 的既有锁定。
9. validate 扩展后零版本副作用：不写 `annotation_version` / `sample_spectrum` / 快照目录 / `annotation_draft`。
10. **不引入任何自动剔除逻辑**：判断主体是人，cos 只排序不裁决。

---

## 3. 接口契约（响应 schema 逐字锁定）

### 3.1 唯一改动端点

`POST /api/v1/datasets/{identifier}/annotations/validate`（`api/annotations.py:353-356`）。保持 POST、无 body（`Depends(no_body)`）、**无 response_model**、零版本副作用。**不新增端点、不改 URL、不改 Rust `AnnotationRequest` 枚举、不改 `api.ts` 请求构造、不重生成 `openapi.json`**（validate 的响应 schema 为 `{}`，加返回字段不改变快照）。

### 3.2 响应结构：在既有 `Quality` 上**只增不删**

| 位置 | 追加字段 | 来源 |
|------|----------|------|
| `comparisons[]` 每项 | `mean: (number \| null)[]`，长度 == `dataset.shape[2]` | `moments.mean`（`quality.py:32-35` 循环内已在手边） |
| 顶层 | `references: [{ label_index: number, mean: (number \| null)[] }]` | `aggregates.labels` 各项 `.mean`（`sorted()` 顺序） |

既有键（`threshold` / `threshold_level` / `reference` / `suspicious` / `comparisons` / `high_variance` / `completeness` / `not_applicable` 及 `comparisons[]` 的 `superpixel_id` / `label_index` / `pixel_count` / `cos`）**一个不删**。`comparisons` 顺序与扩展前完全一致。**不输出 per-curve `nan_bands`**：`Moments` 只有 `count/mean/m2`（`session.py:38-42`），分块 `pixels.mean` 下无法区分「全 NaN 波段」与「部分 NaN 导致 mean 为 NaN」；强做需新增 per-band 计数，属新增算法，与「复用同一累积器」冲突，本期不做。`mean=null` 即断点。**v1.4 补注**：上游 `row_blocks`（锚点 33）已拒绝任何非有限源谱，故「部分 NaN 导致 mean 为 NaN」在当前实现下不可达；此处关于 NaN 的讨论是**防御性口径**，保证未来上游规则若放宽时响应仍不 500，**不构成「现状存在 NaN 曲线」的断言**。

### 3.3 序列化与计算顺序

- **在 `quality.validate` 返回边界做一次递归转换**：float 非有限 → `None`，numpy 标量/ndarray 先转 Python 值。**本卡收口为：在 quality 模块内实现同语义极小函数**，不复用 `preprocess/registry.py:40-56` 的 `json_safe`——其 docstring 明写 "Strict JSON metadata only; never replace NaNs in the spectral matrix"，用于谱线数组属扩展用途，且对非白名单类型抛 `TypeError`，未来响应加字段会 500。
- **计算顺序**：`cos` 必须用原始 float64 ndarray 计算（`quality.py:35`）；转 `null` **只作用于输出层**。禁止先转 null 再算 cos，禁止因转 null 改动 `quality.py:36`。
- 实测依据：`JSONResponse.render` 带 `allow_nan=False`，任何非有限 float 抛 `ValueError: Out of range float values are not JSON compliant` → **HTTP 500**（`backend/app.py:61-68` 未指定 `default_response_class`）。numpy 算术链核实：`superpixels.py:142` 的 `sums / counts[:, None]` 在 `counts=0` 时为 NaN → `quality.py:41-42` 的 `d_s` 含 NaN → `np.median` 返回 NaN，故**计算派生** NaN 理论上可进入 `validate` 返回值；但默认 SLIC 的 segment id 连续，此路径**未实测复现**，标为「理论可达、未验证」。
- **v1.4 关键衔接（上游拒绝规则）**：源谱含任何非有限值时，`row_blocks`（`superpixels.py:59-66`，锚点 33）在 yield 之前抛 `DataError("NON_FINITE_SPECTRA")`；该错误无 `status_code`、路径不在 `LABEL_PATHS`（锚点 34），按 `app.py:82-85` 映射为 **HTTP 400** + `{"error":"NON_FINITE_SPECTRA","detail":"超像素输入包含非有限光谱值","context":{}}`（已按同逻辑最小复现实测）。`aggregate_spectra`（`session.py:96`）与 `spectral_statistics`（`quality.py:40`）共用此读取器，因此**源谱 NaN 永远不会进入 cos / mean / d_s 计算，也永远得不到 HTTP 200**。本卡**不改、不绕过、不放宽**该规则；§3.3 的递归转换只作用于 `quality.validate` 的**返回边界**，是防御性契约，不是把源谱 NaN 变成 200 的手段。
- TS 类型同步：`Comparison.cos: number | null`、`Comparison.mean: (number | null)[]`、`Quality.references`、`high_variance.d_s: (number | null)[]`、`tau: number | null`；`Saved`（`types.ts:73-74`）引用 `Quality` 自动继承。`AnnotationWorkbench.tsx:452` 的 `item.cos.toFixed(6)` 与 `:453` 的 `τ=` 必须加兜底。

### 3.4 明确禁止

新增端点 / 新增 op / 改 Rust / 加 `response_model` / 重生成 openapi / 改 `quality.py:36` / 后端重排 comparisons / 复用波长优先坐标映射 / 单条曲线自缩放 / 自动剔除 / 新增标注状态 / 改动 labelme 5.4.1 JSON 格式 / 写任何版本表或快照 / **新增 Python 侧曲线数或响应体积封顶**。

> **大 n_segments 的口径（v1.1 定案）**：项目虽有 `datasets.py:138-139` 的 `REGION_TOO_LARGE` 前置封顶先例，本卡**不引入同类逻辑**。全精度下约 2000 条曲线逼近 8 MiB，极端 `n_segments=65535` 会在 Python 侧先构建大 JSON 产生瞬时内存尖峰，之后才被 Rust 的 8 MiB 上限拒掉——**这是 P1 功能的已知取舍，不是本卡要修的缺陷**。执行方只按 §6 门 13 实测两档、超限时按 §7 条款 10 停并上报，**禁止自行加封顶、截断曲线、分页或改动响应结构**。Python 侧显式封顶延后另立小卡。默认 200 块约 0.8 MB、对 8 MiB 有约 10 倍余量，不构成默认路径风险。

---

## 4. 改动文件清单（清单外零改动）

| 路径 | 动作 | 说明 |
|------|------|------|
| `src-python/spectrumagent/annotation/quality.py` | 改 | comparisons 加 `mean`、返回加 `references`、返回边界统一非有限转换；**`:36` 一字不动** |
| `src-python/tests/annotation/test_quality.py` | 改（追加用例） | 不重定位 `:53`；新增用例见 §6 |
| `src/components/annotation/types.ts` | 改（**在途 M 之上追加**） | 类型扩展，不回滚在途的 `JsonProjectionStatus` |
| `src/components/annotation/AnnotationWorkbench.tsx` | 改（**在途 M 之上追加**） | tab 联合类型加 `'review'`、手动入口、视图挂载、剔除后重拉、`:452-453` 兜底；不回滚在途的 `annotationBadge` / `projectionStatus` |
| `src/components/annotation/annotation.css` | 改（**在途 M 之上追加**，可选） | 新视图样式；若无需新增样式则不动，并在收据说明 |
| `src/components/annotation/SpectrumReview.tsx` | **新增** | 谱线复核视图组件 |
| `src/components/annotation/spectrumReview.ts` | **新增** | 纯函数：前端排序（cos 升序、null 末尾）、共享 y 轴范围、`curveRuns` 包装 |
| `src/components/annotation/spectrumReview.test.ts` | **新增** | 前端测试：横轴 / 着色 / 排序 / 共享 y 轴 / 空值兜底 / 断线 |
| `src/components/annotation/api.test.ts` | **不改** | 请求形态未变，validate 用例保持 |
| `src/components/annotation/api.ts` | **不改** | `requests.validate` / `annotationClient.validate` 原样复用（`:19, 60`） |
| `src-python/spectrumagent/api/annotations.py` | **不改**（在途 M，禁触碰） | 路由形态不变；其在途 `json_projection` 改动不得回滚 |
| `src-python/spectrumagent/api/openapi.json` | **不改** | response schema `{}`，快照不漂移 |
| `src-tauri/src/**`、`src-python/spectrumagent/preprocess/**`、`src/components/preprocess/**` | **不改** | 只 import `curveRuns`，不改 `pipeline.ts` / `CompareChart.tsx` / 两个 test |
| 其余 34 M 中未列文件、全部 7 个 untracked | **禁触碰** | 含 `TASK-26-永久删除改造.md`、`src/components/annotation/annotationStatus.ts` 等 |

---

## 5. 实现步骤（按依赖顺序）

1. **后端响应扩展**（`quality.py` + `test_quality.py`）：comparisons 循环内用原始 ndarray 先算 cos，再追加 `mean`；`references` 由 `aggregates.labels` 生成；在 `validate` 返回边界加递归转换函数。后端顺序不动、`:36` 不动。**先跑 `test_quality.py` 全绿再进第 2 步**。
2. **TS 契约**（`types.ts`）：扩展 `Comparison` / `Quality` / `high_variance` 空值类型；`Saved` 自动继承。同步给 `AnnotationWorkbench.tsx:452-453` 加兜底。
3. **前端纯函数 + 视图**（`spectrumReview.ts` / `SpectrumReview.tsx` / 可选 css）：`import { curveRuns } from '../preprocess/pipeline.ts'`；横轴 `i`（band index），hover/轴标注取 `record.dataset.wavelengths`；多条曲线共用一次计算的 low/high；按标签 `color_hex` 着色；默认分组叠加 + 参考谱，可切逐块勾选；cos 升序、`null` 排末尾并标注「余弦无法定义」（防御性分支，当前不可达，见 §2.2 ②）。
4. **接线与剔除闭环**（`AnnotationWorkbench.tsx`）：tab 框架加 `'review'`，手动入口（与 `:450` 同构）；进入/刷新调 `api.validate(id)`；剔除复用 `onBlockErase`（`:424`）→ `edit('erase', { superpixels: [id] })`；因 `edit` 前后 `setQuality(null)`（`:257/:259`），**剔除成功后必须重拉 validate 并把结果同时灌回质量态与复核视图**。
5. **测试与收据**：按 §6 逐门跑；记录真实数字、体积实测值、工作区快照；不确定写「未验证」，空断言零容忍。

---

## 6. 验收表（可执行门，逐条留证据）

| # | 门 | 断言 / 命令 | 预期 |
|---|----|-------------|------|
| 1 | 前端全量 | `node --test "src/**/*.test.ts"` | `249 + Nf` pass / 0 fail；`panel.test.ts:59` 三项正则与 `pipeline.test.ts:58` 三段规则仍通过 |
| 2 | Python 两分区 | §0.1 两条 PowerShell 命令逐字 | `391 + Na` passed / 2 skipped；`106 + Nd` passed；0 fail |
| 3 | openapi 不漂移 | `test_api.py:211-214` | 逐字节断言通过；`openapi.json` 零 diff |
| 4 | 曲线条数 | 真实小 cube，`len(comparisons) == len(aggregates.parts)` | 等于已确认（超像素 × 标签）组合数，非 mock |
| 5 | 数值等价 | 任取一块，响应 `mean` vs numpy 直算同区域逐波段均值 | 一致到声明容差；`len(mean) == shape[2]` |
| 6 | 后端原序 | 扩展前后 `comparisons` 按 `(superpixel_id, label_index)` 逐项比对 | 完全一致；`test_quality.py:53` 不失效、不重定位 |
| 7 | 双通道同构 | save 返回 `quality` vs 独立 validate 响应 | 结构一致（字段集合、顺序、类型） |
| 8 | **NaN 契约（v1.4 重写，拆 8A / 8B 两个子门）** | **8A**：构造源谱含 NaN 的真实小 cube，分别请求 validate 与 save → 期望 **HTTP 400** + `error=NON_FINITE_SPECTRA`，**不是 200、不是 500**；断言 `row_blocks`（superpixels.py:59-66）零 diff、未绕过 guard。**8B**：在 `quality.validate` **返回边界注入**非有限值（不经 cube 读取），验证递归转换把 `cos` / `d_s` / `tau` / 两处 `mean` 的非有限值转为 `null`，且经 FastAPI 序列化为 **HTTP 200、整份响应无裸 NaN**；构造方式由执行方在卡允许范围内选择（转换函数单元测试 + validate 路由返回值的 HTTP 契约测试），**禁止**改读取路径、绕过 guard、或伪造 `aggregates` 冒充真实谱线 | 8A 保持上游拒绝规则；8B 证明返回边界转换生效。两门均为**新增用例**，既有基线（249 / 497）不含此类用例。**8B 是防御性契约测试，不是「修复现状活 bug」的回归门**，不得宣称「补丁前必红」；v1.1 对该门的相关表述作废 |
| 9 | cos 与可疑语义 | 8B 注入用例 + 正常 cube 对照 | cos 由原始 ndarray 算出（转 `null` 只作用于输出层）；`suspicious` 成员与扩展前完全一致，转换层不改变它；`quality.py:36` 零 diff；`cos` 为 NaN 的 UI 分支标注为当前不可达（防御性，见 §2.2 ②） |
| 10 | TS 空值兜底 | 前端测试构造 `cos: null` / `tau: null` | `:452` `toFixed` 与 `:453` `τ=` 不抛错，有测试覆盖 |
| 11 | 剔除闭环 | 视图内 erase 一块 → 重拉 validate | 曲线数减一、统计与 `references` 同步、视图与质量态同步刷新；`annotation_draft` 仅按既有 edit 语义变更（validate 本身零写入） |
| 12 | 前端口径 | `spectrumReview.test.ts` | 横轴 band index、hover 显示波长、按标签着色、前端 cos 升序且 null 末尾、多曲线共用 y 轴、`curveRuns` 断线；未复用波长优先映射 |
| 13 | 响应体积 | 按实际 n_segments 实测（至少默认 200 与更大一档），**validate 与 save 两通道都测** | 记录实测字节并对照 8 MiB；超限时的第一缓解是限 6–8 位有效数字，不得擅自改响应结构；**不得自行新增 Python 侧封顶 / 截断曲线 / 分页**（见 §3.4 口径） |
| 14 | 零版本副作用 | **单独一次 validate 请求**前后比对（不含 erase 动作） | `annotation_version` / `sample_spectrum` / 快照目录 / `annotation_draft` 无新增或变更；erase 写 draft 属 §6 门 11 的既有语义，不在本门范围 |
| 15 | 有界读取 | 仿 `test_session.py:153` 的 monkeypatch | `read_region` 单次行块 ≤ `block_size`，无整立方体物化 |
| 16 | 无自动剔除 | 全量 diff 审阅 | 不存在按 cos 阈值自动 erase / 自动改标签的逻辑；D1–D8 与 §2.2 四项无偏移 |
| 17 | **清单隔离（v1.5 判定基准）** | `git show --name-only <功能提交>` + `git diff --cached --name-only` + `git diff --ignore-cr-at-eol --quiet -- <path>` + `git ls-files --eol -- <path>` + mtime | 功能提交 `b41bf10` 仅含 §4 清单内 **8** 文件；Rust / openapi / preprocess / 7 个 untracked 零改动；在途改动无回滚；**暂存区为空**。对 `git status` 显示的清单外 `M`，须同时满足五项判据才判为噪声：①未进功能提交 ②`git diff --cached` 对该路径为空 ③忽略行尾后无实质差异（`--quiet` 退出 0）④`git ls-files --eol` 显示索引与工作区仅 eol 不同（`i/lf w/crlf`）⑤mtime 早于本次开工。全部满足 → **已知行尾/索引可见噪声，不计入「清单外文件改动」，门 17 可关闭**；收据须列全路径、五项实测结果，并声明未做任何恢复操作。已实测 `artifacts/step2/` 14 项全部满足，判为噪声。**不得**对它们执行 `checkout` / `restore` / `add` / `reset --hard` / `--renormalize` |

---

## 7. 即停条款

1. §0.2 任一锚点漂移（grep 值与本卡不符）→ 停，上报，禁止按偏移推算。
2. 基线三项任一失败或既有用例变红 / 变少 → 停。
3. 出现 §4 清单外文件改动，或清单内 in-flight 文件发生回滚 / 在途内容丢失 → 停。**但按 §6 门 17 五项判据核实为行尾/索引可见噪声的 `M` 不算「清单外文件改动」**（v1.5）；此时不得即停掩盖，也不得自行恢复。
4. `openapi.json` 出现 diff、`src-tauri/src/**` 出现改动 → 停。
5. validate 或 save 任一条通道出现 HTTP 500 / 非有限值未转 null → 停，不得靠前端兜底掩盖。
6. `quality.py:36` 出现任何改动、`comparisons` 顺序发生变化、`test_quality.py:53` 被重定位 → 停。
7. 出现 per-curve `nan_bands`、自动剔除逻辑、新增标注状态、labelme JSON 格式变更 → 停。
8. 横轴变波长优先、多曲线各自 y 轴自缩放、`CompareChart.tsx:38` 调用形态被改 → 停。
9. 新增端点 / 新增 Rust op / 加 `response_model` → 停（本卡已定扩展 validate 路线）。
10. 8 MiB 实测超限且无法通过限有效位数缓解 → 停，上报由需求方另拍板，不得自行改响应结构，**也不得自行补 Python 侧封顶 / 截断曲线 / 分页**；Python 侧显式封顶属延后另立卡的范围，执行方在这个点上零裁量权。
11. 任何验收门无法给出真实数字或取数口径 → 停，写「未验证」，禁止空断言。
12. 为构造门 8 的 NaN 输入而修改 `row_blocks` / `aggregate_spectra` / `spectral_statistics`、绕过 guard、放宽 `NON_FINITE_SPECTRA` 检查，或把源谱含 NaN 的请求做成 HTTP 200 → 停（上游拒绝规则是本卡不改的既有设计，见 §3.3）。

## 8. 流程与提交

- 卡**先单文件提交入库**，再发提示词；**两卡不同时在途**；逐文件 `git add`（**禁 `-A` / `.`**）；提交隔离；远程推送归需求方本人。
- 本卡不改历史提交（`3059c45` / `cbb6f9e`），不动 TASK-26 在途改动。
- 测试命令逐字使用 §0.1；Python 必须 `-m pytest` 且分区独立临时根；Rust 本卡不涉及，`cargo test` / `clippy -D warnings` 不触发。
- 收据（`.runtime/` 下）不进 git；环境噪声与代码错误分开陈述。
- **发提示词时不另加口头口径**：卡是唯一口径来源，§3.4 的大 n_segments 取舍、§6 / §7 的验收与即停条款已写死；需要变更须另出修订版卡并入库，不得以对话补充说明替代。

## 9. 证据索引与修订记录

**实测证据（2026-11-05）**：`JSONResponse({'cos': nan})` → `ValueError: Out of range float values are not JSON compliant: nan`；最小 FastAPI 路由 → `500 / Internal Server Error`；`nan < 0.8579512304124653` → `False`；`sorted([0.5, nan, 0.2])` → `[0.5, nan, 0.2]`；`np.median` 含 NaN → `nan`；前端 249/249；Python annotation 391+2 skipped、data 106。

**口径链**：v1 初稿 → v2（独立 validate 路线、D1–D8 定案）→ v2.1（D6 拍板、删 per-curve `nan_bands`）→ v2.2（NaN→500 事实修正、四项实现口径）→ **本卡**（执行期唯一口径）。

**本卡相对 v2.2 新增的三处收口**（均在 v2.2 允许范围内，未重开任何定案项）：
1. 新增 `FR-E23`（P1）编号与优先级拍板（v2.2 §0.3 只说「必须新增 FR」，编号留给出卡）。
2. `json_safe` 二选一收口为「quality 模块内实现同语义极小函数」（v2.2 给了「复用 json_safe 或本模块实现」两个选项）。
3. 基线数字按本卡改动范围实测（前端 249 / Python 497+2 skipped），不照抄 TASK-27。

**v1.1「顺带修复的既有潜在缺陷」补记 —— v1.4 修正（原断言不成立）**：v1.1 曾写「任一已标注超像素含 NaN 波段 → `cos` 为 NaN → validate / save HTTP 500」。经 v1.4 复核，该链被 `row_blocks`（`superpixels.py:59-66`）在 yield 前抛 `NON_FINITE_SPECTRA` 阻断、映射 HTTP 400，**源谱 NaN 不会进入 cos 计算，也不存在这条 500 缺陷**。故 §3.3 的返回边界统一转换改定性为**防御性契约**（防止未来上游规则放宽、或计算派生 NaN 进入响应时触发 `JSONResponse` 500），不是「修复现状活 bug」；§6 门 8 相应拆为 8A / 8B，v1.1「补丁前必红、补丁后必绿」表述作废。**计算派生 NaN 仍理论可达**（numpy 实测 `sums/counts` 在 `counts=0` 时为 NaN → `d_s` → `np.median` 为 NaN），但默认 SLIC 的 segment id 连续，真实 cube 下**未实测复现**，标「未验证」。FR-E23 的 P1 定级不变（本就不依赖该缺陷论证）。

**v1.1 修订记录（2026-11-05，独立复核后）**：① §3.4 新增「大 n_segments 的 Python 侧封顶」定案——本卡不做、延后另立卡、执行方禁止自行加封顶 / 截断 / 分页；② §6 门 13 与 §7 条款 10 同步收紧；③ §8 明确「发提示词时不另加口头口径」，把复核方原建议的「口头带一句」改为卡内固化；④ §6 门 8 补「新增用例、补丁前必红」以免 500 被误归为基线噪声；⑤ §9 补记上述缺陷；⑥ 修正两处引用：`json_safe` `:40-55` → `:40-56`、`SpectrumReadout:45-47` → `DisplayToolbar.tsx:44-48`。**D1–D8、v2.2 四项口径、FR-E23 / P1、三处收口、基线数字均未改动。**

**v1.2 修订记录（2026-11-05，执行方开工闸门首触即停后）**：执行方按首触即停纪律报告——卡 §0.1 要求「全新临时根」，但备卡方实跑基线遗留的 `sa-gate-28-annotation` / `sa-gate-28-data` 两目录已存在且非空，`New-Item -Force` 会复用，卡未规定处置口径。核实属实（两目录分别含 5687 / 673 个条目）。修订：① §0.1 Python 两分区命令改为 **GUID 唯一根 + 去掉 `-Force` + `Test-Path` 存在性断言 + `&` 调用**，备卡方已用新命令实跑 `data` 分区验证（106 passed / EXIT=0）；② 明确旧目录属已知状态、**不复用不删除不改名、不构成即停项**，GUID 碰撞换一次即可；③ 明确**耗时仅记录、pass/fail/skip 才是唯一断言**，避免 800.669 ms / 20.37 s 一类波动触发误停；④ 明确 `.config/git/ignore` 权限 warning 属环境噪声。**D1–D8、v2.2 四项口径、FR-E23 / P1、§3 接口契约、§4 文件清单、§6 17 道门、§7 即停条款、基线计数（249 / 391+2 / 106）全部未改动。**

---

**v1.3 修订记录（2026-11-05，Python 基线失败即停后）**：执行方按 §7 条款 2 停工，报告 `annotation` **349 passed / 42 failed / 2 skipped**（EXIT=1）、`data` **106 passed**（EXIT=0），首个失败 `test_confirm_routes.py::test_overlap_locations_and_four_arbitrations[erase]` 的 `session.py:365 → guard.py:338 → os.mkdir` 抛 `FileNotFoundError: [WinError 3]`。备卡方独立复核：
- **根因 = Windows MAX_PATH 260**，非代码回归。失败路径 `.../app/annotations/<uuid>/v1.<GUID>.tmp` 在旧 C 盘固定根下 229 字符（安全），v1.2 的 C 盘 GUID 根下 **262 字符**（加 `label_map.npz` 达 276）。对照实验：长 C 盘 GUID 根（96 字符）跑该测试 = **1 failed / WinError 3**；E 盘短根（34 字符）跑同一测试 = **1 passed / EXIT=0**；E 盘短根跑 `test_confirm_routes.py` 全文件 = **11 passed / EXIT=0**。
- **裁定**：v1.2 的 C 盘 GUID 唯一根口径作废；42 项失败判为**环境路径长度导致的假失败**，不计入收工门，不得据此改源码 / 改测试 / 放宽断言；基线计数仍为 249 / 391+2 / 106。
- **修订**：§0.1 两分区命令改为 `E:\AI_Agent\.runtime\` 下短根（`t28a-` / `t28d-` + 8 位随机，根路径 ≤ 40 字符），保留全新 / 独立进程 / 无 `-Force` / `Test-Path` 断言；新增 MAX_PATH 硬约束与 safe-delete 回合预算说明。
- **如实记录**：备卡方在同一对话回合内累计多次 pytest，触发 `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":50,"threshold":50,"scope":"turn"}`，其自身发起的全分区复跑出现大量 `E`（setup error），**属备卡方验证环境的回合预算耗尽**，不作为 v1.3 的失败证据，也不宣称「全分区已复跑验证」。全分区计数由执行方在其独立回合按 v1.3 命令实跑确认。

**D1–D8、v2.2 四项实现口径、FR-E23 / P1、§3 接口契约、§4 文件清单、§5 实现步骤、§6 17 道门、§7 即停条款、§8 流程与提交、基线计数全部未改动。**

**v1.4 修订记录（2026-11-05，实现前 NaN 契约冲突停工后）**：执行方三道闸门全通过（annotation **391 passed + 2 skipped / EXIT=0 / 317.40 s**；data **106 passed / EXIT=0 / 13.69 s**；**32 条锚点 32/32 一致**），实现前发现门 8 与上游读取规则衔接不明，按纪律停工。备卡方独立复核：
- `superpixels.py:59-66` 的 `row_blocks` 在任何非有限输入时于 yield 前抛 `DataError("NON_FINITE_SPECTRA")`（纯 Python 实测：code 正确、`status_code` 属性缺失、`as_dict()` 为结构化错误）；`aggregate_spectra`（`session.py:96`）与 `spectral_statistics`（`quality.py:40`）共用该读取器。
- 按 `app.py:82-85` + `LABEL_PATHS`（`api/annotations.py:32`）静态判定并以同逻辑最小复现实测：该错误映射 **HTTP 400** + `{"error":"NON_FINITE_SPECTRA",...}`，不是 200 / 500。
- numpy 实测 `sums / counts[:, None]` 在 `counts=0` 时产生 NaN → `d_s` 含 NaN → `np.median` 为 NaN，计算派生 NaN 理论可达；但默认 SLIC 的 segment id 连续，真实 cube 下**未实测复现**，标「未验证」。
- **裁定**：源谱含 NaN 的用例期望 400，不得要求 200；返回边界转换是防御性契约，用「注入非有限值」的契约测试验证，**不改读取路径**。门 8 拆 8A / 8B、门 9 同步调整、§7 加条款 12、§0.2 加锚点 33 / 34（前 32 条已核验通过，只需补核这两条）；§2.2 ②、§3.2、§3.3、§5 第 3 步、§9 相关表述修正；**v1.1 的「现状 500 缺陷」断言作废**。
- **D1–D8、v2.2 四项实现口径、FR-E23 / P1、§3 接口契约主结构（comparisons 加 `mean`、新增 `references`）、§4 文件清单、§5 五步、§6 其余 16 道门、§8 流程、基线计数（249 / 391+2 / 106）全部未改动。**

**v1.5 修订记录（2026-11-05，门 17 即停后）**：功能提交 `b41bf10` = 8 个 §4 清单内文件（789 insertions / 15 deletions），门 1–16 通过（前端 **264 pass / 0 fail**、TypeScript 通过；Python annotation **400 passed + 2 skipped**、data **106 passed**；响应体积 `n_segments=200` 时 validate **1,626,440 B** / save **1,627,008 B**，`=400` 时 **2,929,463 B** / **2,930,031 B**，均低于 8,388,608 B）。门 17 因收工时新增 14 个 `artifacts/step2/` `M` 即停。

备卡方只读核实（**未对索引 / 工作区做任何写操作**）：
- `git show --name-only b41bf10` = 8 个清单内文件，与 `git diff HEAD^ HEAD --name-only` 一致；**这 14 项未进提交**。
- `git diff --cached --name-only` = **0**，暂存区为空，无 staged 行尾变更，不会误提交。
- 14 项逐一 `git diff --ignore-cr-at-eol --quiet -- <path>` **全部退出 0** → 仅 CRLF/LF 差异、无实质内容改动；样本 `build-output.log` numstat 170/170。
- `git ls-files --eol` = `i/lf    w/crlf  attr/-text` → 索引 blob 为 LF、工作区为 CRLF、无 text 属性自动转换，属固有行尾不一致。
- 14 项 mtime **全部 2026-10-18**（执行方报 10-17，实测为 10-18；均远早于 11-05 开工），工作区字节未被本次改写。
- 最可能成因：整体导入临时索引使索引 stat 缓存被替换，Git 重新比较工作区与索引后暴露了这些历史文件固有的行尾差异；**非文件内容被改、非索引 blob 被改、非 HEAD 变化**（未逐条回溯开工前索引状态，标「最可能原因」）。

**裁定**：按 §6 门 17 五项判据，14 项判为**已知行尾/索引可见噪声，不计入「清单外文件改动」**，门 17 可关闭。这 14 项**不恢复、不改写、不提交**：执行方不得执行 `checkout` / `restore` / `add` / `reset --hard` / `--renormalize`；消除这些 `M` 需改索引或改工作区行尾，超出本卡授权，且它们是 10 月历史产物，保持现状交需求方后续决定（例如统一 `.gitattributes` 或另行规范化，另立项）。收据须列全 14 路径 + 五项判据实测结果 + 「未做任何恢复操作」声明。

**D1–D8、v2.2 四项实现口径、FR-E23 / P1、§3 接口契约、§4 文件清单、§5 五步、§6 门 1–16、§8 流程、基线计数全部未改动。** 本卡的文档修订提交与功能提交 `b41bf10` 分离，门 17 的「功能提交清单」以 `b41bf10` 为准，不以最新 HEAD 为准。

---

> 卡 v1.5：功能提交 `b41bf10` 已落，门 1–16 通过，门 17 按 v1.5 判据可关闭；四次停工（临时根复用 / MAX_PATH / NaN 契约 / 门 17 行尾噪声）均已裁定。未 push / tag / 打包，远程推送归需求方本人。
