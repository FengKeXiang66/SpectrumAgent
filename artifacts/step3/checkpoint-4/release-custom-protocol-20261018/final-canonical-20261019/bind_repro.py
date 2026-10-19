"""Bind the explicit production build to exact shell bytes and sealed engine resources."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(r"E:\AI_Agent")
OUT = ROOT / "artifacts/step3/checkpoint-4/release-custom-protocol-20261018/final-canonical-20261019"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    release = ROOT / "src-tauri/target/repro-check/release"
    shell = release / "spectrum-agent.exe"
    manifest_path = ROOT / "artifacts/step2/revision-20261018-smoke-headers/product-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resource = release / "resources/backend"
    actual = {p.relative_to(resource).as_posix(): (p.stat().st_size, sha(p)) for p in resource.rglob("*") if p.is_file()}
    expected = {x["path"]: (x["bytes"], x["sha256"]) for x in manifest["files"]}
    assert actual == expected and len(actual) == 544
    fingerprint = release / ".fingerprint"
    collected = []
    for name in ["bin-spectrum-agent.json", "lib-spectrum_agent.json", "build-script-build-script-build.json"]:
        matching = []
        for path in fingerprint.glob("spectrum-agent-*/" + name):
            data = json.loads(path.read_text())
            if data["features"] == '["custom-protocol"]':
                matching.append((path, data))
        assert matching, f"production fingerprint absent: {name}"
        path, data = max(matching, key=lambda x: x[0].stat().st_mtime_ns)
        assert "test-probes" not in data["features"]
        collected.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "contents": data})
    digest = sha(shell)
    backup = OUT / "temp" / ("canonical-" + digest[:12])
    assert not backup.exists()
    backup.mkdir(parents=True)
    shutil.copy2(shell, backup / shell.name)
    shutil.copytree(release / "resources", backup / "resources")
    result = {"source_commit": subprocess.check_output(["git", "rev-parse", "a53030d"], cwd=ROOT, text=True).strip(),
              "recorded_at": datetime.now(timezone.utc).isoformat(), "features": "custom-protocol",
              "test_probes_enabled": False, "shell_path": str(shell), "shell_sha256": digest,
              "shell_bytes": shell.stat().st_size, "engine_manifest": str(manifest_path),
              "engine_manifest_sha256": sha(manifest_path), "engine_sha256": sha(resource / "app.exe"),
              "engine_artifact_source_commit": manifest["artifact_source_commit"],
              "engine_manifest_generator_commit": manifest["manifest_generator_commit"],
              "resource_files": len(actual), "resource_bytes": sum(x[0] for x in actual.values()),
              "resource_full_manifest_match": True, "canonical_backup": str(backup), "fingerprints": collected}
    with (OUT / "candidate-repro.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
