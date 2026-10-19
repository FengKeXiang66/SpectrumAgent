"""Current-source core harness only; never presented as Tauri UI evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(r"E:\AI_Agent")
OUT = Path(__file__).resolve().parent
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
temporary = OUT / "temp" / ("starting-stop-" + stamp)
temporary.mkdir()
probe = ROOT / "src-tauri/target/debug/supervisor-probe.exe"
stub = OUT / "temp/timeout-stub/app.exe"
command = [str(probe), "--resource-exe", str(ROOT / "src-tauri/target/release/resources/backend/app.exe"),
           "--injected-exe", str(stub)]
env = dict(os.environ, LOCALAPPDATA=str(temporary), SPECTRUM_STUB_MODE="timeout")
process = subprocess.Popen(command, env=env, cwd=temporary, stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=subprocess.CREATE_NO_WINDOW)
try:
    time.sleep(0.4)
    stdout, stderr = process.communicate(b"stop\n", timeout=10)
finally:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
for suffix, content in (("stdout.jsonl", stdout), ("stderr.txt", stderr)):
    with (OUT / ("starting-stop-" + stamp + "." + suffix)).open("xb") as handle:
        handle.write(content)
log_path = next((temporary / "SpectrumAgent/logs").glob("shell-*.log"))
raw = log_path.read_bytes()
rows = [json.loads(x) for x in raw.splitlines() if x]
transitions = [x for x in rows if x.get("event") == "state_transition"]
assert process.returncode == 0 and [(x["from"], x["to"]) for x in transitions] == [("Starting", "Stopping")]
assert sum(x.get("event") == "app_exit" for x in rows) == 1
assert not any(x.get("event") == "engine_failure" for x in rows)
assert not (temporary / "SpectrumAgent/run/handshake.json").exists()
with (OUT / ("starting-stop-" + stamp + ".shell.log")).open("xb") as handle:
    handle.write(raw)
result = {"command": command, "scope": "current-source core acceptance harness; not Tauri UI or single-instance evidence",
          "source_commit": "a53030d47fc169ddfa67057e45c464fc0f1db2cd",
          "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
          "stub_sha256": hashlib.sha256(stub.read_bytes()).hexdigest(),
          "exit_code": process.returncode, "transitions": transitions, "app_exit_count": 1,
          "log_sha256": hashlib.sha256(raw).hexdigest(), "log": "starting-stop-" + stamp + ".shell.log"}
target = OUT / ("starting-stop-" + stamp + ".json")
with target.open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
