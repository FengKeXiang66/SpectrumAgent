# TASK-07 12.7 技术债与限制挂账

本文件只汇总已给定事项及本段实证，不推认历史问题根因，不改已过闸的12.1–12.6实现。

**R23 collected差三项：已销账。**

| 测试文件 | 12.5 | 当前collected | 新增 |
|---|---:|---:|---:|
| agent/test_annotation_tools.py | 4 | 8 | 4 |
| annotation/test_confirm_routes.py | 0 | 11 | 11 |
| annotation/test_session.py | 25 | 29 | 4 |
| mat/test_mat.py | 0 | 6 | 6 |
| 其余文件 | 897 | 897 | 0 |
| 总数 | 926 | 951 | 25 |

mat/test_mat.py有三个函数，均使用mat_case；其fixture声明params=[False,True]，所以3×2=6，静态函数计数漏掉三项。--collect-only原始输出逐个列出[False]/[True]，见collect-only.txt及collection-reconciliation.json。没有额外收集源或测试改动。

| 事项 | 本轮状态 | 后续/负责人 |
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

flake本轮三个目标各10轮，无失败、无单独复跑，没有把既有Windows文件占用猜成确定根因。生产默认值、schema、状态机、旧测试和依赖均未改。
