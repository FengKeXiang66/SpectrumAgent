"""Read-only cross-checks of the delivered binary, frozen engine and archived evidence."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import subprocess

ROOT = Path(r"E:\AI_Agent")
OUT = ROOT / "artifacts/step3/checkpoint-4"
SHA = "36fbc3df1d220d51c2a1b9e6d347a0ebdb99eb6fa6318d20a18f82d1b9da713f"


def load(path):
    data = Path(path).read_bytes()
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return json.loads(data.decode(encoding))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    exe = ROOT / "src-tauri/target/release/spectrum-agent.exe"
    assert sha(exe) == SHA, "the accepted executable changed"
    authority_path = ROOT / "artifacts/step2/revision-20261018-smoke-headers/product-manifest.json"
    authority = load(authority_path)
    resource = exe.parent / "resources/backend"
    actual = {p.relative_to(resource).as_posix(): (p.stat().st_size, sha(p)) for p in resource.rglob("*") if p.is_file()}
    expected = {x["path"]: (x["bytes"], x["sha256"]) for x in authority["files"]}
    assert actual == expected, "complete Canonical resource manifest differs"
    groups = []
    for mode in ["KillReady", "KillStarting", "Close"]:
        candidates = []
        for folder in OUT.glob(f"*-{mode}"):
            if not (folder / "results.json").exists():
                continue
            rows = load(folder / "results.json")
            if len(rows) == 10 and all(x["binary_sha256"] == SHA for x in rows):
                candidates.append((folder, rows))
        folder, rows = sorted(candidates, key=lambda p: p[0].name)[-1]
        assert all(x["passed"] and x["engine_remaining"] == 0 and x["shell_remaining"] == 0
                   and not x["port_open"] and not x["parent_in_job"] for x in rows)
        if mode == "KillStarting":
            assert all(not x["handshake_published_before_action"] and x["port"] is None for x in rows)
        else:
            assert all(x["handshake_published_before_action"] and x["port"] for x in rows)
        audit = load(folder / "audit.json")
        assert audit["binary_sha256_after"] == SHA
        assert audit["exact_token_hits"] == audit["whole_handshake_json_hits"] == 0
        assert not audit["authorization_bearer"]
        assert sha(folder / "original-shell.log") == audit["sha256"]
        groups.append({"mode": mode, "directory": str(folder.relative_to(ROOT)), "audit": audit, "rows": rows})

    sources = OUT / "release-36-source-snapshot"
    audit = load(OUT / "release-36-source-audit.json")
    assert audit["scan_original_before_copy"]
    for record in audit["records"]:
        assert sha(sources / Path(record["source"]).name) == record["sha256"]
        assert record["exact_token_hits"] == record["whole_handshake_hits"] == 0 and not record["authorization_bearer"]
    documents = []
    for path in sources.glob("dom-*.jsonl"):
        records = [json.loads(x) for x in path.read_bytes().splitlines()]
        complete = [x for x in records if isinstance(x.get("document"), dict) and isinstance(x["document"].get("html"), str)]
        assert complete, f"no complete DOM in {path}"
        assert all(isinstance(x["document"]["fields"], list) for x in complete)
        assert all(x["document"]["localStorage"] == [] and x["document"]["sessionStorage"] == [] for x in complete)
        phases = Counter(x["document"]["phase"] for x in complete)
        documents.append({"path": str(path.relative_to(ROOT)), "callback_records": len(records),
                          "complete_documents": len(complete), "phases": dict(phases),
                          "max_localStorage_entries": 0, "max_sessionStorage_entries": 0,
                          "has_real_smoke_metrics": any('125.013' in x["document"]["html"] for x in complete)})
    assert any(x["has_real_smoke_metrics"] for x in documents), "final release smoke DOM absent"

    cases = load(OUT / "failure-cases-20261018T142530759302Z/results.json")
    assert len(cases) == 3
    for case in cases:
        assert case["shell_sha256"] == SHA
        assert case["fixture_bytes_unchanged"] and case["failure_page_observed"]
        assert case["failed_second_instance_exit"] == 0 and case["engine_start_attempts"] == 1
        if case["fault_fixture"]:
            assert case["failure"]["kind"] == "ExitedBeforeReady" and not case["causal_rows"]
            assert case["fault_fixture_resource_files"] == 543
            assert case["elapsed_ms_to_dom_observation"] < 2000
        else:
            assert case["failure"]["kind"] == "HandshakeInvalid"
            assert len([x for x in case["causal_rows"] if x["phase"] == "startup"]) == 1
            assert all(x["pid"] == case["engine_pid"] for x in case["causal_rows"])

    log = [json.loads(x) for x in (sources / "shell-20261018.log").read_bytes().splitlines()]
    index = next(i for i, x in enumerate(log) if x.get("event") == "shell_started" and x.get("pid") == 14352)
    session = log[index:]
    health = next(x for x in session if x.get("event") == "health_verified")
    interactive = next(x for x in session if x.get("event") == "acceptance_dom_audit" and x.get("interactive"))
    requested = next(x for x in session if x.get("event") == "smoke_requested")
    smoke = next(x for x in session if x.get("event") == "smoke_finished")
    launch = load(OUT / "release-36-launch.json")
    base = utc(launch["launch_before_utc"])
    timing = {"engine_ready_from_pre_spawn_ms": round((utc(health["timestamp"]) - base).total_seconds() * 1000, 3),
              "interactive_from_pre_spawn_ms": round((utc(interactive["timestamp"]) - base).total_seconds() * 1000, 3),
              "first_smoke_from_pre_spawn_ms": round((utc(smoke["timestamp"]) - base).total_seconds() * 1000, 3),
              "manual_wait_before_smoke_ms": round((utc(requested["timestamp"]) - utc(interactive["timestamp"])).total_seconds() * 1000, 3),
              "smoke_round_trip_ms": round((utc(smoke["timestamp"]) - utc(requested["timestamp"])).total_seconds() * 1000, 3),
              "metrics": smoke["result"]["Ok"], "cold_definition": launch["cold_definition"], "clean_vm": False}
    attempts = [x for x in session if x.get("event") == "engine_start_attempt"]
    assert len(attempts) == 2 and all(x["selection_source"] == "resolved_resource" for x in attempts)
    assert all(x["exe"].removeprefix("\\\\?\\").lower() == str(resource / "app.exe").lower() for x in attempts)
    transitions = [x for x in session if x.get("event") == "state_transition"]
    assert [(x["from"], x["to"]) for x in transitions] == [
        ("Starting", "Ready"), ("Ready", "Failed"), ("Failed", "Starting"),
        ("Starting", "Ready"), ("Ready", "Stopping")]
    assert sum(x.get("event") == "engine_failure" and x["failure"]["kind"] == "EngineExitedAfterReady" for x in session) == 1
    assert sum(x.get("event") == "app_exit" for x in session) == 1
    allowed = {("Starting", "Ready"), ("Starting", "Failed"), ("Starting", "Stopping"),
               ("Ready", "Failed"), ("Ready", "Stopping"), ("Failed", "Starting"), ("Failed", "Stopping")}
    observed = {(x["from"], x["to"]) for x in log if x.get("event") == "state_transition"}
    core = [json.loads(x) for x in (OUT / "starting-stop-probe.log").read_bytes().splitlines()]
    observed.update((x["from"], x["to"]) for x in core if x.get("event") == "state_transition")
    assert observed == allowed, (observed, allowed)
    result = {"shell_source_commit": subprocess.check_output(["git", "rev-parse", "83e8c37"], cwd=ROOT, text=True).strip(),
              "evidence_generator_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "shell_sha256": SHA, "engine_manifest": str(authority_path), "engine_manifest_sha256": sha(authority_path),
              "resource_files": len(actual), "resource_bytes": sum(v[0] for v in actual.values()),
              "matrix": groups, "documents": documents, "release_timing": timing, "failure_cases": cases,
              "actual_release_session_transitions": transitions, "all_allowed_transitions_covered_in_labeled_runtime_and_core_logs": sorted(observed),
              "stopping_dom_captured": False, "vm_status": "待实机验证", "legacy_exit_70_cause": "未验证",
              "release_1412_reproduced": 'Error = 1412' in (OUT / "release-36.stderr.txt").read_text()}
    target = OUT / ("release-36-analysis-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"analysis": str(target), "shell_sha256": SHA,
                      "matrix": {g["mode"]: len(g["rows"]) for g in groups}, "documents": documents,
                      "timing": timing, "all_allowed_transition_pairs": len(observed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
