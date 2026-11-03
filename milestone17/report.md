TASK-17 P0 已完成。依据 HEAD `2526ba0` 的任务卡执行；改动尚未提交。

1. 逐文件改动清单

| 文件 | 改动 |
|---|---|
| `src/shell/screens.ts` | 新增 11 值 Screen、10 项 NAV、11 项 SCREEN_TITLE、s04→s03 高亮映射；全文附后。 |
| `src/shell/AppShell.tsx` | 新增 196px 导航、顶栏、内容槽、原 AssistantPanel 槽；切屏重建内容槽以从顶部显示。S05 徽标仅空 data-badge。 |
| `src/shell/theme.css` | 仅变量骨架及新壳布局，内容 padding 18px；现有屏不引用这些变量。 |
| `src/App.tsx` | 默认 s03；四个真实屏 switch、七个统一占位屏；navigation effect 整段上移并保留 get/mergeRecords 和错误处理；S05/S07 直接接 App 数据，不传 navigation；仅 Ready 进壳；设置字面量保留。 |
| `src/components/datasets/DatasetPanel.tsx` | 删除三个提前 return、屏内伪路由状态及 navigation 消费；onOpen 回调化；使用 App 持有的 records，保留原列表和单波段预览逻辑。selectedRecord 同步当前选择；band/preview 仍可在卸载后重置。 |
| `src/style.css` | 原 main 的 flex/min-height/overflow/container-type 搬到 .p-body；独立错误页保留 24px 留白。 |
| `src/components/assistant/assistant.css` | 仅搬家配套：resize handle margin 改 0；面板水平 padding 对齐 18px。 |
| `src-tauri/tauri.conf.json` | 窗口 1280×820，最小 1180×720；CSP 不变。 |
| `src/shell/screens.test.ts` | 新增 3 个静态测试；无 DOM 渲染、无新依赖。 |
| `src/components/preprocess/panel.test.ts` | 原 S06 静态挂载断言由 DatasetPanel 同步到 App，并增加 onOpen('s06', record) 连线断言；用例名、数量与其余断言不变。 |

`milestone17/evidence/`：10 张逐屏截图、3 张引擎相位截图、设置弹窗截图；基线/最终 node 日志、build 日志、浏览器结构及尺寸 JSON、原 201 项保留对照、空 annotation diff；另有仅用于隔离验收的 browser_server.py 与 tauri-shim.js。这些文件不进入产品运行路径。

screens.ts 全文：

```ts
export type Screen = 's01'|'s02'|'s03'|'s04'|'s05'|'s06'|'s07'|'s08'|'s09'|'s10'|'s11';

export const NAV: { group: string; items: { screen: Screen; label: string; icon: string }[] }[] = [
  { group: '主入口', items: [{ screen: 's01', label: '智能助手', icon: '◈' }] },
  { group: '我的工作', items: [{ screen: 's02', label: '工作台', icon: '◧' }] },
  { group: '分析流程', items: [
    { screen: 's03', label: '数据', icon: '▤' },
    { screen: 's05', label: '标注', icon: '✎' },
    { screen: 's06', label: '预处理', icon: '⚗' },
    { screen: 's07', label: '建模', icon: '⊞' },
    { screen: 's08', label: '结果', icon: '◫' },
  ] },
  { group: '沉淀与复用', items: [
    { screen: 's09', label: '实验台账', icon: '☰' },
    { screen: 's10', label: '检索', icon: '⌕' },
  ] },
  { group: '本机', items: [{ screen: 's11', label: '设置与出域记录', icon: '⚙' }] },
];

export const SCREEN_TITLE: Record<Screen, string> = {
  s01: '智能助手', s02: '工作台', s03: '数据', s04: '数据查看器',
  s05: '标注', s06: '预处理', s07: '建模', s08: '结果',
  s09: '实验台账', s10: '检索', s11: '设置与出域记录',
};

export function navHighlight(screen: Screen): Screen {
  return screen === 's04' ? 's03' : screen;
}
```

2. A1–A8 验收

执行模式：本地 Windows/PowerShell；Node 原生测试、TypeScript/Vite 生产构建；浏览器使用该生产构建 + 独立 FastAPI TestClient 应用 + 本地 IPC 桥。两份 PE 原始 cube 只读，数据目录/数据库独立于正在使用的标图会话。真实屏直接挂载原组件、读取真实 API 响应；引擎相位与助手 workspace 事件是受控测试输入，不调用外部 LLM。style-src 'self' 保持一致，浏览器桥仅将 connect-src 调整为本地同源，生产 CSP 未改。未执行 Rust 编译或桌面打包。

| 项 | 结果 | 证据 |
|---|---|---|
| A1 | 通过 | 新增 3/3 静态测试：5 组；1/1/5/2/1；10 项唯一；NAV 无 s04；标题覆盖 11 屏；s04 高亮 s03。 |
| A2 | 通过 | 10 个导航项逐一点击，4 个真实根 + 6 个占位根；截图见第 4 项；s04 无导航入口，仅 A1 静态覆盖。 |
| A3 | 通过 | Failed 的 navCount=0、assistantCount=0；Starting 的 rootChildren=0；Stopping 的根仅一个 P[role=status]，文本“正在关闭”。 |
| A4 | 通过 | 1280×820：`.annotation-canvas-host.clientHeight = 166px`，computedHeight=165.594px；.p-body clientHeight=396px、padding=18px×2、contentHeight=360px；360×0.46=165.6。containerType=size、minHeight=0px。1180×720 下实测 160px；通过现有拖拽条的 Home 键缩小面板后为 166px。 |
| A5 | 通过 | git diff --stat src/components/annotation/ 的 stdout 为空；annotation-diff-stat.txt 为 0 字节。整个目录（含 CSS）零改动。 |
| A6 | 通过 | 原有 201 项全过 + 新增 3 项全过 = 204 / 0 fail。逐项名称对照确认原有 201 项均保留。无删改合并凑总数；S06 挂载断言同步原因见第 1 项。 |
| A7 | 通过 | npm run build：tsc --noEmit + Vite 均通过。 |
| A8 | 通过 | 顶栏设置打开原 LLM 设置 dialog；SettingsPanel.test.ts 原三条源码断言保持绿，该测试文件零改动。 |

附加冒烟：S05/S06 的非 stage 事件只换记录；preprocess/annotation 事件进入对应屏；S07 的普通 workspace 事件返回 s03；冷 App 记录缺失时确实调用 datasets.get，合并后返回数据屏出现 1 条记录；三个工作台返回数据屏后原 2 条记录均保留。导航宽 196px，data-badge 内容为空；依赖仍为 4 项。浏览器控制台无 error/warn，桥接 IPC 返回状态全部小于 400，get_draft 读取全部返回 200。

S05/S06 无可用记录时显示选择数据提示及返回入口；已有记录时导航沿用 workspace 当前记录、selected 或首条已登记记录。未创建示例 record。

3. A5 原始命令输出

```text
PS E:\AI_Agent> git diff --stat src/components/annotation/
```

命令 stdout 为空（无文件条目、无统计行）。

4. 浏览器逐屏截图

全部为最终构建的 1280×820 JPEG，存 `E:/AI_Agent/milestone17/evidence/`。S04 不可达，无 S04 浏览器截图。

| 屏 | 内容 | 截图 |
|---|---|---|
| s01 | 智能助手（占位） | [s01.jpg](E:/AI_Agent/milestone17/evidence/s01.jpg) |
| s02 | 工作台（占位） | [s02.jpg](E:/AI_Agent/milestone17/evidence/s02.jpg) |
| s03 | 数据集管理（真实） | [s03.jpg](E:/AI_Agent/milestone17/evidence/s03.jpg) |
| s05 | 标注工作台（真实） | [s05.jpg](E:/AI_Agent/milestone17/evidence/s05.jpg) |
| s06 | 预处理工作台（真实） | [s06.jpg](E:/AI_Agent/milestone17/evidence/s06.jpg) |
| s07 | PLS 回归工作台（真实） | [s07.jpg](E:/AI_Agent/milestone17/evidence/s07.jpg) |
| s08 | 结果（占位） | [s08.jpg](E:/AI_Agent/milestone17/evidence/s08.jpg) |
| s09 | 实验台账（占位） | [s09.jpg](E:/AI_Agent/milestone17/evidence/s09.jpg) |
| s10 | 检索（占位） | [s10.jpg](E:/AI_Agent/milestone17/evidence/s10.jpg) |
| s11 | 设置与出域记录（占位） | [s11.jpg](E:/AI_Agent/milestone17/evidence/s11.jpg) |

5. 行号漂移清单

无。开工时已复核：App main 101–129 / AssistantPanel 130–146；DatasetPanel navigation effect 67–91 / 提前 return 135–140 / 根标签 142；style.css main container-type 第 4 行；tauri.conf.json app.windows[0] 第 13 行。另已复核现有 S05/S06/S07/助手根、annotation.css 第 47 行和 SettingsPanel.test.ts 第 185–187 行。

6. 未决问题

无。上一轮两处冲突已由 2526ba0 修正：A6 按 201+N、Stopping 留在壳外。本次未新增依赖，未改 Rust 或后端代码，未触碰 annotation 目录。DatasetPanel 卸载后的 band/preview 便利态重置沿用卡中已接受差异。

![S05 画布](E:/AI_Agent/milestone17/evidence/s05.jpg)
