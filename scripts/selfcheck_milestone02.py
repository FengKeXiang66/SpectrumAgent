r"""Repeatable live-HTTP check of the DEV ONLY Python entry, synthetic source only.

Run with E:\AI_Agent\.venv\Scripts\python.exe. Temporary source/data/logs stay
under .runtime. Forced child termination and temporary-folder removal in finally
are TEST HYGIENE, never evidence of the product's Job/handshake cleanup.
"""
import base64
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
        header, _, _ = cube(work / "source")
        stdout = (work / "stdout.txt").open("wb")
        process = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/dev_sidecar.py"), "--data-root", str(work / "app")], stdout=stdout, stderr=subprocess.STDOUT, cwd=ROOT)
        credential = None
        handshake = None
        try:
            handshake_path = work / "app/run/handshake.json"
            deadline = time.monotonic() + 15
            while not handshake_path.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"development entry exited: code={process.returncode}")
                if time.monotonic() > deadline:
                    raise RuntimeError("development handshake timeout")
                time.sleep(0.03)
            handshake = json.loads(handshake_path.read_text("utf-8"))
            credential = handshake["token"]
            print("PROCESS_IDENTITY", json.dumps({"launcher_pid": process.pid, "python_pid": handshake["pid"], "same_pid": handshake["pid"] == process.pid, "supervisor_acceptance": "pending_debug_identity_ruling"}))
            with httpx.Client(base_url=f"http://127.0.0.1:{handshake['port']}", trust_env=False, timeout=10) as client:
                health = client.get("/health")
                assert health.status_code == 200 and health.json()["boot_id"] == handshake["boot_id"]
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
                assert band.status_code == 200 and band.json()["raw"] is True
                print("RAW_BAND", band.status_code, band.text)
                scaled = checked("POST", f"/api/v1/datasets/{identifier}/band/2", json={"l0": 0, "l1": 2, "s0": 0, "s1": 3, "raw": False})
                assert scaled.json()["values"][0][0] == 2 / 65535
                print("SCALED_OVERRIDE", scaled.status_code, scaled.text)
                preview = checked("GET", f"/api/v1/datasets/{identifier}/preview?band=0")
                picture = preview.json()
                assert picture["width"] == 3 and picture["height"] == 2
                png = base64.b64decode(picture["png_base64"])
                assert png[:8] == b"\x89PNG\r\n\x1a\n"
                print("PREVIEW", preview.status_code, preview.text)
                missing = checked("POST", "/api/v1/datasets/import", json={"path": str(work / "absent.hdr")})
                assert missing.status_code == 400
                print("MISSING", missing.status_code, missing.text)
                with ThreadPoolExecutor(3) as pool:
                    futures = [pool.submit(checked, "POST", "/api/v1/datasets/import", json={"path": str(header), "raw": True}) for _ in range(3)]
                    assert client.get("/health").status_code == 200
                    results = [future.result() for future in futures]
                    assert all(result.status_code == 200 and result.json()["datasets"][0]["id"] == identifier for result in results)
                print("CONCURRENT_IMPORTS", json.dumps({"statuses": [result.status_code for result in results], "health": 200, "single_id": True}))
            lines = []
            for path in (work / "app/logs").glob("*.jsonl"):
                content = path.read_text("utf-8")
                assert credential not in content
                lines.extend(json.loads(line) for line in content.splitlines())
            assert lines
            print("LOG_AUDIT", json.dumps({"json_lines": len(lines), "credential_matches": 0, "runtime": "dev_python", "python": sys.version.split()[0]}))
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
            print("TEST_HYGIENE", json.dumps({"forced_popen_cleanup": True, "child_exited": process.poll() is not None, "not_product_lifecycle_evidence": True}))
    print("RESULT PASS")


if __name__ == "__main__":
    main()
