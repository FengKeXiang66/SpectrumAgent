# TASK-25 C：项目路径设置契约待裁定

状态：只读核验与开工基线进行中；未改生产源码、未改任务卡。
权威卡：1383f3e；生产源码基点：d8bb622。

原始任务提示词「二、即停条款与范围红线」明确要求：
> 要改接口契约先停下问。

卡 §4.5 要求两个路径可保存为项目默认并在 S11 展示；现有设置接口仅支持 LLM，无法持久保存这两个字段。

## 现物证据

- src-python/spectrumagent/api/settings.py：现有 GET /llm、PUT /llm、PUT /llm/key。
- src-tauri/src/settings.rs：SettingsRequest 只有 GetLlm / PutLlm / PutKey，deny_unknown_fields。
- src/components/settings/settings-forward.ts：SettingsRequest 与上述三个 op 对应。
- src-python/spectrumagent/annotation/migrations.py：阶段一只有默认项目，已有 project 表及 default_project_id()。
- 现有 GET /api/v1/projects 可取得默认项目 id，无需新增项目创建或切换能力。

## 建议补卡授权（未实施）

1. GET /api/v1/settings/projects/{project_id}/paths。
2. PUT 同路径；严格请求体仅 source_path、output_root 两个字符串。
3. GET / PUT 返回 project_id、source_path、output_root、artifacts_root（实际 paths.root）、output_enabled=false；未保存的两个配置值用空字符串表示。
4. 独立 project_path_settings 表（project_id 主键并引用 project、source_path、output_root、updated_at）；不改 dataset_registry.payload，不并入 cube 删除链。
5. TS SettingsRequest 与 Rust SettingsRequest 同步新增 get_project_paths / put_project_paths 两个严格 op；project_id 校验 UUID，固定目的路径，沿用身份校验与错误结构。
6. 保存仅更新本地数据库，走既有数据库守卫，不创建/读写源目录或所配置输出目录，不启用输出根、不验证 NAS 连通性。
7. smb:// 归一 UNC 后再提交；拒绝含凭据 URL，不将配置路径送入 LLM、工具出参或普通日志。
8. 用现有默认项目 id 保存；S03 独立输入和浏览、查询参数预填；S11 读取同一项目配置并显示当前值与实际落盘根。

收到备卡方修卡或明确接口授权后继续 C；不以 localStorage 替代项目默认持久化来绕过即停条款。
