# TASK-07 v0.4.0 技术债与限制挂账（发布准备）

本文件延续 `milestone07/evidence/12.7/technical-debt.md`（该文件已随 v0.3.0 冻结，不原地修改）。本段只做文书收口，不修改实现、不运行测试，不追认历史问题根因。v0.4.0 的打包、真实数据/云端和安装态冒烟均待科祥执行。

## 12.7 原始事项逐项继承

以下 16 项对应冻结文件 L20–L35，标题、历史状态和后续原文全部保留，不删减、不合并。这里是历史记录；12.8 后三项的当前结论以本文件下一节 R51 销账判定为准，其余 13 项沿用继承状态。R23 collected 差三项的历史销账记录仍以冻结文件 L5–L16 为准，不在本版重新改写。

| 事项 | 12.7 历史状态（原文） | 后续/负责人（原文） |
|---|---|---|
| LLM 配置前端无入口（R26） | 已由 12.7.1 补设置 modal、settings_forward 封装、面板渲染与 UI 可达性测试，并按 R27 验配置/key 分离链 | 根因：§10-1 拍板未回向同步 §4 前端清单，§6 缺 UI 可达性验收；后续拍板逐条回核两章 |
| invoke重组丢detail（12.4 P3） | 沿用历史挂账；本段未重新归因或修改客户端错误处理 | 独立错误展示修补，待科祥安排 |
| datasets.list无上限（§10-7关联） | 现有完整id计数字符串在大目录会膨胀；不在集成段加截断/分页默认值 | 与列表数量上限、draft摘要引用可达性一起拍板 |
| draft_get摘要无region_id | LLM跨轮改/删region引用仍不可达；v1契约不能原地加字段 | 手势/工具联调时评估新skill版本与全标量限量摘要 |
| Chrome_WidgetWin_0 unregister 1412 | 历史日志项，未在本段追认原因或宣称修复 | 桌面实机复现与单独定位 |
| #01 exit code70 | 原因未定位；本轮三链ASGI不代替独立sidecar生命周期复核 | 安装态冒烟留记录 |
| 手势联调排期缺口 | R14②已延后；gesture存储/画布采集、add_region/SAM绑定、SLIC选候选的产品语义未定义 | 待科祥拍板12.8或后续段；不塞进12.7 |
| 算法source=algorithm半边 | candidates端点尚无产源，schema-only占位；manual source路径已覆盖 | 随手势联调验，不用“冒烟”掩盖未实现 |
| 草稿不能直接跑预处理（§0.3） | 既定限制，计算只读annotation_version+label_map；MAT永不作计算输入 | 不开草稿试算通道；先confirm |
| key重启失效 | 仅进程内存的既定选择；配置保留，key重填 | 科祥真实key/reboot冒烟 |
| 8MiB及大MAT | 固定forward限额不放宽；全标大MAT不能经IPC下载，本轮无应用内下载UI | 当前使用API/脚本；应用内大下载另开段 |
| 碎片pixel_set RLE文档大小 | 本轮仅记录两个polygon的document字节，不声称测过高碎片最坏大小；GET draft仍可能超过8MiB | 若实际触发，再定义分页/预览截断，禁静默裁几何 |
| savemat内存副本 | R20明确接受O(n×B)写侧序列化副本，读侧仍有界；记录的是tracemalloc非RSS | 无内存硬门；真实数据性能归冒烟 |
| JSON版本恢复草稿 | §1.2明确不做，不能从旧版本直接载回可编辑draft | 后续能力另立规格 |
| DB annotation的聚合source | 每label一行source=manual表示人工确认；region混合来源只在JSON完整保留 | 审计以JSON为准，不发明algorithm→cluster映射 |
| 真实云端/实机验收 | 自动化通过不包含NAS物理谱义、云端遵循度、WebView交互、签名/SmartScreen/干净机/长路径/reboot | smoke-checklist.md归科祥 |

## R51：12.8 后销账判定

| 继承事项 | v0.4.0 当前判定 | 实证出处 | 剩余事项 / 后续 |
|---|---|---|---|
| 算法source=algorithm半边 | **完全销账**：12.8 已实现 SAM candidates 产源与 source=algorithm 写入路径。 | `src-python/tests/annotation/test_gestures.py::test_sam_queue_floor_writes_region_consumes_queue_and_reports_floor`：`assert region["source"] == "algorithm" and region["confidence"] == confidence`；`src-python/tests/annotation/test_draft_routes.py::test_candidates_rest_shared_service_cas_and_source`：`assert before["document"]["regions"][-1]["source"] == "algorithm"`；`scripts/e2e_task07.py::gesture_chain` 步骤 2/2b：真实引擎双 floor 验证 algorithm / medium 与 algorithm / low。 | 此事项已销账；SLIC 产品语义独立归下一项遗留，不把“没有 SLIC”误当 algorithm 路径尚未接入。 |
| 手势联调排期缺口 | **部分销账（SLIC 语义转 v2）**：主体已实现——gesture 会话存储、画布采集、add_region 三 op、SAM candidates 绑定全部落地（R40–R48）。 | `src-python/tests/annotation/test_gestures.py::test_gesture_storage_copies_unique_refs_and_does_not_persist` 验唯一 ref、deepcopy 与重启失效；`src-python/tests/agent/test_annotation_tools.py::test_gesture_tools_replay_three_ops_and_scalar_summaries` 验三 op；`test_sam_tool_reports_queue_floor_confidence_and_no_ghost` 验 SAM 来源/置信度/无幽灵队列；`scripts/e2e_task07.py::gesture_chain` 步骤 1–4 验存储、SAM 和 LLM 手势写入，步骤 5 断言 SLIC 的 TOOL_NOT_IMPLEMENTED。画布接线出处：`src/components/annotation/AnnotationWorkbench.tsx` 中先 storeGesture、后 api.diffuse；客户端投影出处：`src/components/annotation/draft-api.test.ts`。 | SLIC 选候选产品语义仍未定义，工具与 REST 均显式 TOOL_NOT_IMPLEMENTED，转 v2；不得记为完全销账。 |
| draft_get摘要无region_id | **部分销账（读路径转 skill v2）**：add_region / select_candidates 写摘要已带 region_id，写路径可达；draft_get 自身仍不返回 region_id。 | `src-python/tests/agent/test_annotation_tools.py::test_gesture_tools_replay_three_ops_and_scalar_summaries` 的摘要白名单含 region_id，且 `assert summary["region_id"] == region["region_id"]`；同文件 `test_sam_tool_reports_queue_floor_confidence_and_no_ghost` 的 `set(result)` 白名单含 region_id。读路径源码：`src-python/spectrumagent/agent/tools/annotations.py::draft_get` 仍仅返回 cube_id/revision/n_regions/n_classes/updated_at/estimated_mat_bytes。 | LLM 跨轮改/删 region 的读摘要引用仍不可达，转 skill v2 待办；冻结 v1 契约不原地加字段，不得记为完全销账。 |

本节引用的是 12.8 已过闸的测试/源码和 e2e 步骤证据；12.8.1 未重新运行任何测试。三条判定为 1 完全销账 + 2 部分销账，不能以写路径已有 region_id 代替读路径引用可达性，也不能以 SAM 已实现代替 SLIC 产品定义。

## v0.4.0 新增挂账

**本版无新增挂账。** 空草稿工具首笔不可写、超像素粒度、gesture ref 仅会话内有效及 skill v2 引导待办，均为 R40–R48 已明确的手势边界，随继承的手势事项留档，不另造新事项；SLIC 与 draft_get 读路径的剩余工作已在 R51 两条部分销账中列明。

真实 NAS / provider / WebView、签名/SmartScreen、干净机、长路径和重启验证沿用“真实云端/实机验收”继承项，按同目录 `smoke-checklist.md` 的 S01–S23 执行，结果待科祥回填。12.7 的历史证据、manifest 和版本配置均不回写。
