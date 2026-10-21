"""Resource/byte checks plus real, isolated frozen HTTP startup and domain smoke."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src-python")]
from backend.identity import process_created_at_for_pid


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_data(root=ROOT / "src-python" / "spectrumagent"):
    # The package currently has four JSON resources. Automatically include future
    # JSON additions in the same regression check, rather than only plastic.json.
    return {path.relative_to(root).as_posix(): path for path in sorted(root.rglob("*.json"))}


def verify_data(directory, source=ROOT / "src-python" / "spectrumagent"):
    checks = []
    for relative, original in package_data(source).items():
        target = Path(directory) / "_internal" / "spectrumagent" / relative
        if not target.is_file():
            raise ValueError(f"Frozen package data missing: {relative}")
        if sha(original) != sha(target):
            raise ValueError(f"Frozen package data differs from source: {relative}")
        checks.append({"path": "_internal/spectrumagent/"+relative, "bytes": target.stat().st_size, "sha256": sha(target)})
    if not checks:
        raise ValueError("No source package JSON resources found")
    return checks


def inventory(directory):
    root = Path(directory)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Reparse path in frozen payload: {path}")
        if path.is_file():
            entries.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
    return entries


def stage(source, build_root):
    source, build_root = Path(source).resolve(), Path(build_root).resolve()
    destination = ROOT / "src-tauri" / "resources" / "backend"
    backup = build_root / "prior-resources-backend"
    for path in (source, build_root, destination, backup):
        if not path.resolve().is_relative_to(ROOT) or path.resolve() == ROOT:
            raise ValueError(f"Staging path must remain in the workspace: {path}")
    expected = inventory(source)
    verify_data(source)
    if backup.exists():
        raise ValueError("Do not overwrite a previous stage backup")
    if destination.is_symlink() or destination.is_junction():
        raise ValueError("Refuse a linked stage directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.rename(backup)
    shutil.copytree(source, destination)
    if inventory(destination) != expected:
        raise ValueError("Staged backend byte inventory differs")
    result = {"source": str(source), "destination": str(destination), "previous_stage": str(backup), "files": expected}
    (build_root / "stage-inventory.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", "utf-8")


def smoke(exe, output):
    exe, output = Path(exe).resolve(), Path(output).resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError("Smoke output must be an isolated workspace directory")
    output.mkdir(parents=True, exist_ok=False)
    report = {"exe": str(exe), "exe_sha256": sha(exe), "passed": False, "events": [],
              "package_data": verify_data(exe.parent), "runtime": str(output / "data"),
              "annotation_purpose": "synthetic integration regions on real pe; not human annotation quality"}
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "SPECTRUM_ENGINE_EXE", "GDAL_DATA", "PROJ_DATA", "PROJ_LIB"):
        env.pop(key, None)
    # Verify the onedir does not borrow Python or DLLs from the development PATH.
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    env["PATH"] = os.pathsep.join(map(str, (windows, windows / "System32")))
    env["TEMP"] = env["TMP"] = str(output)
    env["PYTHONIOENCODING"] = "utf-8"
    process = None
    identity = None
    token = None
    try:
        with (output / "stdio.txt").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(exe), "--data-root", report["runtime"]], cwd=output,
                                       env=env, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            handshake = output / "data/run/handshake.json"
            deadline = time.monotonic()+60
            while not handshake.is_file():
                if process.poll() is not None:
                    raise ValueError(f"Frozen engine exited before handshake: {process.returncode}; see {output / 'stdio.txt'}")
                if time.monotonic() > deadline:
                    raise ValueError("Frozen engine readiness deadline exceeded; see smoke logs")
                time.sleep(.1)
            identity = json.loads(handshake.read_text("utf-8"))
            token = identity["token"]
            assert process_created_at_for_pid(identity["pid"]) == identity["process_created_at"]
            report["identity"] = {key: identity[key] for key in ("pid", "boot_id", "version", "port")}
            with httpx.Client(base_url=f"http://127.0.0.1:{identity['port']}", trust_env=False, timeout=300,
                              headers={"Authorization": "Bearer "+token}) as client:
                def call(method, route, body=None):
                    response = client.request(method, route, **({"json": body} if body is not None else {}))
                    assert response.status_code == 200, (route, response.status_code, response.text[:400])
                    assert token.encode() not in response.content
                    data = response.json()
                    assert token not in json.dumps(data)
                    if route == "/health":
                        assert data["pid"] == identity["pid"] and data["boot_id"] == identity["boot_id"]
                    else:
                        assert response.headers["X-SpectrumAgent-Boot-Id"] == identity["boot_id"]
                        assert int(response.headers["X-SpectrumAgent-Pid"]) == identity["pid"]
                    report["events"].append({"method": method, "path": route, "status": response.status_code})
                    return data
                assert call("GET", "/health")["version"] == "0.1.0"
                projects = call("GET", "/api/v1/projects")
                labels = call("GET", "/api/v1/labels?project_id="+projects[0]["id"])
                catalog = call("GET", "/api/v1/catalog/plastic")
                assert len(catalog) == 21
                assert {entry["code"]: entry["name"] for entry in catalog}["PS"] == "聚苯乙烯"
                label_ids = {label["code"]: label["id"] for schema in labels for label in schema["labels"]}
                assert {"PE", "PET", "PP", "BG"} <= label_ids.keys()
                recipes = call("GET", "/api/v1/preprocess/recipes")
                recipe = next(r for r in recipes if r["code"] == "plastic-snv-sg1")
                assert [s["op"] for s in recipe["versions"][0]["pipeline"]["steps"]] == ["snv", "sg_derivative"]
                header = Path((ROOT / "milestone04/evidence/calibration/cubes_11.txt").read_text("utf-8").splitlines()[0])
                assert header.is_file(), "Frozen release smoke requires the real pe cube"
                record = call("POST", "/api/v1/datasets/import", {"path": str(header)})["datasets"][0]
                source_hashes = {record["dataset"][key]: sha(record["dataset"][key]) for key in ("header_path", "data_path")}
                base = "/api/v1/datasets/"+record["id"]
                divided = call("POST", base+"/superpixels", {})
                assert divided["superpixel_count"] > 0 and divided["params"]["pca_components"] == 5
                call("POST", base+"/diffuse", {"seed": {"point": [29, 64]}})
                call("POST", base+"/annotations/regions", {"label_id": label_ids["PE"], "action": "confirm",
                     "geometry": {"polygon": [[20, 20], [20, 45], [45, 45], [45, 20]]}})
                version = call("POST", base+"/annotations/save", {})
                run = call("POST", base+"/preprocess/runs", {"annotation_version_id": version["id"],
                           "recipe_version_id": recipe["versions"][0]["id"]})
                assert run["status"] == "succeeded", run["error"]
                data = call("GET", f"/api/v1/preprocess/runs/{run['id']}/artifacts/report")
                assert data["curves"]["classes"] and data["b01"]["meta"]["branch"] == "scale"
                assert all(sha(path) == before for path, before in source_hashes.items())
                report.update(catalog_count=21, superpixels=divided["superpixel_count"], run_status=run["status"],
                              curves_classes=len(data["curves"]["classes"]), sources_unchanged=True)
        report["passed"] = True
    except BaseException as error:
        report["failure"] = {"type": type(error).__name__, "detail": str(error)}
        raise
    finally:
        if identity and process_created_at_for_pid(identity["pid"]) == identity["process_created_at"]:
            os.kill(identity["pid"], signal.SIGTERM)
        if process is not None:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
            report["stopped"] = process.poll() is not None and (not identity or process_created_at_for_pid(identity["pid"]) is None)
        if token:
            logs = [output / "stdio.txt", *(output / "data/logs").glob("*.jsonl")]
            assert all(token not in p.read_text("utf-8", errors="replace") for p in logs)
        (output / "smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", "utf-8")
    assert report["passed"] and report["stopped"]
    print(json.dumps({"passed": True, "exe": str(exe), "catalog": 21, "run": report["run_status"]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    frozen = sub.add_parser("smoke")
    frozen.add_argument("--exe", required=True)
    frozen.add_argument("--output", required=True)
    copy = sub.add_parser("stage")
    copy.add_argument("--source", required=True)
    copy.add_argument("--build-root", required=True)
    assets = sub.add_parser("assets")
    assets.add_argument("--directory", required=True)
    args = parser.parse_args()
    if args.operation == "smoke":
        smoke(args.exe, args.output)
    elif args.operation == "stage":
        stage(args.source, args.build_root)
    else:
        print(json.dumps(verify_data(args.directory), ensure_ascii=False))


if __name__ == "__main__":
    main()
