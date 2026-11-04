# TASK-25 D 取数命令与执行范围

仓库根为 `E:/AI_Agent`，Windows PowerShell。权威卡 `dfa67a7`，被测生产源码为 `cb97eeb`；D 仅新增测试和证据。所有 `*>` 同时保存 stdout/stderr，退出码逐步检查。

## 开工 / 收口

开工先 `git status --short`、`git log -3 --oneline`，输出分别见 before-status-start.txt / before-status-stderr.txt / before-head.txt。开工锚点命令全文在 before-anchor-commands.ps1；收口重跑同一脚本得 after-anchors.txt，两份全文一致。

```powershell
& ./milestone25/evidence/D/before-anchor-commands.ps1
node --test "src/**/*.test.ts"
npm run build
# 开工 PYTEST_DEBUG_TEMPROOT=t25do，收口=t25df，均为以下 OS 临时目录的子目录。
'C_FreeBytes=' + (Get-PSDrive C).Free
if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free below 3 GiB' }
$task25Tmp = Join-Path $env:TEMP 't25df'
New-Item -ItemType Directory -Force $task25Tmp | Out-Null
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DEBUG_TEMPROOT=$task25Tmp
.venv/Scripts/python.exe -m pytest backend/tests src-python/tests --collect-only -q
.venv/Scripts/python.exe -m pytest backend/tests -q
.venv/Scripts/python.exe -m pytest src-python/tests -q
# 以下 Rust 命令在 E:/AI_Agent/src-tauri 执行。
$env:CARGO_HOME='E:/AI_Agent/.cargo-home'
$env:CARGO_TARGET_DIR='E:/AI_Agent/src-tauri/target'
$env:CARGO_NET_OFFLINE='true'
cargo test
cargo clippy --all-targets -- -D warnings
```

开工原始日志先写 `.runtime/task25/D-opening`，Python 完整结束后逐文件复制为 `before-*`。实际 C_FreeBytes：开工 8180072448；收口 8158597120。收口前仅清理本轮已结束的 `t25do`；清理前同一 PowerShell 验证绝对路径恰为 OS Temp/t25do、父路径吻合且非重解析点。没有清理用户源目录、产物、回收站或其他任意临时目录。

## A / B / 孤儿检查

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DEBUG_TEMPROOT=Join-Path $env:TEMP 't25dt'
if ((Get-PSDrive C).Free -lt 3GB) { throw 'C free below 3 GiB' }
.venv/Scripts/python.exe -m pytest src-python/tests/storage/test_task25_acceptance.py -vv -s
.venv/Scripts/python.exe milestone25/evidence/A/storage_probe.py
.venv/Scripts/python.exe milestone25/evidence/D/reimport-isolation-probe.py
.venv/Scripts/python.exe -m pytest src-python/tests/storage/test_guard.py src-python/tests/storage/test_recycle.py src-python/tests/data/test_api.py src-python/tests/agent/test_project_paths.py -vv
& 'C:/Program Files/Git/usr/bin/grep.exe' -rn -E 'unlink|rmtree' src-python/spectrumagent backend --include=*.py
# write-pattern.txt 保存卡内模式原文，-f 避免 Windows 命令行反斜杠转义误差。
& 'C:/Program Files/Git/usr/bin/grep.exe' -rn -E -f milestone25/evidence/D/write-pattern.txt src-python/spectrumagent backend --include=*.py
# 原始 grep 包含 backend/tests，生产复核排除此域。
Get-Content milestone25/evidence/D/write-grep.txt | Where-Object {$_ -notmatch '/tests/'}
Get-Content milestone25/evidence/D/delete-write-grep.txt | Where-Object {$_ -notmatch '/tests/'}
rg -n -e 'storage\.' -e 'os\.replace|\.rename\(' -e '\.open\(' backend/database.py backend/handshake.py backend/smoke.py backend/diagnostics.py backend/logging_config.py src-python/spectrumagent/annotation/session.py src-python/spectrumagent/annotation/projection_io.py src-python/spectrumagent/agent/mat.py src-python/spectrumagent/preprocess/recipes.py src-python/spectrumagent/preprocess/run.py src-python/spectrumagent/modeling/run.py src-python/spectrumagent/modeling/inference.py src-python/spectrumagent/storage/recycle.py
```

原文依次为 acceptance.txt / guard-probe.txt / reimport-isolation.txt / backend-focused.txt / delete-write-grep.txt / write-grep.txt / production-*.txt / guard-call-sites.txt。新测试首轮 2 failed / 5 passed、第二轮 1 failed / 6 passed，原文保留 acceptance-first-attempt.txt / acceptance-second-attempt.txt；三处均为新测试错误，解释见 REPORT-D。最终 7 passed。

## C 前端与浏览器

```powershell
node --test src/components/datasets/catalog.test.ts src/components/datasets/actions.test.ts src/components/datasets/display_names.test.ts src/components/settings/project-paths.test.ts
npm run dev -- --host 127.0.0.1
```

原文 frontend-focused.txt / ui-server.txt。浏览器 URL：`http://127.0.0.1:1420/milestone25/evidence/D/browser-harness.html?src=smb%3A%2F%2Fqa-nas%2Fprefilled&out=smb%3A%2F%2Fqa-nas%2Ffuture`。

浏览器全部通过 cua_repl 的可见控件操作，未直接改 React 状态。夹具导入真实 `/src/App`，仅 IPC 为内存合成数据；不访问真实 NAS / 用户文件、不启动 sidecar、不做真实 LLM 调用。Cua 的 `getAXState()` 原文按步骤存 ui-steps.json，页面公开展示的操作记录存 ui-ipc-ledger.json，截图 ui-*.png。浏览器结束已关闭该临时页，Vite 在完成后 Ctrl+C 结束（退出码 1 为人工停止，不是构建失败）。

依次操作：冷启动 → 选择数据目录（3 个已有）→ 暂扣下一代目录响应并换代 → 再模拟引擎换代 → 释放旧代次目录响应 → 移入回收站 / 核对预览 → 人点确认 → 再选目录 / 核对新 id 确认框 → 人点确认新建 → 再选目录 / 活跃+回收站不得弹确认 → 状态切已删除 → 恢复 / 人点确认 / 显示同路径冲突 → 保存项目预填路径 → S11 显示路径、占用、日期、禁运清单。

## 生产源码与任务卡未改

```powershell
git diff --exit-code HEAD -- backend src src-python/spectrumagent src-tauri TASK-25-数据集列表与回收站.md
git diff --name-only HEAD -- backend/tests src-python/tests src
```

提交前执行，两者 exit=0 / 第二条空输出。新测试仍未跟踪时，第二条不计入该新文件；最终文件清单单独列出它。没有用此空输出声称“没有新增测试”。
