"""Tracked dev/frozen lifecycle and packaging acceptance; no extra dependencies."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
FROZEN = ROOT / "artifacts" / "step2" / "dist" / "app" / "app.exe"
DATA = Path(os.environ["LOCALAPPDATA"]) / "SpectrumAgent"
HANDSHAKE = DATA / "run" / "handshake.json"
LOGS = DATA / "logs"
HTTP = build_opener(ProxyHandler({}))


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def redacted(value):
    if value is None:
        return None
    return {key: "<redacted>" if key == "token" else item for key, item in value.items()}


def read_handshake():
    try:
        return json.loads(HANDSHAKE.read_bytes())
    except FileNotFoundError:
        return None


def logs_for(*, boot_id=None, pids=()):
    records = []
    for path in sorted(LOGS.glob("engine-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (boot_id is not None and row.get("boot_id") == boot_id) or row.get("pid") in pids:
                records.append(row)
    return records


def write_logs(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def process_api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def signal_helper(pid, event):
    """Attach only the test injector to the engine console; change no engine handlers."""
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.FreeConsole.argtypes = []
    api.FreeConsole.restype = wintypes.BOOL
    api.AttachConsole.argtypes = [wintypes.DWORD]
    api.AttachConsole.restype = wintypes.BOOL
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    api.SetConsoleCtrlHandler.argtypes = [handler_type, wintypes.BOOL]
    api.SetConsoleCtrlHandler.restype = wintypes.BOOL
    api.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    api.FreeConsole()
    if not api.AttachConsole(pid):
        raise ctypes.WinError(ctypes.get_last_error())
    callback = handler_type(lambda event: True)  # Injector only must survive its own event.
    try:
        if not api.SetConsoleCtrlHandler(callback, True):
            raise ctypes.WinError(ctypes.get_last_error())
        if not api.GenerateConsoleCtrlEvent(event, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.2)
    finally:
        api.FreeConsole()


class Suite:
    def __init__(self, output, rounds):
        self.output = output
        self.rounds = rounds
        self.active = []
        self.tokens = set()
        self.owned_boot_ids = set()
        self.records = []
        self.launch_number = 0
        self.current = "preflight"
        self.failed = False
        self.first_launch_ms = None

    def emit(self, **row):
        self.records.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def command(self, mode, argument=None):
        command = [str(FROZEN)] if mode == "frozen" else [str(PYTHON), "-m", "backend"]
        if argument:
            command.append(argument)
        return command

    def spawn(self, mode, label, argument=None):
        self.launch_number += 1
        prefix = self.output / f"{self.launch_number:03d}-{label}"
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        env = dict(os.environ, PYTHONUTF8="1")
        if mode == "frozen":
            env["PATH"] = os.environ["SystemRoot"] + "\\System32;" + os.environ["SystemRoot"]
        stdout = prefix.with_suffix(".stdout.txt").open("wb")
        stderr = prefix.with_suffix(".stderr.txt").open("wb")
        clock = time.perf_counter()
        process = subprocess.Popen(
            self.command(mode, argument), cwd=ROOT if mode == "dev" else self.output,
            env=env, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup,
        )
        item = {"process": process, "stdout": stdout, "stderr": stderr, "prefix": prefix,
                "clock": clock, "handshake": None, "mode": mode}
        self.active.append(item)
        return item

    def health(self, handshake):
        with HTTP.open(f"http://127.0.0.1:{handshake['port']}/health", timeout=3) as response:
            result = json.load(response)
            assert response.status == 200
        assert result["boot_id"] == handshake["boot_id"] and result["pid"] == handshake["pid"]
        return result

    def start(self, mode, label):
        old = read_handshake()
        item = self.spawn(mode, label)
        process = item["process"]
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.close_streams(item)
                raise AssertionError(f"Startup exited code={process.returncode}; see {item['prefix'].name}.stderr.txt")
            current = read_handshake()
            if current and (old is None or current["boot_id"] != old["boot_id"]):
                self.health(current)
                item["handshake"] = current
                api = process_api()
                handle = api.OpenProcess(0x101000, False, current["pid"])
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                item["engine_handle"] = handle
                item["process_api"] = api
                sys.path.insert(0, str(ROOT))
                from backend.identity import process_created_at_for_pid
                assert process_created_at_for_pid(current["pid"]) == current["process_created_at"]
                self.tokens.add(current["token"])
                self.owned_boot_ids.add(current["boot_id"])
                elapsed = round((time.perf_counter() - item["clock"]) * 1000, 3)
                if mode == "frozen" and self.first_launch_ms is None:
                    self.first_launch_ms = elapsed
                if mode == "frozen":
                    assert process.pid == current["pid"], "Frozen spawn/handshake PID mismatch"
                dump(item["prefix"].with_suffix(".handshake.json"), redacted(current))
                self.emit(event="handshake_confirmed_published", mode=mode, label=label,
                          spawn_pid=process.pid, handshake=redacted(current), elapsed_ms=elapsed)
                return item
            time.sleep(0.02)
        raise AssertionError("No new healthy handshake within 35 seconds")

    def close_streams(self, item):
        item["stdout"].close()
        item["stderr"].close()

    def assert_absent(self, handshake):
        sys.path.insert(0, str(ROOT))
        from backend.identity import process_created_at_for_pid
        assert process_created_at_for_pid(handshake["pid"]) is None, "Engine PID still alive"
        with socket.socket() as stream:
            stream.settimeout(0.3)
            assert stream.connect_ex(("127.0.0.1", handshake["port"])) != 0, "Port still listening"

    def stop(self, item, kind, *, expected_absent=True, foreign=None):
        handshake = item["handshake"]
        if kind == "taskkill":
            command = [str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"), "/F", "/PID", str(handshake["pid"])]
            outcome = subprocess.run(command, capture_output=True, timeout=10)
            item["prefix"].with_suffix(".taskkill.stdout.txt").write_bytes(outcome.stdout)
            assert outcome.returncode == 0, "taskkill failed"
        else:
            event = 1 if kind == "break" else 0
            command = [str(PYTHON), str(Path(__file__).resolve()), "--inject-signal", str(handshake["pid"]), str(event)]
            outcome = subprocess.run(command, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            assert outcome.returncode == 0, f"Signal injector failed code={outcome.returncode}"
        process = item["process"]
        process.wait(timeout=15)
        api = item["process_api"]
        assert api.WaitForSingleObject(item["engine_handle"], 15000) == 0, "Actual engine did not exit"
        actual_exit_code = wintypes.DWORD()
        if not api.GetExitCodeProcess(item["engine_handle"], ctypes.byref(actual_exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        api.CloseHandle(item["engine_handle"])
        item["engine_handle"] = None
        self.close_streams(item)
        self.assert_absent(handshake)
        after = read_handshake()
        rows = logs_for(boot_id=handshake["boot_id"])
        write_logs(item["prefix"].with_suffix(".boot.jsonl"), rows)
        stopped = [row for row in rows if row.get("event") == "engine_stopped"]
        assert len(stopped) <= 1, "Duplicate engine_stopped for this boot_id"
        if kind == "break" and foreign is None:
            assert after is None, "CTRL_BREAK left handshake"
            assert len(stopped) == 1 and stopped[0]["cleanup_phase"] == "lifespan", "Missing lifespan owned cleanup"
            assert any(row["event"] == "Application shutdown complete." for row in rows)
        if foreign is not None:
            assert after == foreign, "A deleted or modified another generation's handshake"
            assert len(stopped) == 0, "Foreign-generation cleanup incorrectly logged engine_stopped"
        elif kind != "break" and after is not None:
            assert after["boot_id"] == handshake["boot_id"], "Unexpected residual owner"
        result = {"event": "exit_verified", "mode": item["mode"], "signal": kind,
                  "boot_id": handshake["boot_id"], "pid": handshake["pid"],
                  "process_created_at": handshake["process_created_at"], "port": handshake["port"],
                  "exit_code": actual_exit_code.value, "launcher_exit_code": process.returncode,
                  "pid_absent": True, "port_absent": True,
                  "engine_stopped_count": len(stopped), "handshake_exists": after is not None,
                  "residual_handshake": redacted(after),
                  "classification": ("foreign_generation_preserved" if foreign is not None else
                                     "immediate_cleanup" if kind == "break" else "recovery_path_not_graceful_exit_claim")}
        self.emit(**result)
        dump(item["prefix"].with_suffix(".exit.json"), result)
        return after

    def require_stale_event(self, item, old):
        rows = logs_for(boot_id=item["handshake"]["boot_id"])
        matches = [row for row in rows if row.get("event") == "stale_handshake_removed"]
        assert len(matches) == (1 if old is not None else 0), "Wrong per-boot stale cleanup count"
        if old is not None:
            for key in ("boot_id", "pid", "process_created_at", "port"):
                assert matches[0][f"old_{key}"] == old[key]
        self.emit(event="stale_sweep_verified", mode=item["mode"], boot_id=item["handshake"]["boot_id"],
                  stale_handshake_removed_count=len(matches), records=matches)

    def curl(self, item, path, status, name, auth=False):
        handshake = item["handshake"]
        body = self.output / f"{name}.json"
        command = ["curl.exe", "--silent", "--show-error", "--noproxy", "*", "--max-time", "20", "-o", str(body), "-w", "%{http_code}"]
        if auth:
            command += ["-H", "Authorization: Bearer " + handshake["token"]]
        command.append(f"http://127.0.0.1:{handshake['port']}{path}")
        outcome = subprocess.run(command, capture_output=True, timeout=25)
        assert outcome.returncode == 0 and int(outcome.stdout) == status
        payload = json.loads(body.read_bytes())
        self.emit(event="curl_response", path=path, http_status=status, body=payload)

    def diagnostics(self, main):
        before = HANDSHAKE.read_bytes()
        identity = main["handshake"]
        for argument in ("--selfcheck-geotiff", "--selfcheck-worker"):
            item = self.spawn("frozen", argument[2:], argument)
            item["process"].wait(timeout=30)
            self.close_streams(item)
            assert item["process"].returncode == 0
            result = json.loads(item["prefix"].with_suffix(".stdout.txt").read_bytes())
            assert HANDSHAKE.read_bytes() == before
            assert not result["engine_module_loaded"] and not result["uvicorn_module_loaded"]
            if argument == "--selfcheck-geotiff":
                assert all(result[name] is None for name in ("GDAL_DATA", "PROJ_DATA", "PROJ_LIB"))
                assert result["frozen"] and result["crs"] == "EPSG:32650"
                assert result["shape"] == [10, 12] and result["count"] == 3
                assert result["transform"] == [30, 0, 500000, 0, -30, 4000000]
                assert result["sample_removed"] and result["pixel_values_equal"]
                internal = FROZEN.parent / "_internal"
                assert Path(result["rasterio_module"]).is_relative_to(internal)
                assert Path(result["numpy_module"]).is_relative_to(internal)
            pids = [result["diagnostic_pid"]]
            if "worker_pid" in result:
                pids.append(result["worker_pid"])
                assert not result["worker_engine_module_loaded"] and not result["worker_uvicorn_module_loaded"]
            rows = logs_for(pids=pids)
            assert any(row["event"] == "diagnostic_started" for row in rows)
            forbidden = [row for row in rows if row["event"] in ("engine_boot", "engine_ready") or str(row.get("logger", "")).startswith("uvicorn")]
            assert forbidden == []
            self.health(identity)
            write_logs(item["prefix"].with_suffix(".diagnostic.jsonl"), rows)
            self.emit(event="diagnostic_isolation_verified", argument=argument,
                      main_pid=identity["pid"], main_boot_id=identity["boot_id"],
                      before_sha256=hashlib.sha256(before).hexdigest(),
                      after_sha256=hashlib.sha256(HANDSHAKE.read_bytes()).hexdigest(),
                      forbidden_engine_events=0, diagnostic=result, diagnostic_logs=rows)

    def write_handshake(self, payload):
        self.owned_boot_ids.add(payload["boot_id"])
        temporary = HANDSHAKE.with_suffix(".test.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, HANDSHAKE)

    def dead_payload(self):
        process = subprocess.Popen([str(PYTHON), "-c", "pass"], creationflags=subprocess.CREATE_NO_WINDOW)
        dead_pid = process.pid
        process.wait(timeout=10)
        payload = {"boot_id": uuid.uuid4().hex[:8], "pid": dead_pid,
                "process_created_at": "2000-01-01T00:00:00.000Z", "port": 54321,
                "token": uuid.uuid4().hex, "protocol": 1, "version": "0.1.0", "started_at": "2000-01-01T00:00:00.000Z"}
        self.tokens.add(payload["token"])
        return payload

    def rejection(self, mode, owner):
        before = HANDSHAKE.read_bytes()
        item = self.spawn(mode, "legitimate-owner-rejected")
        item["process"].wait(timeout=15)
        self.close_streams(item)
        assert item["process"].returncode != 0
        assert HANDSHAKE.read_bytes() == before, "Second engine overwrote live owner"
        # Frozen native console text may use the Windows ANSI code page; preserve
        # raw bytes and check the ASCII error code without lossy transcoding.
        stderr = item["prefix"].with_suffix(".stderr.txt").read_bytes()
        assert b"HANDSHAKE_OWNER_ALIVE" in stderr
        assert b'Uvicorn running on' not in stderr and b'Application startup complete.' not in stderr
        self.health(owner["handshake"])
        self.emit(event="legitimate_owner_protected", mode=mode, owner=redacted(owner["handshake"]),
                  challenger_spawn_pid=item["process"].pid, challenger_exit_code=item["process"].returncode,
                  handshake_bytes_unchanged=True, explicit_error="HANDSHAKE_OWNER_ALIVE", bound_service=False)

    def scenarios(self):
        for mode in ("frozen", "dev"):
            for kind in ("break", "ctrl_c", "taskkill"):
                for number in range(1, self.rounds + 1):
                    self.current = f"{mode}-{kind}-{number}"
                    assert not HANDSHAKE.exists(), "Handshake present before round; harness must not mask a failure"
                    self.emit(event="round_started", case=self.current, handshake_absent_before_start=True)
                    item = self.start(mode, self.current)
                    if mode == "frozen" and kind == "break" and number == 1:
                        self.process_inventory(item)
                        for path, status, name, auth in [("/health", 200, "health", False), ("/smoke", 401, "unauthorized", False), ("/smoke", 200, "smoke", True), ("/smoke?blocks=8", 200, "smoke-blocks", True)]:
                            self.curl(item, path, status, name, auth)
                        self.diagnostics(item)
                    residue = self.stop(item, kind)
                    if kind != "break":
                        # No deletion/rewrite here: new engine owns startup recovery.
                        recovered = self.start(mode, self.current + "-recovery")
                        assert recovered["handshake"]["boot_id"] != item["handshake"]["boot_id"]
                        assert recovered["handshake"]["port"] != item["handshake"]["port"]
                        self.require_stale_event(recovered, residue)
                        self.stop(recovered, "break")
                    self.emit(event="round_passed", case=self.current)

            self.current = f"{mode}-foreign-handshake"
            a = self.start(mode, self.current + "-A")
            foreign = self.dead_payload()
            self.write_handshake(foreign)
            self.emit(event="foreign_handshake_injected", mode=mode, old=redacted(foreign))
            self.stop(a, "break", foreign=foreign)
            b = self.start(mode, self.current + "-B")
            self.require_stale_event(b, foreign)
            self.stop(b, "break")

            self.current = f"{mode}-live-owner"
            owner = self.start(mode, self.current)
            self.rejection(mode, owner)
            self.stop(owner, "break")

            self.current = f"{mode}-pid-reuse"
            reused = self.dead_payload()
            sys.path.insert(0, str(ROOT))
            from backend.identity import process_created_at_for_pid
            reused["pid"] = os.getpid()  # Real live process, deliberately incorrect creation time.
            assert process_created_at_for_pid(reused["pid"]) != reused["process_created_at"]
            self.write_handshake(reused)
            item = self.start(mode, self.current)
            self.require_stale_event(item, reused)
            rows = logs_for(boot_id=item["handshake"]["boot_id"])
            assert any(row.get("reason") == "pid_reused" for row in rows)
            self.stop(item, "break")

    def process_inventory(self, item):
        tasklist = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq app.exe"], capture_output=True, check=True)
        (self.output / "tasklist.txt").write_bytes(tasklist.stdout)
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        query = "Get-CimInstance Win32_Process -Filter \"Name = 'app.exe'\" | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        cim = subprocess.run([str(powershell), "-NoProfile", "-Command", query], capture_output=True, check=True)
        (self.output / "process-cim.json").write_bytes(cim.stdout)
        rows = json.loads(cim.stdout)
        rows = rows if isinstance(rows, list) else [rows]
        assert len(rows) == 1 and rows[0]["ProcessId"] == item["handshake"]["pid"]
        self.emit(event="process_inventory", process_count=len(rows), cim=rows,
                  tasklist_stdout=tasklist.stdout.decode("mbcs"))

    def missing_dll(self):
        self.current = "frozen-missing-dll"
        assert not HANDSHAKE.exists()
        dll = FROZEN.parent / "_internal/python312.dll"
        backup = self.output / "python312.dll.test-backup"
        assert dll.resolve().is_relative_to(ROOT) and backup.resolve().is_relative_to(ROOT)
        original = dll.read_bytes()
        backup.write_bytes(original)
        dll.unlink()
        try:
            outcome = subprocess.run([str(FROZEN)], capture_output=True, timeout=10,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            (self.output / "missing-dll.stdout.txt").write_bytes(outcome.stdout)
            (self.output / "missing-dll.stderr.txt").write_bytes(outcome.stderr)
            assert outcome.returncode != 0
            assert b"Failed to load Python DLL" in outcome.stderr and b"python312.dll" in outcome.stderr
            assert b"Traceback (most recent call last)" not in outcome.stderr
            assert not HANDSHAKE.exists()
            self.emit(event="missing_dll_verified", exit_code=outcome.returncode,
                      native_stderr=outcome.stderr.decode("utf-8", errors="backslashreplace"))
        finally:
            os.replace(backup, dll)
            assert hashlib.sha256(dll.read_bytes()).digest() == hashlib.sha256(original).digest()

    def mutex_edge_cases(self):
        sys.path.insert(0, str(ROOT))
        from backend.startup_mutex import StartupMutex, _kernel, MUTEX_NAME
        self.current = "frozen-mutex-timeout"
        assert not HANDSHAKE.exists()
        with StartupMutex():
            item = self.spawn("frozen", "mutex-timeout")
            item["process"].wait(timeout=40)
            self.close_streams(item)
            elapsed = (time.perf_counter() - item["clock"]) * 1000
            stderr = item["prefix"].with_suffix(".stderr.txt").read_bytes()
            assert item["process"].returncode != 0 and b"STARTUP_MUTEX_TIMEOUT" in stderr
            assert b"Application startup complete." not in stderr and not HANDSHAKE.exists()
            assert elapsed >= 29500
        self.emit(event="mutex_timeout_verified", timeout_ms=30000, elapsed_ms=round(elapsed, 3),
                  exit_code=item["process"].returncode, bound_service=False, handshake_exists=False)

        self.current = "frozen-mutex-abandoned"
        api = _kernel()
        keeper = api.CreateMutexW(None, False, MUTEX_NAME)  # Keep the object alive, do not acquire.
        assert keeper
        ready = self.output / "mutex-holder-ready.json"
        holder = subprocess.Popen([str(PYTHON), str(Path(__file__).resolve()), "--hold-mutex", str(ready)],
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                assert holder.poll() is None
                time.sleep(0.02)
            assert ready.exists(), "Mutex holder never acquired ownership"
            holder.kill()
            holder.wait(timeout=10)
            item = self.start("frozen", "mutex-abandoned")
            rows = logs_for(boot_id=item["handshake"]["boot_id"])
            abandoned = [row for row in rows if row["event"] == "startup_mutex_abandoned"]
            assert len(abandoned) == 1
            self.emit(event="mutex_abandoned_verified", boot_id=item["handshake"]["boot_id"], records=abandoned)
            self.stop(item, "break")
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=10)
            api.CloseHandle(keeper)

    def run(self):
        try:
            self.output.mkdir(parents=True, exist_ok=False)
            inputs = list((ROOT / "backend").glob("*.py")) + [
                Path(__file__).resolve(), ROOT / "artifacts/step2/selfcheck_step2.ps1",
                ROOT / "artifacts/step2/build.spec", ROOT / "requirements-lock.txt",
            ]
            dump(self.output / "input-sha256.json", {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs
            })
            sys.path.insert(0, str(ROOT))
            from backend.handshake import read_snapshot
            snapshot = read_snapshot(HANDSHAKE, phase="test_preflight")
            old = snapshot.payload if snapshot is not None else None
            if old is not None:
                sys.path.insert(0, str(ROOT))
                from backend.handshake import ownership
                assert ownership(old) != "live_owner", "A legitimate engine is already running"
                self.tokens.add(old["token"])
                self.emit(event="preflight_test_hygiene", purpose="before all launches only; not acceptance evidence", old=redacted(old))
                assert HANDSHAKE.read_bytes() == snapshot.raw, "Historical handshake changed before hygiene"
                HANDSHAKE.unlink()
            assert not HANDSHAKE.exists()
            self.scenarios()
            self.mutex_edge_cases()
            self.missing_dll()
            internal = FROZEN.parent / "_internal"
            files = [path for path in internal.rglob("*") if path.is_file()]
            dlls = list((internal / "rasterio.libs").glob("*.dll"))
            pyds = list((internal / "rasterio").glob("*.pyd"))
            self.emit(event="bundle_inventory", internal_file_count=len(files),
                      internal_bytes=sum(path.stat().st_size for path in files),
                      exe_bytes=FROZEN.stat().st_size, rasterio_dll_count=len(dlls), rasterio_pyd_count=len(pyds))
            assert len(files) == 543 and len(dlls) == 36 and len(pyds) == 15
            for path in LOGS.glob("engine-*.jsonl"):
                content = path.read_text(encoding="utf-8")
                assert all(token not in content for token in self.tokens), "Handshake token leaked in engine log"
            self.emit(event="regression_passed", matrix_rounds=2 * 3 * self.rounds,
                      rounds_per_signal_per_mode=self.rounds, token_leaks=0, handshake_absent=not HANDSHAKE.exists(),
                      first_frozen_launch_ms=self.first_launch_ms)
        except Exception as exc:
            self.failed = True
            leftover = self.failure_snapshot()
            self.emit(event="regression_failed", case=self.current, error=str(exc), residual_handshake=redacted(leftover))
        finally:
            for item in self.active:
                if item["process"].poll() is None:
                    self.emit(event="TEST_HYGIENE_ONLY", action="force_terminate_test_process", spawn_pid=item["process"].pid)
                    # /T includes the dev venv launcher's actual Python child.
                    subprocess.run(["taskkill.exe", "/F", "/T", "/PID", str(item["process"].pid)],
                                   capture_output=True, timeout=10)
                    item["process"].wait(timeout=10)
                self.close_streams(item)
                if item.get("engine_handle"):
                    item["process_api"].CloseHandle(item["engine_handle"])
                    item["engine_handle"] = None
            leftover = self.failure_snapshot()
            if self.failed and leftover and leftover.get("boot_id") in self.owned_boot_ids:
                before = HANDSHAKE.read_bytes()
                reread_owner = json.loads(before)
                if reread_owner.get("boot_id") in self.owned_boot_ids and HANDSHAKE.read_bytes() == before:
                    self.emit(event="TEST_HYGIENE_ONLY", action="remove_owned_residue_after_failure", residual_handshake=redacted(reread_owner))
                    HANDSHAKE.unlink()
            dump(self.output / "summary.json", {"passed": not self.failed, "failed_case": self.current if self.failed else None,
                                                 "rounds_per_signal_per_mode": self.rounds, "matrix_rounds": 2 * 3 * self.rounds,
                                                 "first_frozen_launch_ms": self.first_launch_ms, "records": self.records})
        return 1 if self.failed else 0

    def failure_snapshot(self):
        try:
            return read_handshake()
        except (ValueError, OSError):
            # Malformed input may contain secrets; never dump unparsed bytes.
            return {"unreadable_handshake": True}


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--inject-signal":
        signal_helper(int(sys.argv[2]), int(sys.argv[3]))
    elif len(sys.argv) == 3 and sys.argv[1] == "--hold-mutex":
        sys.path.insert(0, str(ROOT))
        from backend.startup_mutex import StartupMutex
        with StartupMutex():
            dump(sys.argv[2], {"pid": os.getpid(), "acquired": True})
            while True:
                time.sleep(1)
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--output", required=True, type=Path)
        parser.add_argument("--rounds", type=int, default=5)
        args = parser.parse_args()
        if args.rounds < 5:
            parser.error("At least five rounds per signal and mode are required")
        raise SystemExit(Suite(args.output, args.rounds).run())
