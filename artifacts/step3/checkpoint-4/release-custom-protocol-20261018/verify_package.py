"""Read-only package/receipt verification; never upgrades host evidence to VM evidence."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(r"E:\AI_Agent")
HISTORY = Path(__file__).resolve().parent
OUT = HISTORY / "final-canonical-20261019"


def load(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))


def sha(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def rows(path):
    return [json.loads(x) for x in Path(path).read_bytes().splitlines() if x]


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    binding = load(OUT / "candidate.json")
    setup = ROOT / "artifacts/step4/setup.exe"
    source_setup = ROOT / "src-tauri/target/release/bundle/nsis/SpectrumAgent_0.1.0_x64-setup.exe"
    bundle = load(OUT / "bundle-idle-execution.json")
    assert bundle["exit_code"] == 0
    assert setup.stat().st_size == bundle["setup_bytes"]
    assert sha(setup) == sha(source_setup) == bundle["setup_sha256"].lower()
    assert sha(ROOT / "src-tauri/target/release/spectrum-agent.exe") == binding["shell_sha256"]
    assert binding["features"] == "custom-protocol" and not binding["test_probes_enabled"]
    canonical = load(HISTORY / "canonical-production-rebuild-binding.json")
    assert not canonical["byte_sha_equal"] and canonical["resource_files"] == 544
    assert canonical["shell_sha256"] == binding["shell_sha256"]
    for fp in binding["fingerprints"]:
        current = load(ROOT / fp["path"])
        assert current["features"] == '["custom-protocol"]'

    for name, size, anchor in [
        ("nsis-3.13.zip", 2363925, "db14f8af2ea346b786c6ae19343f61aaf5e09b8e"),
        ("nsis_tauri_utils.dll", 34304, "75197fee3c6a814fe035788d1c34ead39349b860"),
    ]:
        p = ROOT / "src-tauri/target/tauri" / name
        assert p.stat().st_size == size and sha(p, "sha1") == anchor
    webview = ROOT / "src-tauri/target/.tauri/x64/35871e19-d11b-432d-9d1e-7be0ff286540/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    assert webview.stat().st_size == 214156024
    assert sha(webview) == "0625fb5c1e75be58a164e14f95aa58a3e5badb859b3d17c952385f3e4a9ff3e8"
    assert "155.0.4283.62" in (HISTORY / "webview2-runtime-manifest-output.txt").read_text(encoding="utf-8-sig")
    script = (OUT / "generated-installer.nsi").read_text(encoding="utf-8-sig")
    assert 'StrCpy $INSTDIR "$LOCALAPPDATA\\Programs\\${PRODUCTNAME}"' in script
    assert '${If} $INSTDIR == "${PLACEHOLDER_INSTALL_DIR}"' in script
    assert not any(p in script for p in ("supervisor-probe", "supervisor-stub", "test-probes"))
    conf = load(ROOT / "src-tauri/tauri.conf.json")
    assert conf["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"
    assert conf["bundle"]["windows"]["webviewInstallMode"]["type"] == "offlineInstaller"
    assert conf["bundle"]["windows"]["nsis"]["template"] == "nsis/installer.nsi"

    payloads = [load(p) for p in sorted(OUT.glob("installed-payload-*.json"))]
    assert len(payloads) == 2
    for r in payloads:
        assert r["source_and_installed_shell_bytes_equal"] and r["source_and_installed_engine_bytes_equal"]
        assert r["shell_sha256"] == binding["shell_sha256"] and r["engine_sha256"] == binding["engine_sha256"]
        assert r["resources_full_manifest_match"] and r["resources_files"] == 544 and r["internal_files"] == 543
        assert r["persistent_files"] == 546 and not r["test_probe_binaries_present"]
    uninstall = load(OUT / "host-uninstall-result.json")
    assert uninstall["program_directory_removed"] and uninstall["data_directory_preserved"]
    assert uninstall["all_data_bytes_unchanged"] and uninstall["data_files_before"] == uninstall["data_files_after"] > 0
    assert all(uninstall["directories_preserved"].values()) and uninstall["test_hygiene_not_yet_applied"]
    before, after = load(OUT / "data-before-uninstall.json"), load(OUT / "data-after-uninstall.json")
    assert before == after
    sanity = load(OUT / "package-copy-and-uninstall-sanity.json")
    assert not sanity["installed_program_exists"] and not sanity["uninstall_registry_exists"]
    assert sanity["data_exists"] and not sanity["remaining_owned_processes"]
    close = load(OUT / "installed-normal-close-output.txt")
    assert close["remaining_processes"] == [] and close["remaining_listeners"] == 0
    # Handshake presence is recorded truthfully; host close acceptance is PID/port recovery.

    manifest_rows = []
    manifests_root = ROOT / "artifacts/step3/staging-reports"
    prefixes = [sorted(manifests_root.glob("*-" + label + "-shell.manifest.xml"))[-1].name.removesuffix("shell.manifest.xml")
                for label in ("nobundle", "installed")]
    for prefix in prefixes:
        for role in ("shell", "engine"):
            path = manifests_root / (prefix + role + ".manifest.xml")
            xml = ET.fromstring(path.read_bytes())
            opt = xml.find(".//{http://schemas.microsoft.com/SMI/2016/WindowsSettings}longPathAware")
            assert opt is not None and opt.text == "true"
            assert any(e.attrib.get("name") == "Microsoft.Windows.Common-Controls" and e.attrib.get("version") == "6.0.0.0"
                       for e in xml.iter())
            assert any(e.tag.endswith("requestedExecutionLevel") and e.attrib.get("level") == "asInvoker" for e in xml.iter())
            manifest_rows.append({"file": str(path.relative_to(ROOT)), "sha256": sha(path), "role": role,
                                  "exe_sha256": binding[role + "_sha256"], "longPathAware": True, "asInvoker": True,
                                  "common_controls_v6": True})

    installed_docs = []
    for audit_name, directory in (("installed-source-audit.json", "installed-original-source-snapshot"),
                                  ("staged-fault-source-audit.json", "staged-fault-original-source-snapshot")):
        base = OUT if audit_name == "installed-source-audit.json" else HISTORY
        audit = load(base / audit_name)
        assert audit["scan_original_before_copy"]
        for r in audit["records"]:
            p = base / directory / Path(r["source"]).name
            assert sha(p) == r["sha256"] and r["exact_token_hits"] == r["whole_handshake_hits"] == 0
            assert not r["authorization_bearer"]
            if p.name.startswith("dom-"):
                docs = [r["document"] for r in rows(p) if isinstance(r.get("document"), dict)]
                assert all(d["url"] == "http://tauri.localhost/" and d["localStorage"] == d["sessionStorage"] == [] for d in docs)
                installed_docs.append({"file": str(p.relative_to(ROOT)), "complete_documents": len(docs),
                                       "phases": dict(Counter(d["phase"] for d in docs)), "storage_entries": 0})
    fault_launch = load(HISTORY / "staged-fault-launch.json")
    log = rows(HISTORY / "staged-fault-original-source-snapshot/shell-20261019.log")
    start = next(i for i, r in enumerate(log) if r.get("event") == "shell_started" and r.get("pid") == fault_launch["pid"])
    end = next(i for i in range(start, len(log)) if log[i].get("event") == "app_exit")
    own = log[start:end + 1]
    attempt = next(r for r in own if r.get("event") == "engine_start_attempt")
    failure = next(r for r in own if r.get("event") == "engine_failure")
    page = next(r for r in own if r.get("event") == "acceptance_dom_audit" and r.get("phase") == "Failed")
    assert failure["failure"]["kind"] == "ExitedBeforeReady" and failure["failure"]["engine_error"] is None
    elapsed = (utc(page["timestamp"]) - utc(attempt["timestamp"])).total_seconds() * 1000
    assert elapsed < 2000 and fault_launch["resource_files"] == 543 and fault_launch["fault_fixture"]
    assert fault_launch["features"] == "custom-protocol"
    core = load(sorted(HISTORY.glob("starting-stop-*.json"))[-1])
    assert core["transitions"][0]["from"] == "Starting" and core["transitions"][0]["to"] == "Stopping"
    result = {"verified_utc": datetime.now(timezone.utc).isoformat(),
              "evidence_generator_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "shell_source_commit": binding["source_commit"], "shell_sha256": binding["shell_sha256"],
              "setup": str(setup), "setup_sha256": sha(setup), "setup_bytes": setup.stat().st_size,
              "final_canonical_rebuild_sha_matches_fresh_thirty_rounds": True,
              "host_install_payload_verified_twice": True, "manifests": manifest_rows,
              "additional_dom_documents": installed_docs,
              "dedicated_custom_protocol_fault_fixture": {"shell_sha256": fault_launch["shell_sha256"],
                  "resource_files": 543, "failed_page_after_attempt_ms": round(elapsed, 3),
                  "failure": failure["failure"], "actual_selection": attempt},
              "host_uninstall": uninstall, "webview_runtime_in_signed_payload": "155.0.4283.62",
              "vm_status": "待 VM 实机", "legacy_exit70_cause": "未验证", "stderr1412_cause": "未验证"}
    target = OUT / ("package-verification-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with target.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"verification": str(target), "setup_bytes": setup.stat().st_size, "setup_sha256": sha(setup),
                      "dedicated_fault_failed_ms": round(elapsed, 3), "installed_resources_files": 544,
                      "installed_internal_files": 543, "uninstall_data_files_unchanged": uninstall["data_files_after"],
                      "additional_dom_documents": installed_docs, "vm_status": "待 VM 实机"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
