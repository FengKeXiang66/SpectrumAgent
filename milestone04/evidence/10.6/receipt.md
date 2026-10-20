# 10.6 S05 工作台 + R21 接缝交付回执

事实源：TASK-04 §5.6/§5.7/§5.8/§12 R21（552 行）；UUID 规范化按科祥后续“选 2”裁定：严格 uuid() + to_ascii_lowercase，不引入解析器依赖。原型：E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html，ui-v2.3，S05 从 1618 行开始。

## 两次提交与文件清单

接缝 commit：507520d552ac346d6f3067844aa38111a6f3b6af。

- src-tauri/src/annotation.rs：13 变体，按族构造路径；Labels 严格校验后转小写并 set_query；datasets 九路径保留原 id 拼写；AddLabel 序列化 UTF-8 ≤64 KiB，业务校验只在 Python。
- src-tauri/capabilities/main.json：仅描述扩展路径族；权限不变。
- src-tauri/gen/schemas/capabilities.json：构建生成的描述同步；ACL/schema 权限及六命令总数不变。
- src-python/spectrumagent/api/annotations.py：仅 working_view 增 project_id/queue 及 deepcopy 导入；get 保留未登记错误边界，SQL 只读查询项目，queue 为 sidecar 当前候选深拷贝，包含原 overlay，空态也返回两字段。
- src-python/tests/annotation/test_routes.py：空态断言加强，新加三个 R21 测试；原测试保留。
- milestone04/evidence/10.6/receipt-blocked.md、receipt-r21-blocked.md：保留两次即停记录并标注已解除。
- milestone04/evidence/10.6/seam/pytest-full.txt、cargo-test.txt、clippy-all-targets.txt、boundary-output.txt、results.json：接缝测试、执行模式和审计证据。

前端提交的逐路径清单：

- src/components/annotation/api.ts：唯一 annotation IPC client；13 个类型化请求构造、白名单字段投影，无组件内 invoke。
- src/components/annotation/types.ts：请求与 Python 响应字段类型，包括三种标签 body、质量/版本/working/queue。
- src/components/annotation/working.ts：working 显示投影、编辑后读回、队列选择恢复、R17 排序、仅本地估计及目录色近提示逻辑。
- src/components/annotation/shortcuts.ts：默认映射、改键/关闭、0 仅背景、未绑定标签仅鼠标、保留全局对话条键位。
- src/components/annotation/AnnotationWorkbench.tsx：三栏工作台、参数、四层画布装配、操作/撤销/保存/覆写确认/版本/质量校验、只读恢复与异步隔离。
- src/components/annotation/LabelPanel.tsx：项目标签、目录/自定义/schema 三形态表单、色近改用自定义颜色提示。
- src/components/annotation/CandidateQueue.tsx：右栏仅读取 working.queue，像素分布按后端统计与 R17 全序对齐。
- src/components/annotation/canvas/AnnotationCanvas.tsx：Canvas 2D 四逻辑图层、滚轮缩放、空格/中键平移、单击/框选/涂鸦、手绘/多边形区域及矩形橡皮。
- src/components/annotation/canvas/viewport.ts：视口坐标变换、半开框、单像素矩形与手绘轮廓；不维护 label map、不在前端栅格化提示。
- src/components/annotation/annotation.css：工作台范围内样式、三栏及窄屏布局、首入快捷键浮层；无 fixed 全屏覆盖。
- src/components/annotation/api.test.ts：17 项 node 测试。
- src/components/annotation/shortcuts.test.ts：4 项 node 测试。
- src/components/annotation/working.test.ts：8 项 node 测试。
- src/components/datasets/DatasetPanel.tsx：每项“标注”按钮与最小视图切换；不改 App 或常驻对话条。
- milestone04/evidence/10.6/seam/annotation-routes.diff：从 git diff 507520d^ 507520d -- 两个实际文件重新生成，零上下文，供逐行核对分族与 working 两字段；随前端提交补齐该证据。
- milestone04/evidence/10.6/node-annotation.txt、node-full.txt、build.txt、build-first.txt、results.json、receipt.md：前端测试/构建原始输出、首轮编译发现及修复记录、结果与本回执。

## 三套测试 / 构建 / 执行模式

| 门槛 | 实际结果 | 执行模式 |
|---|---|---|
| Python 全量 | 340 passed / 0 failed / 0 skipped；10 个既有依赖弃用提示 | 仓库根，单条 PowerShell 命令设 PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp；.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q；默认参数 |
| Cargo 全量 | 38 passed / 0 failed / 0 ignored，37 常规 + 1 文档测试 | src-tauri 下 cargo test；默认并行，未设置 RUST_TEST_THREADS，未传 --test-threads/筛选/附加 feature；既有 E 盘离线缓存 |
| Clippy | exit 0，零警告 | cargo clippy --all-targets -- -D warnings |
| 六命令审计 | exit 0 | 原 audit_boundary.py 断言未改，实际执行；六命令清单与既有隔离/lock 检查保留 |
| annotation node | 29 passed / 0 failed / 0 skipped | 指定 node24.19.0 --test src/components/annotation/*.test.ts；内置 runner 默认模式，无 vitest/jsdom |
| 全部 node | 31 passed / 0 failed / 0 skipped | 同一 Node，--test src/components/datasets/*.test.ts src/components/annotation/*.test.ts；既有 2 项全部保留 |
| 前端构建 | exit 0 | 同一 Node/npm，npm run build = tsc --noEmit && vite build；TEMP/TMP 与 npm cache 在 E 盘 |

Python/Rust 门槛先通过并提交接缝后才开始前端；前端提交不改后端或 Rust。未运行 VM/本机应用冒烟、未进行浏览器或原生 UI 验收，相关实机工作仍由科祥执行；本回执的前端验证为逻辑测试、静态接线检查和生产构建。

## 新测试落点与断言

Rust annotation.rs::tests 新增 3 项：

1. four_management_operations_have_literal_paths_methods_and_bodies：四变体无 id，固定路径/方法/body，query 仅 Labels 的构造式 project_id，fragment 恒无。
2. project_query_is_strict_then_lowercase_but_dataset_path_is_unchanged：project UUID 大写转小写；拒 &/?/#/斜杠/编码注入；datasets 大写 id 保持原路径拼写。
3. label_body_limit_counts_serialized_utf8_and_business_validation_stays_in_python：恰 64 KiB 可过、超 1 字节与多字节超限拒；不复制 Python 三 body 校验。原自由 URL/host/port/path/method 测试扩至四新变体，原九变体及安全测试保留。

Python test_routes.py 新增 3 项：

1. test_r21_working_queue_readback_is_pure_and_contains_project_and_overlays：project 与登记值一致，queue/overlay 与 diffuse.queue 相同，多次 GET 不改变 sidecar，响应修改不影响内存。
2. test_r21_confirm_consumes_one_candidate_and_working_recovers_remainder：两条不同候选确认一条，regions 响应与后续只读 working 都恢复剩余一条。
3. test_r21_switch_cube_recovers_isolated_queue_without_regenerating_candidates：另一 cube 未分割仍空态、project/queue 齐全；分割后队列为空，切回原 cube 不丢原队列。

Node api.test.ts 的 13 项逐变体断言命令名/请求字段精确一致；其余 4 项覆盖缺省委托 Python、三种标签 body、所有请求剔除本地估计/显示字段、错误信封及拒绝传播。

Node shortcuts.test.ts 的 4 项覆盖背景 0、1–9、NULL/越界仅鼠标、Enter/Z/D/E-B-P/方向键/Ctrl+S/空格、文本输入不误触、可改/可关、重复键拒绝与对话条保留键。

Node working.test.ts 的 8 项覆盖编辑后 GET working、剔除运行时 map/history、多 cube 队列读回与选择恢复、错误不伪造成功态、R17 全序（含非 BMP）、仅本地速度估计、色距提示、视口/半开框/手绘轮廓、组件唯一 IPC 出口/无本地 map 或撤销栈/外壳对话条保留。

## S05 原型 / §6.1 逐条对位

| 原型 / 验收项 | 本阶段落法 | 状态与验证边界 |
|---|---|---|
| 左栏标签色块/code/数字键 | color_hex 与键位来自项目标签；0 仅背景，未绑定仅鼠标；不复制原型示例色表/背景键5 | 已实现；node 逻辑验证 |
| 添加标签、目录与 schema | 四 IPC 变体；project_id 只取 working；目录选用、自定义必填颜色/路径、四类 schema 最简表单；色距<30 可转自定义颜色登记 | 已实现；请求逻辑验证，业务约束仍由 Python 422 负责 |
| 工具 D/B/P/E | D 扩散；B 手绘闭合区域/单像素，提示分段中为后端涂鸦提示；P 逐点多边形；E 拖框/单像素擦除，交既有 regions | 已实现；几何构造/请求验证，未自行增加笔宽默认值 |
| 中栏分段与参数 | 超像素/扩散/提示切换；n、compactness、PCA3/5；扩散/入队两阈值可调，输入完成后按已有种子重新预览 | 已实现；默认值均注明任务卡/需求场景/UI 出处 |
| Canvas 四层 | 底图、后端超像素轮廓/编号 PNG、working.queue 候选 PNG、working.overlay 已确认/不确定/留白；可独立开关 | 已实现；只绘后端图像，不从颜色推断像素标签或候选 mask |
| 缩放/平移/三种提示 | 视口变换、滚轮、空格/中键；点击 point、半开 box、doodle 点序列直传 | 已实现；逻辑测试；Bresenham 仍由后端唯一执行 |
| 确认/不确定/橡皮/多边形 | 人工选 label_id 后 confirm；uncertain 不传标签；erase 不推测队列变化；都在操作后 GET working | 已实现；原 Python 回归包含编辑、三态、撤销/再编辑等验收 |
| 候选队列与高亮恢复 | 右栏与高亮仅工作态 queue；切 cube/重新进入读 working，不调 diffuse 重建 | 已实现；Python + node 队列恢复验证 |
| 参数变更保像素/清候选 | 由既有 superpixels→set_segmentation；前端读取新 working，不清/重算本地 map | 已实现；沿用通过的后端验收，不持本地像素数组 |
| 撤销≥5、栈空错误、再编辑 | POST undo，后端唯一栈；每步重新读取 PNG/统计；信封渲染错误码 | 已接线；全量 Python 原验收与 node 路径检查通过 |
| 统计/分布/预计剩余 | 当前超像素数/已确认/不确定/留白/待确认并集/分类计数均取 working；预计剩余仅按本地确认速度计算 | 已实现；估计不上报、不作为性能/标注质量验收指标 |
| 保存即聚合/版本/覆写 | 默认新建；覆写最新版本有二次确认，只有此时发送 confirm=true；历史 overlay 只用版本 UUID，单独只读显示 | 已实现；API/源码接线与既有后端回归验证 |
| 质量校验 | 展示当前原谱余弦可疑清单、高方差、默认阈值出处；两项无模型不适用原样显式显示 | 已实现；不伪造模型质量结果 |
| 快捷键可查/改/关/首入提示 | 本机设置与首入浮层；重绑定校验；输入框不误改标签；全局 Ctrl+K/Ctrl+Enter 保留 | 已实现；node 验证；浮层不采用 fixed 全屏覆盖 |
| L0–L4 / 当前 L1 | 静态层级指示器，只有 L1 当前态；写明机器不赋标签与 L2 差距 | 已实现；L2/L3 自动赋标、模型、迁移、HITL/多人等按卡属阶段二 |
| DatasetPanel 入口/上下张 | 每项标注按钮，组件内最小切换；切 cube 重建显示状态并从 sidecar 恢复 | 已实现；不做完整左导航 |
| 全局常驻对话条 | App.tsx 与 style.css 未改；工作台仅为 DatasetPanel 内容，不覆盖/替换 footer | 静态接线验证；实机可见性仍待负责人冒烟 |
| 阶段二扩展位 | 瓦片/大图数据源、SAM/GPU、L2+ 自动化与多人能力未实现，不增加假可用按钮 | 按卡阶段二，不抢跑 |

## 边界与问题

未新增依赖、未安装/下载；Cargo.toml/Cargo.lock/package-lock/requirements-lock 均不变。未改 session.py、engines、app.py、Rust 注册/六命令清单、任务卡或固定种子。公司文档与 seeds_20.json 保持未跟踪。seed SHA256 仍为 388ed3a86bdf60c5054e8df9a5eb197a96a112b0bf2fc59efa1bcf1a29f648d2。

首轮构建仅发现一个未使用类型导入（build-first.txt），已移除并通过完整构建。接缝实际 diff 已按接缝 commit 重生并补齐，避免暂存后无工作区 diff 造成空证据。无未决口径问题。

10.6 完成后停止等待复核，10.7 未开工。
