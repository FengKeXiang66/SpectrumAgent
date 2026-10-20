# #04 10.1 自验回执

事实源：仓库根目录 `TASK-04-标注L1.md`，R13，503 行。未修改任务卡内容。

## 执行模式与测试

- 命令：`E:\AI_Agent\.venv\Scripts\python.exe -m pytest src-python/tests backend/tests -q`
- 默认 pytest 执行模式，串行全收集，无自定义 pytest 配置或环境覆盖。
- 202 passed；其中 annotation 新增 58 项，既有回归 144 项；无失败、无跳过。
- 10.1 存储和 HTTP 验收使用真实 SQLite 临时库、原生 FastAPI TestClient；外键连接探针仅包装真实连接，不替换数据库实现。
- 输出见 `pytest.txt`。10 条第三方弃用警告来自 Starlette/httpx 与 spectral/NumPy；未安装或变更依赖。
- 未运行桌面、VM 或冻结程序人工冒烟；该项由科祥执行。

## 开工令八项与 R13 自验

1. 通过：旧四列登记表预置既有行后，完整 create_app/lifespan 启动两次；项目/schema/四标签及既有 payload、ID 不变，project_id 加列并回填。迁移后新导入也写入默认项目。证据：`test_two_startups_backfill_existing_registry_without_replacing_payload`、`test_every_application_connection_enables_foreign_keys`。
2. 通过：真实表直接 INSERT 验证 BG=0、普通 1–9、非背景=0 拒绝、NULL 允许多条、10 拒绝、重复 UNIQUE 拒绝；HTTP 同时验证越界和重复返回 422 字段错误。证据：`test_shortcut_table_check`、`test_shortcut_unique_and_multiple_nulls`、`test_custom_invalid_inputs_are_field_errors`。
3. 通过：GET /api/v1/catalog/plastic 返回 21 条，含 PS=聚苯乙烯、PVC=聚氯乙烯；目录查询和项目选用均不改目录。证据：`test_catalog_readonly_and_null_shortcuts_above_nine_classes`、`test_catalog_colors_and_names_match_card`。
4. 通过：产品唯一 sqlite3.connect 入口在 backend/database.py，建立连接后立即 PRAGMA foreign_keys=ON；foundation lifespan、Registry、LabelStore 均共用它。连接探针检查启动、查询、导入各连接实际开启；annotation.version_id 悬空写入触发 FK，params 缺失触发 NOT NULL。证据：`test_every_application_connection_enables_foreign_keys`、`test_version_params_and_foreign_keys`。
5. 通过：仅创建 annotation DDL，无产品 annotation 写入路径；启动、导入和三个 labels POST 路径后 scene count 均为 0。DDL 保留 scene 枚举、每 label 每版本一条及操作历史不落库的原卡注释；DDL 全文与卡逐字比较。超像素/版本保存/校验尚非 10.1 范围，未声称已验。
6. 通过：上列默认参数 pytest 共 202 项通过，其中新阶段测试 58 项。无运行分割引擎，不涉及 PCA 特征图、原始立方体物化或 RSS 指标。
7. 通过：三个 POST body 各返回 201；目录返回行数组，自定义返回单行，schema 返回 schema 行。混用、缺必填、缺 color_hex、非法 hex、重复 code/快捷键、越界快捷键均返回 422，DataError 信封含字段级 message；目录批量失败整体回滚。
8. 通过：plastic.json 后 18 条色值逐点对比 §4.4 卡表，并用 HLS 规则独立复算全部吻合；PE/PET/PP 与 §4.3 一致。PBT/PP 已知近色保持卡值，未进行 10.6 提示开发。
9. R13 通过：schema_id 定位与 sort_order 各为一个函数，种子/目录/自定义共用。预置四标签路径与 sort 与 §4.3 一致；目录生成材料/塑料/<code>，倒序添加 PVC/PS 仍 sort=5/4；自定义 max+1（含空项目取 1、并发顺序不重复）；第一段无匹配或匹配非 enum schema 均 422，schema.tree_path 含 / 拒绝，body 带 schema_id/sort_order 拒绝。

## 范围与完整性

- 新增业务端点仅 GET projects、GET labels、POST labels、GET catalog/plastic；既有 OpenAPI 路径内容不变，快照仅增加上述端点及请求模型。
- 无项目 CRUD、分割/扩散/会话/校验、Rust IPC 或前端改动，无自动赋标。
- 不修改任何 lock；不安装依赖、不下载权重、不打 tag、不推远端、不操作 Release。
- 固定种子只读，SHA256：`388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`。
- R13 任务卡 SHA256：`705ED8230F773559A6A1295BEE21E568071D0A6078A0B0CA64CDF53D180018D9`。
- 根目录两份公司文档及 seeds_20.json 不纳入本次提交。

问题/口径疑问：无未决项。10.1 完成，等待科祥复核；10.2 仅在收到指令后启动。
