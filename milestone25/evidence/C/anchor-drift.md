# C 段收口后的全部锚点变更上报

权威卡起点为 3091c13；本表与 C 段源码同一提交。备卡方应按 C 收口提交的 HEAD 独立重取后修卡，执行方未改任务卡。D 段尚未开工。

取数命令：PowerShell 执行 `& 'milestone25/evidence/C/anchor-commands.ps1'`；完整 grep -nH 原文见 [anchors-after-C.txt](E:/AI_Agent/milestone25/evidence/C/anchors-after-C.txt)。

| 卡内位置 / 事实 | C 前 → C 后 | 说明 |
|---|---|---|
| App.tsx 初始 records | 54 → 56 | 类型改为 CatalogRecord[]，冷启动只存摘要；详情打开时单独 get |
| App.tsx 换代清空 | 85 → 111 | 清空保留；重置与 Ready 自动加载在 113–119，旧代次与新请求由 controller 双重失效 |
| DatasetPanel.tsx 合并全库出口 | 48 → 已移除 | 本次批次接入移到 actions.ts:47 `callbacks.imported(result.datasets)`；catalog.ts 的 imported / refreshNames 仅更新当前可见集合，不用 all_datasets 扩大列表 |
| types.ts mergeRecords / Map / set / values | 50/51/52/53 → 51/52/53/54 | G2 所依赖的原函数与字段保留，G2 测试原样未改 |
| types.ts DatasetTransport | 37–48 → 38–49 | 五个 B 段新增方法当前在 42–46；SpectrumRegion 仍在 26 |
| api.ts Request / 目录对话框 | 6/44 → 7/45 | 新增 SMB→UNC 字符串归一 import；请求 op 未增加 |
| settings.rs destination | 46–52 → 69–79 | 完整 match 在 72–100，新增项目路径 GET/PUT 分支在 83/91；serde tag / enum 的 12/13 未漂移 |
| settings.rs 敏感字段向量分支 | 64–65 → 114–115 | 两个路径的错误响应保护另在 106–111，成功设置响应仍须把路径展示给 UI；原 key 的全响应保护保持 |
| settings-forward.ts 联合类型 / forward | 5/20 → 8/28 | 现为五 op，项目路径严格投影，不接收调用者 URL / port |
| api/settings.py make_router / prefix | 13/14 → 14/16 | make_router 改收 paths，调用独立项目设置安装函数 |
| api/settings.py GET llm / PUT llm / PUT key | 19/23/28 → 22/26/31 | 新项目 GET/PUT 在 api/project_paths.py:57/66；表定义在 :43 |
| OpenAPI llm / llm-key | 644/700 → 738/794 | 项目路径 GET/PUT 共用的 path item 在 :644；schema 快照断言未改 |

`app.py:54` 行号未漂移，注册实参依授权改为 `paths`；`:93/:110` 前缀白名单完全未改，未重复加入新路径。

卡 §3.5 前端方法行号范围也须统一校准：旧卡写新增方法在 39–43；`git show 3091c13:src/components/datasets/types.ts` 的实际五方法是 41–45，C 后是 42–46。§0.2 的旧完整类型范围 37–48 开工复核吻合。这一旧局部范围误注一并上报，执行方没有自行修卡。

其余全表项均复核未漂移：types.ts:15、schemas.py:36、display_names.test.ts:14；registry.py:121/177/199/231/258/262/219；datasets_dev.rs:51/52；database.py:10；paths.py:8/9/40/44/48/52/56；agent/state.py:166/173；llm.py:136；mat.py:52/88/190；session.py:387–389/405；modeling/migrations.py:68–102；projection_io.py:21/73/74；guard.py:329/333/337/341/345/349。§3.3 产物根锚点也未改。

以上是 C 段正常实现及授权接口扩展造成的收口上报，不能把旧卡中的「合并全库」「仅三 op」事实继续当作 D 段当前事实。请备卡方统一更新事实描述与所有重复引用后解除 D 段即停。
