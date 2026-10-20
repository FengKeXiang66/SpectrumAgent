> 已解除：R21 接缝授权及 UUID 选项 2 裁定已明确；以下保留原始即停记录。接缝实现与验证见 seam/。

# 10.6 R21 接缝复检：UUID 依赖声明冲突，即停待裁定

事实源：当前 TASK-04（552 行，R21）、本次“两次 commit”开工令。

前次两项缺口（标签管理 IPC、working 的 project_id/queue）已获 R21 明确授权，本次不再询问。尚未改产品代码或进入前端 commit。

## 新发现的具体冲突

- §5.7 / 开工令指定 Labels.project_id 先经既有 uuid() 校验，再调用 `Uuid::parse_str(...).to_string()` 规范化后 set_query。
- 同时明确“不新增依赖”。
- 实际 src-tauri/Cargo.toml 的直接 dependencies 没有 uuid；Cargo.lock 中 spectrum-agent 的依赖数组也没有 uuid。
- uuid 1.28.0 已在 Cargo.lock 中作为传递依赖，E 盘 Cargo 缓存中已有该版本。它不是当前 crate 可直接 import 的依赖；检查 tauri 2.12.4 / tauri-utils 2.10.2 源码未发现公开的 Uuid 重导出。
- 因此不能在当前依赖声明下直接 `use uuid::Uuid`。把传递依赖提升为直接依赖需要改 Cargo.toml 与 lock 中根包依赖数组；自行改用字符串规范化又违背 R21 指定的 Uuid::parse_str 写法。不能伪造本地 Uuid 类型冒充库解析器。

## 需裁定的两条可执行路径

1. 授权复用锁内 uuid 1.28.0 为直接依赖：Cargo.toml 精确声明该现有版本、Cargo.lock 只更新根包的直接依赖关系；不引入新 crate 版本、不安装、不下载。按卡原文调用 Uuid::parse_str。
2. 保持直接依赖清单不变，明确修订实现要求：复用现有 uuid() 的 36 字符规范 UUID 校验（固定连字符位置，其余 ASCII hex），再 to_ascii_lowercase，之后构造固定 project_id query 并 set_query。该输入子集上规范化结果与 UUID parser 相同，但必须先获准偏离卡内指定调用。

## 本次回执

- 文件：仅新增 milestone04/evidence/10.6/receipt-r21-blocked.md。
- commit：无；HEAD 保持 3a519e32729e5cdf19fe8ec7faa30ae18362921d。
- pytest/cargo/node/build/clippy：本次未执行，不冒报 10.6 通过数。
- R21 两个 commit 均未创建；未改后端、Rust、前端、任务卡、任何 lock 或固定种子。
- §6 自验：尚未实施，均不报通过；等待此单项裁定后继续 Commit 1，门槛全绿后再进 Commit 2。
- 根目录两份公司文档与 seeds_20.json 保持未跟踪。
