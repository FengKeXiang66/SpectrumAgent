# /smoke 响应身份头增补（2026-10-18）

依据：负责人在检查点 3 批准 reqwest 仅请求本代固定 `/health`、`/smoke`，
并要求响应侧核验身份；随后明确选择方案 2（响应头），批准修订与重新冻结。

采用 `X-SpectrumAgent-Boot-Id`、`X-SpectrumAgent-Pid`，从 create_app 内
同一个 EngineIdentity 注入。中间件列表按外至内显式注册 authenticate、
inject_smoke_identity；认证拒绝不进入注入层。路径精确等于 `/smoke` 才注入。
授权响应的 200/409/500/422 均带头，401 不带。token 不进入响应头。

响应头能覆盖成功、取消、失败三种 JSON 形态，保持 JSON 体与原精确键集合
断言不变；422 也有身份。`/health` 行为不变。旧证据继续描述旧批次，保持有效，
不用于声称新响应头已验证。开发期全量 pytest 39 passed，原始输出见
pytest-headers-development-output.txt；冻结态回归与 Rust/UI 联调尚待新批次。

旧批次：source d218262；manifest artifacts/step2/product-manifest.json，
artifact_root artifacts/step2/dist/app。新批次计划位于
artifacts/step2/revision-20261018-smoke-headers/。

新批次已完成：artifact_source_commit=3acd979f3b5a94ad32283eb1608c95f0b8721696，
manifest_generator_commit=e7c3c9d90f83d23639a4ee54832c8b4bc75bf706；权威 manifest
为该新批次下 product-manifest.json。app.exe SHA256
3f62c1895152a01eb0a92b61a733985c15ca7888d233fd9408ca5b9dc61d7703，
16,771,455 字节；_internal 543 文件/238,793,334 字节，整体 544 文件。
39 pytest passed；session-20261018-171326-708 全量矩阵 30 轮通过，token 0 泄漏。
旧证据及旧 manifest 校验未改；base_library.zip 仅归档顺序不同，155 个成员字节
及元数据一致，其余 542 个 internal 文件逐字节一致。详细八项原始输出见
artifacts/step2/REVISION-20261018-smoke-headers.md。

Rust 对每个 /smoke 响应先核验两个头，再解释 HTTP 状态或 JSON；缺失、非法、
不匹配均为身份不匹配。HTTP 头名大小写不敏感。前端 run_smoke 无参，token
仅在 Rust；无代理、无重定向、有限超时、工作线程、无 TLS 与无外网请求边界不变。

旧 exit code=70 内部原因仍未验证；第 2 步 VM 仍待实机验证，未正式关闭。
