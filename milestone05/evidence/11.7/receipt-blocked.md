# 11.7 开工核对：待裁定接缝

开工核对时状态（历史记录）：仅只读核对及本回执落盘；当时尚未执行本阶段回归或 e2e，未修改引擎、路由、Rust、前端、文档或任务卡，未提交。11.6 的 621/56/59 当时只是已知基线，不冒充本阶段实跑结果。

续记：科祥已在本聊天的后续开工令逐项裁定：内置配方复用+不同code创建；SG无delta/mode默认interp；字节数对下载与stat、SHA对DB；生命周期与HTTP双计时、触发线用HTTP；允许本目录Rust真实forward探针、不冒充WebView。阻塞现已解除，实际执行结果见 receipt.md、summary.json、e2e-result.json；以下保留原核对事实，不是未决问题。T1/T2仍按令只记录不实施。

## 1. 指定配方的创建与 SG 参数

事实：`src-python/spectrumagent/preprocess/migrations.py:60-83` 在 RecipeStore 初始化迁移时，已种入 `code=plastic-snv-sg1`、version_no=1；code 有 UNIQUE 约束。`POST /preprocess/recipes` 再用相同 code 会按已发货契约返回 400，不能作为创建成功路径。

待裁定：e2e 是否使用并核验这条内置 v1，另以不同 code 新建相同链来覆盖 POST 创建和后续项目关联？或另指定允许的创建方案。不得删除/改名内置种子以凑成功。

开工令写 `sg_derivative(1,15,2,1)`；既有模型字段是 `order/window/polyorder/mode`，而 delta=1.0 固定、不暴露。待确认最后的 1 是否仅指固定 delta：实际请求仍为 `{"order":1,"window":15,"polyorder":2}`，不发 delta，mode 留既有默认 interp。

## 2. 产物字节数对账

事实：卡 §3 与 `preprocess_artifact` 现有列只有 `id/run_id/kind/relative_path/sha256/created_at`，没有字节数字段；本阶段也不允许改表。

待裁定：是否按 artifact 行定位文件并核对 sha256，同时将下载原字节长度与磁盘 stat 大小逐项相等作为“字节数对账”，把字节数写入 e2e/performance 证据，而不声称 DB 存有 size 列。

## 3. 单 run 内部耗时

事实：run 响应和 report 未提供 elapsed_seconds；只有 preprocess_run.created_at/finished_at。created_at 在预检成功后、建 pending 行前生成，故二者差值不含验源/源哈希/标注与配方预检，也不等于完整 RunEngine.run 调用耗时。

待裁定：是否将 `(finished_at-created_at)` 明确记为“落库生命周期区间（预检后）”，另记 HTTP 全程耗时，并分别判定性能触发线？或需要其他无需回改引擎的测量口径。不得以该差值冒充包含预检的完整内部计时。

## 4. report 经 IPC 的真实验收层级

事实：Python loopback HTTP 可以取得 application/json，但这只证明 HTTP。真正的 Tauri 命令 `preprocess_forward` 位于 main.rs，依赖 Desktop/supervisor；已有 public `spectrum_agent::preprocess::{parse_request,forward}` 可用于不改产品源码的外部 Rust 证据探针。

待裁定：是否允许在本证据目录新建 Rust 探针，链接已发货库，读取真实 sidecar 握手，调用实际 parse_request/forward 获取 report 并断言返回 JSON object、无 body_base64？该证据覆盖真实 Rust 转发与 HTTP，不冒充 WebView invoke/完整 Tauri 命令或实机 UI 冒烟。若必须验到完整 Tauri invoke，需指定获准的自动化入口；本阶段不自行改 Rust 或接入替身。

## 已明确跳过的例外

- T1：runs 摘要仍为七字段，前端实际通过新 run id 的 get_run 详情逐个核对 recipe_version_id；不修改实现。
- T2：package.json engines 声明 24.19.0，11.7 验收将按科祥指定的托管 Node 22.22.2 执行；不改 engines。11.6 也实际按此托管版本验收。
- 当前工作区已有科祥对卡 §5.1 数量 11→10 及 §12 R15 勘误的未提交修改；本阶段未动，后续仅在既有工作区版本上追加 R16。
