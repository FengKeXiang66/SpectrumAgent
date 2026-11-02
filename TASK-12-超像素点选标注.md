# TASK-12 超像素点选标注（点击即写 / 悬停高亮 / 撤销加深）

> 备卡方：本 agent ｜ 执行：codex ｜ 验收：独立复核
> **基线**：开工前由执行方实测并在回报中写明执行模式（本项目纪律：自报测试数必须带执行模式）。上次记录值 Python **1154** / node **120** / cargo **75** / e2e08 **116** / e2e07 **218**（TASK-08 13.1 时期，**不得当作本次基线**）。
> 本卡性质：**交互能力补齐**。不改标注存储语义——`label_map` / `regions[]` / RLE / 候选队列 / 撤销以外的状态一律不动。
> 卡来源：2026-10-31～11-01 五轮交叉验证（本 agent ↔ 独立复核方），六问已定案，净分歧清零。决策固化见 §7。
> **行号基线**：§0.3 / §2 / §4 中的行号均为 **TASK-12 改动前**（commit `3c2e029`）的基线。实现后的映射见 §9，直接 grep 现码会全部对不上。

---

## 0. 背景与依据（先读，不要跳过）

### 0.1 用户要什么（原话口径）

> 「超参数合适时，一个超像素能直接框住图中一个塑料瓶，想让用户直接点击超像素完成标注。」
> 「范围就是用户所点击的这一块超像素。」

即：**点击 = 整块覆盖写入，不做二次确认**。注意"确认"一词在本项目专指候选队列的 `draft/confirm`，与点选无关——`region_from_gesture` 内部调 `sessions.edit(action="confirm")`（`annotation/gestures.py:31`），那个 `"confirm"` 是"赋标签"的内部动词，落到 document 里是 `op="add"`（`annotation/draft.py` 中 `op="add" if action == "confirm" else action`）。

### 0.2 现状：点击被解释为扩散种子

`AnnotationWorkbench.tsx:355` 的 `onSeed` 把画布单击交给 `diffuse(seed)`；`AnnotationCanvas` 只持有 `segmentation: Png`（带白色边界与 id 文字的可视化图，`engines/superpixels.py:205-223`），**不是 id 映射**。因此前端无法回答"点到了哪一块"。

### 0.3 已定案的事实（全部行号级核实，勿再重复论证）

| 事实 | 证据 |
|---|---|
| 点选**可以**单次往返写入，且撤销已具备 | `api/annotations.py:311-316` 的 `POST /datasets/{id}/annotations/regions` 收 `SuperpixelGeometry \| PolygonGeometry`（`:99-102`），内部调 `sessions.edit(...)`，而 `sessions.edit` 在 `annotation/session.py:258` push 撤销栈 |
| 该路径写入的是 **RLE 不是 polygon** | `annotation/session.py:250-251`：`if geometry is None or "superpixels" in geometry: actual = {"type":"pixel_set","rows":encode_rle(mask),"segments_fingerprint":state.params}` |
| draft 新路由只收 `Polygon \| DraftGesture` | `api/annotations.py:123-126`；走它才是两跳。**本卡不走这条路** |
| 撤销栈深度只有 5 | `annotation/session.py:138` `deque(maxlen=5)`，`:181` 重建处同样 `maxlen=5` |
| 手势表只增不减 | `annotation/session.py:136` / `:220-225`，无任何淘汰逻辑（本卡绕开它，不修） |
| 每次点击渲染两次 overlay | `src/components/annotation/working.ts:12-15` `editThenRead = await edit(); return readWorking(...)`——POST 响应被整包丢弃，随后 GET working 再渲一次 |
| Rust 转发层对响应是 `Value` 透传 | `src-tauri/src/annotation.rs:319` `-> Result<Value, ForwardError>`，`:393` `Ok(value)`（`:384-387` 另有 SENSITIVE_RESPONSE 扫描，`:389-391` 错误分支）；请求侧 `deny_unknown_fields` 在 **`:49`** → **禁止加请求字段，只加响应字段** |
| 响应体上限 8 MiB | `src-tauri/src/annotation.rs:968` 测试 `an_exactly_eight_mib_json_response_is_allowed` |
| 前端进入标注页即会 POST superpixels（同参数命中服务端缓存） | `AnnotationWorkbench.tsx:198-200` |

### 0.4 为什么不是"三处后端改动"

上一轮本 agent 主张"点选必须两跳、需扩 draft 联合类型"。经复核方指正并回查：**legacy 路由已完整具备单次往返 + 撤销 + id 校验**（`geometry_mask` 里 `np.isin(...).all()`，`api/annotations.py:158-163`）。因此本卡的后端改动收缩为：**只加 id 图下发**。`SuperpixelGeometry` 进 draft 联合属语义洁癖，**不做**（见 R1）。

---

## 1. 范围裁定

### 1.1 本卡要做（P0）

| # | 功能 | 说明 |
|---|---|---|
| F1 | **id 图下发** | `POST /superpixels` 响应新增 `segments_png` + `block_counts`（见 §2.1、§3.1） |
| F2 | **本地命中与悬停高亮** | 前端从 id 图解码出块 id，光标处直接命中，无需往返 |
| F3 | **点选写入** | 新增 `click` 工具位；左键 = 当前类 `add`，右键 = `erase`，均走 legacy 路由 |
| F4 | **平移与点击判别** | 位移 ≤3px 判点击，>3px 判平移（工具内） |
| F5 | **块状态徽标** | 悬停显示：块 id / 像素数 / 当前类与纯度 / 混合块提示（只读） |
| F6 | **撤销加深** | 5 → 30，两处 `maxlen` 统一到常量 |
| F7 | **消除重复渲染** | `POST /regions` 响应不再携带 overlay（GET working 仍是唯一权威读回） |

### 1.2 本卡不做（明确禁止，不要"顺手加"）

- ❌ **参数变更后的块量化迁移**（`source="migration"`）。与 TASK-04 §6.1 已验收断言冲突（"换参数按像素保留，不得重算 label map"），属需求变更，须单独立项（见 R4）。
- ❌ 混合块的多种删除语义。整块覆盖 / 整块清空就是用户预期语义（§0.1），本卡只做只读徽标。
- ❌ 扩散阈值改分位数、双阈值生长、库匹配、自动标注 —— 全属阶段 2/5（§8）。
- ❌ SAM / 任何新依赖（torch、onnx 等）。
- ❌ 扩展 `DraftRegionInput.geometry` 联合类型。
- ❌ 给 `DraftStore` 加锁（锁序反转死锁风险，见项目红线）。
- ❌ 动 `safe_name` / `display_names`（LLM 可见面，见 TASK-13 阶段 3）。

---

## 2. 口径钉死（照抄，不得自行发挥）

### 2.1 id 图编码（D1）

**必须是 8 位双通道打包，不得用 16 位灰度 PNG。** 理由：浏览器 `canvas.getImageData` 只能取回 8 位/通道，16 位 PNG 经 `drawImage` 会被压成 8 位，块 id > 255 时全部塌陷——n=800 是默认值，必然踩中。

```
R = id & 0xFF
G = (id >> 8) & 0xFF
B = 0
```

**块数上限 65535**：`Parameters` 目前只校验 `n_segments >= 1`（`engines/superpixels.py:250-255`），用户手输 70000 会让 `id >> 8` 溢出、静默错位而不报错。F1 必须同时加 `n_segments <= 65535` 校验，超限抛 `INVALID_SUPERPIXEL_PARAMETERS`。

**参数上限挡不住实际块数**：高方差自动细分（`refine`，`superpixels.py:179-202`）会新增子块，n 逼近上限时大块仍会触发细分。因此 F1 还须在 `refine()` **之后**加生成后校验 `len(np.unique(segments)) <= 65536`，超限抛同一错误码。id 最大 65535 = `0xFFFF` 恰好安全，溢出是静默错位（图看起来完全正常、命中全错），必须硬拦。

- 尺寸必须与 `segments.shape` **完全一致**，禁止任何 `stride` 降采样（`overlay_png` 的 `stride = ceil(max(shape)/512)` 只用于显示，见 `engines/superpixels.py:206`）。
- 前端解码：`id = R + 256 * G`，且离屏 canvas 必须 **1:1 绘制**、`imageSmoothingEnabled = false`。任何缩放都会插值出假 id。
- 服务端同时返回 `block_counts`（每块像素数，`np.bincount` 结果）供前端做解码自检（§5-A2）。

### 2.2 命中与点击判别（D2）

- 光标像素 → id 图取值 → 块 id。**命中全在本地，不产生网络请求**（悬停尤其）。
- **复用 `drag.current` 记录机制，但不复用其语义**：现有状态机里左键拖拽产生 `points`（涂鸦/框选/多边形），**从来不是平移**（`AnnotationCanvas.tsx:156-164`）。`click` 工具内的「左键拖拽 = 平移」是**新增语义**，不是还原既有行为——不要按"沿用现有状态机"理解。
- 工具为 `click` 时：`pointerdown` 记录起点，`pointerup` 时位移 ≤3px 判点击，>3px 判平移。
- `panHeld`（空格）或中键 → 一律平移，不判点击（与现状一致，`:150`）。
- **右键擦除必须先改既有守卫**：`AnnotationCanvas.tsx:151` 的 `event.button !== 0` 在 `pointerdown` 阶段直接早退，右键永远进不了状态机。`click` 工具下须放行 `button === 2`，把 `button` 记入 `drag.current`，在 `pointerup` 分发 `erase`。
- `contextmenu` 的 `preventDefault` **已存在**（`AnnotationCanvas.tsx:142` 的 `onContextMenu`），属既有事实，**不要当作新增改动**。
- **`click` 分支必须插在末尾 fallthrough 之前**：`onPointerUp` 末尾是 `props.onSeed({ point: last })`（`AnnotationCanvas.tsx:181`），任何未命中的工具都会落到扩散种子；新增分支若加在它之后将永不执行。

### 2.3 键位映射（D3）

| 操作 | 语义 | 写入 |
|---|---|---|
| 左键单击块 | 标注为当前选中类 | `POST /regions`，`geometry={superpixels:[id]}`，`action="confirm"`，`label_id=<当前类>` |
| 右键单击块 | 该块像素全部擦回 -1 | 同上，`action="erase"`，`label_id` 省略 |
| Shift+左键 | 标记不确定（-2） | 同上，`action="uncertain"` |
| 左键拖拽 | 平移 | 无写入 |
| 悬停 | 高亮该块 + 徽标 | 无写入 |

**不设 Delete 键**：删除的对象是"鼠标下的那一块"，键盘没有空间定位语义；配一个 Delete 只能删"上次点过的块"或"悬停的块"，前者要维护一个与 hover 冲突的选中态，后者键鼠并用反而更慢。删除由右键承担，误删由撤销承担（F6）。**Shift 不是键位绑定**，是 `pointerdown` 时记录的修饰键状态（见 §2.2 D2）。

写入后**不弹确认卡**。撤销是唯一兜底（F6）。

### 2.4 块状态徽标（D4）

服务端从 `label_map` + `segments` 一次向量化算出：

```
block_label[i]       = 该块内**非 -1** 像素中占比最多的 label 值（-2 不确定 / ≥0 类下标）；全为 -1 时 = -1
block_purity[i]      = 该 label 的像素数 ÷ 整块像素数 × 100，向下取整（0–100 整数）
block_label_count[i] = 该块内不同非 -1 label 值的个数（含 -2；全留白块 = 0）
```

**字段名是 `label_count`，不是 `class_count`**：-2（不确定）不是类，叫 `class_count` 会让后续写自动标注的人误以为它只数类。徽标文案随之用「种标记」而非「类」。

**取值规则（三处歧义一次定死，不得自行发挥）**：

1. **留白不参与竞争**：块内只要有非 -1 像素，`label` 就只在非 -1 值里取最多的；**全部为 -1 时** `label = -1`、`purity = 100`、`label_count = 0`。
   理由：`60% 留白 + 40% PET` 的块若显示「未标注 60%」，用户会当成空块直接擦掉，而它含 40% 的 PET——徽标的用途就是擦除前预警。
2. **并列的裁决顺序**：计数相同 → 已确认类（`≥0`）优先于 `-2` → 同类内取**数值最小**的 label。
   `≥0` 优先于 `-2`：有确定标注时不该显示"不确定"；数值最小保证确定性，且与类注册顺序一致。
3. **纯度向下取整**：`purity = (100 * count) // block_size`（整数除法，不是四舍五入）。
   向上取整会让 `799/800` 显示 100%，恰好把"这块不纯"说成"纯"——徽标只在擦除前看，说反了代价最大。向下取整保证**只有真正 100% 才显示 100**。
4. `purity` 的分母**恒为整块像素数**，不是非留白像素数——它回答的是"擦掉这块会损失多少"。

徽标文案：`块 137 · 312 px · 聚乙烯 92%`；`label_count ≥ 2` 时追加 `· 含 N 种标记`；`label = -1` 时显示 `· 未标注`（不显示纯度）；`label = -2` 时显示 `· 不确定`。**类名用 `Label.name`（中文名），不用 `code`**——与 `LabelPanel` 展示口径一致；实现里按 `labels[label]` 的位置索引取，该顺序由 `orderedLabels`（`sort_order` 后 `code`）保证，与后端 `drafts.labels` 的 `ORDER BY l.sort_order, l.code` 同序。

**不设 `mixed` 布尔字段**：`mixed === (label_count >= 2)` 是同一事实的两种表示，双字段必然漂移（改一个忘另一个）。前端从 `label_count` 派生。

**注意**：`workingView`（`working.ts:5-7`）是显式白名单，注释写明"Drop unknown runtime fields too, so a future response cannot introduce a map"。新增 `blocks` 必须显式加进白名单，并在注释里写明**块级摘要不是像素图**，避免后人误判为泄漏。

### 2.5 撤销深度（D5）

- 新增模块常量 `UNDO_DEPTH = 30`，`session.py:138` 与 `:181` 两处 `maxlen=5` 全部替换。
- 内存：单条快照 ≈ `label_map.copy()`（231×640×4 B = 590 KB）+ document JSON。30 步 ≈ 18–20 MB，桌面应用可接受，**本卡不做惰性编码**。

---

## 3. 接口契约

### 3.1 `POST /api/v1/datasets/{id}/superpixels`（扩展，向后兼容）

响应新增三个字段，**不新增请求字段**（Rust 请求侧 `deny_unknown_fields`，加请求字段会连带改 Rust）：

```jsonc
{
  // ...现有 report 字段全部保留...
  "segments_png": "<base64, RGB PNG, R=id&0xFF, G=id>>8>",
  "segments_shape": [231, 640],
  "block_counts": [312, 198, ...]        // 长度 = superpixel_count
}
```

体积预算：231×640 双通道 PNG 预期 40–120 KB，base64 后 < 160 KB，远低于 8 MiB 上限。

### 3.2 `POST /api/v1/datasets/{id}/annotations/regions`（收窄）

响应**不再包含 `overlay`**，其余字段（`superpixel_count` / `params` / `statistics` / `queue` / `project_id` / `blocks`）保留——注意 `blocks` 会随本响应一并返回（`regions()` 内部走同一个 `working_view`），无消费方受影响：`editThenRead` 整包丢弃该响应，且 `blocks` 不是 PNG、不污染 §5-A1 的 `png_base64` 计数。

实现上**省略该键**，不要置 `null`：`editThenRead`（`working.ts:12-15`）整包丢弃该响应，没有任何消费方依赖键存在；置 `null` 反而让 §5-A1 的 `png_base64` 计数口径含混。

实现建议：给 `working_view(identifier)` 加关键字参数 `with_overlay=True`，`regions()` 调用时传 `False`。**不要**改前端 `editThenRead` 的"POST 后必读 GET"原则（`working.ts:14` 注释已钉死）。

### 3.3 `GET /api/v1/datasets/{id}/annotations/working`（扩展）

响应新增：

```jsonc
{
  "blocks": {
    "label":       [-1, 3, 3, ...],    // 长度 = superpixel_count
    "purity":      [100, 92, 71, ...], // 0–100
    "label_count": [0, 1, 2, ...]      // 不同非 -1 label 值的个数，含 -2
  }
}
```

体积：n=800 时约 12–18 KB JSON，可随每次 working 返回（一次 `bincount` 级开销）。

**空态定义（不得自行发挥）**：`state.segments is None` 时 `working_view` 走早退分支（`api/annotations.py:269-270`，现返回 `superpixel_count: 0`）。此时 `blocks` 必须返回 `{"label": [], "purity": [], "label_count": []}`（三个空数组），**不得省略 `blocks` 键**——前端 `workingView` 按字段取值，键缺失会得到 `undefined` 而非空数组，渲染层会炸。

### 3.4 错误码

复用现有：`SUPERPIXELS_REQUIRED`（未生成分割）、`INVALID_GEOMETRY`（id 不存在）、`INVALID_LABEL`（label 不属于本项目）、`ANNOTATION_CONFLICT`（revision 失配）、`INVALID_SUPERPIXEL_PARAMETERS`（块数超 65535，代码中已在 `engines/superpixels.py:97` 与 `:255` 两处使用，本卡复用不新造）。

---

## 4. 改动清单（逐文件，不要扩大范围）

### Python

| 文件 | 改动 |
|---|---|
| `annotation/engines/superpixels.py` | 新增 `segments_png(segments) -> {png_base64, shape, counts}`：双通道打包 + `np.bincount`。**不得复用 `overlay_png`** |
| `api/annotations.py` | `superpixels()` 响应合并 `segments_png` 等三字段；`regions()` 改用 `working_view(..., with_overlay=False)`；`working_view` 增加 `blocks` 计算与参数 |
| `annotation/engines/superpixels.py`（校验） | `Parameters` 校验补 `n_segments <= 65535`（见 §2.1 块数上限） |
| `annotation/session.py` | `UNDO_DEPTH = 30`，替换 `:138` 与 `:181` 两处 `maxlen` |

### Rust

**零改动。** 依据：响应为 `serde_json::Value` 透传（`annotation.rs:319/393`），新增字段自动通过；请求侧不加字段故 `deny_unknown_fields` 不受影响。若执行中发现需改，**先停手回报**，说明哪一行拦住了。

### 前端

| 文件 | 改动 |
|---|---|
| `src/components/annotation/types.ts` | `Working` 增 `blocks`；新增 `SegmentsMap` 类型 |
| `src/components/annotation/working.ts` | `workingView` 白名单加 `blocks`（附"块级摘要不是像素图"注释） |
| `src/components/annotation/canvas/AnnotationCanvas.tsx` | 载入 id 图到离屏 canvas；`click` 工具下的命中 / 悬停 / 3px 判别 / 右键擦除；hover 徽标渲染 |
| `src/components/annotation/shortcuts.ts` | `Tool` 增 `'click'`；`defaultPreferences().bindings` 增 `click: 'c'`（`'c'` 未被占用，不触发 `bindingProblem` 的数字键/重复/保留键规则）；**不新增 Delete 键**（§2.3）；Shift 不是绑定，是 canvas 内 `pointerdown` 记录的修饰键状态 |
| `src/components/annotation/AnnotationWorkbench.tsx` | 工具行加 `click` 按钮（复用 `['diffuse','brush','polygon','erase']` 那一行，`:310`）；`commandNames: Record<Command,string>`（`:24`）补 `click: '点选'` 条目，否则 `Command` 联合类型扩宽后 TS 报缺键；接 `onBlockClick` / `onBlockErase`；`api.regions` 调用与 `editThenRead` 串联 |

**已知副作用（可接受，但要记录）**：`loadPreferences()`（`AnnotationWorkbench.tsx:26-33`）用 `Object.keys(stored.bindings).length === Object.keys(defaultPreferences().bindings).length` 校验存量偏好。默认键从 10 个变 11 个后，**老用户存的自定义键位会因长度不符静默回退默认，丢一次自定义**。这是 schema 演化防御的本职行为（`bindingProblem` 兜不住缺键），不在本卡修；若后续要保平滑，须引入版本号迁移而不是放宽长度校验。
| `src/components/annotation/api.ts` | `regions` 已存在，**不新增请求形状**；仅在测试里断言 `geometryBody({superpixels:[...]})` 输出 |

### 测试

| 文件 | 断言 |
|---|---|
| `src-python/tests/annotation/test_superpixels.py` | id 图往返：解码后逐元素等于 `segments`；`block_counts` 与 `np.bincount` 一致 |
| `src-python/tests/annotation/test_routes.py` | superpixels 响应含三新字段；regions 响应**不含** `overlay`；working 含 `blocks`（三数组，长度 = `superpixel_count`）；`label_count` 在 60/40 与 60/20/20 两种构造下分别为 2 与 3；**取值规则四条各一例**（60% 留白+40% PET → `PET/40`；50/50 → 数值小者；799/800 → 99；全留白 → `-1/100/0`） |
| `src-python/tests/annotation/test_session.py` | `UNDO_DEPTH=30`：连续 30 次写入后仍可逐步撤销至初态 |
| `src/components/annotation/working.test.ts` | `workingView` 白名单包含 `blocks`，且丢弃未知字段的既有行为不变 |
| `src/components/annotation/canvas/*.test.ts` | 3px 判别、右键 preventDefault、命中函数纯函数化后可单测 |

---

## 5. 验收标准（逐条可验）

| # | 断言 | 判据 |
|---|---|---|
| A1 | **点击成本（硬门槛）** | 连点 100 块，**统计窗口 = 第 1 次点击到第 100 次点击，不含初始加载**：`POST /regions` 100 次 + `GET /working` 100 次；插桩客户端累计**所有响应体中 `png_base64` 键的出现次数 = 100**（当前基线 200）。注意 `png_base64` 是 `overlay` 对象内的字段名，`segments_png` 是顶层字段名，**不要混计**；同窗口内 `segments_png` 出现次数必须 = 0（它只在初始加载出现一次）。F7 若拿不出这条证明即视为未完成 |
| A2 | **id 图解码正确** | 前端解码后 `bincount` 与 `block_counts` 逐元素相等（n=800 全等）；不等即判失败 |
| A3 | **本地命中正确** | 随机 200 像素，前端本地命中结果 = 服务端 `segments[r,c]`（用一次性调试探针比对，探针不进产品代码） |
| A4 | **撤销深度** | 连续 30 次点击后逐次撤销 30 次，`label_map` 与初始逐像素相等 |
| A5 | **整块语义 + 计数 + 取值规则** | 右键后该块全部像素 = -1；`60/40` → `label_count = 2`、`60/20/20` → `3`（两者 `label` 与 `purity` 相同，只有 `label_count` 能区分——这条就是 codex 停手的那条契约缺口，必须可验）；`60% 留白 + 40% PET` → `label = PET`、`purity = 40`（不得显示"未标注 60%"）；`50/50` 两类 → 取**数值较小**的 label、`purity = 50`；`799/800` → `purity = 99`（不得为 100）；全留白块 → `label = -1`、`purity = 100`、`label_count = 0` |
| A6 | **拖拽不误写** | 拖拽 20 次（位移均 >3px）：`regions` 写入 0 条，`revision` 不变 |
| A7 | **无回归** | e2e07（218）/ e2e08（116）全绿；`npm run build`（含 `tsc --noEmit`）通过；`cargo test` + `cargo clippy --all-targets -- -D warnings` 通过（Rust 未改也须复跑） |
| A8 | **性能** | id 图 ≤ 160 KB；前端解码 + bincount ≤ 80 ms（231×640）；悬停响应 ≤ 16 ms（本地，无网络） |
| A9 | **路径纪律** | 本卡不触碰 `safe_name` / `display_names`；grep 确认无新增调用 |

---

## 6. 红线

1. 不改 `label_map` 三态语义、不改 `regions[]` 结构、不改 RLE 编码（`annotation/raster.py:23-31`）。
2. 不给 `DraftStore` 加锁（锁序反转死锁；生产路径由 `api/annotations.py:199-206` 的 `with sessions._lock` 包住）。
3. 不做块量化迁移（R4）。
4. 不引新依赖；PIL 已在依赖内。
5. 不改 `working.ts` 的"POST 后必读 GET"原则。
6. 悬停与命中**禁止**发网络请求（A8 的 16 ms 判据就是为此）。
7. 执行中若发现行号与实物不符，**必须在回报中显式说明**，不得静默改口径。

---

## 7. 决策记录（五轮交叉验证固化，R 号自本卡起编）

| R | 决策 | 依据 |
|---|---|---|
| R1 | 点选走 legacy 路由；**不**扩展 `DraftRegionInput.geometry` | `api/annotations.py:311-316` 已具备单次往返 + 撤销 + id 校验；扩展属语义洁癖 |
| R2 | id 图用 **8 位双通道 PNG**，不用 16 位灰度 | 浏览器 canvas 只能取回 8 位/通道，16 位会塌陷；n=800 > 255 必然踩中 |
| R3 | 撤销深度 5 → 30 | 点选节奏下 5 步只有几秒历史；30 步 ≈ 20 MB 可接受 |
| R4 | **不做**参数变更后的块量化迁移；混合块只做只读徽标 | 迁移与 TASK-04 §6.1「换参数按像素保留、不得重算 label map」冲突，属需求变更；且用户口径本就是"整块" |
| R5 | `POST /regions` 不再返回 overlay | `working.ts:14` 已钉死 GET 为权威读回；重复渲染纯浪费（实测 2 倍） |
| R6 | **阈值纪律**：凡"跨材质比较"的阈值（`cos_s`、库匹配、入队下限）一律用**同 cube 相对量**（分位数 / 稳健 z）；`cos_uv` 例外。阶段 2 落地时四条护栏必须同时写死：①**分位数参照系显式化**（取全部超像素的 `cos_s` 还是剔除种子后的块，两个实现必须可比）；②**大物体截断**（物体真占全图 >X% 时会被分位闸砍掉，卡里须写明适用边界）；③**空 cube 假阳**（纯背景 cube 上 top X% 照样出候选，配绝对下限兜底 `AND cos_s ≥ 0.5`）；④**实测不豁免**（X 与兜底下限仍须在 11 个标定 cube 上跑触发率后落，且属对 TASK-04 §5.3"可调默认值"的语义变更，须记 R 号） | 跨材质比较双方分布不同、批次敏感；`cos_uv` 比较"假定同材质的邻接对"，同分布，绝对值相对稳——这也解释了 0.92 标定后一直没出事 |
| R7 | labelme 导出以**公司自带 exe** 为实测对象（`E:\Software\IrisCubeStudio\labelme.exe`，162,126,104 B，LastWrite 2024-07-15 → 5.x 时代产物；PyPI 今日最新 7.9.1，不可想当然下移）；默认**按类投影**（模式 B），顺序约定仅用于审计导出 | 布尔运算在 `label_map` 已解完；顺序约定只对认约定的消费者成立 |
| R8 | 自动标注**两级闸门**（取代原「z ≥ 3 且 margin ≥ 1.5」）：**闸门 0（只能否决）**——2–3 cube/类即可，用 `spectra.npz` 的 `mean_i` 算类均值谱的类间/类内距离比，`min_inter / mean_intra < 2` 当场判死；**闸门 1（决定开不开）**——10–15 cube/类，留一 cube 的 **AUC ≥ 0.95** 开工、0.85–0.95 只做候选提示、< 0.85 转学习型。另配 **sanity band**：单 cube 接受块占比须落在 1%–60% | `z` 的分母是该 cube 自己的块间离散度，**不可跨 cube 比较**，拿它当开工闸门等于用每张图刻度不同的尺子量同一门槛；`z` 是判决阈值不是可行性指标。闸门 0 只能否决不能批准（类均值谱把类内多模态平均掉了，是乐观估计）。sanity band 同时挡住"空转"（<1%）与"零分布被污染"（>60%） |
| R9 | 零分布用 **median + MAD**（`σ = max(1.4826·MAD, ε)`，ε≈0.01），配 dominance 保护（单 cube 内 z≥z_hi 块占比 >80% 判污染、全部降级 -2） | 剔除 top-k 会抬高 z、让匹配器过度自信；median/MAD 失败方向是漏报，安全 |
| R10 | PLS 样本单位是 **cube，且不分 类**：`build_sample_training_set` 读快照 `label_map.npz`（`modeling/dataset.py:150`），对该 cube **全部已标前景像素**（`labels >= 0`、去掉 `is_background` 类，`:169-177`）求**一条**均值谱 → 一个 cube 一行（`modeling/run.py:145-147` "One row per cube"）。粒度只影响这条谱的纯度，不影响样本量 | 数据源是**快照 label_map**，不是 `sample_spectrum` 表——该表全仓库只写不读（仅 `session.py:388/399` 两处 INSERT/DELETE，无任何消费方）。两条推论：①"聚合前腐蚀内芯 1–2 px"仍是阶段 2 唯一真正影响建模质量的改动；②**同一 cube 上标了多个类会被平均成一条谱**，混标在建模层无法再分开 → 探针集必须一个 cube 只标一个类 |

---

## 8. 后续里程碑登记（不在本卡执行，仅防丢失）

| 阶段 | 内容 | 依赖 / 决策点 |
|---|---|---|
| 阶段 2 · 阈值纪律 | 双阈值生长（`cos_uv ≥ τ_local` 且 `cos_s ≥ τ_purity`）+ `report.isolation`（邻域一致性）+ 聚合前腐蚀内芯 | 默认值必须按 R6 用分位数、并在 11 个标定 cube 上跑触发率后落；**0.75 已被实测 0.6–0.72 否掉**；UI 现有 0.92 / 0.60 两个输入框语义会变，文案与迁移说明须同步。**启动前置**：阶段 1 落地并被真实使用 + 人工标注 10–15 cube/类（同一批数据同时喂 R6 触发率标定与 R8 探针）；`report.isolation` 的观测值可在阶段 1 使用期间零成本积累 |
| 阶段 3 · 层级展示 | `metadata.relpath`（**只做展示**）+ `metadata.class_code`（**语义字段，导入时落库**）+ 重导入**显式 merge** + `hierarchy()` 旁函数 + 路径纪律测试化 | 必改 `api/registry.py:150-156`（现在只 replace `name`）；`safe_name`/`display_names` 不动。**relpath 与 class_code 必须分开**：换根导入时 relpath 会变（`pet/x.hdr` → `plastic/pet/x.hdr`），按"第一段"解析类名会静默错位；class_code 一旦落库只有用户显式改才变。folder→code **必须支持一对多**（`pe` → `{PE, HDPE, LDPE}` 集合内竞争），`catalog/plastic.json` 21 个 code 里 PE/HDPE/LDPE 同属聚乙烯，一对一映射会把 HDPE 判成"folder 不符" |
| 阶段 4 · labelme 导出 | 双轨（模式 B 按类投影为默认 + masks 轨无损）+ `find_contours(0.5)` 半像素 + DP 简化 + IoU 回栅格自检 + 全分辨率底图 | 先用公司 exe 存一条 JSON 验 `description` 是否存在（VersionInfo 全空，无法按版本号推断） |
| 阶段 5 · 自动标注 | 多模板（类内 k-means）+ 背景零分布 z（R9）+ 三态判决 + folder 先验/一致性 QA | 须先过 R8 闸门；folder→code 走 `catalog/plastic.json`（21 个 code，**一对多**），且类 code 须先注册（否则 `_label_id` 抛 `LABEL_NOT_FOUND`）。**四条硬约束**：①**参考谱库只由 `source="manual"` 的区域聚合**——自动标注结果永不回流，否则错标抬高自身分数、确认偏误自增强，这是全套方案里最危险的一环；②**一致性 QA 用同 folder 内兄弟 cube 的相对离群**（该 cube 最好类 z 相对同 folder 中位数/MAD），不用绝对阈值——光面/哑光混装的多模态类会被绝对阈值整类误报；③**探针集的每块必须 `source="manual"` 且不经候选队列**——用"一键接受候选"标出来的探针集测的是匹配器自洽度，AUC 虚高后闸门放行、全线错标；④**单类 regime 仍保留 one-vs-rest 分数作为 reject 出口**，只放宽阈值不关闭——否则混入的异物/标签纸/瓶盖被静默赋成该 folder 类，且无任何信号。"无先验"（单文件导入 relpath 为空）是合法状态，不得报错 |

---

## 9. 实现后行号映射（阶段 1 落地后补，读现码前先看这里）

TASK-12 的插入使多个引用后移。下表是**卡内行号（改动前）→ 实现后**的对应；Rust 引用未变。

| 卡内引用（改动前） | 实现后 | 所在位置 |
|---|---|---|
| `engines/superpixels.py:206` | `:217` | `overlay_png` 的 `stride` |
| `engines/superpixels.py:250-255` | `:266`（参数校验）、`:285`（细分后块数校验） | `generate()` 内两处 `raise` |
| `annotation/session.py:138` / `:181` | `:141` / `:184` | 撤销 deque 两处 |
| `api/annotations.py:269-270` | `:290` | `working_view` 空态分支的 `blocks` |
| `api/annotations.py:311-316` | `:340` | `regions()` 的 `with_overlay=False` |
| `AnnotationCanvas.tsx:151` | `:198` | 指针守卫 |
| `AnnotationCanvas.tsx:181` | `:250` | `onPointerUp` fallthrough |
| `AnnotationWorkbench.tsx:310` | `:316` | 工具行 |

**一处口径修正**：卡原引 `AnnotationWorkbench.tsx:198-200` 为"进入标注页即 POST superpixels"，那实际是**刷新同步**分支；**初始恢复**在改动前 `:129-130`、改动后 `:135-136`。两条路径都已接入 id 图（`applySegmentation`），结论不变，但引用位置应改指初始恢复分支。

---

## 10. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-01 | 初版。五轮交叉验证定案后由备卡方落卡；R1 修正本 agent 前一轮"必须两跳"的误判；R4 将迁移方案挂起（与 TASK-04 §6.1 冲突）；F3 修正"方案 A 为主"的漏判——左键已被扩散种子占用，必须加工具位 |
| 2026-11-01 | 复核轮修正 4 处 B/C 级歧义：①§3.3 补 `blocks` 空态定义（三空数组、不得省键）；②§2.2 D2 澄清「左键拖拽=平移」是 click 工具内新增语义，现有状态机左键拖拽产出 `points` 不是平移；③§2.2 点名右键守卫 `AnnotationCanvas.tsx:151` 必须放行 `button === 2`，且 `contextmenu` 的 preventDefault 属既有（`:142`）非新增，`click` 分支须插在 `:181` fallthrough 之前；④§5-A1 补度量方法（数 `png_base64` 出现次数、与 `segments_png` 不混计、窗口不含初始加载）并标为硬门槛。另自纠 `deny_unknown_fields` 行号 `:51`→`:49`；§8 补阶段 2 启动前置 |
| 2026-11-01 | **执行方即停后补契约**（`mixed` 推不出 N）：§2.4 把 `mixed` 布尔改为 `label_count`（不同非 -1 label 值个数，含 -2），徽标文案「含 N 种标记」，并明写**不设 `mixed`**（同一事实双字段必漂移）；§3.3 同步字段与空态；§5-A5 补 60/40→2、60/20/20→3 的可验断言。另补 §2.1 **块数上限 65535** 校验（原 `n_segments` 只校验 ≥1，溢出会静默错位） |
| 2026-11-01 | **补齐"结论只在对话里、卡上还是旧文"的缺口**（复核方指出，属本 agent 同类错误第二次）：①R8 由「z≥3 且 margin≥1.5」改为**两级闸门 + sanity band**（闸门 0 距离比只能否决、闸门 1 留一 AUC≥0.95、接受占比 1%–60%）；②§8 阶段 3 改为 **relpath 只做展示 / `class_code` 落库为语义字段 / folder→code 一对多**（原设计"相对导入根"会在换根导入时类名静默错位）；③§8 阶段 5 补四条硬约束（**库只由 manual 喂养**、QA 用同 folder 相对离群、探针集 source=manual 且不经候选队列、单类 regime 保留 reject 出口）。另三处小修：§2.1 补 refine 后生成校验 `len(unique) <= 65536`；§3.4 错误码补 `INVALID_SUPERPIXEL_PARAMETERS`；续跑指令措辞收窄 |
| 2026-11-01 | **第二次即停后补三处未定口径**：①§2.3 **不设 Delete 键**（删除的对象是鼠标下的块，键盘无空间定位语义；右键承担删除、撤销承担纠错），Shift 明示为修饰键状态而非键位绑定；§4 补 `bindings.click = 'c'` 与 `commandNames` 缺键风险。②§2.4 补**取值规则四条**：留白不参与竞争（60% 留白+40% PET 显示 PET/40 而非"未标注 60%"）、并列按「≥0 优先于 -2，再取数值最小」、**纯度向下取整**（否则 799/800 会显示 100%，把"不纯"说成"纯"）、`purity` 分母恒为整块。③§5-A5 与测试行补对应可验断言 |
| 2026-11-01 | **修 §2.4 公式块与新规则的自相矛盾**（复核方发现，属同类错误第三次苗头：结论改了、9 行外的旧公式没动）：`block_label` 由"含 -1 留白"改为"非 -1 像素中占比最多；全为 -1 时 = -1"，`block_purity` 明写分母与向下取整，与规则 1–4 及 A5 断言对齐。另两处 C 级：§3.2 字段清单补 `blocks` 并说明无消费方受影响；§4 记录 `loadPreferences` 长度校验导致老用户自定义键位回退默认的已知副作用 |
| 2026-11-01 | **R10 依据栏重写**（第五次"错误结论进卡被交叉验证捞出"）：原依据隐含"PLS 读 `sample_spectrum` 表"，实测该表**只写不读**，建模真源是快照 `label_map.npz`（`dataset.py:150`）。结论（样本单位 = cube）不变，但补出一条更硬的推论：聚合**不分 类**，同 cube 多类标注会被平均成一条谱 → 探针集必须一个 cube 只标一个类 |
