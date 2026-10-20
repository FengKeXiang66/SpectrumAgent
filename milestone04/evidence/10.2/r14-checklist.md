# 10.2 R14 与引擎代码提交回执

事实源：TASK-04 R14，505 行。此提交未做 compactness 标定回填；55 格完整标定与峰值完整验收在此提交之后单独执行。

执行命令（同一个 PowerShell 调用，cwd=E:\AI_Agent）：

```powershell
Set-Location -LiteralPath 'E:\AI_Agent'
$env:PYTEST_DEBUG_TEMPROOT='E:\AI_Agent\.runtime\pytest-tmp'
& E:\AI_Agent\.venv\Scripts\python.exe -m pytest backend/tests src-python/tests -q
```

结果：231 passed、0 skipped、10 条第三方弃用警告。计数=202 既有+23 超像素+6 R14；默认执行参数，无筛选、无并行执行、无 pytest.exe 直跑、无 --basetemp 覆盖。stdout 完整输出见 pytest-r14.txt（22.08 秒为本次实测）。

## 六项对位

文件统一为 src-python/tests/annotation/test_source_changed_r14.py：

1. test_r14_01_deleted_hdr_preserves_source_context：删除 hdr 后 readable 返回 SOURCE_CHANGED，source_error=FILE_NOT_FOUND，保留 path、source_detail 与异常链；另验导入仍 FILE_NOT_FOUND，以及 source_error/source_detail 同名键碰撞时由包装字段覆盖。
2. test_r14_02_renamed_hdr_is_source_changed：重命名 hdr 后同样返回 SOURCE_CHANGED，原码 FILE_NOT_FOUND，path 为原 hdr 路径。
3. test_r14_03_smaller_binary_preserves_observed_reader_code：先独立实跑 4608 字节预期/2 字节实有的探针，reader 原码为 SIZE_MISMATCH；测试固定断言该实测值，再验 readable 包装为 SOURCE_CHANGED 并保留原码、原 detail、二进制 path 和异常链。
4. test_r14_04_unknown_id_remains_not_found_404：未知 id 的 readable 仍 DATASET_NOT_FOUND、无包装异常链；HTTP info/preview/superpixels 仍为 404。
5. test_r14_05_cached_engine_revalidates_deleted_source_without_force：首次 generate 与缓存命中成功，删除 hdr 后不传 force 再 generate 必须 SOURCE_CHANGED，不能返回旧缓存。
6. test_r14_06_http_preview_and_superpixels_return_source_changed_400：登记后删 hdr，preview 与 superpixels 均 400+SOURCE_CHANGED+原码 FILE_NOT_FOUND；同时核对 #02 band/region 同行为，info 仍可查登记记录。

## 实现与边界

- 仅 Registry.readable 的 read_header 调用放入 try/except DataError；source_error/source_detail 展开前去重，原 context/path 保留，使用 raise ... from error。
- get()、candidates()、字段比对循环及原 detail、reader 实现和 reader 既有单测均未改动。
- #02 preview/band/region 的已登记源不可用错误分类由原码统一为 SOURCE_CHANGED，HTTP 400 不变；变更记入 docs/release-notes-v0.1.2.md，未发布 Release。
- 引擎新增项已验 PCA 3/5、convert2lab=False、enforce_connectivity=True、有界读取、四步特征、均值谱/std、原区域内细分且邻居 id 原样保留、父子关系、固定 PCA-5 的 R 独立复算、响应参数/PNG/内存字节字段、无 scene 写入。
- OpenAPI 仅增加 superpixels 操作及其请求模型；既有路径保持不变。
- 标定脚本已入库以供现有 23 项测试的独立 R 复算调用；尚未完成的标定表、调试日志不在本提交中。
- seeds_20.json 未修改、不入库，SHA256=388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2。公司文档不入库。

未决口径：无。10.2 尚待完整标定回填和峰值完整验收；不进入后续阶段。
