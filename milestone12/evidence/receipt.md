# TASK-12 阶段 1 执行回报

执行日期：2026-11-01（Asia/Shanghai）。F1–F7 已实现；A7 因三项既有失败未全绿。Rust 零改动，未增加依赖，未修改 safe_name / display_names、DraftStore 锁、迁移逻辑或阶段 2 功能。当前提示与当前卡未发现口径冲突。

## 1. 逐文件改动

| 文件（仓库根 E:/AI_Agent） | 改动 / 新增函数签名 |
|---|---|
| src-python/spectrumagent/annotation/engines/superpixels.py | `segments_png(segments)`：完整尺寸 RGB 双字节打包、base64、shape、bincount；参数 65535 上限和 refine 后 65536 实际块数上限。overlay_png 未复用、未修改。 |
| src-python/spectrumagent/api/annotations.py | `block_summary(segments, label_map)`：一次联合 bincount 向量化；`working_view(identifier, *, with_overlay=True)`；superpixels 合并三个响应字段；regions 传 False 并省略 overlay；空态保持 overlay=None、补 blocks 三空数组。 |
| src-python/spectrumagent/annotation/session.py | `UNDO_DEPTH = 30`，两个 deque maxlen 均使用常量；不压缩、不延迟编码。 |
| src/components/annotation/types.ts | 新增 SegmentsMap、Blocks；Working 增 blocks；SuperpixelReport 增三字段；regions 响应类型为 Omit<Working, 'overlay'>。请求类型未扩展。 |
| src/components/annotation/working.ts | 白名单显式保留 blocks，注明“块级摘要不是像素图”；POST 后必读 GET 原则不变。 |
| src/components/annotation/shortcuts.ts | Tool 增 click，默认 c；不加 Delete 或 Shift binding。 |
| src/components/annotation/AnnotationWorkbench.tsx | commandNames/工具按钮增加点选；`applySegmentation(report: SuperpixelReport)` 同步轮廓和 id 图；三个 superpixels 返回路径均同步；onBlockClick/onBlockErase 调用现有 edit→api.regions→editThenRead。 |
| src/components/annotation/canvas/AnnotationCanvas.tsx | segments/labels props、原尺寸离屏读图、本地悬停高亮与徽标；click 内新增拖拽平移；down 记录 button/shiftKey；右键守卫放行；click 分支在 onSeed 前 return；既有 onContextMenu 只有一处。 |
| src/components/annotation/canvas/segments.ts（新增） | `decodeSegments(rgba: Uint8ClampedArray, map: SegmentsMap): DecodedSegments`；`hitTest(map: DecodedSegments, r: number, c: number): number \| null`；`isBlockClick(startX: number, startY: number, x: number, y: number): boolean`；`blockAction(button: number, shiftKey: boolean): EditAction \| null`；`blockBadge(id: number, counts: number[], blocks: Blocks, labels: Label[]): string`。 |
| src-python/tests/annotation/test_superpixels.py | 新增完整尺寸 RGB 往返、65535 id、counts、参数边界及 refine 后超限断言，共新增 5 项。 |
| src-python/tests/annotation/test_routes.py | 新响应字段、空态、POST overlay 省键、块摘要四规则、整块擦除、100 次响应键与渲染次数；旧 5 步断言更新为 30 步；新增 9 项。 |
| src-python/tests/annotation/test_session.py | 31 次操作验证保留上限；30 块点击撤销回初态，并覆盖标签重映射重建 deque；新增 2 项。 |
| src/components/annotation/working.test.ts | 新增 blocks 投影断言，保留未知字段过滤；保留开工前用户已有 AssistantPanel 断言改动。 |
| src/components/annotation/api.test.ts | 单块 superpixels 请求投影与数组复制；erase/uncertain 省略 label_id；新增 1 项。 |
| src/components/annotation/shortcuts.test.ts | C 点选、Delete/Shift 无独立命令；新增 1 项。 |
| src/components/annotation/canvas/segments.test.ts（新增） | 800 id 解码与计数、命中边界、3px/按钮动作、徽标、画布接线；新增 5 项。 |

工作区原有 App、assistant、样式等修改未触碰。api.ts 产品实现未改。

## 2. F1–F7 与 A1–A9

| 功能 | 完成情况 | 验收证据 |
|---|---|---|
| F1/F1b | 完成 | A2：513×640 合成 id 图逐像素往返，涵盖 id=65535；真实 cube 请求 n=800，实际 refine 后 830 块，前端所有 bincount 与服务端全等。容量校验测试通过。 |
| F2 | 完成 | A3：真实 231×640 cube 的 200 个固定随机点，浏览器 hitTest 与服务端 segments 全部一致；A8：本地高亮无请求。 |
| F3 | 完成 | A5：真实浏览器原生左键标注、右键擦除、Shift+左键不确定，徽标分别显示确定类 100%、未标注、不确定 100%；HTTP 测试逐像素断言整块覆盖/擦除。 |
| F4 | 完成 | A6：浏览器原生左键拖拽 20 次，每次 4px，POST/GET 均 0，revision 163→163，label_map SHA256 不变；纯函数覆盖 3px 含边界、>3px 排除。 |
| F5 | 完成 | A5：三数组与空态、留白排除、并列优先级、floor、整块分母、2/3 种标记均通过。 |
| F6 | 完成 | A4：session 测试 np.testing.assert_array_equal 逐像素回初态（含重映射）；浏览器连续 30 个不同块写入再撤销 30 步，前后 SHA256 相等，revision 103→163。 |
| F7 | 完成 | A1：改前/改后插桩 200→100，segments_png 始终 0；另有 label_overlay 渲染计数恰好 100 的回归测试。 |

- A7：未全绿，详见下表与未决问题，未将既有失败报告为通过。
- A8：真实 231×640 / n=800→830 块，segments_png base64 长度 31,744 bytes（PNG 原始 23,808 bytes）；浏览器包含图片解码、1:1 drawImage、getImageData、id 解码和 bincount 的测量为 5.9 ms 与 23 ms，均 ≤80 ms；20 次本地悬停同步 React 提交与画布更新最大 0.6 ms，≤16 ms，服务端请求数与 revision 均不变。此数不包含显示器扫描延时。
- A9：diff 检查无新增 safe_name/display_names 调用，Rust diff 为空。未增加依赖、迁移、DraftStore 锁。

### 测试执行模式和数量

全部从现有 checkout 执行，使用默认沙箱，无 require_escalated；未安装依赖、未过滤失败。

| 套件 | 改前实测 | 改后实测 | 执行模式 |
|---|---:|---:|---|
| Python 全量 | 1450 passed | 1466 passed，0 failed | 仓库根 `.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`，默认顺序/无 xdist；同命令设已创建的 E 盘 PYTEST_DEBUG_TEMPROOT。改后 278.98 s，15 条既有警告。 |
| Python superpixels/routes/session | — | 112 passed | 同 venv，三个指定文件，独立 E 盘 temproot，74.90 s。属于全量子集，不重复累计。 |
| Node 全量 | 178 passed / 1 failed（179） | 185 passed / 1 failed（186） | Node 24.19.0，`node --test "src/**/*.test.ts"`，默认 runner/concurrency。 |
| Node 标注子集 | — | 59 passed | `node --test "src/components/annotation/**/*.test.ts"`，属于全量子集。 |
| Rust | 87 passed | 87 passed | src-tauri 内 cargo test --locked --offline，默认 features、默认并行，含 1 doc-test；未指定 test-threads。 |
| clippy | Rust 源码未改 | 失败，18 处既有 unwrap_used | cargo clippy --locked --offline --all-targets -- -D warnings；编译检查，无测试用例计数。 |
| npm run build | 通过 | 通过 | 本地 Node 24.19.0 / npm 10.8.2，tsc --noEmit && vite build；编译检查，无测试用例计数。 |
| e2e07 | 63/65 断言，提前失败 | 相同 63/65，提前失败 | 既有脚本 main，真实 TestClient/ASGI、合成数据、MockTransport；只将 OUT 重定向到本次 .runtime 证据目录，未改测试逻辑，未跑至卡中旧记录 218。 |
| e2e08 | 116/116 | 116/116 | 既有脚本，真实 ASGI/引擎、4 个合成 cube、无 provider 网络。 |
| 浏览器 | — | A1–A6/A8 指定探针通过 | Chromium/IAB，构建后的实际 AnnotationCanvas/segments/editThenRead，加隔离 TestClient 代理；真实 PE 源文件只读。原生点击/右键/Shift 与原生 20 次拖拽；100 块与 30 步撤销由测试页顺序调用同一个编辑回调。调试探针全部在 .runtime，不进入产品代码。 |

Python 第一轮因我未创建 PYTEST_DEBUG_TEMPROOT 父目录出现 435 passed/1015 setup errors；创建目录后改前全量 1450 passed，未修改配置、断言或请求提权。该失败尝试不作为功能基线。浏览器最初 Vite 开发服务响应不稳定，最终使用构建后的静态测试页完成验收，产品 build 未变。

## 3. A1 插桩证明

统计所有响应 JSON 中键的实际出现次数，递归统计；从第一次写入到第 100 次写入及其权威 GET 完成，不含 initial superpixels/working 加载。

| 窗口 | POST /regions | GET /working | png_base64 | segments_png |
|---|---:|---:|---:|---:|
| 改前 TestClient 客户端 | 100 | 100 | 200 | 0 |
| 改后相同 TestClient 客户端 | 100 | 100 | 100 | 0 |
| 改后浏览器真实 cube，100 个不同块 | 100 | 100 | 100 | 0 |

原始文件：baseline-clicks/counts.json、final-clicks/counts.json、browser-click-window.json。浏览器窗口 revision 3→103；随后撤销与性能检查均在窗口之外。queue 在该窗口为空；既有候选 queue 响应契约未变。

## 4. A5 取值规则构造与结果

| 构造 | 返回 label / purity / label_count |
|---|---|
| 60% 留白 + 40% PET（288+192/480） | PET 对应下标 2 / 40 / 1 |
| 50% PET + 50% PE（240+240/480） | 较小下标 PE=1 / 50 / 2 |
| 50% 不确定 + 50% PET | PET=2 / 50 / 2，确定类优先 |
| PET 799/800，其余 1 像素留白 | 2 / 99 / 1（禁止 round） |
| 全留白 | -1 / 100 / 0 |
| 60% PET + 40% PP | 2 / 60 / 2 |
| 60% PET + 20% PE + 20% PP | 2 / 60 / 3 |
| 全不确定 | -2 / 100 / 1 |

所有路由构造随后执行整块 erase 并逐像素断言全为 -1。799/800 使用 block_summary 直接构造断言。purity 分母始终整块像素数。

## 5. 行号漂移清单

发现一处卡内既有定位不精确：§0.3 将“进入标注页即 POST superpixels”指向 Workbench 原 198–200，实物该段是 refreshVersion 同步分支；初始恢复实际在原 129–130（现 135–136）。原 200 的刷新 POST 现为 206。两条路径都已同步 id 图，未静默替换口径。

其余已核对开工前行号一致；本次插入代码造成以下正常后移，供复核定位：

| 文件 | 卡中旧行 → 现行 |
|---|---|
| superpixels.py | overlay_png 205→216；stride 206→217；参数拒绝码 255→266；新 segments_png 205，refine 后容量校验 284。pca_features 错误码 97、refine 179 均未漂移。 |
| session.py | deque 138→141、181→184；RLE 250–251→253–254；undo push 258→261。 |
| annotations.py | 请求模型 99→118、123→142；geometry_mask 158→177；working_view 262→281；空态 269–270→288–290；superpixels 路由 296–302→318–326；regions 311–316→335–340。 |
| AnnotationCanvas.tsx | contextmenu 142→188；pan 150→196；右键守卫 151→198；pointermove 156→204；pointerup 165→219；onSeed fallthrough 181→250。 |
| AnnotationWorkbench.tsx | commandNames 24 不变；工具行 310→316；onSeed 355→361；刷新 POST 200→206，初始恢复 POST 129→135。 |
| working.ts | 白名单 5–7→6–8；editThenRead 12–15→13–16。 |
| annotation.rs | 49/319/393/968 均不变，Rust 零改动。 |

## 6. 未决问题

没有新增设计歧义；以下既有回归失败使 A7 不能标通过，本卡范围内未修：

1. Node：src/components/preprocess/panel.test.ts:52 的 `/projects\[0\]/` 源码形状断言已在开工前失败；185/186 的唯一失败与基线一致。
2. e2e07：改前/改后均记录 `INTERPRET sends tools=None` 与 `approve SSE sequence step/done` 两个失败断言；脚本在审批序列处中止，63/65，不宣称旧记录 218 全绿。
3. clippy：src-tauri/src/models.rs 测试中的 18 处 unwrap_used，位置为 320、321、374（两处）、380、411、412、413（两处）、417、418、420、421、427、450、459、461、462。Rust 工作区 diff 为空；保持用户的 Rust 零改动约束。

按卡记录的可接受副作用：旧用户快捷键偏好因 bindings 从 10 个变 11 个而回退默认，可能丢一次自定义；未做偏好迁移。

原始日志与 JSON、浏览器截图保留在本目录。验收不等同于打包安装态测试，未构建或发布安装包。
