> 已解除：R21 接缝授权及 UUID 选项 2 裁定已明确；以下保留原始即停记录。接缝实现与验证见 seam/。

# 10.6 首检回执：按“问询即停”暂停

事实源：TASK-04-标注L1.md，531 行，R20；已通读任务卡并核对现有 Python / Rust / datasets 前端。
S05 原型已定位：E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html（文件内版本 ui-v2.3，S05 从第 1618 行开始）。未改原型。

## 改动文件 / commit / 测试

- 仅新增 milestone04/evidence/10.6/receipt-blocked.md；无产品代码改动。
- 未提交；当前 HEAD 保持 3a519e32729e5cdf19fe8ec7faa30ae18362921d（10.5 Rust 交付）。
- 未运行本阶段 node 测试或 npm run build；不沿用历史测试数充当 10.6 结果。

## 即停问题一：标签管理缺少受限 IPC 入口

依据：卡 §5.8 / 开工令第 2、6 条要求后端 color_hex、标签/目录读取、从目录添加、自定义标签、schema 字段管理；同一开工令锁死“不碰后端/Rust”。

实际落点：

- src-tauri/src/annotation.rs:48 AnnotationRequest 仅九个数据集标注变体，没有项目、标签、塑料目录操作。
- src-tauri/src/datasets_dev.rs:52 DatasetRequest 也只有 import/get/preview/band/region。
- Python 已有 GET /api/v1/projects、GET /api/v1/labels?project_id=、POST /api/v1/labels、GET /api/v1/catalog/plastic（src-python/spectrumagent/api/annotations.py:159-173），但前端无可用 IPC 到达它们。
- dataset info/import 响应未透出 dataset_registry.project_id（api/datasets.py 的 DatasetRecord；api/registry.py:130 的 get 只取 payload/raw），项目绑定也不能凭空填写。

因此，仅改前端不能完成真实标签面板及管理。不会把默认标签/颜色/项目 ID 硬编码到前端，也不会读握手 token 或自行 fetch 绕过受限 IPC。

需裁定：是否追加最小接缝授权，在既有 annotations_forward 中增加 projects / labels / add_label / plastic_catalog 四个固定变体（POST 复用现有三种 LabelRequest 契约），保持六命令总数与所有既有传输边界；并明确 cube→project_id 的只读透出位置。此方案需要修改 Rust，不能在当前授权范围内自行执行。

## 即停问题二：当前候选队列缺少无副作用读回

依据：卡 §5.3 队列为 sidecar 唯一真源、切 cube 隔离，§5.8 右栏须显示候选；开工令第 3 条每次操作后 GET working 读回，前端不得另起真源。

实际落点：

- api/annotations.py:145-153 working_view 只返回 superpixel_count / params / statistics / overlay；没有队列。GET versions 复用此 working_view，同样没有队列。
- annotation/session.py:177-183 working 只返回 label_map / label_index / params / statistics，没有候选列表；HTTP 也不会回传 label_map。
- 目前只有 POST diffuse 返回完整 queue；该 POST 会生成候选并执行入队判定，不能当只读查询使用。
- regions / undo 都返回 working_view。确认/不确定后的真实队列、切图返回/工作台重新挂载后的队列，前端无法无副作用重取；pending_pixels 只有并集数量，不能重建候选项及相似度。

需裁定：是否授权只读扩展 GET working 的响应，增加 queue，形状与现有 diffuse.queue 一致，取 sidecar 当前队列副本，不改变队列状态机；regions/undo/versions.working 随同复用。建议同处透出该 cube 的 project_id，解决前一项项目归属。字段及最小授权需负责人明确后实施，不自行改卡。

## §6.1 / S05 对位状态

- 布局、层级指示器、参数、Canvas、快捷键、版本交互、DatasetPanel 入口：本次仅核对，未实现，不报通过。
- 标签结构化管理与颜色来源：被问题一阻塞，不降为阶段二。
- 候选队列、确认/不确定移除、erase 不动、切 cube 恢复：被问题二阻塞，不用前端缓存或推测代替验收。
- 常驻对话条、sidecar label map/撤销栈、后端/Rust/任务卡：未改动。
- 不把原型示例的 compactness=10、背景键=5、PP/PET/PS/ABS 示例色表作为实现值；执行仍以当前任务卡为准。

## 只读文件核对与就绪状态

TASK-04 SHA256：FD34459542B93F155AED676AC27B099C1886BB2BB9654FED775BCED6969E1B20。
seeds_20.json SHA256：388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2。
两者与开工读取值相同；根目录两份公司文档与 seeds_20.json 保持未跟踪。

10.6 停在接口接缝裁定，等待明确授权后继续；未进入 10.7。
