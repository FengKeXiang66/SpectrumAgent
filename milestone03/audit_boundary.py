"""D1/D2 boundary audit with approved #04/#05/#07 fixed-command deltas."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "f4e5c90b8bad9144150d7d0b377834c2cc9909e2"
TASK07_BASE = "e8eea56"
TASK07_12_6_BASE = "ecaef1a"


def read(path):
    return (ROOT / path).read_text("utf-8")


def original(path, revision=BASE):
    return subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT).decode("utf-8")


def main():
    source = read("src-tauri/src/main.rs")
    old_source = original("src-tauri/src/main.rs")
    release = source.split("#[cfg(not(debug_assertions))]", 1)[1].split("let app", 1)[0]
    literal = re.search(r"tauri::generate_handler!\[[^\]]+\]", release).group()
    expected = "tauri::generate_handler![engine_status, retry_engine, run_smoke, open_data_directory, datasets_forward, annotations_forward, preprocess_forward, agent_forward, settings_forward, annotations_draft_forward]"
    assert literal == expected
    dev_handler = lambda text: re.search(r"let builder = builder.invoke_handler\((tauri::generate_handler!\[[^\]]+\])\)", text).group(1)
    assert dev_handler(source) == expected
    assert dev_handler(source).replace(", annotations_forward", "").replace(", preprocess_forward", "").replace(", agent_forward", "").replace(", settings_forward", "").replace(", annotations_draft_forward", "") == dev_handler(old_source)
    task07_source = original("src-tauri/src/main.rs", TASK07_BASE)
    assert dev_handler(source).replace(", agent_forward", "").replace(", settings_forward", "").replace(", annotations_draft_forward", "") == dev_handler(task07_source)
    task07_release = task07_source.split("#[cfg(not(debug_assertions))]", 1)[1].split("let app", 1)[0]
    assert literal.replace(", agent_forward", "").replace(", settings_forward", "").replace(", annotations_draft_forward", "") == re.search(r"tauri::generate_handler!\[[^\]]+\]", task07_release).group()
    prior_source = original("src-tauri/src/main.rs", TASK07_12_6_BASE)
    assert dev_handler(source).replace(", annotations_draft_forward", "") == dev_handler(prior_source)
    prior_release = prior_source.split("#[cfg(not(debug_assertions))]", 1)[1].split("let app", 1)[0]
    assert literal.replace(", annotations_draft_forward", "") == re.search(r"tauri::generate_handler!\[[^\]]+\]", prior_release).group()
    assert read("src-tauri/src/annotation.rs") == original("src-tauri/src/annotation.rs", TASK07_12_6_BASE)
    assert "#[cfg(debug_assertions)]\n#[tauri::command]\nasync fn datasets_forward" not in source
    assert "#[cfg(debug_assertions)]\n#[tauri::command]\nasync fn annotations_forward" not in source
    assert "#[cfg(debug_assertions)]\n#[tauri::command]\nasync fn preprocess_forward" not in source
    lib = read("src-tauri/src/lib.rs")
    assert "#[cfg(debug_assertions)]\npub mod dev_engine;" in lib
    assert "#[cfg(debug_assertions)]\npub mod datasets_dev;" not in lib
    assert "pub mod annotation;" in lib and "#[cfg(debug_assertions)]\npub mod annotation;" not in lib
    for domain in ("agent", "settings", "annotations_draft"):
        assert f"pub mod {domain};" in lib
        assert f"#[cfg(debug_assertions)]\npub mod {domain};" not in lib
        assert f"#[cfg(debug_assertions)]\n#[tauri::command]\nasync fn {domain}_forward" not in source
    command_functions = lambda text: re.findall(r"#\[tauri::command\]\s+(?:async )?fn ([a-z_]+)", text)
    assert command_functions(source) == command_functions(task07_source) + ["agent_forward", "settings_forward", "annotations_draft_forward"]
    assert command_functions(source) == command_functions(prior_source) + ["annotations_draft_forward"]
    isolated = ["src-tauri/src/dev_engine.rs", "src-tauri/src/dev_supervision.rs", "src-tauri/src/process.rs", "src-tauri/src/win32.rs", "src-tauri/src/handshake.rs", "src-tauri/src/engine_path.rs"]
    assert all(read(path) == original(path) for path in isolated)
    assert "#[cfg(debug_assertions)]\n#[path = \"dev_supervision.rs\"]" in read("src-tauri/src/supervisor.rs")
    capability = json.loads(read("src-tauri/capabilities/main.json"))
    old_permissions = json.loads(original("src-tauri/capabilities/main.json"))["permissions"]
    assert capability["permissions"].count("allow-annotations-forward") == 1
    assert capability["permissions"].count("allow-preprocess-forward") == 1
    added_permissions = ["allow-agent-forward", "allow-settings-forward", "allow-annotations-draft-forward"]
    task07_permissions = json.loads(original("src-tauri/capabilities/main.json", TASK07_BASE))["permissions"]
    assert capability["permissions"] == task07_permissions + added_permissions
    assert capability["permissions"] == json.loads(original("src-tauri/capabilities/main.json", TASK07_12_6_BASE))["permissions"] + ["allow-annotations-draft-forward"]
    assert [p for p in capability["permissions"] if p not in ("allow-annotations-forward", "allow-preprocess-forward", *added_permissions)] == old_permissions
    commands = ["engine_status", "retry_engine", "run_smoke", "open_data_directory", "datasets_forward", "annotations_forward", "preprocess_forward", "agent_forward", "settings_forward", "annotations_draft_forward"]
    build_commands = re.search(r'\.commands\(&\[(.*?)\]\)', read("src-tauri/build.rs"), re.S).group(1)
    assert re.findall(r'"([a-z_]+)"', build_commands) == commands
    acl = json.loads(read("src-tauri/gen/schemas/acl-manifests.json"))["__app-acl__"]["permissions"]
    assert {c for p in acl.values() for c in p["commands"]["allow"]} == set(commands)
    previous_build = re.search(r'\.commands\(&\[(.*?)\]\)', original("src-tauri/build.rs", TASK07_BASE), re.S).group(1)
    assert commands == re.findall(r'"([a-z_]+)"', previous_build) + ["agent_forward", "settings_forward", "annotations_draft_forward"]
    prior_build = re.search(r'\.commands\(&\[(.*?)\]\)', original("src-tauri/build.rs", TASK07_12_6_BASE), re.S).group(1)
    assert commands == re.findall(r'"([a-z_]+)"', prior_build) + ["annotations_draft_forward"]
    previous_acl = json.loads(original("src-tauri/gen/schemas/acl-manifests.json", TASK07_BASE))["__app-acl__"]["permissions"]
    assert {key: value for key, value in acl.items() if key in previous_acl} == previous_acl
    assert set(acl) - set(previous_acl) == {f"{action}-{domain}-forward" for action in ("allow", "deny") for domain in ("agent", "settings", "annotations-draft")}
    prior_acl = json.loads(original("src-tauri/gen/schemas/acl-manifests.json", TASK07_12_6_BASE))["__app-acl__"]["permissions"]
    assert {key: value for key, value in acl.items() if key in prior_acl} == prior_acl
    assert set(acl) - set(prior_acl) == {"allow-annotations-draft-forward", "deny-annotations-draft-forward"}
    config = json.loads(read("src-tauri/tauri.conf.json"))
    assert config["version"] == "0.1.3" and config["identifier"] == "com.spectrumagent.desktop"
    previous = json.loads(original("src-tauri/tauri.conf.json"))
    # 授权变更字段：version（升版）与 app.security.csp（2026-10-22 hotfix，见下）。
    # 其余字段仍必须与 BASE 逐字一致，防止顺手改配置。
    def strip_csp(payload):
        payload = json.loads(json.dumps(payload))
        payload.pop("version", None)
        payload.get("app", {}).get("security", {}).pop("csp", None)
        return payload
    assert strip_csp(config) == strip_csp(previous)
    # csp 只允许"原样插入 img-src 'self' data:; "这一处，移除后必须与 BASE 完全一致。
    assert "img-src 'self' data:" in config["app"]["security"]["csp"]
    assert config["app"]["security"]["csp"].replace("img-src 'self' data:; ", "") == previous["app"]["security"]["csp"]
    assert read("backend/__init__.py") == original("backend/__init__.py")
    assert "import.meta.env.DEV && <DatasetPanel" not in read("src/App.tsx")
    baseline = json.loads(read("milestone03/evidence/P0/baseline.json"))["locks"]
    assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest for path,digest in baseline.items())
    old_revision = "artifacts/step2/revision-20261018-smoke-headers"
    assert not subprocess.check_output(["git","diff",BASE,"--",old_revision],cwd=ROOT)
    historical_evidence = ["milestone03/evidence", "milestone05/evidence"]
    assert not subprocess.check_output(["git", "diff", TASK07_12_6_BASE, "--", "milestone07/evidence/12.4"], cwd=ROOT)
    assert not subprocess.check_output(["git", "diff", TASK07_BASE, "--", *historical_evidence], cwd=ROOT)
    # Compare canonical Git blobs: Windows checkout CRLF is not a content delta.
    evidence_hashes = {}
    for path in subprocess.check_output(["git", "ls-tree", "-r", "--name-only", TASK07_BASE, "--", *historical_evidence], cwd=ROOT).decode().splitlines():
        previous_bytes = subprocess.check_output(["git", "show", TASK07_BASE + ":" + path], cwd=ROOT)
        current_blob = subprocess.check_output(["git", "hash-object", "--path", path, path], cwd=ROOT).strip()
        previous_blob = subprocess.check_output(["git", "rev-parse", TASK07_BASE + ":" + path], cwd=ROOT).strip()
        assert current_blob == previous_blob, path
        evidence_hashes[path] = hashlib.sha256(previous_bytes).hexdigest()
    result = {"authorization":"TASK-03 D1=A; D2=0.1.1; TASK-04 §5.7 annotations_forward only (2026-10-20); TASK-05 §11.5 preprocess_forward approved 2026-10-21; TASK-07 12.4 R11/R12 agent_forward + settings_forward only", "prior_milestone_head":BASE,
              "release_handler_literal":literal,"release_handler_count":10,"dev_handler_matches_release":True,
              "commands":commands,"only_added_command":"annotations_forward,preprocess_forward,agent_forward,settings_forward",
              "unchanged_debug_adoption_and_identity_files":isolated,"only_added_permission":"allow-annotations-forward,allow-preprocess-forward,allow-agent-forward,allow-settings-forward",
              "task07_delta":{"base":TASK07_BASE,"added_commands":["agent_forward","settings_forward","annotations_draft_forward"],"added_permissions":added_permissions,"dev_release_build_acl_equal":True,"historical_evidence_sha256":evidence_hashes},
              "product_version":"0.1.3","protocol_version":"0.1.0","locks_unchanged":baseline,
              "old_revision_tracked_diff_empty":True,"frontend_dataset_panel_release_enabled":True}
    result["authorization"] += "; TASK-07 12.6 R19/R20/R21/R22 annotations_draft_forward only"
    result["only_added_command"] += ",annotations_draft_forward"
    result["only_added_permission"] += ",allow-annotations-draft-forward"
    result["task07_12_6_delta"] = {"base": TASK07_12_6_BASE, "added_commands": ["annotations_draft_forward"],
                                  "added_permissions": ["allow-annotations-draft-forward"], "legacy_annotation_unchanged": True}
    # Keep historical #03 evidence immutable; this approved extension has its own evidence.
    output = ROOT / "milestone07/evidence/12.6/boundary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
