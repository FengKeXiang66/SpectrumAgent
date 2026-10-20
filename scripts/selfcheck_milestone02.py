r"""Same synthetic live-HTTP contract for the venv and frozen engine.

Run with E:\AI_Agent\.venv\Scripts\python.exe. Temporary source/data/logs stay
under .runtime. Forced child termination and temporary-folder removal in finally
are TEST HYGIENE, never evidence of the product's Job/handshake cleanup.
SPECTRUMAGENT_SELFCHECK_EXE selects a frozen app.exe; unset uses dev_sidecar.
SPECTRUMAGENT_SELFCHECK_RESULT optionally writes comparable contract results.
"""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src-python/tests/fixtures"))
from cubes import cube


def main():
    if Path(sys.executable).resolve() != ROOT / ".venv/Scripts/python.exe":
        raise RuntimeError("Use the approved explicit venv interpreter")
    scratch = ROOT / ".runtime/milestone02-http"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        work = Path(temporary)
        header, _, logical = cube(work / "source")
        invalid_header, _, _ = cube(work / "invalid-header")
        invalid_header.write_text("ENVI\nsamples = invalid\n", "utf-8")
        wrong_header, wrong_data, _ = cube(work / "wrong-size")
        with wrong_data.open("ab") as stream:
            stream.write(b"x")  # Oversize must be rejected before a reader maps it.
        def source_fingerprints():
            return {str(path.relative_to(work)): (path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                    for directory in ("source", "invalid-header", "wrong-size") for path in sorted((work / directory).iterdir())}
        original_sources = source_fingerprints()
        frozen = os.environ.get("SPECTRUMAGENT_SELFCHECK_EXE")
        runtime = "onedir" if frozen else "venv"
        if frozen:
            executable = Path(frozen)
            if not executable.is_absolute() or not executable.is_file():
                raise RuntimeError("SPECTRUMAGENT_SELFCHECK_EXE must be an existing absolute app.exe")
            command = [str(executable), "--data-root", str(work / "app")]
        else:
            command = [sys.executable, "-B", str(ROOT / "scripts/dev_sidecar.py"), "--data-root", str(work / "app")]
        print("COMMAND", json.dumps({"runtime": runtime, "argv": command}))
        stdout = (work / "stdout.txt").open("wb")
        process = subprocess.Popen(command, stdout=stdout, stderr=subprocess.STDOUT, cwd=work)
        credential = None
        handshake = None
        failed = True
        try:
            handshake_path = work / "app/run/handshake.json"
            deadline = time.monotonic() + 15
            while not handshake_path.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"{runtime} entry exited: code={process.returncode}")
                if time.monotonic() > deadline:
                    raise RuntimeError(f"{runtime} handshake timeout")
                time.sleep(0.03)
            handshake = json.loads(handshake_path.read_text("utf-8"))
            credential = handshake["token"]
            if frozen:
                assert handshake["pid"] == process.pid, "onedir expected a single engine process"
            print("PROCESS_IDENTITY", json.dumps({"launcher_pid": process.pid, "python_pid": handshake["pid"], "same_pid": handshake["pid"] == process.pid, "scope": "standalone HTTP; not a Job supervision test"}))
            with httpx.Client(base_url=f"http://127.0.0.1:{handshake['port']}", trust_env=False, timeout=10) as client:
                health = client.get("/health")
                assert health.status_code == 200 and health.json()["boot_id"] == handshake["boot_id"] and health.json()["pid"] == handshake["pid"]
                print("HEALTH", health.status_code, health.text)
                unauthorized = client.post("/api/v1/datasets/import", json={"path": str(header)})
                assert unauthorized.status_code == 401
                print("UNAUTHORIZED", unauthorized.status_code, unauthorized.text)
                client.headers["Authorization"] = "Bearer " + credential

                def checked(method, path, **kwargs):
                    response = client.request(method, path, **kwargs)
                    assert response.headers["X-SpectrumAgent-Boot-Id"] == handshake["boot_id"]
                    assert response.headers["X-SpectrumAgent-Pid"] == str(handshake["pid"])
                    assert credential not in response.text
                    return response

                first = checked("POST", "/api/v1/datasets/import", json={"path": str(header), "raw": True})
                assert first.status_code == 200
                body = first.json()
                identifier = body["datasets"][0]["id"]
                print("IMPORT", first.status_code, first.text)
                again = checked("POST", "/api/v1/datasets/import", json={"path": str(header), "raw": True})
                assert again.json()["summary"] == {"total": 1, "imported": 0, "existing": 1}
                print("IDEMPOTENT", again.status_code, json.dumps(again.json()["summary"]))
                band = checked("POST", f"/api/v1/datasets/{identifier}/band/2", json={"l0": 0, "l1": 2, "s0": 0, "s1": 3})
                assert band.status_code == 200 and band.json()["raw"] is True and band.json()["values"] == logical[:, :, 2].tolist()
                print("RAW_BAND", band.status_code, band.text)
                scaled = checked("POST", f"/api/v1/datasets/{identifier}/band/2", json={"l0": 0, "l1": 2, "s0": 0, "s1": 3, "raw": False})
                assert scaled.status_code == 200 and scaled.json()["values"] == (logical[:, :, 2] / 65535).tolist()
                print("SCALED_OVERRIDE", scaled.status_code, scaled.text)
                preview = checked("GET", f"/api/v1/datasets/{identifier}/preview?band=0")
                picture = preview.json()
                assert picture["width"] == 3 and picture["height"] == 2
                png = base64.b64decode(picture["png_base64"])
                assert png[:8] == b"\x89PNG\r\n\x1a\n"
                print("PREVIEW", preview.status_code, preview.text)
                missing = checked("POST", "/api/v1/datasets/import", json={"path": str(work / "absent.hdr")})
                assert missing.status_code == 400 and missing.json()["error"] == "FILE_NOT_FOUND"
                print("MISSING", missing.status_code, missing.text)
                errors = {"FILE_NOT_FOUND": {"status": missing.status_code, "top": missing.json()["error"]}}
                for expected, path in (("HEADER_INVALID", invalid_header), ("SIZE_MISMATCH", wrong_header)):
                    response = checked("POST", "/api/v1/datasets/import", json={"path": str(path)})
                    payload = response.json()
                    # Keep the approved atomic-batch envelope; inspect its leaf code.
                    assert response.status_code == 400 and payload["error"] == "IMPORT_BATCH_INVALID"
                    codes = [item["error"] for item in payload["context"]["items"]]
                    assert codes == [expected]
                    errors[expected] = {"status": response.status_code, "top": payload["error"], "items": codes}
                    print(expected, response.status_code, response.text)
                with ThreadPoolExecutor(3) as pool:
                    futures = [pool.submit(checked, "POST", "/api/v1/datasets/import", json={"path": str(header), "raw": True}) for _ in range(3)]
                    assert client.get("/health").status_code == 200
                    results = [future.result() for future in futures]
                    assert all(result.status_code == 200 and result.json()["datasets"][0]["id"] == identifier for result in results)
                print("CONCURRENT_IMPORTS", json.dumps({"statuses": [result.status_code for result in results], "health": 200, "single_id": True}))
                def comparable(value):
                    if isinstance(value, dict):
                        return {key: comparable(item) for key, item in value.items()
                                if key not in {"id", "dataset_id", "header_path", "data_path", "elapsed_ms"}}
                    if isinstance(value, list):
                        return [comparable(item) for item in value]
                    return value
                assert source_fingerprints() == original_sources
                contract = {"health": {key: value for key, value in health.json().items() if key not in {"boot_id", "pid"}},
                            "health_status": health.status_code, "unauthorized": {"status": unauthorized.status_code, "body": unauthorized.json()},
                            "import": comparable(body), "idempotent": {"status": again.status_code, "summary": again.json()["summary"], "same_id": again.json()["datasets"][0]["id"] == identifier},
                            "raw_band": comparable(band.json()), "scaled_override": comparable(scaled.json()),
                            "preview": {"status": preview.status_code, "width": picture["width"], "height": picture["height"], "png_sha256": hashlib.sha256(png).hexdigest()},
                            "errors": errors, "concurrent_statuses": [result.status_code for result in results], "source_bytes_and_mtime_unchanged": True}
            lines = []
            for path in (work / "app/logs").glob("*.jsonl"):
                content = path.read_text("utf-8")
                assert credential not in content
                lines.extend(json.loads(line) for line in content.splitlines())
            assert lines
            print("LOG_AUDIT", json.dumps({"json_lines": len(lines), "credential_matches": 0, "runtime": runtime, "driver_python": sys.version.split()[0]}))
            print("CONTRACT_RESULT", json.dumps(contract, ensure_ascii=False, sort_keys=True))
            result_path = os.environ.get("SPECTRUMAGENT_SELFCHECK_RESULT")
            if result_path:
                with Path(result_path).open("x", encoding="utf-8") as stream:
                    json.dump(contract, stream, ensure_ascii=False, indent=2, sort_keys=True)
            failed = False
        finally:
            # Test hygiene only: direct Popen has no product Job supervisor.
            if handshake and handshake["pid"] != process.pid:
                try:
                    os.kill(handshake["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            stdout.close()
            captured = (work / "stdout.txt").read_text("utf-8", errors="replace")
            if credential and credential in captured:
                raise RuntimeError("credential found in child output; output withheld")
            if failed:
                print("CHILD_OUTPUT_ON_FAILURE", captured)
            print("TEST_HYGIENE", json.dumps({"forced_popen_cleanup": True, "child_exited": process.poll() is not None, "not_product_lifecycle_evidence": True}))
    print("RESULT PASS")


if __name__ == "__main__":
    main()
