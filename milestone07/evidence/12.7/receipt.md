# TASK-07 12.7 交付凭据

基线 commit=21e4f84（R24）。本文件与集成脚本/全部证据同一个提交；交付 commit 的精确 SHA 用 `git log -1 --format=%H -- milestone07/evidence/12.7/receipt.md` 解析，并在交付回复中给出，避免文件自引用自身 commit 哈希。

| 出口 | 结果 | 执行模式 |
|---|---|---|
| Python | 951 passed / 0 failed，基线951+0 | 默认参数并发，无串行限制；环境变量与 python -m pytest 同条 |
| Rust | 75 passed / 0 failed（含doctest1），基线75+0；Clippy零警告 | cargo test 默认并发；clippy --all-targets -- -D warnings |
| 前端 | 95 passed / 0 failed，基线95+0；npm run build通过，含tsc --noEmit | node --test 默认发现/默认并发，含artifacts既有两项 |
| 集成 | exit0，92/92断言通过 | TestClient真实ASGI+MockTransport，真实provider网络0 |
| flake | 3目标各10轮，30通过/0失败，无复跑 | 暴露按轮顺序编排；各pytest新进程/默认参数 |
| MAT门 | 0.643606s < 30s，通过 | R24合成231×640×200全标，独立计时，无并发构建/回归 |

本轮不向 pytest/Rust/Node 单测套件加项，新增为独立集成断言与验收脚本；没有改既有实现或测试凑数。

## A0 / R23 销账

| 文件 | 12.5 collected | 12.6/当前 collected | 增量 |
|---|---:|---:|---:|
| agent/test_annotation_tools.py | 4 | 8 | 4 |
| annotation/test_confirm_routes.py | 0 | 11 | 11 |
| annotation/test_session.py | 25 | 29 | 4 |
| mat/test_mat.py | 0 | 6 | 6 |
| 其他文件 | 897 | 897 | 0 |
| 合计 | 926 | 951 | 25 |

MAT 三个函数被 mat_case fixture 的 params=[False,True] 展开为六个 collected，静态22少算的三项全部定位；没有其他收集源，也没有改测试。原始 collect-only.txt 与 collection-reconciliation.json 已保留。

## e2e 与边界

导入→真实小图分割→draft 三态体积→confirm→四件套互锁→MAT下载→export八标量；MockTransport真实网关→human_check→approve→版本/MAT/step落库→INTERPRET→SSE step/done；legacy regions/undo/save与旧三件套 document=None；另补失败保版→无半份MAT→service rebuild连续恢复路径。原始事件、断言和DB行见e2e-result.json。

标签集合{0,3}未重映射，label_index完整四类；两次网关调用真实session_id留痕，未上报usage均NULL。没有真实key或provider请求。真实S05/UI、NAS性能与云端延迟只列冒烟，不计自动化通过。

## 文档与证据清单

acceptance-map.md（卡§6完整55项）/ performance.md+json / scripts/e2e_task07.py与本目录e2e.py等字节副本+output+result / flake_smoke.py+30条per-test日志+flake-summary.json / smoke-checklist.md / technical-debt.md / 本receipt / collection-reconciliation.json+collect-only.txt / pytest/cargo/clippy/node/build原始日志 / boundary-output.txt / scope-check.json / summary.json / finalize.py。release草稿位于docs/release-notes-v0.3.0.md。

## 自定项与理由

1. 小图使用40×12×8，形状/种子17/范围来源既有annotation与#05夹具；真实分割参数24/.5/5来自现有HTTP测试。大图用float32 DN以使原始源文件约118MB，逐行公式生成，完整记录dtype与公式。
2. 大图性能用由默认n_segments=800推导的17×48规则网格作前置状态；不把SLIC准备计入MAT门，不声称测过大图SLIC质量。小图链路实际走superpixels端点。
3. 观测器只包装原MatStore.generate和原scipy.savemat，原函数全部执行；MAT门取generate完整span，confirm/写入单列，tracemalloc为writer周围Python分配峰值而非RSS。
4. e2e补连续失败→重建路径及字面{0,3}原index夹具，闭合§6组合要求，没有改生产实现。
5. 对话两个HTTP span相加排除人工思考，内部span嵌套不相加；TestClient缓冲SSE不能冒充真实WebView/网络到达延迟。
6. flake脚本逐个启动新pytest进程，每目标十轮；只有失败时才单独复跑并留痕、不推断根因。本次零失败，未触发复跑。
7. acceptance-map保留§6逐项原文，按R14/R19/R20/R22注明延期和历史时点，不把算法手势半边或人工冒烟标绿。
8. receipt通过本文件Git历史定位交付SHA，父提交明确列出；完整SHA在交付回复，避免同一commit内自引用哈希。所有证据生成脚本留存以便复算。

9. 原审计脚本全套断言实际重跑，harness仅将固定的12.6输出文件重定向为12.7/boundary.json，保留旧证据字节；没有改审计代码或豁免新语义。

## 即停与剩余事项

本轮没有新增即停点或实现修复。e2e首次启动的自动审批超时后按工具许可重试成功，没有失败运行被覆盖为通过。三出口、MAT门与flake均通过；真实NAS/DeepSeek/UI、签名/SmartScreen、干净机、长路径与reboot仍归科祥。未打tag、未push、未建Release、未改manifest或tauri.conf.json；五个公司文档与任务卡不动。
