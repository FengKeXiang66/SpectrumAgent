"""Read-only verification of the production-feature candidate and its own evidence."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess

ROOT = Path(r"E:\AI_Agent")
OUT = ROOT / "artifacts/step3/checkpoint-4/release-custom-protocol-20261018"


def load(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    return [json.loads(x) for x in Path(path).read_bytes().splitlines() if x]


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def session(log, pid):
    start = next(i for i, row in enumerate(log) if row.get("event") == "shell_started" and row.get("pid") == pid)
    end = next(i for i in range(start, len(log)) if log[i].get("event") == "app_exit")
    return log[start:end + 1]


class Buttons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.disabled = []

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self.disabled.append("disabled" in dict(attrs))


def main():
    binding = load(OUT / "candidate.json")
    assert binding["features"] == "custom-protocol" and not binding["test_probes_enabled"]
    release = ROOT / "src-tauri/target/release"
    assert sha(release / "spectrum-agent.exe") == binding["shell_sha256"]
    authority = load(binding["engine_manifest"])
    resource = release / "resources/backend"
    actual = {p.relative_to(resource).as_posix(): (p.stat().st_size, sha(p)) for p in resource.rglob("*") if p.is_file()}
    expected = {x["path"]: (x["bytes"], x["sha256"]) for x in authority["files"]}
    assert actual == expected and len(actual) == 544
    for fp in binding["fingerprints"]:
        assert sha(ROOT / fp["path"]) == fp["sha256"]
        assert fp["contents"]["features"] == '["custom-protocol"]'
    locks = {"requirements-lock.txt": "58e24b59da34461a17fd942b4047071e42b5120b3d474ba976a7e28535d40bcc",
             "package-lock.json": "5122b8e2dbd8b84ce2d7365088d01e657de7c178037533194ab17504eb7ecb14",
             "src-tauri/Cargo.lock": "19677a37d746c188184f4948d8bc5739759be755e3afeaa2c9f58471fec13b12"}
    assert all(sha(ROOT / p) == digest for p, digest in locks.items())
    source = (OUT / "upstream-installer.nsi").read_bytes()
    template = (ROOT / "src-tauri/nsis/installer.nsi").read_bytes()
    old = b'      StrCpy $INSTDIR "$LOCALAPPDATA\\${PRODUCTNAME}"'
    new = b'      StrCpy $INSTDIR "$LOCALAPPDATA\\Programs\\${PRODUCTNAME}"'
    assert source.count(old) == 1 and source.replace(old, new) == template

    matrices = []
    for mode in ("KillReady", "KillStarting", "Close"):
        folder = sorted(OUT.glob("*-" + mode))[-1]
        rows = load(folder / "results.json")
        audit = load(folder / "audit.json")
        assert len(rows) == 10 and audit["binary_sha256_after"] == binding["shell_sha256"]
        assert audit["exact_token_hits"] == audit["whole_handshake_json_hits"] == 0 and not audit["authorization_bearer"]
        assert sha(folder / "original-shell.log") == audit["sha256"]
        for row in rows:
            assert row["passed"] and row["binary_sha256"] == binding["shell_sha256"]
            assert row["engine_remaining"] == row["shell_remaining"] == 0 and not row["port_open"]
            assert not row["parent_in_job"] and row["parent_path"].lower() == r"c:\windows\explorer.exe"
            if mode == "KillStarting":
                assert row["port"] is None and not row["handshake_published_before_action"]
            else:
                assert row["port"] and row["port_status"] == "closed"
        matrices.append({"mode": mode, "directory": str(folder.relative_to(ROOT)), "audit": audit, "rows": rows})

    snapshots = OUT / "original-source-snapshot"
    for name in ("source-audit.json", "timeout-source-audit.json"):
        audit = load(OUT / name)
        assert audit["scan_original_before_copy"]
        for row in audit["records"]:
            assert sha(snapshots / Path(row["source"]).name) == row["sha256"]
            assert row["exact_token_hits"] == 0 and not row["authorization_bearer"]
            assert row.get("whole_handshake_hits", 0) == 0
    documents = []
    phases = Counter()
    stopping = []
    for path in sorted(snapshots.glob("dom-*.jsonl")):
        if path.name == "dom-6568.jsonl":
            continue  # Debug test-host evidence is kept separate from production evidence.
        records = lines(path)
        complete = [x["document"] for x in records if isinstance(x.get("document"), dict) and isinstance(x["document"].get("html"), str)]
        assert complete
        counts = Counter(d["phase"] for d in complete)
        phases.update(counts)
        for doc in complete:
            assert doc["url"] == "http://tauri.localhost/" and "1420" not in doc["url"]
            assert all(url.startswith("http://tauri.localhost/assets/") for url in doc["scripts"])
            assert doc["localStorage"] == doc["sessionStorage"] == []
            if doc["phase"] == "Stopping":
                buttons = Buttons()
                buttons.feed(doc["html"])
                assert buttons.disabled and all(buttons.disabled)
                assert all(field["disabled"] for field in doc["fields"])
                assert "正在关闭" in doc["html"]
                stopping.append({"source": path.name, "fields": doc["fields"], "buttons_disabled": buttons.disabled})
        documents.append({"file": path.name, "callbacks": len(records), "complete_documents": len(complete), "phases": dict(counts),
                          "url": "http://tauri.localhost/", "localStorage_entries": 0, "sessionStorage_entries": 0})
    assert set(phases) == {"Starting", "Ready", "Failed", "Stopping"} and stopping
    log = lines(snapshots / "shell-20261018.log")
    smoke_launch = load(OUT / "smoke-close-launch.json")
    smoke_session = session(log, smoke_launch["pid"])
    health = next(x for x in smoke_session if x.get("event") == "health_verified")
    interactive = next(x for x in smoke_session if x.get("event") == "acceptance_dom_audit" and x.get("interactive"))
    request = next(x for x in smoke_session if x.get("event") == "smoke_requested")
    smoke = next(x for x in smoke_session if x.get("event") == "smoke_finished")
    base = utc(smoke_launch["launch_before_utc"])
    timing = {"engine_ready_ms": round((utc(health["timestamp"]) - base).total_seconds() * 1000, 3),
              "interactive_ms": round((utc(interactive["timestamp"]) - base).total_seconds() * 1000, 3),
              "first_smoke_completed_ms": round((utc(smoke["timestamp"]) - base).total_seconds() * 1000, 3),
              "manual_wait_before_smoke_ms": round((utc(request["timestamp"]) - utc(interactive["timestamp"])).total_seconds() * 1000, 3),
              "smoke_round_trip_ms": round((utc(smoke["timestamp"]) - utc(request["timestamp"])).total_seconds() * 1000, 3),
              "metrics": smoke["result"]["Ok"], "cold_definition": smoke_launch["cold_definition"], "clean_vm": False}
    assert set(timing["metrics"]) == {"nan_ratio", "reflectance_range", "bands", "shape", "elapsed_ms"}
    retry_session = session(log, load(OUT / "retry-unknown-launch.json")["pid"])
    transitions = [x for x in retry_session if x.get("event") == "state_transition"]
    assert [(x["from"], x["to"]) for x in transitions] == [
        ("Starting", "Ready"), ("Ready", "Failed"), ("Failed", "Starting"), ("Starting", "Ready"), ("Ready", "Stopping")]
    assert sum(x.get("event") == "engine_failure" and x["failure"]["kind"] == "EngineExitedAfterReady" for x in retry_session) == 1
    assert sum(x.get("event") == "app_exit" for x in retry_session) == 1
    assert all(x["selection_source"] == "resolved_resource" for x in retry_session if x.get("event") == "engine_start_attempt")
    secondary = load(OUT / "ready-single-instance.json")
    assert secondary["secondary_exit"] == 0 and secondary["handshake_bytes_unchanged"]

    timeout = session(lines(snapshots / "shell-20261019.log"), load(OUT / "timeout-host-launch.json")["pid"])
    failure = next(x for x in timeout if x.get("event") == "engine_failure")
    assert failure["failure"]["kind"] == "StartupTimeout"
    started = next(x for x in timeout if x.get("event") == "engine_start_attempt")
    heartbeats = [x for x in timeout if x.get("event") == "acceptance_heartbeat" and utc(x["timestamp"]) < utc(failure["timestamp"])]
    assert len(heartbeats) >= 250 and all(not x["visible"] for x in heartbeats)
    max_gap = max((utc(b["timestamp"]) - utc(a["timestamp"])).total_seconds() * 1000 for a, b in zip(heartbeats, heartbeats[1:]))
    assert max_gap < 1000
    assert any(x.get("event") == "activation_requested" and x["phase"] == "Starting" and x["pending_activation"] for x in timeout)
    assert any(x.get("event") == "acceptance_dom_audit" and x.get("invoke", {}).get("ok") and x["invoke"]["value"]["phase"] == "Starting" for x in timeout)
    timeout_result = {"starting_heartbeats": len(heartbeats), "max_queue_ms": max(x["queue_ms"] for x in heartbeats),
                      "max_gap_ms": round(max_gap, 3), "starting_visible_true": 0,
                      "elapsed_start_to_failure_ms": round((utc(failure["timestamp"]) - utc(started["timestamp"])).total_seconds() * 1000, 3),
                      "pending_activation": True, "internal_invoke_returned_starting": True, "scope": "current-source Tauri debug test host"}

    cases = load(sorted(OUT.glob("failure-cases-*/results.json"))[-1])
    assert len(cases) == 3
    for case in cases:
        assert case["shell_sha256"] == binding["shell_sha256"] and case["fixture_bytes_unchanged"]
        assert case["failure_page_observed"] and case["failed_second_instance_exit"] == 0 and case["engine_start_attempts"] == 1
        if case["fault_fixture"]:
            assert case["failure"]["kind"] == "ExitedBeforeReady" and not case["causal_rows"]
            assert case["elapsed_ms_to_dom_observation"] < 2000
        else:
            assert case["failure"]["kind"] == "HandshakeInvalid"
            assert sum(x["phase"] == "startup" for x in case["causal_rows"]) == 1
            assert all(x["pid"] == case["engine_pid"] for x in case["causal_rows"])
    result = {"source_commit": binding["source_commit"], "evidence_generator_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "shell_sha256": binding["shell_sha256"], "shell_bytes": binding["shell_bytes"], "features": "custom-protocol",
              "resource_files": len(actual), "matrix": matrices, "documents": documents, "production_dom_phases": dict(phases),
              "stopping_observations": stopping, "timing": timing, "retry_transitions": transitions,
              "timeout_test_host": timeout_result, "failure_cases": cases, "locks": locks,
              "template_single_line_verified": True, "vm_status": "待 VM 实机", "legacy_exit70_cause": "未验证"}
    target = OUT / ("analysis-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with target.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"analysis": str(target), "shell_sha256": binding["shell_sha256"], "matrix": {x["mode"]: len(x["rows"]) for x in matrices},
                      "production_dom_phases": dict(phases), "timing": timing, "timeout_test_host": timeout_result,
                      "template_single_line_verified": True, "three_locks_unchanged": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
