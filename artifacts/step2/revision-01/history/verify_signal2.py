import ctypes
import os
import subprocess
import sys
import time

APP = r"E:\AI_Agent\artifacts\step2\dist\app\app.exe"
HS = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run", "handshake.json")
NEWGROUP = subprocess.CREATE_NEW_PROCESS_GROUP

label = sys.argv[1] if len(sys.argv) > 1 else "break"
event = 0 if label == "c" else 1
if os.path.exists(HS):
    os.remove(HS)
err = open(r"E:\AI_Agent\artifacts\step2\signal-%s-stderr.txt" % label, "wb")
p = subprocess.Popen(
    [APP], cwd=os.path.dirname(APP), creationflags=NEWGROUP,
    stdout=subprocess.DEVNULL, stderr=err,
)
end = time.time() + 30
while time.time() < end:
    if os.path.exists(HS):
        break
    time.sleep(0.05)
time.sleep(1.0)
print("GenerateConsoleCtrlEvent ->", ctypes.windll.kernel32.GenerateConsoleCtrlEvent(event, p.pid))
time.sleep(4.0)
if p.poll() is None:
    subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)
p.wait()
err.close()
print("exit code =", p.returncode)
print("handshake exists =", os.path.exists(HS))
