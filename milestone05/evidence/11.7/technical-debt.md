# 11.7 技术债评估（只评估，未实施）

来源：已发货的 `src-tauri/src/datasets_dev.rs`、`annotation.rs`、`preprocess.rs`、`main.rs` 与 `milestone03/audit_boundary.py`；R13/R15 及本次实测。以下是设计建议，不构成新增产品行为或已交付能力。

## forward_common 差异矩阵

| 核对项 | datasets_dev.rs | annotation.rs | preprocess.rs |
|---|---|---|---|
| 超时 | 30s，总连接 500ms | 30s，总连接 500ms | 300s，总连接 500ms（R13）；独立 client_builder |
| 目的地/方法 | 固定 127.0.0.1+握手端口；5 变体；GET/POST；preview 自建 band query | 同一目的地边界；13 变体；GET/POST；Labels 自建规范化 project_id query | 同一目的地边界；12 变体；GET/POST/DELETE；无自由 query/path |
| 8MiB 上限 | 自有 MAX_RESPONSE_BYTES；Content-Length 预判 + take(MAX+1) 实读后判 | 自有同值常量；同样双判 | 复用 annotation::MAX_RESPONSE_BYTES；同样双判 |
| 身份头 | status/body 前校验 boot_id/pid | 同左 | 同左；先身份、再大小/状态/解析 |
| 二进制/204 | JSON only；空 body 解析拒绝 | JSON only；空 body 解析拒绝 | GetArtifact 成功+octet-stream 才编码包装；report 保持 JSON；仅204映射 Null，200空体仍拒绝 |
| token | 原字节+canonical JSON 双检；不回传敏感响应 | 同左 | 同左，原始二进制以及包含 filename 的包装 JSON 也检查 |
| HTTP/错误映射 | 共用 ForwardError(error/detail/context)；HTTP 信封失败回退 HTTP_ERROR；Tauri 按 enum 反序列化 | 复用 ForwardError；parse_request 把反序列化失败收敛 INVALID_REQUEST、不泄露 serde 原文 | 同左；ArtifactKind 强枚举，ListRecipes 的未知键额外检查 |
| UUID | dataset_id 规范小写 hex+36位/四横线 | uuid 接受 ASCII hex 大小写；不同 id 保持各自错误码；仅 Labels query 转小写 | 复制 annotation 的严格 uuid；dataset/run/recipe/project 四类错误码分别保留 |
| 代次校验 | main.rs 命令完成 forward 后 snapshot，generation+Ready 双判 | 同左 | 命令同样 snapshot 后检查，抽成实际使用的 validate_generation，已有单测 |
| 请求体特殊规则 | 类型化 region/import | AddLabel Value ≤64KiB；业务校验归 Python | 动态 body 的业务校验归 Python；不复制默认值 |

以上所有生产文件本阶段零修改。证据 Rust 探针只调用实际 parse_request/forward 连接实际 sidecar，不建立模拟 server，也不宣称覆盖主窗口、supervisor 或完整 WebView invoke。代次护栏继续由既有 Rust 单测覆盖。

## 抽取方案与结论

**建议下阶段实施共享函数，暂不选宏或复杂 trait。** 三份 transport 的身份、限长、秘密检查和错误流程大段重复，单处修复易遗漏；函数比宏容易逐行审查安全顺序。建议先写三路契约对照测试，再抽私有 `forward_common(identity, resolved_endpoint, transport_policy)`：

1. 保留每个业务 enum、validate/destination 与方法/路径拼接，调用方仍不能传自由 URL。公共 endpoint 类型的构造器不暴露给 IPC；强制身份端口和 loopback 校验。
2. 策略只承载既有差异：30s/300s、JSON-only/两种 artifact 响应、204空体策略。不得借抽取扩大方法、路径、权限或把 Python 参数默认值复制到 Rust。
3. 公共逻辑保持顺序：发送认证→身份头→声明/实际响应大小→原字节 token→按策略解析→canonical token→HTTP错误信封。二进制包装 filename 也必须经过后一次检查。
4. dataset 的小写 UUID 纪律、annotation Labels 的 query 规范化、各自错误码和请求限制继续在业务族保留，不能为“统一”改变已有失败语义。
5. supervisor 的代次/Ready 判定仍在命令层，避免 transport helper 冒充外壳状态；可复用实际 validate_generation，但不得省略 snapshot 或调整判定时点。

风险面：三路响应类型、204、超时、raw/canonical token、Content-Length 缺失/错误、8MiB 边界、身份头优先级、重定向、UUID大小写、未知字段/值以及代次变化均须重跑。三份 enum 路径/方法精确测试要继续保留，不能只测 common。

audit_boundary 当前查七命令、dev/release 一致、权限/ACL、版本、锁文件与指定身份/进程源码不变。若只抽 transport 并保留命令/权限/handler 字面量，原则上不应需要改审计字面量；必须原样跑审计及全部安全测试证明，不以“重构”为由削弱断言。若要动其禁止变化的 handshake/process 等源码，另行裁定。本阶段不实施。

## MSC / EMSC reference（R15 D2）

现状：schema 必填显式有限 reference；run 不自动填；S06 不开放二者。算子已有 reference_sha256/reference_len、系数形状/哈希及退化处理，但没有可选参考来源的前端流转。不得把指纹记录冒充训练集均值/指定样品的来源选择已交付。

**建议阶段二**提供用户明确选择的 report/version/class 作为参考来源，并记录来源 ID、B01 分支、轴、样本数与原产物/参考指纹。可用 report.curves.before 的均值谱，但必须注意它可能已被512点抽样或含 null：只有完整轴/完整有限参考、波段一一对齐时才能直接使用；否则需要另行裁定完整参考 artifact 通道，不能插值/零填或把抽样均值直接当200/更多波段参考。不得默认选择当前数据均值。本阶段只记债。

## T1：runs 摘要

现状是七字段：id/status/b01_branch/input_fingerprint/created_at/finished_at/error_code；没有 recipe_version_id。11.6 的实际恢复逻辑先 list_runs 识别新 succeeded id，再 get_run 逐个核对配方版本，并非仅凭 created_at/status 猜测。代价为额外详情请求。建议以后经裁定增加摘要字段并加强恢复测试；**当前未获回改11.4授权，不改 SQL、路由、前端或既有断言**。

## T2：Node engines 与验收版本

package.json 声明 node 24.19.0 / npm10.8.2；本次按科祥指定的 `C:/Users/Administrator/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe`（22.22.2）运行 node 与 tsc。系统 nvm node20.18.0 不用于该验收。声明与指定验收版本不一致，**待裁定，不擅改 engines、lock 或工具链**。

## 本轮探针浮点观察（不改依赖）

HTTP JSON 经 shipped serde_json Value 解析/重序列化后，部分 float 在最后有效位发生变化；具体数量/最大绝对差以 e2e-result.json 的 ipc_probe.numeric_roundtrip 为准。report 的 object 结构、字符串/整数/布尔/null 元数据精确核对；浮点额外复用卡§5的1e-12复现容差核对。此记录不承诺 IPC 浮点逐位无损，也未开启依赖 feature 或修改 Rust。完整 WebView/UI 仍由科祥冒烟验收。
