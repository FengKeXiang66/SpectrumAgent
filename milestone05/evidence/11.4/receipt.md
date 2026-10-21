# 11.4 预处理 HTTP 路由回执

事实源：同提交 TASK-05-预处理.md（295 行，R13）与 11.4 开工令；error_code 遵用户后续裁定，从 DataError.as_dict 的 error 键提取。

## 改动文件

- TASK-05-预处理.md：纳入科祥已落盘 R13，执行者未修改任务卡。
- src-python/spectrumagent/api/preprocess.py：十二个 HTTP 操作、四个 extra=forbid 请求模型、错误适配、七字段摘要与产物下载护栏。
- src-python/spectrumagent/app.py：同一 registry 装配 RunEngine / CompareEngine，app.state 挂载、router 注入；仅扩 preprocess 校验与身份头前缀，旧 404/409/422 分支不动。
- src-python/spectrumagent/preprocess/recipes.py：仅 additive deselect_project 与语义注释，删除项目关联行；既有方法零修改。
- src-python/spectrumagent/api/openapi.json：真实 create_app → json.dumps(app.openapi(), ensure_ascii=False, indent=2) 程序化生成。
- src-python/tests/preprocess/test_routes.py：新增 44 项参数展开测试；旧测试零修改。
- milestone05/evidence/11.4/pytest-routes.txt
- milestone05/evidence/11.4/pytest-full.txt
- milestone05/evidence/11.4/app-recipes.diff
- milestone05/evidence/11.4/openapi-diff.txt
- milestone05/evidence/11.4/receipt.md

## 运行与数量

定向 44 passed；全量 617 passed / 0 failed / 0 skipped，既有 573 项保留。数字出处为同目录 pytest-routes.txt / pytest-full.txt；全量耗时 55.50s，10 条既有依赖弃用警告，无依赖安装或更新。

执行模式：cwd=E:/AI_Agent，默认参数、默认执行顺序，.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q；同一 PowerShell 命令设置 PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp。未用 pytest.exe、未过滤旧用例。

## 十二个端点点名表

下列路径均以 /api/v1 为前缀；标识符路径参数为 UUID，kind 为两值枚举。

| # | 方法 | 路径 | 成功 | 错误路径与测试 |
|---|---|---|---|---|
| 1 | GET | /preprocess/recipes | 200 列表 | legacy ValueError→400；无认证→401 |
| 2 | POST | /preprocess/recipes | 201 新建 | 重复 code / 坏 pipeline / 未知键 / 缺字段 / 超长 note→400 |
| 3 | GET | /preprocess/recipes/{recipe_id} | 200，含 versions | 未知 UUID→404；坏 UUID→400 |
| 4 | POST | /preprocess/recipes/{recipe_id}/versions | 201，version_no+1 | 未知 UUID→404；空 body / 坏 pipeline / 超长 note→400 |
| 5 | POST | /preprocess/projects/{project_id}/recipes/{recipe_id} | 200，重复选用幂等 | 未知配方 UUID→404；坏 UUID→400；ValueError→400 |
| 6 | DELETE | /preprocess/projects/{project_id}/recipes/{recipe_id} | 204，两次均空 body | 未知 UUID→404；坏 UUID→400；ValueError→400 |
| 7 | GET | /preprocess/projects/{project_id}/recipes | 200 列表 | 未知项目 UUID→404；坏 UUID→400 |
| 8 | POST | /datasets/{identifier}/preprocess/runs | 200，同步终态 succeeded/failed | 缺标注/配方/数据集→404；STALE→409；坏 body→400 |
| 9 | GET | /datasets/{identifier}/preprocess/runs | 200，七字段最近列表 | 未知数据集→404；身份头可验 |
| 10 | GET | /preprocess/runs/{run_id} | 200，完整字段 | 未知 UUID→404；坏 UUID→400 |
| 11 | POST | /datasets/{identifier}/preprocess/compare | 200，runs+ranking+boundaries | 空版本列表→400；未知版本→404；STALE→409 |
| 12 | GET | /preprocess/runs/{run_id}/artifacts/{kind} | 200，npz octet-stream / report application/json | 坏 kind→400；failed 无 artifact→404；超过 8 MiB→400，带 size；穿越路径→400 |

## 逐项验收

| 开工令验收 | 自验与落点 |
|---|---|
| 十二操作成功路径 | test_all_twelve_operations_success_and_delete_idempotence 完整执行；版本只增、旧版本不变、取消选用后配方及两个版本仍在；下载 npz 可解析，谱均值与夹具 DN/65535 数值对拍，report.metrics 与 run.metrics 完全相等。 |
| 错误路径 | test_bad_recipe_body_structured_400 / test_duplicate_code_and_version_bad_body_400 / test_unknown_uuid_structured_404_and_invalid_uuid_400 / test_artifact_kind_is_only_two / test_run_bad_body_400 / test_run_and_compare_preflight_errors_keep_404_and_409。七种 store 方法注入 ValueError 均返回 400 结构化错误，不透传 500；现有引擎 DataError 404/409 保留。 |
| 请求护栏 | 四个 body 模型继承 extra=forbid；note max_length=2000。test_note_limit_accepts_exact_boundary 实跑恰好 2000 字符，超长通过 400 校验路径。Pipeline/Step 复用既有 schema，不复制算子校验。 |
| 同步终态 | 成功和失败 POST 均返回已收尾行，finished_at 已供值；详情含 metrics/scaler_params/error，不创建后台任务、不在路由计算谱指标。 |
| 摘要精确七字段 | test_failed_run_summary_excludes_context_and_artifact_is_404：键集合完全相等，failed error_code=INVALID_OPERATOR_PARAMS，来自 error JSON 的 error 键；成功为 null。不含 metrics/scaler_params/error/context。 |
| 默认最近列表 | test_runs_list_default_recent_fifty_sorted_and_cube_isolated：同 cube 放 55 条、另一 cube 放一条，返回同 cube 最近 50 条且 created_at 降序；大 context 不入摘要。50 为开工令指定的实现层默认，非需求硬常数。 |
| artifact 上限与路径 | test_artifact_size_guard_precedes_response 实跑 8,388,608 bytes→200、8,388,609→ARTIFACT_TOO_LARGE(400)，context.size=实际值（出处：开工令 8 MiB 护栏）；路径四种非法形态均拒绝；failed 两类 artifact 均 404。 |
| compare 复用与排序 | test_compare_calls_runner_once_per_version_in_order_no_route_metrics：spy 确认按显式版本列表顺序，各调用 runner.run 一次；Fisher 排序由现有 CompareEngine 完成。实际两配方 HTTP 比较另验降序与三边界。 |
| 单实例、认证、身份头 | test_single_registry_identity_headers_and_auth：RunEngine.registry is superpixel_engine.registry，CompareEngine.runner is preprocess_runner；preprocess 与 datasets 路径响应验证 boot_id/pid；401 不注入身份头。middleware 仅新增 /api/v1/preprocess 前缀，无重复 datasets/*/preprocess 判断。 |
| deselect 语义 | 方法旁注释明确只删关联、不删配方、不复制/修改历史；11.2 既有方法与 test_recipes.py 零改且全绿。 |
| OpenAPI | 程序化从真实 app 生成，机械检查新增 721 行、删除 0 行；test_api_schema_snapshot 完整相等断言零改并通过，无过滤、无手写 schema。 |

## 边界与停止点

app.py / recipes.py 实际最小 diff 见 app-recipes.diff；OpenAPI 机械检查见 openapi-diff.txt。所有数值拟合与指标继续由既有 RunEngine / CompareEngine 计算，路由仅校验、调用、查询摘要与下载。

未改引擎、既有存储方法、Rust、前端或旧测试；未新增依赖。TASK-05 R13 与实现同提交。seeds_20.json SHA256 保持 388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2；两份公司文档不入库。

口径疑问已按用户裁定收敛为 error_code←error_json.error。11.4 完成后停止，等待复核，不开 11.5。
