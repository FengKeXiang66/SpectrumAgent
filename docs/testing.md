# 本地回归固定命令

在仓库根目录、已激活项目 Python 虚拟环境的正常 Windows 用户终端执行：

```powershell
python -m pytest -q --basetemp=.tmp-sample-suite
node --test --test-concurrency=1 tests/*.test.mjs
npm run build
cargo test --manifest-path src-tauri/Cargo.toml --lib
python scripts/audit_project_resources.py --check
```

`.tmp-sample-suite` 是专用测试临时目录，匹配仓库忽略规则；pytest 会管理并清空它，不可改成已有数据目录。固定短路径避免默认用户临时目录叠加测试名、模型和推理 UUID 以及原子写入临时文件名后触及 Windows 传统长路径限制。不能将这一类文件写入失败解释为模型数值回归。

后端测试还包含仅针对临时测试密钥的 DPAPI 往返，需要正常 Windows 用户上下文。项目数据、实际模型服务密钥和真实训练任务不参与测试。

源码测试与前端构建通过不等于已经重打包安装版；桌面交付仍需验证打包后的后端、前端及真实窗口行为。

## 项目、对话与数据的界面引导

项目管理回归：`python -m pytest -q tests/test_project_lifecycle.py tests/test_project_scopes.py tests/test_session_management.py --basetemp=.tmp-project-lifecycle`，`node --test --test-concurrency=1 tests/project-management.test.mjs tests/project-guidance.test.mjs tests/project-scopes.test.mjs`。Rust 转发用例为 `project_operations_have_fixed_routes_and_session_identity`。覆盖可恢复删除、旧编号拒绝、恢复、最后项目保护、并发删除、预览过期、各类后台任务阻塞及删除后新会话归属。

本轮实测：项目生命周期与作用域/会话专项 27 项通过，前端全量 39 项通过，Rust 95 项通过，生产构建通过。受限进程中的完整后端回归为 **284 通过、1 跳过、1 失败**；失败为 `test_router_key_is_encrypted_restored_and_cleared_independently`，Windows `CryptProtectData` 返回 `WinError 2`，单独在同一受限上下文复跑仍失败。相同源码在正常 Windows 用户上下文下，单项通过，整个 `tests/test_router_settings.py` **8 项全部通过**。因此将该项定性为测试进程的 DPAPI 上下文限制，不是项目删除的回归；未跳过它、未改加密实现或保存明文。完整后端命令不应记作单次全绿。1 项原有跳过需配置显式本地发布数据路径。

DPAPI 对照复核应在正常 Windows 用户终端运行：`python -m pytest -q tests/test_router_settings.py --basetemp=.tmp-project-settings-user`。该模块仅使用临时测试密钥和临时工作区，不操作实际模型服务密钥。

`tests/project-guidance.test.mjs` 覆盖项目与对话层级、项目目录就绪/未就绪时的计数、新对话复用数据、历史导入卡归属和引导入口只填写消息。计数不使用单张画布数据，也不使用旧会话的历史数量覆盖当前目录。

真实窗口验收：

1. 左侧始终能看到当前项目，其下是本项目对话；切换项目后，对话列表、项目数据和标题同步更新。
2. 同项目新建对话后，数据数量保留，显示开始引导；打开原对话继续原步骤。
3. 点击开始引导的目录导入，选择目录后只填写输入框；发送后导入卡标明所属项目。已有输入文本应保留；选择期间若切换对话或项目，旧选择结果应丢弃。
4. 查看紧凑输入条和窄窗口：范围摘要可读；展开项目帮助或新建项目表单时，左侧内容可滚动，仍能访问对话列表。

本次环境禁用了浏览器访问，因此没有执行真实窗口截图验收；静态渲染与生产构建不代替上述窗口检查。

## 2026-11-28：Windows 重命名拒绝访问的定性

本次不能把两个不同位置的失败混为一谈：

| 检查项 | 实测结果 | 判断 |
|---|---|---|
| `test_incompatible_or_changed_inputs_cannot_predict[new_member]`：刚生成的 `unlabelled.npz` 移入子目录 | 独立进程重复 5 次，5/5 通过，未加 GC 或重试 | 未复现该 NPZ rename 失败 |
| `test_chat_entry_and_step_plan_do_not_leak_future_actions_or_defaults`：保存区域标注时把 `current.<uuid>.tmp` 原子发布为 `current` | 原实现独立重复 5 次，5/5 失败；每次仅部分样品的发布发生 WinError 5，导致可用标注不足 | 上轮实际失败点，不能忽略 |
| 失败现场 | 源目录存在、目标不存在；Python 打开的文件中没有该快照下的 NPZ/JSON；目录和全部文件的 Win32 DELETE 访问探测成功；成功启动的 Restart Manager 查询返回无占用者 | 没有发现持续占用这些文件的产品句柄；也不是目标目录已存在 |
| 一次 GC + 100 ms 重试 | 用例通过 | 仅此不足以判断是 GC 还是等待起效 |
| **不做 GC，只等待 100 ms 重试一次** | 独立重复 5 次，5/5 通过 | 支持短时 Windows 重命名访问冲突，而非必须靠 GC 释放的持久句柄 |
| 产品层修复后，不加载诊断包装器 | 原失败用例独立重复 5 次，5/5 通过 | 已交付有界恢复，不标 flaky、不跳过此用例 |

定性：本次实际问题是 **Windows 的短时目录重命名访问拒绝**。不能仅因整条用例稳定失败，就认定产品有句柄泄漏；也没有证据把占用者指定为杀毒软件或索引服务。Restart Manager 的空结果只表示查询时未发现文件占用者，不证明此前没有瞬时占用。查询只注册快照内文件；[微软文档](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmgetlist)说明注册目录本身可能导致 ERROR_ACCESS_DENIED，不能把该诊断错误当成占用证据。

指定 NPZ 用例中的 rename 发生在 `dialogue.capture`、输入检查和预测读取该新文件之前；`train()` 处理的是另外的 train/test NPZ，不能据此认定新生成的 `unlabelled.npz` 已被产品加载后泄漏。

处理：`storage.guard.replace` 仅对 Windows 错误 5/32/33 等待 100 ms，再尝试一次原子的 `os.replace`；每次都重新校验并审计源/目标路径。不做 GC、不改权限、不用复制后删除替代原子发布。第二次仍失败、其他错误及非 Windows 错误原样抛出。`test_windows_replace.py` 覆盖恢复、持续失败、非目标错误及等待后权限变化。

另外发现 `tests/test_experiments.py` 的一个对照测试直接持有三个未显式关闭的 NPZ 归档，已改成 `with np.load` 后复制数组。它是独立的测试资源管理问题，不是上述快照目录错误的证据；`train()` 调用的 `config_for()` 只使用 `np.savez`，没有打开 NPZ 归档。

`test_file_handle_lifecycle.py` 专门保留所有加载过的 `NpzFile` 的强引用，验证正常训练/推理及校验异常后均已关闭，且无需 GC/重试即可移动训练、测试和预测输入；另验证 ENVI 推理结束后 HDR/IMG 可移动。当前覆盖路径未发现产品 NPZ 或 ENVI memmap 持久句柄泄漏。

复核命令（PowerShell；每次使用新的短临时目录）：

```powershell
$renameRunTag = [guid]::NewGuid().ToString('N').Substring(0,8)
foreach ($renameIteration in 1..5) {
    python -m pytest 'tests/test_experiment_inference.py::test_incompatible_or_changed_inputs_cannot_predict[new_member]' -q "--basetemp=.tmp-npz-$renameRunTag-$renameIteration"
    if ($LASTEXITCODE -ne 0) { throw "NPZ rename failed: $renameIteration" }
}
foreach ($renameIteration in 1..5) {
    python -m pytest tests/test_project_scopes.py::test_chat_entry_and_step_plan_do_not_leak_future_actions_or_defaults -q "--basetemp=.tmp-dir-$renameRunTag-$renameIteration"
    if ($LASTEXITCODE -ne 0) { throw "Annotation publish failed: $renameIteration" }
}
python -m pytest -q tests/test_windows_replace.py tests/test_file_handle_lifecycle.py --basetemp=.tmp-handle-suite
```

失败时先记录原始 WinError、源/目标存在性、文件占用者和是否需要 GC，再决定修复；不能先将测试标记 flaky 或把失败排除出通过率。
