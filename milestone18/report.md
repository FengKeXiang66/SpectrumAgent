TASK-18 P1 已完成，未提交。AssistantBar 选择“保留消息渲染体”：会话态和执行链路抽到 useSession，中栏的消息流、PlanCard、ConfirmCard、执行日志、完整输入表单仍在 AssistantBar；左栏、右栏由 S01 承接。

1. 逐文件改动清单

| 文件 | 改动 |
|---|---|
| `src/components/assistant/useSession.ts`（新增） | 唯一 reducer、草稿、runtime、sessionId、inFlight、请求链路和四个 App 回调。保留原引擎代次重置语义，切屏不重置；过期请求不写入新会话。 |
| `src/components/assistant/Composer.tsx`（新增） | 单行上下文、输入、展开、发送；原常驻对话条 aria-label 保留；局部 Ctrl+Enter 发送，Ctrl+K 保留焦点。 |
| `src/screens/S01.tsx`（新增） | 左 172 / 中自适应 / 右 236；开始新对话与上下文区域搬入；冒烟表单、状态行和真实 metrics 移入 S01；中栏输入行保留。 |
| `src/components/assistant/AssistantBar.tsx` | 保留消息渲染体，改为消费传入 session；输入 form 与 ConfirmCard renderCheck 块逐字保留；左栏/右栏内容搬到 S01。 |
| `src/App.tsx` | 只调用一次 useSession，两形态接收同一 session；S01 真屏挂载；assistant 槽在 s01 条件渲染 null；全局两键转归 composer。 |
| `src/components/assistant/assistant.css` | 删除面板/把手规则；新增恰好 6 个布局类；无主题变量引用。 |
| `src/components/assistant/session-shell.test.ts`（新增） | 4 个静态契约测试，无 DOM 渲染与新依赖。 |
| `src/components/annotation/working.test.ts` | 按 §2.7 仅同步两行：App 匹配 Composer；被读文件改 Composer.tsx。footer 常驻对话条断言原样保留。 |
| `src/components/assistant/AssistantPanel.tsx` | 删除。 |
| `src/components/assistant/panel-height.ts` | 删除。 |
| `src/components/assistant/panel-height.test.ts` | 删除，其 3 项用例退场。 |

`src/shell/AppShell.tsx`、`.p-body` 所在 style.css、theme.css、tauri.conf.json、package.json/package-lock.json 均零改动。后端与 Rust 零改动。`milestone18/evidence/` 存测试日志、浏览器实测 JSON、IPC 记录、截图及隔离验收桥，均不进入产品运行路径。

2. A1–A10

执行模式：单代理，本地 Windows/PowerShell；Node 原生测试；TypeScript/Vite 生产构建；浏览器使用生产前端 + 独立 FastAPI TestClient + 本地 Tauri IPC 桥。数据读取两份真实 PE cube；smoke 为后端真实计算；agent 的回复/计划/确认事件为受控验收输入，不调用外部 LLM。数据目录/数据库独立于用户标图会话。浏览器桥仅将 connect-src 设为本地同源，style-src 'self' 保持；生产 CSP 未改。未运行 Rust 构建或桌面打包。

| 验收 | 结果与证据 |
|---|---|
| A1 单源会话 | 通过：App 的 useSession( 恰 1 次；Composer 与 S01 接收同一 session。双向草稿保留；同一 session ID 完成 composer、中栏消息、计划、确认；只有开始新对话后下一条消息才创建新 ID。 |
| A2 单行/隐藏 | 通过：全部 9 个可达非 s01 屏 clientHeight=57px（<80）；S01 中 Composer DOM 数量=0，按 App 条件渲染隐藏。中栏聊天输入可见。 |
| A3 快捷键 | 通过：9 个非 s01 导航屏 Ctrl+K 均聚焦 composer-message；composer 内 Ctrl+K 保持草稿和焦点；内/外 Ctrl+Enter 均提交一次，未触发冒烟；S01 两键未发送，草稿保持。 |
| A4 冒烟 | 通过：S01 冒烟测试表单执行真实 /smoke，显示 bands=8、shape=[8,8,8]、nan_ratio=0 等 metrics；placeholder 为“运行冒烟测试”，不含快捷键。 |
| A5 三栏 | 通过：1280×820 下左 172px、中 616px、右 236px。左栏只有当前会话和开始新对话两个子节点。 |
| A6 退场/基线 | 通过：开工 204/204/0，删除 panel-height 三项后保留基线 201/201/0；新增静态 4/4/0；全量 205/205/0。用例名称逐项对照，仅退休指定三项，其他 201 项均保留。 |
| A7 源码断言 | 通过：working 授权同步；confirm、SettingsPanel、panel.test.ts 均零改动且测试通过；详见第 4 项。 |
| A8 不换皮 | 通过：S01.tsx / Composer.tsx / assistant.css 的 var(--brand 及其他主题变量引用均为 0；新增布局类恰 6 个。 |
| A9 画布 | 通过：`.annotation-canvas-host.clientHeight = 305px`（>100）；computedHeight=304.51px；.p-body 内容高 662px，46cqh≈304.52px；container-type=size、min-height=0px。 |
| A10 构建 | 通过：npm run build，含 tsc --noEmit。 |

附加冒烟：PlanCard 批准、执行日志、ConfirmCard 读真实草稿与确认续接、待确认时禁止开始新对话、确认态跨形态保留、错误呈现、开始新对话清空消息/草稿/错误而保留当前数据，以及请求未结束时切换到 S01 后响应仍归同一会话，均通过。浏览器控制台无 error/warn，IPC 无失败。

3. 退场文件与测试数

- AssistantPanel.tsx：已删除。
- panel-height.ts：已删除。
- panel-height.test.ts：已删除，恰 3 项退休。
- assistant.css 的 assistant-panel* / assistant-resize-handle* 规则：已删除。
- 保留基线：201 tests / 201 pass / 0 fail。
- 新增静态：4 tests / 4 pass / 0 fail。
- 全量：205 tests / 205 pass / 0 fail。

新增用例逐条名称：

- `P1 A1 App owns one session shared by Composer and S01; renderers have no reducer`
- `P1 A2 A3 composer hiding and global shortcuts leave S01 input independent`
- `P1 A4 A5 smoke stays in S01 and the three columns use current session context`
- `P1 A6 A8 retired panel files and rules are absent with only six new layout classes`

4. 源码断言四处逐一核对

| 位置 | 处理与核对 |
|---|---|
| working.test.ts:94–97 | 仅两行授权同步：匹配 `<Composer`，读取 Composer.tsx；footer 的 `aria-label="常驻对话条"` 断言不变。 |
| confirm.test.ts:80–90 | 文件零改动。AssistantBar 仍保留 ConfirmCard import、key=state.pending.check_id、approve decision 字面量与原 renderCheck 块；同强度通过。 |
| SettingsPanel.test.ts:185–187 | 文件零改动；App import、设置按钮、settingsOpen && Ready 渲染块三段字面量均保留，测试通过。 |
| preprocess/panel.test.ts:61–62 | **未触碰**；App 的 PreprocessPanel 与 DatasetPanel 的 onOpen('s06', record) 原连接保留，测试通过。 |

shortcuts.test.ts:60 同样零改动，常驻对话条术语保持。标注目录生产文件与 CSS 零 diff；整个 annotation 目录的唯一差异是明确授权的 working.test.ts 两行调整。原始 `git diff --stat src/components/annotation/`：

```text
 src/components/annotation/working.test.ts | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
```

排除该授权测试后的 annotation diff-stat 输出为空（annotation-production-diff-stat.txt 为 0 字节）。

5. 截图

全部存于 `E:/AI_Agent/milestone18/evidence/`，1280×820。

| 内容 | 文件 |
|---|---|
| S01 三栏，聊天输入行保留 | [s01-three-columns.jpg](E:/AI_Agent/milestone18/evidence/s01-three-columns.jpg) |
| 非 s01 屏的单行 composer | [composer-s03.jpg](E:/AI_Agent/milestone18/evidence/composer-s03.jpg) |
| s01 屏 composer 隐藏 | [s01-composer-hidden.jpg](E:/AI_Agent/milestone18/evidence/s01-composer-hidden.jpg) |
| Ctrl+K 聚焦态 | [ctrl-k-focus.jpg](E:/AI_Agent/milestone18/evidence/ctrl-k-focus.jpg) |
| 真实冒烟结果 | [s01-smoke-result.jpg](E:/AI_Agent/milestone18/evidence/s01-smoke-result.jpg) |
| S05 画布回归 | [s05-canvas.jpg](E:/AI_Agent/milestone18/evidence/s05-canvas.jpg) |

6. 行号漂移与口径

行号漂移清单：无。已复核卡 §0 全部行号；开工 HEAD 的代码相对 809f76d 无 src/、src-tauri/ 提交差异，工作区干净，204 项通过。

口径冲突点：卡 §1.2/§5 的 annotation 目录通用禁改条款，与 §1.1/§2.7 对 working.test.ts 的明确同步授权并列；本批按具体授权只调整该测试两行，其余标注文件（含 ConfirmCard.ts、annotation.css）全部零改动。AssistantBar 保留渲染体，因此 confirm.test.ts 无需同步。上一轮 HEAD 闸门冲突已由新版卡消除。

未决问题：无。S01/Composer 共用会话，保留原消息执行语义；没有新增依赖、假历史或出域情况卡。

![S01 三栏](E:/AI_Agent/milestone18/evidence/s01-three-columns.jpg)
