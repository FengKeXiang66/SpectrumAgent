"""Assemble verbatim raw evidence into the new checkpoint report, without editing sources."""
from pathlib import Path
import json

ROOT = Path(r"E:\AI_Agent")
OUT = ROOT / "artifacts/step3/checkpoint-4"


def read(path):
    raw = Path(path).read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def main():
    report = OUT / "REPORT.md"
    original = report.read_text(encoding="utf-8")
    start = "<!-- RAW_OUTPUTS_BEGIN -->"
    end = "<!-- RAW_OUTPUTS_END -->"
    assert original.count(start) == original.count(end) == 1
    assert not original.split(start, 1)[1].split(end, 1)[0].strip(), "Never overwrite an assembled report"

    matrix = OUT / "20261018T141341066Z-KillReady"
    rows = json.loads(read(matrix / "results.json"))
    events = json.loads(read(matrix / "round-2-events.json"))
    previous = rows[0]
    old = next(x for x in events if x["event"] == "preexisting_handshake_snapshot")
    identity = next(x for x in events if x["event"] == "handshake_identity_verified")
    assert previous["engine_remaining"] == 0 and previous["engine_pid"] == old["old_identity"]["pid"]
    assert identity["pid"] == rows[1]["engine_pid"] != old["old_identity"]["pid"]
    assert identity["boot_id"] != old["old_identity"]["boot_id"]
    selected = [x for x in events if x["event"] in {
        "engine_start_attempt", "preexisting_handshake_snapshot", "process_identity_recorded",
        "handshake_ignored", "handshake_identity_verified", "health_verified", "state_transition"}]
    stale = {"source": str(matrix), "previous_round_verbatim": previous, "next_round_selected_verbatim_events": selected,
             "scope": "derived excerpt; complete original event file remains unchanged"}
    (OUT / "release-36-stale-handshake-excerpt.json").write_text(
        json.dumps(stale, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sections = [
        ("fmt 空输出对应的执行元数据", "fmt-committed-source-execution.json"),
        ("clippy 完整原始输出", "clippy-delivery-output.txt"),
        ("Rust 全量22+1测试原始输出（包括Win32参数与句柄顺序）", "tests-delivery-output.txt"),
        ("正式 --no-bundle 构建及strict TS/Vite原始输出", "release-committed-source-build-output.txt"),
        ("专用FaultFixture暂存", "fault-staging-output.txt"),
        ("专用FaultFixture实际宿主全量事件", "fault-host-events.jsonl"),
        ("Canonical暂存", "canonical-staging-output.txt"),
        ("最终36fb源码/资源绑定", "release-36fbc-source-binding.json"),
        ("最终36fb失败三案例，含因果原行与测试卫生声明", "release-36-failure-cases-output.txt"),
        ("真实Tauri dev/test SpawnFailed", "spawn-failed-result.json"),
        ("Starting 30秒测试宿主断言（完整原事件另存timeout-events.jsonl）", "timeout-assertions.json"),
        ("Starting第二实例", "timeout-second-instance.txt"),
        ("最终36fb Ready第二实例", "release-36-ready-single-instance.json"),
        ("最终36fb实际 /health HTTP原文", "release-36-health-http.txt"),
        ("最终36fb握手全文（仅token打码）", "release-36-handshake-redacted.json"),
        ("最终36fb真实前端smoke操作及完整五指标", "release-36-smoke-ui.txt"),
        ("最终36fb Ctrl+K操作证据", "release-36-ctrl-k.txt"),
        ("最终36fb Failed页面", "release-36-failed-ui.txt"),
        ("最终36fb重试后界面", "release-36-retry-ui.txt"),
        ("最终36fb未知输入处理完成后的界面", "release-36-unknown-settled-ui.txt"),
        ("dev实际计时与冷启动定义", "dev-three-stage-timing.json"),
        ("dev真实CLI完整输出与1412", "dev-timing-output.txt"),
        ("最终36fb Ready强杀10轮完整控制台", "explorer-KillReady-20261018T141340640Z-console.txt"),
        ("最终36fb发布握手前强杀10轮完整控制台", "explorer-KillStarting-20261018T141558561Z-console.txt"),
        ("最终36fb正常关窗10轮完整控制台", "explorer-Close-20261018T141931396Z-console.txt"),
        ("最终36fb陈旧握手原始事件节选（完整原件不变）", "release-36-stale-handshake-excerpt.json"),
        ("原始C盘源日志/完整DOM扫描后再复制的审计收据", "release-36-source-audit.json"),
        ("提交后的只读全量复核及最终release三段计时", "release-36-analysis-committed-output.txt"),
        ("Starting→Stopping core harness（不是TauriUI证据）", "starting-stop-probe-output.txt"),
        ("两个最终exe的mt命令、完整XML、SHA256及LongPathsEnabled", "rt-manifest-final-output.txt"),
        ("最终36fb stderr原文", "release-36.stderr.txt"),
        ("旧证据封存/新批次全量复核", "engine-batch-delivery-output.txt"),
        ("三锁、进程/端口、资源未入库等授权只读复核", "delivery-readonly-authorized-output.txt"),
        ("本机已安装Tauri CLI bundle --help原始输出", "tauri-bundle-help-output.txt"),
    ]
    blocks = []
    for label, name in sections:
        content = read(OUT / name)
        blocks.append(f"<details>\n<summary>{label}：{name}</summary>\n\n````text\n{content}"
                      + ("" if content.endswith("\n") else "\n") + "````\n\n</details>\n")
    analysis = json.loads(read(OUT / "release-36-analysis-20261018T150041946516Z.json"))
    table = ["### 最终36fb逐轮PID/端口核验（原始完整行见上方控制台）\n",
             "| 模式 | 轮 | 外壳PID | 引擎PID | 端口/状态 | 引擎残留 | 外壳残留 | 父级Job |",
             "|---|---:|---:|---:|---|---:|---:|---|"]
    for group in analysis["matrix"]:
        for row in group["rows"]:
            port = str(row["port"]) + " closed" if row["port"] else "null / unpublished_before_kill"
            table.append(f'| {row["mode"]} | {row["round"]} | {row["shell_pid"]} | {row["engine_pid"]} | '
                         f'{port} | {row["engine_remaining"]} | {row["shell_remaining"]} | {row["parent_in_job"]} |')
    transitions = json.dumps(analysis["actual_release_session_transitions"], ensure_ascii=False, indent=2)
    blocks.append("\n".join(table) + "\n\n### 最终36fb主例完整迁移序列（从原日志逐行提取）\n\n````json\n"
                  + transitions + "\n````\n")
    expanded = original.replace(start + "\n\n" + end, start + "\n\n" + "\n".join(blocks) + "\n" + end)
    expanded = expanded.replace("(/E:/AI_Agent/", "(E:/AI_Agent/")
    assert expanded != original
    report.write_text(expanded, encoding="utf-8", newline="\n")
    print(f"REPORT_ASSEMBLED raw_sections={len(sections)} bytes={report.stat().st_size} final_rounds=30")


if __name__ == "__main__":
    main()
