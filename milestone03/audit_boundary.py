"""Read-only D1/D2 boundary audit. Does not rewrite milestone02 history."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "f4e5c90b8bad9144150d7d0b377834c2cc9909e2"


def read(path):
    return (ROOT / path).read_text("utf-8")


def original(path):
    return subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT).decode("utf-8")


def main():
    source = read("src-tauri/src/main.rs")
    old_source = original("src-tauri/src/main.rs")
    release = source.split("#[cfg(not(debug_assertions))]", 1)[1].split("let app", 1)[0]
    literal = re.search(r"tauri::generate_handler!\[[^\]]+\]", release).group()
    expected = "tauri::generate_handler![engine_status, retry_engine, run_smoke, open_data_directory, datasets_forward]"
    assert literal == expected
    dev_handler = lambda text: re.search(r"let builder = builder.invoke_handler\((tauri::generate_handler!\[[^\]]+\])\)", text).group(1)
    assert dev_handler(source) == dev_handler(old_source)
    assert "#[cfg(debug_assertions)]\n#[tauri::command]\nasync fn datasets_forward" not in source
    lib = read("src-tauri/src/lib.rs")
    assert "#[cfg(debug_assertions)]\npub mod dev_engine;" in lib
    assert "#[cfg(debug_assertions)]\npub mod datasets_dev;" not in lib
    isolated = ["src-tauri/src/dev_engine.rs", "src-tauri/src/dev_supervision.rs", "src-tauri/src/process.rs", "src-tauri/src/win32.rs", "src-tauri/src/handshake.rs", "src-tauri/src/engine_path.rs"]
    assert all(read(path) == original(path) for path in isolated)
    assert "#[cfg(debug_assertions)]\n#[path = \"dev_supervision.rs\"]" in read("src-tauri/src/supervisor.rs")
    capability = json.loads(read("src-tauri/capabilities/main.json"))
    assert capability["permissions"] == json.loads(original("src-tauri/capabilities/main.json"))["permissions"]
    config = json.loads(read("src-tauri/tauri.conf.json"))
    assert config["version"] == "0.1.1" and config["identifier"] == "com.spectrumagent.desktop"
    previous = json.loads(original("src-tauri/tauri.conf.json"))
    assert {k:v for k,v in config.items() if k != "version"} == {k:v for k,v in previous.items() if k != "version"}
    assert read("backend/__init__.py") == original("backend/__init__.py")
    assert "import.meta.env.DEV && <DatasetPanel" not in read("src/App.tsx")
    baseline = json.loads(read("milestone03/evidence/P0/baseline.json"))["locks"]
    assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest for path,digest in baseline.items())
    old_revision = "artifacts/step2/revision-20261018-smoke-headers"
    assert not subprocess.check_output(["git","diff",BASE,"--",old_revision],cwd=ROOT)
    result = {"authorization":"TASK-03 D1=A; D2=0.1.1", "prior_milestone_head":BASE,
              "release_handler_literal":literal,"release_handler_count":5,"dev_handler_unchanged":True,
              "unchanged_debug_adoption_and_identity_files":isolated,"capability_permissions_unchanged":True,
              "product_version":"0.1.1","protocol_version":"0.1.0","locks_unchanged":baseline,
              "old_revision_tracked_diff_empty":True,"frontend_dataset_panel_release_enabled":True}
    output = ROOT / "milestone03/evidence/P2/release-boundary.json"
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n","utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
