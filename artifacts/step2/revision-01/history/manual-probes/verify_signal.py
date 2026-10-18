import ctypes
import json
import os
import subprocess
import sys
import time

APP = r"E:\AI_Agent\artifacts\step2\dist\app\app.exe"
HS = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run", "handshake.json")
LOG = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "logs", "engine-20261018.jsonl")
NEWGROUP = subprocess.CREATE_NEW_PROCESS_GROUP
CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1


def read_hs():
    if not os.path.exists(HS):
        return None
    with open(HS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def start():
    return subprocess.Popen(
        [APP], cwd=os.path.dirname(APP), creationflags=NEWGROUP,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_hs(timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        d = read_hs()
        if d and "boot_id" in d:
            return d
        time.sleep(0.05)
    return None


def log_lines():
    if not os.path.exists(LOG):
        return []
    with open(LOG, "r", encoding="utf-8", errors="replace") as fh:
        return [ln for ln in fh.read().splitlines() if ln.strip()]


def trial(label, event):
    if os.path.exists(HS):
        os.remove(HS)
    before = len(log_lines())
    p = start()
    hs = wait_hs()
    if not hs:
        print("%s FAIL no handshake" % label)
        p.kill()
        return
    time.sleep(1.0)
    ok = ctypes.windll.kernel32.GenerateConsoleCtrlEvent(event, p.pid)
    time.sleep(3.0)
    if p.poll() is None:
        subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)
    p.wait()
    after = log_lines()[before:]
    stopped = [ln for ln in after if "engine_stopped" in ln]
    finished = [ln for ln in after if "Finished server process" in ln]
    left = read_hs()
    print("%s: GenerateConsoleCtrlEvent ok=%s exit=%s finished=%d engine_stopped=%d handshake=%s" % (
        label, bool(ok), p.returncode, len(finished), len(stopped),
        "present(boot=%s)" % left["boot_id"] if left else "absent"))
    if not stopped:
        print("   -> 最后 3 行日志:")
        for ln in after[-3:]:
            print("     ", ln[:150])


print("=== CTRL_C_EVENT x2 ===")
trial("CTRL_C #1", CTRL_C_EVENT)
trial("CTRL_C #2", CTRL_C_EVENT)
print()
print("=== CTRL_BREAK_EVENT x2 ===")
trial("CTRL_BREAK #1", CTRL_BREAK_EVENT)
trial("CTRL_BREAK #2", CTRL_BREAK_EVENT)
print()
out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq app.exe"],
                     capture_output=True).stdout.decode("gbk", "replace")
print("残留进程:", out.strip()[-120:])
