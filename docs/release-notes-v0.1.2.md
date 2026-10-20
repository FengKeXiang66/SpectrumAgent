# v0.1.2 release notes（待发布记账）

- R14 跨里程碑修正：#02 的 preview、band、region 对“数据集已登记，但源文件移动、缺失或不可用”的错误码，由读取器原始码（如 FILE_NOT_FOUND）统一改为 SOURCE_CHANGED；HTTP 状态仍为 400。响应 context 保留 source_error、source_detail 和读取器原 path。
- 包装仅发生在 Registry.readable 的 read_header 调用处。未知数据集仍返回 DATASET_NOT_FOUND（404）；导入期路径错误仍为 FILE_NOT_FOUND；info 仅查询登记记录，行为不变。
- #04 superpixels 共用该规则，包括命中引擎缓存后对源文件的重新验证。

依据：TASK-04 §6.4、§12 R14（2026-10-20）。本文件仅记录未来版本变更，不发布 Release、不打 tag。
