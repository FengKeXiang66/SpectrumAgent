import ctypes
import os
import subprocess
import sys
import time

ROOT = r"E:\AI_Agent"
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
HS = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run", "handshake.json")
LOG = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "logs", "engine-20261018.jsonl")
NEWGROUP = subprocess.CREATE_NEW_PROCESS_GROUP

mode = sys.argv[1] if len(sys.argv) > 1 else "frozen"
event = int(sys.argv[2]) if len(sys.argv) > 2 else 1

cmd = [os.path.join(ROOT, "artifacts", "step2", "dist", "app", "app.exe")] if mode == "frozen" \
    else [PY, "-m", "backend"]
err = open(r"E:\AI_Agent\artifacts\step2\mode-%s-e%d.log" % (mode, event), "wb")

if os.path.exists(HS):
    os.remove(HS)
before = os.path.getsize(LOG) if os.path.exists(LOG) else 0
p = subprocess.Popen(cmd, cwd=ROOT if mode != "frozen" else os.path.dirname(cmd[0]),
                     creationflags=NEWGROUP, stdout=subprocess.DEVNULL, stderr=err)
end = time.time() + 40
while time.time() < end:
    if os.path.exists(HS):
        break
    time.sleep(0.05)
time.sleep(1.0)
print("mode=%s event=%d console_ctrl=%s" % (
    mode, event, ctypes.windll.kernel32.GenerateConsoleCtrlEvent(event, p.pid)))
time.sleep(4.0)
if p.poll() is None:
    subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)
p.wait()
err.close()
print("exit code =", p.returncode)
print("handshake exists =", os.path.exists(HS))
with open(LOG, "r", encoding="utf-8", errors="replace") as fh:
    fh.seek(before)
    tail = [ln for ln in fh.read().splitlines() if ln.strip()][-6:]
print("stopped logged =", any("engine_stopped" in ln for ln in tail))
for ln in tail:
    print("  ", ln[:130])
