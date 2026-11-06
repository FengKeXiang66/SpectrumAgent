# TASK-32 按需导出卡（P0-1 · 正式卡）

> **状态**：**已入库、可执行**（2026-11-06 23:58 起草方按需求方授权单文件提交；提交号以 `git log -1 --format=%h` 为准，提示词中亦给出）。队列：TASK-30 复现基线 `c59dc1d`、TASK-31 输出根接线 `974e8f4` 均已入库并 G1–G8 收口，零卡在途；本卡入库后提示词不用排队。**本卡不代发提示词**；卡是执行期唯一口径，对话补充无效，变更另出修订版。P0-4（`scaler_params` 唯一真源）与 NAS 专属语义卡继续挂账，本卡不承载。
> **卡型**：正式卡。契约改动（新增导出端点、`kind` 枚举扩容、`api/openapi.json` 重生成）+ 多项新口径决策（导出范围、标定真源、ENVI 格式、内存红线、流式下载、manifest 关联）。轻量判据（无新口径决策）不满足。
> **事实源**：需求 v2.7 `artifacts/step3/requirements-v2.7.txt`；需求/UI 文档 `E:/中达瑞和公司/10月15日/光谱数据AI-Agent处理平台_需求分析与设计.html`（FR-A12 `—:523`、§6 `—:1096/2852`）、`…_第一阶段UI设计与高保真原型.html`（S03 `—:1432`、S09 产物清单 `—:2074-2076`、验收项 13 `—:2517`）；`TASK-05-预处理.md:121/197`；`TASK-31-输出根接线.md:17`（D1 裁定）、`:128`（导出卡挂账）、`TASK-30-复现基线.md:112`（`test_run.py:60` 点名）。归档版本禁引。
> **行号时效**：以下全部为 **代码基线 `974e8f4`（TASK-31 十九文件入库后）** 实读重锚；**本卡提交只新增卡文件、不含任何代码改动，故 §3 代码行号仍以 `974e8f4` 为准，不按本卡提交号推算**。开工须同时确认 HEAD 含 `974e8f4` 与本卡提交号，并逐条 grep §3，漂移即停，禁止按偏移推算；格式与键清单一律锚当前代码基线，引用历史证据须标快照时间与提交。**锚点订正记录**：首次开工即停时发现 `TASK-30-复现基线.md:110` 为空行（该卡 §8「导出卡已知影响点」实际在 `:112`），本卡三处引用已统一改为 `:112`；同时对 `TASK-31-输出根接线.md:17/128`、`workflows.py:132-141`、`api/preprocess.py:40-46`、`types.ts:6,27-31`、`PreprocessPanel.tsx:33/85/175/185`、`panel.test.ts:48-64` 及 §3 全部代码锚点逐条复核，无其它漂移。
> **不承载**：FR-A12 vs §6 的「默认只存参数、物化只走显式导出」裁定已由 **TASK-31 D1（`TASK-31-输出根接线.md:17`）写定一次**，本卡按行号引用、不各裁一套；`scaler_params` 双口径（P0-4）、输出根接线、配方哈希 / manifest 字段集（TASK-30）均不在本卡。

## 1. 改什么（一句话）

给「默认不物化」补上唯一出口：一次**显式、被审计**的导出动作，把某次 run 的处理结果按全图形状写成 ENVI `.hdr + .img`（可被 ENVI / MATLAB 直接读取），登记进 `preprocess_artifact` 并关联 run manifest；**不改 `report.json`、不改 run 的默认产物集合、不把整幅立方体常驻内存**。

## 2. 定案口径（不重开）

| # | 口径 | 依据 |
|---|---|---|
| D1 | **承接裁定**：默认维持「中间产物只存参数不存数据」（`TASK-05:121`），物化只走「显式导出」这一条被审计的动作路径。引用 `TASK-31-输出根接线.md:17`（D1）与 `:128`（挂账清单），本卡不重开裁定 | 需求 FR-A12 `—:523` 要求中间立方体落输出根，§6 `—:1096/2852` 要求只存参数；矛盾已由 TASK-31 收口。`run.py:360` 的 `not_applicable` 保持原样 |
| D2 | **触发 = 显式动作**：新增 `POST /api/v1/preprocess/runs/{run_id}/exports`，只有该请求才产出 `processed_cube`；**run 创建 / 完成一律不自动导出**，默认产物仍恰为 `sample_spectra` + `report` 两件。幂等：同一 run 重复导出覆盖同一路径并更新登记，不产生第二套目录 | `run.py:389` 现行只登记两件；UI S09 `—:2074-2076` 的「产物」清单是每次实验的台账，需有可点名的动作 |
| D3 | **导出范围 = `full_cube`**：输出形状与源 `(lines, samples, bands)` 一致，逐行遍历**全部像素**（不做 `label_map` 筛选）；拟合参数只用 run 当时的**已标注像素**（与训练侧一致），外推到全图。`scope="full_cube"` 与拟合像素数写进 export manifest。`labeled_only` 不实现、挂账 | `run.py:89-108` 的 `BoundedInput.lines()` 按 `label_map` 选像素且 `:99-100` 对 raw DN 施加 B01；ENVI / MATLAB 直接读取要求立方体形状完整（UI `—:1432`） |
| D4 | **标定真源 = `report.json` 的 `steps[*].meta`，transform-only 重放**：`standardize` 的 `meta.fitted`、`pca` / `mnf` / `ica` 的 `meta.mean` + `meta.loadings` 在 run 时已完整落进 report（`fit_standard` `run.py:142-143` 返回 `{"method","fitted",…}`；`fit_pca` `operators/pca.py:59-64` 返回 `loadings/mean`；`run.py:352` 把 `records` 写进 `report.steps`；`_merge_records` `run.py:231` 对 `i in fits` 明确 `continue`，保留原 meta）。导出据此重建逐像素变换，**禁止重新 fit、禁止逐块 fit、禁止把全图像素纳入拟合**；B01 反射率转换参数取 `report.b01.meta`，对每个 raw 行施加（与 `run.py:98-100` 同一支） | 预处理算子是 fit-on-apply；逐块重 fit 会产出整张错图且不报错（R15）。`inference.py:38` `apply_with_calibration` 的冻结思路可参照，但其 calibration 是注册时重建、非 run 实测值，本卡不引用它作真源 |
| D5 | **不碰 P0-4 / 不改 run.py 契约**：导出读 `report.json` 与 `preprocess_run` / `preprocess_artifact`，**不读 `scaler_params`、不改 `run.py` 的 report 键集、不改配方哈希与 manifest 字段集**（TASK-30 / TASK-31 契约零漂移）。`report.json` **禁止回写**（TASK-30 v1.2 已禁两阶段回写） | 两套标定来源属 P0-4 另卡；`run.py:391` 写 `scaler_params` 而 modeling 层零读取，是已知双口径，本卡不介入 |
| D6 | **格式 = ENVI Standard `.hdr` + `.img`**：`data_type=4`（`float32`，见 `data/readers/header.py:13` `CODES[4]="f4"`）、`interleave=bsq`、`byte_order=0`、`header_offset=0`，必填 `samples/lines/bands/data_type`，并写 `wavelengths`（取 `report.wavelengths`，即 run 的 `final_axis` `run.py:309`）、`fwhm`（源 header 有则透出）、`data_file=<同名>.img`。头字段逐字对齐 `header.py:15` 的 `KNOWN` 词表与 `:19-23` 的 `key_name` 规范化，**必须能被自家 `data/readers/envi.py:15-40` 读回并通过 `validate_size`**。`bbl` 不在 `KNOWN`（`header.py:15`），本卡不写、挂账 | UI `—:1432`「可被 ENVI / MATLAB 直接读取」；`header.py:87-107` `normalize` 对缺字段 / 非法 interleave / 非法 dtype 会抛 `HEADER_INVALID` |
| D7 | **内存红线（流式分块写）**：按 `block_size=32` 行逐块 `read_region` → 施加 B01 → transform-only → 以 `np.memmap` / 追加写落 `.img`，**禁止整幅 `ndarray` 常驻**；每块处理完 `del block`，峰值 RSS 用 `run.py` 的 `peak_rss()` 监控并写进 export manifest。`.hdr` 在全部块写完后一次性生成（体量 KB 级）。**论证**：`TASK-05:121` 禁的是「run 时全量物化 / 长期占用存储」；显式导出是用户动作 + 分块流式写，不违 RAM 红线，产物落在已配置输出根（`backend/paths.py:51-61`）并纳入既有备份 | `run.py:210-215` `_stream` 已有逐块遍历；`run.py:90-92` `BoundedInput.lines()` 每块重新 `readable` 且 `:108` `del block, dataset, line` |
| D8 | **登记与审计**：复用 `preprocess_artifact.kind` 已留位的 `'processed_cube'`（`migrations.py:52` CHECK 枚举），登记 `.hdr` / `.img` **两行同 kind**（`UNIQUE(run_id,kind,relative_path)` `migrations.py:56` 允许），`relative_path` 为 POSIX 相对**生效产物根**（`backend/paths.py:51` `artifact_root`、`:59` `preprocess_directory`），sha256 实算（`run.py:387` 同款 `file_sha256`）。写文件一律走 `storage.resolve_write`（`guard.py:387`）与 `storage.replace`（`guard.py:407`），导出动作留 `EXPORT_CREATE` 审计；输出根不可用时由 TASK-31 D5 的局部状态结构化拒绝 `OUTPUT_ROOT_UNAVAILABLE`（`guard.py:210`），**不静默回落本机**。**`DDL` 常量零改动**（`test_migrations.py:23-33` 逐字节比对 TASK-05 卡内 SQL） | 输出根分层已由 TASK-31 落地；`recycle.py:219-235` 的 `_owned` 已同时支持「未配置 3 段 / 已配置 4 段」`preprocessed` 路径，导出物放 run 目录内自动纳管 |
| D9 | **超 8 MiB 流式下载**：`MAX_ARTIFACT_BYTES`（`api/preprocess.py:17`）是 IPC 响应保护，**本卡不改**；`artifact` 端点 `:144` 的 `kind: Literal["sample_spectra","report"]` 扩到含 `processed_cube`，但 `:160` 的 size 门对大立方体必拒。定案：新增**独立流式端点** `GET /api/v1/preprocess/runs/{run_id}/exports/{filename}`，按固定 chunk 迭代读、`StreamingResponse` 返回，保留 `:149-154` 的 POSIX 相对路径与越界校验；既有 `test_routes.py:262-273` 的 8 MiB 边界断言保持绿 | 用户口径检查单 ④；`api/preprocess.py:143-163` 端点全文；超大产物不应挤占 IPC 响应缓冲 |
| D10 | **关联 run manifest（不回写 report）**：导出目录内新增 `export_manifest.json`，字段 `run_id` / `recipe_pipeline_sha256` / `recipe_hash_alg` / `input_fingerprint` / `code_version` / `scope` / `fit_signature`（各 fitted step 的规范化参数摘要 sha256）/ `envi`（shape/dtype/interleave/wavelengths 摘要）/ `artifacts`（两文件 kind + relative_path + sha256）/ `peak_rss_bytes` / `exported_at`。`report.json` 字节不变；关联靠 `run_id` + 哈希引用，可被 `run_provenance` 只透出白名单字段 | TASK-30 D5 的 manifest 字段集不改；FR-A13⑤ 路径不进日志 / 工具 / LLM 上下文（`workflows.py:132-141` 白名单） |
| D11 | **契约与 openapi**：新增端点 + `Literal` 扩容会改变 `app.openapi()` → **必须重生成 `src-python/spectrumagent/api/openapi.json`**（格式 `test_api.py:209-215`：`json.dumps(app.openapi(), ensure_ascii=False, indent=2)+"\n"`，按 `os.linesep` 换行），断言本身不得删改。前端 `src/components/preprocess/api.ts:21` 的 `getArtifact` kind 联合类型、`types.ts` 的封闭结构、`PreprocessPanel.tsx` 需同步扩字段并加「显式导出」入口 | `test_api.py:209-215` 逐字节断言；TASK-31 D9 同款处置；前端封闭 TS 结构不同步会静默不可见 |
| D12 | **`test_run.py:60` 的处置（对 TASK-30 §8 的精确化）**：TASK-30 预判「导出卡登记 `processed_cube` 后该行必红」，本卡定案 `export` 默认关闭 → 既有 `run_case` 从不触发导出，该集合断言**预期保持绿**；新增导出用例显式断言导出后集合含第三 kind。若实现使既有 run 也产生第三 kind 而变红，须按「按 export 分支判定」**适配语义**，不得删断言、不得放宽为子集判定凑绿 | `tests/preprocess/test_run.py:60` 逐字为 `== {"sample_spectra","report"}`（HEAD `974e8f4` 实读）；`TASK-30-复现基线.md:112` 挂账原文；TASK-30 §7 即停 6「既有用例变红变少 → 停」 |

## 3. 现场锚点与影响面（HEAD `974e8f4` 重锚，开工 grep，漂移即停）

| 文件:行 | 锚定内容 | 动作 |
|---|---|---|
| `TASK-31-输出根接线.md:17` / `:128` | D1 裁定原文与导出卡挂账清单 | 只引用，不改 |
| `TASK-30-复现基线.md:112` | 「导出卡已知影响点：`test_run.py:60` 必红」 | 见下方 D12 处置，不改该文件 |
| `preprocess/run.py:98-100,89-108,142-143,210-215,231,309,352,360,369,387-389` | B01 施加、逐块 `lines()`、`fit_standard` 的 `meta.fitted`、`_stream`、`_merge_records` 保留 fits meta、`final_axis`、`report.steps`、`not_applicable`、`outputs.artifacts`、artifact 登记与 sha256 实算 | **不改 run.py**；只读其 report 产物与复用分块遍历思路 |
| `preprocess/operators/pca.py:52-64` | `fit_pca` 返回 `mean/loadings/meta`（`loadings` 进 meta） | 只读，作为 D4 真源证据 |
| `modeling/inference.py:38-101` | `apply_with_calibration` 冻结重放思路 | 参照思路，**不作标定真源**（其 calibration 是注册时重建） |
| `preprocess/migrations.py:49-57,67-95` | `preprocess_artifact.kind` CHECK 枚举已含 `processed_cube`、`UNIQUE(run_id,kind,relative_path)`；`migrate()` 内 TASK-30 附表 | **DDL 常量零改动**；无需新表 |
| `tests/preprocess/test_migrations.py:23-33` | `DDL.strip()` 与 TASK-05 卡内 SQL 逐字节比对 + PRAGMA 快照 | 验收门 G1；改 DDL 或给原表加列都会红 |
| `tests/preprocess/test_run.py:60` | `{item["kind"] for item in row["artifacts"]} == {"sample_spectra","report"}` | **D12**：`export` 默认关闭 → 既有 `run_case` 不触发导出，该断言预期**保持绿**；若实现使既有 run 也产生第三 kind 而变红，须按「按 export 分支判定」适配语义，**不得删断言 / 放宽为子集判定凑绿**；新增用例显式断言导出后集合含 `processed_cube` |
| `api/preprocess.py:17,40-46,72-80,143-163` | `MAX_ARTIFACT_BYTES`、`PreprocessRunRequest`、`make_router`、`artifact` 端点（Literal kind、路径越界、8 MiB、FileResponse） | **改**：新增 POST 导出端点、新 GET 流式端点、Literal 扩容；**不改** `MAX_ARTIFACT_BYTES` 与既有端点语义 |
| `backend/paths.py:48-61,70-82` | `preprocessed` / `artifact_root` / `preprocess_directory(project_id,cube_id,run_id)` 分层、`create_directories(activate_output=…)` | 不改；导出目录取同一 `preprocess_directory` |
| `storage/guard.py:199-226,387-407` | `_resolve` 输出根分流、`resolve_write` / `mkdir` / `replace` / `resolve_delete` | 不改；导出写走既有单一出口 |
| `storage/recycle.py:219-235,270-279` | `_owned` 的 `preprocessed` 三段 / 四段判定、删除清单拼接 | 不改；导出物在 run 目录内自动纳管 |
| `data/readers/header.py:13-15,19-23,78-107` | `CODES`、`KNOWN`、`key_name`、`Header`、`normalize` | 不改；导出头按此词表生成，G2 用 `readers/envi.py:15-40` 读回 |
| `data/readers/binary.py:30-44` | `mapped_dataset` 的 interleave / dtype / offset 处理 | 只读，G2 依据 |
| `api/openapi.json` + `tests/data/test_api.py:209-215` | openapi 逐字节快照 | **必须重生成**（D11），断言不得删改 |
| `src/components/preprocess/api.ts:21,26-29` / `types.ts:6,27-31` / `PreprocessPanel.tsx:33-85,175-185` | `getArtifact` kind 联合、`Report` 封闭结构、面板取 report / 渲染注脚 | **改**：扩 kind 联合与类型、加「显式导出」按钮与产物清单条目；注脚语义不变 |
| `src/components/preprocess/panel.test.ts:48-64` | 三条 `doesNotMatch` 源码 pin（网络调用 / 更新删除配方 / 数值计算） | 新按钮须走既有 `preprocessClient`，禁引入新网络通道或数值计算 |
| UI `—:1432` / `—:2074-2076` / `—:2517` | 「可被 ENVI / MATLAB 直接读取」、S09 产物清单、验收项 13 源目录零改动 | G2 / G4 依据 |

**影响面结论**：`run.py` / `guard.py` / `paths.py` / `recycle.py` / `migrations.py` 的 DDL 与 TASK-30 / TASK-31 契约零改动；必红点集中在 `test_run.py:60`（按 D12 处置）、`test_api.py:209-215`（重生成快照）、openapi 三处，均按适配语义处理。

**开工自检**：① `git status --short` 全文回报（现场为 14 项 `artifacts/step2/` 噪声 M + 1 个 untracked `docs/AI自动标注路径分析.md` = 15 项，暂存区空、HEAD 含 `974e8f4`；§4 目标文件须为非 M，否则按 §7 即停 1 上报）；② 后端基线（仓库根、命令逐字、全路径）：`./.venv/Scripts/python.exe -m pytest src-python/tests/agent/test_project_paths.py src-python/tests/storage/test_task25_acceptance.py src-python/tests/data/test_api.py::test_api_schema_snapshot src-python/tests/preprocess -q --no-header`，**HEAD `974e8f4` 起草方实测参照 317 passed / 1 warning / 80.00s**（隔离短根 `.runtime/t32p`，耗时软判据），须实测回报、不得沿用参照数字当已通过；执行前在仓库内预建**本次全新**临时根 `.runtime/task32-exec-temproot`（`.gitignore:43` 已忽略；**短根**，避免 Windows MAX_PATH 260 —— TASK-31 长根 262 字符曾触发 `FileNotFoundError`），并**同时**设 `PYTEST_DEBUG_TEMPROOT` / `TMP` / `TEMP` 三变量指向它；③ 前端 `node --test "src/**/*.test.ts"`（双层 glob 逐字；`src/*/.test.ts` 实测 0 tests 且 exit 0 假绿、禁用），**实测参照 266 / 266 pass / 0 fail**；`node node_modules/typescript/bin/tsc --noEmit` **实测 EXIT=0**；④ 回报 Python / Node 版本（参照 Python 3.12.13；node 版本差异不作判据、不触发即停）。唯一判据「既有用例不变红变少」；数字与参照不符先说明差异来源，不得继续。

## 4. 改动清单（清单外零改动）

| 文件 | 动作 |
|---|---|
| `src-python/spectrumagent/preprocess/export.py` | **新建**：`replay_from_report`（D4 transform-only 重放）、ENVI 头生成、分块流式写、export_manifest、动作编排 |
| `src-python/spectrumagent/api/preprocess.py` | 新增 `POST …/runs/{run_id}/exports` 与 `GET …/runs/{run_id}/exports/{filename}`；`artifact` 的 `Literal` 扩 `processed_cube`；不改 `MAX_ARTIFACT_BYTES` |
| `src-python/spectrumagent/api/openapi.json` | **重生成**（D11 格式） |
| `src/components/preprocess/api.ts` / `types.ts` | `getArtifact` kind 联合、导出请求与响应类型 |
| `src/components/preprocess/PreprocessPanel.tsx`（或 S09 对应组件） | 「显式导出」按钮 + 产物清单条目；不新增独立网络通道 |
| `src-python/tests/preprocess/test_export.py` | **新建**：ENVI 自读回、数值等价、内存红线、登记/审计、流式下载、manifest 用例 |
| `src-python/tests/preprocess/test_run.py` | D12：`test_run.py:60` 按分支适配（若变红）+ 新增导出后 kind 集合用例；既有断言不得删改 |
| `src-python/tests/preprocess/test_routes.py` | 新端点 / 越界 / 8 MiB 既有断言保持绿的回归用例 |
| `src/components/preprocess/api.test.ts` / `panel.test.ts` | 前端类型与按钮 pin，既有断言零改动 |
| 本卡 `TASK-32-按需导出.md` | 新建（单文件提交） |
| `preprocess/run.py`、`migrations.py`（DDL 常量）、`storage/guard.py`、`backend/paths.py`、`storage/recycle.py`、`TASK-05-预处理.md`、`TASK-30` / `TASK-31` 卡 | **零改动** |
| 14 项 step2 噪声 + 1 个 untracked `docs/AI自动标注路径分析.md` | **禁触碰**，不恢复、不改写、不提交 |

## 5. 实现要点

1. **重放顺序**：读 `report.json` → 取 `report.b01.meta` 的分支 / hdr / guard → 对每个 raw 行施加 B01（与 `run.py:98-100` 同支）→ 按 `report.steps` 顺序逐像素 transform-only：`standardize` 用 `meta.fitted`（`mean/std` 或 `min/max`，含 `zero_scale_count` 语义），`pca` / `mnf` / `ica` 用 `meta.mean` + `meta.loadings` 调 `operators/pca.py` 的 `transform`（单行调用，避免 BLAS 批大小舍入差异，参照 `inference.py:85-88`）；`meta.method` / `axis` 与 `report.wavelengths` 校对，不一致即抛 `EXPORT_CALIBRATION_MISMATCH` 并停止，**不静默降级**。
2. **只写全图、不重拟合**：拟合像素集合来自 run 当时的标注，`fit_signature` 是对 `report.steps[*].meta` 中 fitted 参数做的规范化 sha256（`sha256/json-canonical-v1`，与 TASK-30 D2 同算法）；导出全过程**不调用任何 `fit_*` 入口**，也不把全图像素喂进拟合。
3. **分块与峰值**：`block_size=32` 行一块；`.img` 用 `np.memmap(..., mode='w+', shape=(bands, lines, samples))`（bsq 物理序）按块切片写入，或 `open('ab')` 追加；每块结束 `del` 并复用 `run.py` 的 `peak_rss()`。`.hdr` 与 `export_manifest.json` 在 `.img` 完整写入、`file_sha256` 实算之后再落，先写 `.tmp` 再 `storage.replace` 原子替换（与 `run.py:380-387` 同款）。
4. **登记与清理**：`preprocess_artifact` 两行（`.hdr` / `.img`，同 kind `processed_cube`）；失败时删除本次 `.tmp` 与半份 `.img`，`preprocess_run` 状态不改、`report.json` 字节不变。幂等重复导出：先 `resolve_delete` 旧两行对应文件再重写，或同名覆盖 + `INSERT OR REPLACE`，须保证 `UNIQUE(run_id,kind,relative_path)` 不产生重复行。
5. **出域边界**：`export_manifest.json` 只含 POSIX 相对路径与哈希，绝对路径、原始谱不进 LLM 上下文 / 日志；`run_provenance` 若透出导出信息，只送 `run_id` / `scope` / `kind` 白名单字段。
6. **流式端点**：新 GET 按固定 chunk（1 MiB）迭代，`content-disposition` 带文件名；路径校验逐字复用 `api/preprocess.py:149-154`（含 `..` / 反斜杠 / 盘符 / 越出 `artifact_root`），**不得因流式而放宽**。

## 6. 验收门（8 道，可执行、不自指）

| 门 | 命令 / 断言 | 预期 |
|---|---|---|
| G1 契约零漂移 | `pytest tests/data/test_api.py::test_api_schema_snapshot tests/preprocess/test_migrations.py` | 重生成的 `openapi.json` 与 `app.openapi()` 全等且逐字节匹配；`DDL` 常量、TASK-05 卡、TASK-30/TASK-31 契约零字节改动；逐字节断言未被删改 |
| G2 ENVI 标准与自读回 | 导出的 `.hdr + .img` 交给 `data/readers/envi.py:15-40` 解析 + `validate_size` | 返回 `SpectrumDataSet` 的 `shape=(lines,samples,bands)`、`dtype=float32`、`interleave=bsq`、`wavelengths == report.wavelengths`、`data_file` 指向同目录 `.img`；字段全在 `header.py:15` `KNOWN` 内 |
| G3 数值等价（非自指） | 随机抽 ≥20 个像素（含未标注像素），导出值与「同 report meta 的 transform-only 直算」逐元素比对 | `np.testing.assert_allclose(rtol=0, atol=1e-6)`；另断言导出过程零 `fit_*` 调用（monkeypatch 计数）；`fit_signature` 与 report meta 规范化哈希相等 |
| G4 内存红线 | 470 MB 级立方体导出，记录 `peak_rss_bytes` 与逐块增量 sha256 | 峰值 RSS 有界（与单块量级同阶，**不随立方体大小线性增长**）、无整幅 `ndarray` 常驻；增量摘要与整文件 `sha256` 相等；`TASK-05:121` 的分块论证在卡内可查 |
| G5 登记 / 审计 / 源零改动 | `preprocess_artifact` 两行 + `write_audit` 查询 + 前后源目录清单 / 哈希 / mtime 比对 | 两行 kind=`processed_cube`、sha256 与文件实算一致、`EXPORT_CREATE` 审计留痕；源目录无新增 / 删除 / 改名；输出根不可用时结构化 `OUTPUT_ROOT_UNAVAILABLE` 且不静默回落（UI 验收 13） |
| G6 流式下载 | >8 MiB 的 `.img` 走新 GET；既有 `test_routes.py:262-273` 8 MiB 边界回归 | 200，分块字节拼接与磁盘 sha256 一致；既有 `MAX_ARTIFACT_BYTES` 边界断言与 `INVALID_ARTIFACT_PATH` 断言保持绿；路径越界仍 400 |
| G7 manifest 与不回写 | `export_manifest.json` 字段逐项核验；导出前后 `report.json` 字节比对 | 字段齐全、`fit_signature` / `input_fingerprint` / `recipe_pipeline_sha256` 可回查 run；`report.json` **字节零变化**；`outputs.artifacts` 仍只列原两件 |
| G8 全量与清单隔离 | Python 七分区独立进程 + 每部全新短临时根（三变量同设、逐部启动不并行）；前端双层 glob；`tsc --noEmit`；收工 `git status` 对照开工快照 | 唯一判据「既有用例不变红变少」；仅 §4 清单文件为新增改动，14 噪声与 1 untracked 零变化、未提交 |

## 7. 即停（9 条）

1. §3 锚点漂移，或开工时 §4 目标文件已为 M → 停，上报。
2. 需要改 `preprocess/run.py` 的 report 键集 / `migrations.py` 的 `DDL` 常量 / `TASK-05-预处理.md` / TASK-30 与 TASK-31 的既有契约（**`api/openapi.json` 按 D11 重生成属许可**），或改 TASK-30 的 manifest / 配方哈希语义 → 停。
3. 重新 fit、逐块 fit、把全图像素纳入拟合、或拿 `inference.py` 的注册期 calibration / `preprocess_run.scaler_params` 当导出标定真源（P0-4）→ 停。
4. run 创建 / 完成时**自动**产出 `processed_cube`，或导出物改变 run 的默认两件产物集合 → 停。
5. 删改既有断言凑绿（尤其 `test_run.py:60`、`test_routes.py:262-273`、`test_api.py:209-215`、`test_migrations.py:23-33`）→ 停；`test_run.py:60` 若因实现变红，按 D12 分支适配语义，不放宽为子集判定。
6. 回写 `report.json`、改 `MAX_ARTIFACT_BYTES`、为流式下载放宽路径越界校验、或把绝对路径 / 原始谱送进日志 / 工具 / LLM 上下文 → 停。
7. 整幅立方体常驻内存、非分块写、峰值 RSS 随数据量线性增长，或 `.hdr` 在 `.img` 写完前先落盘 → 停。
8. 写向源目录、绕过 `storage.resolve_write` / `storage.replace`、输出根不可用时静默回落本机、或导出失败留下半份 `.img` 与幽灵登记 → 停。
9. ENVI 头缺必填字段 / 使用 `KNOWN` 外词表 / 自定义非标准 dtype 或 interleave，或新增用例只断言「文件存在」而无数值 / 出处核验 → 停。

## 8. 边界与后续（挂账，不在本卡）

- **P0-4**（`scaler_params` 唯一真源）另开卡，先裁定「两套标定来源」口径；本卡以 `report.steps[*].meta` 为真源，刻意不碰 `scaler_params`。
- **NAS 专属语义卡**：FR-A13① 连接可用性自检、③ 断线重试 / 断点续传、④ 凭据加密、只读挂载层，均不在本卡。
- `bbl` / 坏波段掩膜：`data/readers/header.py:15` 的 `KNOWN` 无 `bbl`，本卡不写；与「剔除坏波段 / 去背景」一并另卡。
- `labeled_only` 导出范围、报告导出（UI 标注为阶段三）、复现命令 `iris run reproduce`（UI `—:2080-2082`）、ENVI 压缩 / 分块切片导出，均挂账。
- 既有 `test_project_paths.py:137` 的子进程 stdout 整段解析（TASK-31 v1.2 挂账）与长临时根 262 字符 MAX_PATH 症状，另卡统一处理；本卡已直接采用短根 + 逐部启动。
- 默认仍「不物化」：导出物随数据集删除进回收站（`recycle.py:219-235` 已覆盖），「可重算产物」的定期清理桶归后续卡。
