# 10.4 路由交付回执（原两项阻塞已解除）

保留用户指定的 receipt-blocked.md 文件名；本回执内容已更新为最终交付状态。
两项契约同步已获授权并完成，全量 337 passed / 0 failed / 0 skipped。

## 已完成的授权范围

- api/annotations.py：新增 8 个端点；superpixels 严格 generate → set_segmentation → report；R19 参数失配检查；geometry→mask；工作态/版本 PNG；R20 UUID 版本路径。
- app.py：单 Registry 装配三对象；status_code 优先；note 请求校验映射。
- annotation/session.py：只有三处 diff（冲突码参数、save note 入参与校验、note JSON 组装）；短事务、快照、聚合和版本号逻辑未改。
- test_routes.py：41 个真实 HTTP 用例；test_routes_acceptance.py：1 个真实 pe 固定 20 种子 HTTP 验收。
- app.py/session.py 实际 diff：本目录 app-session.diff。

用户已将 R20 落盘至 531 行任务卡；当前 SHA-256
`FD34459542B93F155AED676AC27B099C1886BB2BB9654FED775BCED6969E1B20`。
执行者未改卡；按本轮明确的 git add 清单，用户任务卡本地修改保持未暂存，不纳入本次提交。

## 测试模式与实际结果

仓库根一条 PowerShell 调用内设置 PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp，
E:/AI_Agent/.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q，默认参数。
最终实际 **337 passed、0 failed、0 skipped、10 warnings，39.67s**；基线 295 + 新增 42 = 337 collected。
原始输出见 pytest-full.txt。

原先全量为 335 passed / 2 failed，按“验收断言变更即停”暂停后，用户授权两项契约同步，现均已解决：

1. src-python/tests/annotation/test_labels_api.py:130，test_auth_identity_and_stage_boundary：
   旧断言禁止 /annotations 或 /diffuse；现按用户给定代码改为九端点完整肯定式集合。
   认证、身份头及 token 不泄漏断言原样保留，已程序化逐字核对。
2. src-python/tests/data/test_api.py:210，test_api_schema_snapshot：
   保留完整相等断言；整个 test_api.py 未改，已程序化逐字核对。
   openapi.json 由真实 create_app → json.dumps(app.openapi(), ensure_ascii=False, indent=2) 程序生成，无手写修补。

首次机械检查发现 44 行删除，已立即停下查因：新增标注 RegionRequest 与既有数据 RegionRequest 重名，
导致 Pydantic 为两者生成全限定 schema 名称，并改写旧引用。FastAPI 0.143.3 / Pydantic 2.14.1 均与 lock 一致。
仅将新增模型改名为 AnnotationRegionRequest 后重新从真实 app 生成，旧 RegionRequest 及全部旧引用不变。
最终 OpenAPI diff **新增 580 行 / 删除 0 行**；`^-` 排除 `^---` 的机械检查零输出。
证据见 openapi-check.txt；没有过滤 schema 比较或手工修快照。

## 当前端点验收

| 端点（均在 /api/v1/datasets/{id} 下） | 当前新增测试结果 |
|---|---|
| POST /superpixels | generate → sync → return；工作态首次初始化、三参数变更同步通过 |
| POST /diffuse | point/box/doodle 成功；cos_s、生成候选列表、当前队列、原因计数和实际阈值通过 |
| POST /annotations/regions | 超像素并集；polygon 中心 even-odd、边界包含、无膨胀；三种操作通过 |
| POST /annotations/undo | 连续 5 次、空栈 409、再编辑和撤销对位通过 |
| GET /annotations/working | 空态不报错、PNG/统计、参数失配时仍可读通过 |
| POST /annotations/validate | 复用既有校验、不接受 body、不适用项通过 |
| POST /annotations/save | 新建/覆写/note 2000 边界及双校验/旧版不变/created_at 保留通过 |
| GET /annotations | 版本列表与当前工作态通过 |
| GET /annotations/{version}/overlay | UUID 路径，已知/未知 UUID 委托 read_version；错误格式/整数拒绝，跨 cube 按落盘 R20 返回 VERSION_NOT_FOUND(404) |

SEGMENTATION_STALE 四条写/校验入口全部 409、没有静默同步；缺 confirm / 无版本覆写 / 空撤销栈均 409。
坏 body、坏 geometry、混用 geometry 均结构化 400；未知 cube 仍 404；已有标签端点 422 行为未改。
注册类色、留白/不确定不同斜纹和 PNG 解码验证通过。
按用户 R20 指令，version_no 仅在版本列表 HTTP 响应中出现；save HTTP 响应不含此字段，
SessionStore.save 的内部返回和版本号逻辑未改。未知 UUID 沿用 read_version 的 VERSION_NOT_FOUND(400)。

## 新增测试落点（42 项）

src-python/tests/annotation/test_routes.py（41 项，真实 HTTP + 既有引擎 + SQLite）：

| 测试函数 | 用例数 | 覆盖 |
|---|---:|---|
| test_working_empty_versions_empty_and_single_registry_assembly | 1 | 空态及单 Registry 装配 |
| test_superpixels_generate_then_sync_before_response_initializes_state | 1 | generate → sync → return，首次工作态初始化 |
| test_diffuse_three_prompts_response_cos_s_queue_effective_defaults | 3 | 三种提示、cos_s、当前队列、实际默认值、原因统计 |
| test_regions_superpixel_actions_working_statistics_registered_colors | 3 | 确认/擦除/不确定、统计、登记色、PNG |
| test_polygon_centres_even_odd_boundary_included_no_dilation | 3 | 中心点、边界包含、自交 even-odd、无膨胀 |
| test_polygon_after_superpixels_overwrites_only_selected_centres | 1 | 单值 map 后写覆盖，区域外像素保留 |
| test_five_http_undos_empty_409_then_edit_stays_aligned | 1 | 五步撤销、空栈409、恢复后继续编辑 |
| test_http_candidate_consumption_and_pending_union | 3 | confirm/uncertain 消费、erase 不消费、待确认并集 |
| test_http_resegment_clears_queue_preserves_labels_uncertain_and_statistics | 3 | 三种参数变更同步，保 map/-2/统计、清候选 |
| test_segmentation_stale_four_routes_409_no_silent_sync | 4 | 四端点失配409，working 不受限、不静默同步 |
| test_cache_params_stale_detected_and_superpixels_resynchronizes | 1 | 缓存 params 失配与重新生成恢复 |
| test_validate_save_list_uuid_overlay_note_overwrite_and_old_version | 1 | 校验/保存/列表/回放、UUID 委托、note、覆写及历史不变 |
| test_no_version_overwrite_http_409 | 2 | 无版本覆写均409 |
| test_note_2000_boundary_request_and_application_layer_double_validation | 1 | 2000边界、请求/应用双校验、无备注与空备注 |
| test_bad_bodies_geometry_mixed_geometry_400_no_side_effect | 10 | 坏 body、坏 geometry、混用、额外字段、不产生副作用 |
| test_validation_has_no_body_and_uuid_only_version_errors | 1 | 无body约束、未知/坏UUID、拒绝整数路径、跨cube404 |
| test_http_error_envelopes_identity_and_source_changed | 1 | 原有404/400/401信封、身份头、SOURCE_CHANGED |
| test_missing_superpixels_http_structured_and_empty_undo_409 | 1 | 未分割错误及空撤销409 |

src-python/tests/annotation/test_routes_acceptance.py（1 项）：
test_http_fixed_twenty_default_queue_three_assertions。
从真实 HTTP import/superpixels/diffuse/working/annotations 全链路执行固定种子验收，
无认证绕过；种子或真实 cube 缺失时明确 skip，禁止重生成；本机本轮实际未 skip。

## §6.1 HTTP 固定种子结果

http_queue_20.json：真实 pe/20260804205214_64，默认分割 765→830，
threshold=0.92、queue_min_similarity=0.80，固定 seeds_20.json 全部 20 点原样读取。
①入队 **10**、被拦 **10**；②min_similarity<0.92 有 **19**；③入队最小 **0.8093943702234402**，全 ≥0.80。
working 待确认像素并集 **64,183**；label_map 全 -1，无自动赋标；版本列表为空。
特征图 **2,956,800 字节**，独立 HTTP 验收进程峰值 RSS **332,038,144 字节**，均为实现层实测。

confirm/uncertain 消费、erase 保队列、待确认并集、三参数变更清队列保 label_map/-2 也均通过 HTTP 测试。
未修改 superpixels/diffusion/quality、Rust、前端或依赖；未安装、未打 tag、未推远端。
种子 SHA-256 保持 `388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`，
与两份公司文档保持未跟踪，不入库。

## 提交文件清单与停止点

逐路径暂存，仅以下文件：

- src-python/tests/annotation/test_labels_api.py
- src-python/spectrumagent/api/openapi.json
- src-python/spectrumagent/api/annotations.py
- src-python/spectrumagent/app.py
- src-python/spectrumagent/annotation/session.py
- src-python/tests/annotation/test_routes.py
- src-python/tests/annotation/test_routes_acceptance.py
- milestone04/evidence/10.4/app-session.diff
- milestone04/evidence/10.4/pytest-full.txt
- milestone04/evidence/10.4/http_queue_20.json
- milestone04/evidence/10.4/receipt-blocked.md
- milestone04/evidence/10.4/openapi-check.txt

没有新增待决口径问题。10.4 完成后停止，等复核；10.5 仅就绪，不开工。
