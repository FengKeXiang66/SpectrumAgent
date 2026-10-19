"""Verify unpacked installer payload against the exact tested production build."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(r"E:\AI_Agent")
OUT = ROOT / "artifacts/step3/checkpoint-4/release-custom-protocol-20261018/final-canonical-20261019"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    binding = json.loads((OUT / "candidate-repro.json").read_text(encoding="utf-8"))
    program = Path(os.environ["LOCALAPPDATA"]) / "Programs/SpectrumAgent"
    installed = program / "spectrum-agent.exe"
    source = ROOT / "src-tauri/target/repro-check/release/spectrum-agent.exe"
    assert installed.read_bytes() == source.read_bytes() and sha(source) == binding["shell_sha256"]
    authority = json.loads(Path(binding["engine_manifest"]).read_text(encoding="utf-8"))
    resource = program / "resources/backend"
    actual = {p.relative_to(resource).as_posix(): (p.stat().st_size, sha(p)) for p in resource.rglob("*") if p.is_file()}
    expected = {x["path"]: (x["bytes"], x["sha256"]) for x in authority["files"]}
    assert actual == expected and len(actual) == 544
    assert (resource / "app.exe").read_bytes() == (ROOT / "src-tauri/target/repro-check/release/resources/backend/app.exe").read_bytes()
    files = {p.relative_to(program).as_posix() for p in program.rglob("*") if p.is_file()}
    assert files == {"spectrum-agent.exe", "uninstall.exe"} | {"resources/backend/" + p for p in actual}
    assert not any("supervisor-probe" in p or "supervisor-stub" in p for p in files)
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "program": str(program), "features": "custom-protocol",
              "source_and_installed_shell_bytes_equal": True, "shell_sha256": sha(installed), "shell_bytes": installed.stat().st_size,
              "source_and_installed_engine_bytes_equal": True, "engine_sha256": sha(resource / "app.exe"),
              "resources_full_manifest_match": True, "resources_files": len(actual), "internal_files": sum(p.startswith("_internal/") for p in actual),
              "persistent_files": len(files), "persistent_payload": "main shell + resources/backend; NSIS generated uninstall.exe additionally present",
              "test_probe_binaries_present": False, "scope": "host installer payload; not a clean-VM claim"}
    target = OUT / ("repro-installed-payload-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with target.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
