# TASK-16 标注工作台简化（自动选标签 + 移除 MAT 入口）

> 备卡方：本 agent ｜ 执行：codex ｜ 验收：独立复核
> **基线**：Python 1484 passed / 2 skipped（B1/B2 无 cv2）｜ Node 191 通过 / 1 既有失败（`panel.test.ts:52`）｜ cargo 89 ｜ clippy 18 处既有（`models.rs`）。开工前复测并在回报中注明执行模式。
> 本卡性质：**B 段是前端交互增强，C 段是 UI 减法**。后端零改动、数据库零改动。
> 口径基线：2026-11-03 命名口径定案（文件夹名 = 类码，不做 `PE_W0`）。

---

## 0. 背景

### 0.1 命名口径（已定案）

```
文件夹 pe（小写）→ 大小写不敏感匹配标签 code → 自动选中 PE → JSON label = "PE"
```

- JSON 里的 `label` 就是**类码**（`PE` / `PET` / `PP`），与标签面板显示一致；
- 文件夹名的大小写差异由匹配规则归一，**不需要任何转换配置**；
- 新类别文件夹（如 `abs/`）→ 弹提示 → 从 catalog 预填创建 `ABS` → JSON `label = "ABS"`，同样是"按文件夹命名"；
- **公司 `W0` 后缀问题正式关闭**。映射机制保留（`projection.json`），默认恒等；万一公司脚本拒收 `PE`，改一行配置即可恢复兼容，**不需要改代码、不需要重新标注**（内部数据与映射无关，重新保存即重投影）。

### 0.2 为什么移除 MAT 入口

口径 3/4：标注完成 = labelme JSON 落盘（"保存并聚合"即完成）；预训练 MAT 是后续**离线独立步骤**（TASK-15）。标注者不该看到一个指向"当前流程里不存在"的入口。

### 0.3 B 的收益比"省一次点击"大

`selectedId` 初始是 `null`（`AnnotationWorkbench.tsx:57`），而"确认选中候选 / 区域"按钮在 `!selectedId` 时禁用（`:381`），`edit()` 里也有 `!selectedId` 守卫（`:227`）。也就是说**现在进图后必须先去左侧面板选一次标签，否则点选和确认都用不了**。

B 把这道前置门槛直接消掉：进 `pet/` 的图，标签已经选好，点下去就能标。

---

## 1. 范围裁定

### 1.1 B 段 · 自动选标签（P0）

| # | 功能 |
|---|---|
| B-1 | 进图 / 切图、标签列表加载完成后，按文件夹名自动选中对应标签 |
| B-2 | 未命中时弹提示，可从 catalog 一键创建并选中 |
| B-3 | 三条守卫：labels 未加载不触发 / 每 cube 只弹一次 / 不抢用户已选 |

### 1.2 C 段 · 移除 MAT 入口（P0）

| # | 功能 |
|---|---|
| C-1 | 移除"确认版本并生成训练 MAT"按钮与其确认卡渲染 |
| C-2 | 后端 `confirm` 路由保留，标记 deprecated |

### 1.3 不做（明确禁止）

- ❌ 模糊 / 前缀匹配（`pe_0602` 宁可弹提示也不猜成 `PE`——猜错整图标错类）
- ❌ 静默新建标签（必须弹提示 + 用户确认）
- ❌ 改后端、删后端 `confirm` 路由、改 `drafts` 任何逻辑
- ❌ 动 `label_map` 三态 / `regions[]` / 快照格式 / 版本语义（FR-E05 是 P0）
- ❌ 动"保存并聚合"、默认覆写勾选、覆写弹窗三行文案、版本记录折叠列表、撤销 30 步
- ❌ 自动切换**工具**（只自动选标签，不自动切到"点选"工具）

---

## 2. 口径钉死（照抄，不得自行发挥）

### 2.1 匹配规则

- **来源**：`record.dataset.header_path` 的父目录名。该字段已在前端类型里（`src/components/datasets/types.ts:9` `header_path: string`），无需后端配合。
- **必须同时处理 `\` 和 `/`**：Windows 路径是反斜杠（`E:\高光谱数据集\plastic\pet\xxx.hdr`）。只按 `/` 切会取到整串路径，永远匹配不上。
- **大小写不敏感精确匹配** `label.code`，**排除 `is_background`**（`Label.is_background` 是 number，`0/1`）。
- **除 `trim` 外不做任何规范化**：不拆下划线、不去数字后缀、不做同义词。
- 匹配到多个（理论上不会，code 唯一）→ 取 `orderedLabels` 里的第一个，不报错。

### 2.2 三条守卫（缺一条就出怪行为）

1. **effect 必须 gate 在 `labels.length > 0`。** `labels` 来自 `orderedLabels(schemas)`，而 `schemas` 来自 `api.labels(project_id)`，`project_id` 又来自 `working`——整条是异步链。若 effect 在 labels 加载前跑，匹配必然落空 → **每张图都弹"新建标签"**。这是本卡最可能翻车的一处。
   **依赖数组必须是 `[id, schemas]`**，两端都不能省：
   - 只写 `[id]` → `addLabel` 成功后会重拉 `schemas`，但 effect 不再跑，**新建的标签不会被自动选中**，B2 会挂在"创建成功但没选中"；
   - 写 `[labels]` → `orderedLabels` 每次渲染都产新数组（`flatMap` + `sort`），effect 每次渲染都触发，靠守卫兜底只是白烧 CPU；
   - `schemas` 的引用只在重拉时变，正好对上"加载完成"和"新建完成"两个时点。
2. **每个 cube 只弹一次。** 用 `useRef<Set<string>>` 或 `useRef<string|null>` 记已弹过的 cube id；否则每次重渲染都弹一遍。
3. **不抢用户已选。** 用**独立的** `labelTouched` ref（**不要复用 TASK-12b 的 `overwriteTouched`**——两者生命周期不同，共用一个 ref 会让"改选标签"意外影响"覆写勾选"）。用户手动改选后，刷新 / 保存 / 覆写都不得抢回；切图时重置。

### 2.3 未命中时的提示与 catalog 预填

提示文案：

```
检测到文件夹「abs」尚无对应标签，是否新建？
```

- **catalog 命中**（大小写不敏感，`catalog/plastic.json` 21 个 code）→ 确认按钮调
  `addLabel({ project_id, from_catalog: 'plastic', codes: [CODE] })`
  （`api.ts:29` 已有此分支，后端自动填 `name` / `color_hex` / `tree_path`，**前端不要自己拼这三个字段**）；
  创建成功后**立即选中**新标签，并写 `labelTouched.current = true`。
- **catalog 未命中**（如文件夹叫 `2026-10-01`）→ 只提示"该名称不在塑料目录中，请到左侧面板手动新建"，**不给一键新建按钮**——避免用户手滑建出一堆脏标签。
- **严禁静默新建**：任何情况下都不能在没有用户点击的情况下调用 `addLabel`。

### 2.4 单文件导入 = 无匹配 = 弹提示（这是设计，不是 bug）

用户直接选一个 `.hdr` 时，父目录可能是任意路径（`E:\临时\`），必然匹配不上。此时走 §2.3 的提示路径，用户点"取消"即可，不影响标注。

**卡里写明这一条，是为了防止实现者把它当 bug 去"修"**（比如加个"匹配不上就默认选第一个"——那等于静默错标）。

### 2.5 C 段的边界

移除：

| 位置 | 内容 |
|---|---|
| `AnnotationWorkbench.tsx:398` | `确认版本并生成训练 MAT` 按钮 |
| `:399` 起 | `{confirmVersion && <ConfirmCard ... />}` 渲染块 |
| `:69` | `confirmVersion` 状态 |
| `:13` | `import ConfirmCard from './ConfirmCard.ts'`（若不再引用） |

**`ConfirmCard.ts` 文件本身不删**——TASK-15 可能复用其"2GB 二次确认"的交互形态；只是标注工作台不再引用它。

后端保留：

- `POST /annotations/{cube_id}/draft/confirm` 路由、2GB 闸、重叠检查**全部不动**；
- 但要在路由处加一行注释：`# TASK-16：UI 入口已移除，保留供审计与未来复用；TASK-15 不走此路径（它读 exports/ 下的 JSON）。`

**不要写"TASK-15 复用此路由"**——TASK-15 的输入是 `exports/<cube_id>/<stem>.json` + 源 HDR，不经过 `drafts.confirm`。写错了将来会有人去找一个不存在的依赖。

**连带后果：前端 `drafts.confirm` 变成死代码。** `draft-api.ts:30` 定义它，唯一调用方是 ConfirmCard 的 onApprove（在 Workbench 里）；C1 删完后前端再无调用方，而 `confirm.test.ts:88` 还专门断言助手侧不调它。保留（与后端路由对应），但在 `draft-api.ts` 该行加注释：`// TASK-16 后前端已无调用方；保留以对应后端 deprecated 路由。`

### 2.6 过时测试的授权同步（confirm.test.ts:80）

`confirm.test.ts:80` 的 `REST and HUMAN_CHECK use the same card and pending-call revision stays server-owned` 断言了：

```ts
:83  for (const source of [rest, agent]) assert.match(source, /import ConfirmCard from/)
:84  assert.match(rest, /drafts.confirm\(id, \{ revision: view.revision/)
```

这两条与 C1 正面冲突（C1 做完必红）。**允许只改这一项测试**，方向是"授权同步非弱化"：

- `rest`（AnnotationWorkbench）侧：`import ConfirmCard`、`drafts.confirm` 改为 `assert.doesNotMatch`；
- **新增** `assert.doesNotMatch(rest, /confirmVersion/)` —— 锁死删除清单第三项（状态残留是最典型的漏删）；
- **新增** `assert.doesNotMatch(rest, /确认版本并生成训练 MAT/)` —— 锁死删除清单第一项（按钮文案；否则将来加个同文案按钮也没人发现）；
- `agent`（AssistantBar）侧与 `drafts.confirm` 服务端 revision 断言：**原样保留**（助手 HITL 仍用 ConfirmCard，§2.5 本就保留它）；
- **测试名必须改**（如 `only HUMAN_CHECK uses the card...`）——改完还叫"use the same card"就是名字说谎。

四项删除清单（按钮 / 渲染块 / 状态 / import）对四条 `doesNotMatch`，一条不漏。

---

## 3. 改动清单（逐文件，不要扩大范围）

| 文件 | 改动 |
|---|---|
| `src/components/annotation/folder-label.ts`（新增） | 纯函数 `folderName(headerPath): string \| null`（同时处理 `\` `/`）、`matchLabel(labels, folder): Label \| null`（大小写不敏感、排除 `is_background`）、`catalogCode(catalog, folder): string \| null` |
| `src/components/annotation/folder-label.test.ts`（新增） | §4 B1–B5 的纯函数部分 |
| `src/components/annotation/AnnotationWorkbench.tsx` | 新增 `labelTouched` ref + `askedFolders` ref；自动选中 effect（gate 在 `labels.length`）；未命中提示 UI；删除 MAT 按钮 / `ConfirmCard` 渲染 / `confirmVersion` 状态 |
| `src/components/annotation/annotation.css` | 提示条样式（若现有 `.annotation-warning` 够用则不动） |
| `src-python/spectrumagent/api/annotations.py` | **仅一行注释**（§2.5 的 deprecated 说明），逻辑零改动 |
| `src/components/annotation/confirm.test.ts` | **仅改 `:80` 那一项测试**（详见 §2.6）；其余测试一行不动 |

**Rust：零改动。** 若发现需要改，先停手回报。

---

## 4. 验收标准

### B 段

| # | 断言 | 判据 |
|---|---|---|
| B1 | **按文件夹自动选中** | 进 `plastic/pet/` 的图 → `selectedId` 为 PET；`plastic/pe/` → PE（**大小写不敏感**：`Pe` / `PE` / `pe` 都命中）；进图后"确认选中候选"按钮**立即可用**（不再因 `!selectedId` 禁用） |
| B2 | **未命中弹提示 + catalog 预填 + 创建后自动选中** | 进 `abs/` → 弹提示含文件夹名；确认后标签 `ABS` 创建成功**并被自动选中**（依赖 `[id, schemas]` 的二次触发，见 §2.2-1），`name`/`color_hex` 与 `catalog/plastic.json` 一致；取消后**不新建**、`selectedId` 保持原值 |
| B3 | **不抢用户已选** | 进 `pet/` 自动选中 PET → 手动改选 PP → 保存（含覆写）→ 仍是 PP；撤销一步后仍是 PP |
| B4 | **切图重置** | A 图手动改选 PP → 切到 B 图（`pet/`）→ B 图自动选中 PET |
| B5 | **单文件导入不崩** | `header_path` 父目录无匹配（如 `E:\临时\`）→ 弹提示 → 取消 → 无报错、不新建、`selectedId` 不变 |
| B6 | **路径分隔符** | `folderName` 单测覆盖 `E:\a\pet\x.hdr` 与 `E:/a/pet/x.hdr` 两种写法，都返回 `pet` |

### C 段

| # | 断言 | 判据 |
|---|---|---|
| C1 | **入口消失** | 标注工作台页面上不存在"确认版本并生成训练 MAT"按钮；`confirmVersion` 状态与 `ConfirmCard` 渲染均已移除 |
| C2 | **保存链路不变** | 保存并聚合 / 默认覆写勾选 / 覆写弹窗三行文案 / 版本记录列表 / 撤销 30 步，全部与改前一致（逐项点一遍） |
| C3 | **后端仍可达** | 直接调 `POST /annotations/{id}/draft/confirm` 仍返回 200（路由未删），且源码含 §2.5 的 deprecated 注释 |
| C4 | **过时测试已同步** | `confirm.test.ts:80` 四条 `doesNotMatch` 全在（import / drafts.confirm / confirmVersion / 按钮文案），agent 侧断言原样保留，测试名已改；其余测试一行未动 |

### 全局

| # | 断言 |
|---|---|
| G1 | Python 1484 passed / 2 skipped 不减少；Node 191 通过 / 1 既有失败（`panel.test.ts:52`）不变；`npm run build`（含 `tsc --noEmit`）通过 |
| G2 | 8 个 assistant 在途文件未被触碰；`src-tauri/` 零条目 |

---

## 5. 红线

1. 不做模糊 / 前缀匹配；不静默新建标签（§2.1、§2.3）。
2. effect 必须 gate 在 `labels.length > 0`（§2.2-1）。
3. `labelTouched` 必须独立于 `overwriteTouched`（§2.2-3）。
4. 不动保存链路、版本语义、`label_map` / `regions[]` / 快照。
5. 不删后端 `confirm` 路由；不写"TASK-15 复用此路由"（§2.5）。
6. 行号与实物不符须在回报中显式说明。
7. 卡未覆盖的设计歧义，停手回报，不自行拍板。

---

## 6. 决策记录

| R | 决策 | 依据 |
|---|---|---|
| R1 | 文件夹名 → 类码，JSON `label` = 类码，不做 `PE_W0` | 2026-11-03 用户定案；映射机制保留、默认恒等，公司若拒收改一行配置即可 |
| R2 | 只做精确匹配，不做模糊 | `pe_0602` 猜成 `PE` 会让整图标错类，且无声 |
| R3 | 未命中只提示、不静默新建；catalog 未命中不给一键新建 | 防止手滑建出脏标签 |
| R4 | 移除 MAT 入口但保留后端路由 | 口径 3/4：标注完成 = JSON 落盘；MAT 是离线步骤。删路由要改一堆测试，收益不抵 |
| R5 | `labelTouched` 独立于 `overwriteTouched` | 两者生命周期不同，共用会让"改选标签"意外影响"覆写勾选" |

---

## 7. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-03 | 初版。B/C 合卡但验收分两段（B1–B6 / C1–C3），避免"只测了简单的那个"；§2.2 三条守卫按复核意见钉死；§2.5 把"TASK-15 复用"改为"deprecated，TASK-15 不走此路径" |
| 2026-11-03 | **补 §2.6 + C4**：C 段删除清单原只列了四处代码位置，**漏扫了断言这些位置存在的测试**（`confirm.test.ts:80` 的 `import ConfirmCard` 与 `drafts.confirm` 断言）。属本卡的系统性缺口，非执行方理解问题。处理：授权同步该项测试（非弱化），四项删除清单对四条 `doesNotMatch`，测试必须改名。**此后规矩：删代码类任务的卡，§4 必须预先跑 `grep -rln "<被删符号>" src/ --include=*.test.ts`** |
