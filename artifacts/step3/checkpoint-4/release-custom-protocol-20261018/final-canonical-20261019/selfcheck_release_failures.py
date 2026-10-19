"""Real release failure cases. Fixture restoration is test hygiene, never a product claim."""
from __future__ import annotations

import hashlib
import ctypes
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime, timezone

ROOT = Path(r"E:\AI_Agent")
EVIDENCE = ROOT / "artifacts/step3/checkpoint-4/release-custom-protocol-20261018/final-canonical-20261019"
RELEASE = ROOT / "src-tauri/target/release"
DATA = Path(os.environ["LOCALAPPDATA"]) / "SpectrumAgent"
HANDSHAKE = DATA / "run/handshake.json"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
OUT = EVIDENCE / f"failure-cases-{STAMP}"
OUT.mkdir()
ORIGINAL_HANDSHAKE: bytes | None = None
CURRENT_FIXTURE: bytes | None = None
SETUP_OWNED = False
KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)


class ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("pid", wt.DWORD),
                ("heap", ctypes.c_size_t), ("module", wt.DWORD), ("threads", wt.DWORD),
                ("parent", wt.DWORD), ("priority", wt.LONG), ("flags", wt.DWORD), ("name", wt.WCHAR * 260)]


KERNEL.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
KERNEL.CreateToolhelp32Snapshot.restype = wt.HANDLE
KERNEL.Process32FirstW.argtypes = KERNEL.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
KERNEL.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
KERNEL.OpenProcess.restype = wt.HANDLE
KERNEL.CloseHandle.argtypes = [wt.HANDLE]
KERNEL.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
KERNEL.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]


def pid_alive(pid: int) -> bool:
    handle = KERNEL.OpenProcess(0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return False
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        code = wt.DWORD()
        if not KERNEL.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value == 259
    finally:
        KERNEL.CloseHandle(handle)


def image_path(pid: int) -> str | None:
    handle = KERNEL.OpenProcess(0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        count = wt.DWORD(len(buffer))
        if not KERNEL.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value
    finally:
        KERNEL.CloseHandle(handle)


def norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path).removeprefix("\\\\?\\")))


def processes_at(exe: Path) -> list[int]:
    found = []
    snapshot = KERNEL.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = KERNEL.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.name.lower() == exe.name.lower():
                path = image_path(entry.pid)
                if path and norm(path) == norm(exe):
                    found.append(entry.pid)
            more = KERNEL.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        KERNEL.CloseHandle(snapshot)
    return found


def read_lines(path: Path, offset: int) -> list[dict]:
    if not path.exists():
        return []
    with path.open("rb") as source:
        source.seek(offset)
        data = source.read()
    return [json.loads(line) for line in data.splitlines() if line]


def run() -> None:
    global ORIGINAL_HANDSHAKE, CURRENT_FIXTURE, SETUP_OWNED
    shell = RELEASE / "spectrum-agent.exe"
    binding = json.loads((EVIDENCE / "candidate.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(shell.read_bytes()).hexdigest() == binding["shell_sha256"]
    assert binding["features"] == "custom-protocol"
    engine = RELEASE / "resources/backend/app.exe"
    assert not processes_at(shell) and not processes_at(engine), "own release already running"
    original = HANDSHAKE.read_bytes() if HANDSHAKE.exists() else None
    known_tokens = []
    if original:
        previous = json.loads(original)
        assert not pid_alive(previous["pid"]), "existing handshake PID is alive"
        known_tokens.append(previous["token"])
    ORIGINAL_HANDSHAKE = original
    SETUP_OWNED = True
    fault = EVIDENCE / "temp" / f"failure-release-{STAMP}"
    fault.mkdir()
    shutil.copy2(shell, fault / shell.name)
    shutil.copytree(RELEASE / "resources", fault / "resources")
    (fault / "resources/backend/_internal/python312.dll").unlink()
    authority = json.loads((ROOT / "artifacts/step2/revision-20261018-smoke-headers/product-manifest.json").read_text())
    actual = {p.relative_to(fault / "resources/backend").as_posix(): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in (fault / "resources/backend").rglob("*") if p.is_file()}
    expected = {row["path"]: (row["bytes"], row["sha256"]) for row in authority["files"] if row["path"] != "_internal/python312.dll"}
    assert actual == expected
    results = []
    shell_log = DATA / "logs" / f"shell-{datetime.now():%Y%m%d}.log"
    engine_log = DATA / "logs" / f"engine-{datetime.now():%Y%m%d}.jsonl"
    for name, executable, fixture, kind, code in [
        ("invalid-json", shell, b"{invalid-json", "HandshakeInvalid", "HANDSHAKE_INVALID_JSON"),
        ("missing-fields", shell, b'{"boot_id":"deadbeef"}', "HandshakeInvalid", "HANDSHAKE_INVALID_FIELDS"),
        ("missing-dll-plus-invalid-json", fault / shell.name, b"{invalid-json", "ExitedBeforeReady", None),
    ]:
        case = OUT / name
        case.mkdir()
        assert not processes_at(executable)
        HANDSHAKE.parent.mkdir(parents=True, exist_ok=True)
        HANDSHAKE.write_bytes(fixture)  # Explicit test setup, never shell behavior.
        CURRENT_FIXTURE = fixture
        before_shell = shell_log.stat().st_size if shell_log.exists() else 0
        before_engine = engine_log.stat().st_size if engine_log.exists() else 0
        env = dict(os.environ, SPECTRUM_ACCEPTANCE_PROBE="1",
                   WEBVIEW2_USER_DATA_FOLDER=str(EVIDENCE / "temp" / f"webview-{STAMP}-{name}"),
                   SPECTRUM_ENGINE_EXE=str(ROOT / "invalid-release-override/app.exe"))
        start = time.perf_counter()
        process = None
        with (case / "stdout.txt").open("wb") as stdout, (case / "stderr.txt").open("wb") as stderr:
            try:
                process = subprocess.Popen([str(executable)], cwd=executable.parent, env=env,
                                           stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
                deadline = time.monotonic() + 15
                events = []
                while time.monotonic() < deadline:
                    events = read_lines(shell_log, before_shell)
                    failed = [x for x in events if x.get("event") == "engine_failure"]
                    dom = [x for x in events if x.get("event") == "acceptance_dom_audit" and x.get("phase") == "Failed"]
                    cleaned = [x for x in events if x.get("event") == "generation_cleanup" and x.get("complete")]
                    if failed and dom and cleaned:
                        break
                    assert process.poll() is None, f"unexpected shell exit={process.returncode}"
                    time.sleep(0.025)
                else:
                    raise AssertionError("failure page and cleanup were not observed within 15 seconds")
                failure = failed[0]["failure"]
                identity = next(x for x in events if x.get("event") == "process_identity_recorded")
                causal = [x for x in read_lines(engine_log, before_engine)
                          if x.get("event") == "handshake_error" and x.get("logger") == "engine.handshake" and x.get("pid") == identity["pid"]]
                assert failure["kind"] == kind, failure
                assert failure["engine_error"] == code, failure
                assert failure["preexisting_handshake_invalid"] is not None
                assert failure["exit_reason"].get("ProcessExit") is not None
                assert HANDSHAKE.read_bytes() == fixture, "test fixture changed"
                if code:
                    startup_rows = [row for row in causal if row.get("phase") == "startup"]
                    assert len(startup_rows) == 1 and all(row["error"] == code for row in causal), causal
                else:
                    assert not causal, "Python must not run with its DLL missing"
                assert all(x["exact_token_hits"] == 0 and not x["authorization_bearer"] for x in dom)
                second = subprocess.Popen([str(executable)], cwd=executable.parent, env=env,
                                          stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
                assert second.wait(10) == 0, "Failed-state secondary instance must exit successfully"
                events = read_lines(shell_log, before_shell)
                assert any(x.get("event") == "single_instance_activation" for x in events)
                assert len([x for x in events if x.get("event") == "engine_start_attempt"]) == 1
                assert process.poll() is None
                record = {"case": name, "shell_pid": process.pid, "shell_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                          "engine_pid": identity["pid"], "failure": failure, "causal_rows": causal,
                          "fixture_bytes_unchanged": True, "failure_page_observed": True,
                          "elapsed_ms_to_dom_observation": round((time.perf_counter() - start) * 1000, 3),
                          "fault_fixture": code is None, "fault_fixture_resource_files": len(actual) if code is None else None,
                          "failed_second_instance_pid": second.pid, "failed_second_instance_exit": second.returncode,
                          "engine_start_attempts": 1, "activation_received": True}
                (case / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (case / "shell-events.jsonl").write_bytes(b"".join(json.dumps(x, ensure_ascii=False).encode() + b"\n" for x in events))
                results.append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
            finally:
                if process and process.poll() is None:
                    print(f"TEST_HYGIENE_ONLY: terminate observed failure-page shell PID={process.pid}; not a normal-close test", flush=True)
                    process.terminate()
                    process.wait(10)
                assert not processes_at(executable), "own shell remained"
                child_exe = executable.parent / "resources/backend/app.exe"
                assert not processes_at(child_exe), "own engine remained"
    source = shell_log.read_bytes()
    assert not any(token.encode() in source for token in known_tokens)
    assert b"authorization: bearer" not in source.lower()
    (OUT / "original-shell.log").write_bytes(source)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FAILURE_CASES_PASSED count={len(results)} output={OUT}", flush=True)


if __name__ == "__main__":
    try:
        run()
    finally:
        if SETUP_OWNED and CURRENT_FIXTURE is not None:
            assert HANDSHAKE.read_bytes() == CURRENT_FIXTURE, "refuse to overwrite a changed/foreign handshake"
            if ORIGINAL_HANDSHAKE is None:
                HANDSHAKE.unlink()
            else:
                HANDSHAKE.write_bytes(ORIGINAL_HANDSHAKE)
            print("TEST_HYGIENE_ONLY: restored pre-test handshake bytes; not an acceptance predicate", flush=True)
