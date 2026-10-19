"""Read-only source/evidence audit; emits no credentials and writes only #02 evidence."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "src-python/tests/evidence"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def main():
    baseline = "205f0ad"
    source_baseline = "bb7cc6f"
    changed = git("diff", "--name-only", baseline, "--").splitlines()
    protected = [p for p in changed if p.startswith(("artifacts/", "backend/", "src-tauri/resources/", "src-tauri/nsis/")) or p in {"requirements-lock.txt", "VM-BUILD-Win11Clean.md", "VM-ACCEPTANCE-CHECKPOINT4.md", "collect-vm-evidence.ps1", "src-tauri/tauri.conf.json"}]
    assert not protected, protected
    original = git("show", f"{source_baseline}:src-tauri/src/main.rs")
    source = (ROOT / "src-tauri/src/main.rs").read_text("utf-8")
    command = re.search(r"tauri::generate_handler!\[[^\]]+\]", original).group()
    release = source.split("#[cfg(not(debug_assertions))]", 1)[1].split("let app", 1)[0]
    assert command in release and "datasets_forward" not in release
    assert "#[cfg(debug_assertions)]\n#[tauri::command]\nasync fn datasets_forward" in source
    insert_only = ["src-tauri/src/process.rs", "src-tauri/src/win32.rs", "src-tauri/src/supervisor.rs", "src-tauri/src/lib.rs"]
    for path in insert_only:
        patch = git("diff", "--unified=0", source_baseline, "--", path)
        assert not [line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")], path
    boundary = git("diff", source_baseline, "--", *insert_only, "src-tauri/src/main.rs", "src-tauri/build.rs", "src-tauri/capabilities/main.json")
    (EVIDENCE / "4.6-release-boundary.diff").write_text(boundary, "utf-8")
    capability = json.loads((ROOT / "src-tauri/capabilities/main.json").read_text("utf-8"))
    previous = json.loads(git("show", f"{source_baseline}:src-tauri/capabilities/main.json"))
    permission_additions = set(capability["permissions"]) - set(previous["permissions"])
    assert permission_additions == {"dialog:allow-open", "allow-datasets-forward"}
    assert set(previous["permissions"]) <= set(capability["permissions"])

    desktop = EVIDENCE / "desktop"
    run = json.loads((desktop / "run.json").read_text("utf-8-sig"))
    close = json.loads((desktop / "close-receipt.json").read_text("utf-8-sig"))
    assert close["survivors"] == [] and close["shell_exit"] == 0
    assert close["observed_before_host_script_exit"] and not close["script_removed_handshake"]
    root = Path(run["data_root"])
    live_identity = json.loads((root / "run/handshake.json").read_text("utf-8"))
    assert live_identity["boot_id"] == run["boot_id"], "旧凭证已不可用；不得用其它boot的token倒推旧审计"
    credential = live_identity["token"]
    samples = [json.loads(line) for line in (desktop / f"dom-{run['shell_pid']}.jsonl").read_text("utf-8").splitlines()]
    for path in desktop.iterdir():
        if path.is_file():
            assert credential.encode() not in path.read_bytes(), path.name
    phases = Counter(row["document"]["phase"] for row in samples)
    # The existing bounded observer stops at 45s. Later UI interactions are
    # evidenced by accessibility snapshots plus timestamped engine access logs.
    ui = (desktop / "ui-idempotent.txt").read_text("utf-8")
    assert "新增 0 个，已有 11 个" in ui
    assert (desktop / "ui-imported.txt").read_text("utf-8").count("项 231×640×200") == 11
    assert "HEADER_INVALID" in (desktop / "ui-invalid-header.txt").read_text("utf-8")
    result = {
        "baseline": baseline, "protected_file_changes": protected,
        "release_commands_literal": command, "release_command_list_identical": True,
        "existing_supervisor_process_win32_lines_removed_or_edited": 0,
        "new_permissions": sorted(permission_additions),
        "python_lock_sha256": hashlib.sha256((ROOT / "requirements-lock.txt").read_bytes()).hexdigest(),
        "desktop": {"data_root":str(root),"shell_pid":run["shell_pid"],"python_pid":run["python_pid"],"launcher_pid":run["launcher_pid"],"shell_sha256":run["binary_sha256"],"dom_samples":len(samples),"dom_phases":dict(phases),"dom_urls":sorted({row["document"]["url"] for row in samples}),"local_storage_nonempty_samples":sum(bool(row["document"]["localStorage"]) for row in samples),"session_storage_nonempty_samples":sum(bool(row["document"]["sessionStorage"]) for row in samples),"credential_matches":0,"later_ui_evidence":"ui-*.txt + engine timestamped access records; outside 45s DOM window","close":close},
    }
    (EVIDENCE / "4.6-evidence-audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
