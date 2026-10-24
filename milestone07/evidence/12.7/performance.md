# TASK-07 12.7 性能记录

R24 数据口径：合成固定尺寸 cube，谱值无物理意义；实际 registry/readable(raw=True)/row_blocks/memmap/savemat/DB 路径运行，没有模拟计时。真实 NAS PE 数据与真实 LLM 延迟仍归科祥冒烟。本机单次测量不是跨机性能承诺。

大夹具 231×640×200，147,840 像素全标，源 float32 原始 DN 共 118,272,000 字节；公式 `1000 + (sample-band flatten index + row) % 5000`。大图分割为 17×48 确定性网格，按既有 Parameters.n_segments=800 推导，仅作为 confirm 前置夹具，未把它宣称为 SLIC 性能。小图 40×12×8 实际调用 superpixels 端点（24/.5/5 来自既有路由测试），DN RNG=17/range1000..5999 来自 annotation fixture。

| 记录 | 小图（480全标） | 大图（147840全标） |
|---|---:|---:|
| MatStore.generate 全程秒（含源hash/IO/写盘/落库） | 0.06341169998631813 | 0.6436063000001013 |
| confirm 全程秒（小图含ASGI HTTP，大图service） | 0.10185679999995045 | 1.711524600017583 |
| savemat 写入秒 | 0.0033192999835591763 | 0.19264209998073056 |
| MAT 文件字节 | 23016 | 120049512 |
| 写侧 tracemalloc 峰值增量字节 | 51949 | 118282655 |

30s 门：**通过，维持同步，无需重议异步**。判据用独立 MatStore.generate span=0.643606s；confirm 全程=1.711525s 另列，不将嵌套耗时相加。

内存口径按 R20：读侧一行有界，写侧 savemat 固有 O(n×B) 序列化副本接受。tracemalloc 只在原 scipy writer 调用周围启停，记录 Python 分配增量，不是进程 RSS、不含已存在 memmap 的物理驻留页，也不声称整体 O(B)。do_compression=False。

大图 DB 行：n_spectra=147840、n_bands=200、n_classes=4；完整 id/fingerprint/sha256/relative_path/created_at 逐项见 performance.json。预计纯 spectra=118272000 字节，实际 MAT 增量含 labels/rows/cols/类表/元数据。

大图 polygon draft document=802 UTF-8 字节。此为两个矩形的记录，不代表高碎片 RLE 最坏体积；GET draft 8MiB 限额风险保持挂账，未据此发明截断或采样。

## 对话延迟（mock transport）

| 阶段 | 秒 |
|---|---:|
| 用户消息→PARSE→human_check SSE 返回 | 0.039642399991862476 |
| PARSE provider callback | 0.0001449999981559813 |
| approve→confirm→MAT→INTERPRET→step/done SSE | 0.1260586999997031 |
| confirm service（嵌套） | 0.0758899999782443 |
| MAT generate（嵌套） | 0.04388179999659769 |
| savemat（嵌套） | 0.002440700016450137 |
| INTERPRET provider callback | 5.9999991208314896e-05 |
| 两个 HTTP 请求耗时之和（排除人类思考） | 0.16570109999156557 |

TestClient 会缓冲有限 SSE，计时是请求到事件集合返回及内部观测 span，不冒充真实网络逐事件到达延迟。provider 两次均为 MockTransport，真实云端请求=0；usage 未上报，调用留痕三 token 列均为 NULL，不估算 token。

机器/线程环境和原精度值在 performance.json；测量时无并发回归、构建或flake进程，未设 BLAS 线程限制，未调整生产参数。生成数据与运行应用均留在 E 盘 .runtime，不进 Git。
