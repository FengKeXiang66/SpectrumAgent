# 22a13e6a 历史候选的 Failed=20 归属

本表直接引用负责人已核验的 `candidate.json` 与 `analysis-20261019T015517607982Z.json`，不重跑该批次。20 是完整 DOM 的 Failed **采样帧数**，不是20次失败、20个用例或20次引擎退出。真实重编产生29a2829b后，本表仍作为22a13e6a历史证据保留，新候选的DOM与矩阵另行绑定。

| 原始DOM文件（original-source-snapshot/） | 来源 | Failed帧数 |
|---|---|---:|
| dom-10452.jsonl | smoke-close会话，与已完成30轮矩阵同属22a13e6a候选 | 0 |
| dom-30208.jsonl | invalid-json注入 | 1 |
| dom-28200.jsonl | missing-fields注入 | 1 |
| dom-17240.jsonl | missing-dll-plus-invalid-json注入 | 1 |
| dom-3996.jsonl | retry-unknown会话，单次终止引擎后对同一失败页持续采样 | 17 |
| 合计 | 3个故障注入页面，加1个运行期退出页面 | 20 |

dom-3996因果链：`retry-unknown-engine-kill-output.txt` 记录一次 taskkill 成功，目标引擎PID30700；`engine_process_exit code=1` 于 `2026-10-19T01:54:03.934Z` 出现，随后 `Ready→Failed(reason=engine_failure)`。同一页面由100ms探针重复采样17次（ticks433–449，elapsed44043–45653ms），直到45s有界探针结束。之后generation2于 `01:54:17.964Z` 经 `retry_after_cleanup` 恢复。该机制是在失败页触发重试后、清理完成再创建下一代，不表示20次自动重启。

`timeout-host` 的30秒StartupTimeout是独立测试宿主场景：starting_heartbeats=298；不在这20帧之内，归入报告的 `timeout_test_host` 一节。
