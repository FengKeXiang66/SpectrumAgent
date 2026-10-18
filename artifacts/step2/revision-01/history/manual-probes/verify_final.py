import ctypes
import json
import os
import subprocess
import sys
import time

APP = r"E:\AI_Agent\artifacts\step2\dist\app\app.exe"
HS = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run", "handshake.json")
LOGDIR = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "logs")
NEWGROUP = subprocess.CREATE_NEW_PROCESS_GROUP
CTRL_C = 0
CTRL_BREAK = 1


def read_hs():
    if not os.path.exists(HS):
        return None
    try:
        with open(HS, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def start():
    return subprocess.Popen([APP], cwd=os.path.dirname(APP), creationflags=NEWGROUP,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_hs(timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        d = read_hs()
        if d and "boot_id" in d:
            return d
        time.sleep(0.05)
    return None


def boot_lines(boot_id):
    """Only log lines belonging to this boot id."""
    out = []
    if not os.path.isdir(LOGDIR):
        return out
    for name in sorted(os.listdir(LOGDIR)):
        with open(os.path.join(LOGDIR, name), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("boot_id") == boot_id:
                    out.append(d)
    return out


def send(pid, event):
    return bool(ctypes.windll.kernel32.GenerateConsoleCtrlEvent(event, pid))


def wait_gone(p, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        if p.poll() is not None:
            return True
        time.sleep(0.1)
    subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)
    return False


results = {"break_clean": 0, "break_dirty": 0, "c_remains": 0, "c_clean": 0,
           "c_recovered": 0, "c_lost": 0, "stopped_exactly_one": 0, "stopped_wrong": 0}

print("=== A. CTLR_BREAK 即时清理 x5（冻结态）===")
for i in range(5):
    if os.path.exists(HS):
        os.remove(HS)
    p = start()
    hs = wait_hs()
    if not hs:
        print("A%d FAIL 无握手" % (i + 1)); p.kill(); continue
    boot = hs["boot_id"]
    time.sleep(0.8)
    send(p.pid, CTRL_BREAK)
    gone = wait_gone(p)
    time.sleep(1.2)
    lines = boot_lines(boot)
    stopped = sum(1 for d in lines if d.get("event") == "engine_stopped")
    finished = sum(1 for d in lines if d.get("event") == "Finished server process")
    left = read_hs()
    own = left and left.get("boot_id") == boot
    ok = gone and not own and stopped == 1 and finished >= 1
    print("A%d exit=%s gone=%s finished=%d engine_stopped=%d 残留本代握手=%s -> %s" % (
        i + 1, p.returncode, gone, finished, stopped, bool(own), "PASS" if ok else "FAIL"))
    if ok:
        results["break_clean"] += 1
    else:
        results["break_dirty"] += 1
    if stopped == 1:
        results["stopped_exactly_one"] += 1
    elif stopped > 1:
        results["stopped_wrong"] += 1

print()
print("=== B. CTLR_C 恢复路径 x3（冻结态）===")
for i in range(3):
    if os.path.exists(HS):
        os.remove(HS)
    p = start()
    hs = wait_hs()
    if not hs:
        print("B%d FAIL 无握手" % (i + 1)); p.kill(); continue
    boot = hs["boot_id"]
    time.sleep(0.8)
    send(p.pid, CTRL_C)
    wait_gone(p)
    time.sleep(1.2)
    left = read_hs()
    if left and left.get("boot_id") == boot:
        results["c_remains"] += 1
        remains = True
    else:
        remains = bool(left)
    # 直接重启（不清洗），验证恢复
    p2 = start()
    hs2 = wait_hs()
    time.sleep(0.8)
    lines2 = boot_lines(hs2["boot_id"]) if hs2 else []
    swept = sum(1 for d in lines2 if d.get("event") == "stale_handshake_removed")
    send(p2.pid, CTRL_BREAK)
    wait_gone(p2)
    time.sleep(1.0)
    lines3 = boot_lines(hs2["boot_id"]) if hs2 else []
    stopped = sum(1 for d in lines3 if d.get("event") == "engine_stopped")
    tail = read_hs()
    ok = remains and swept >= 1 and hs2 and not (tail and tail.get("boot_id") == hs2["boot_id"])
    print("B%d 退出后残留=%s 重启清扫=%d 新boot=%s 关后无残留=%s engine_stopped=%d -> %s" % (
        i + 1, remains, swept, hs2 and hs2["boot_id"][:8],
        not (tail and tail.get("boot_id") == hs2["boot_id"]), stopped,
        "PASS" if ok else "FAIL"))
    if ok:
        results["c_recovered"] += 1
    else:
        results["c_lost"] += 1

print()
print("=== C. taskkill /F 恢复路径 x2（冻结态）===")
for i in range(2):
    if os.path.exists(HS):
        os.remove(HS)
    p = start()
    hs = wait_hs()
    boot = hs["boot_id"]
    time.sleep(0.8)
    subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)
    p.wait()
    time.sleep(1.0)
    left = read_hs()
    p2 = start()
    hs2 = wait_hs()
    time.sleep(0.8)
    lines2 = boot_lines(hs2["boot_id"]) if hs2 else []
    swept = sum(1 for d in lines2 if d.get("event") == "stale_handshake_removed")
    send(p2.pid, CTRL_BREAK)
    wait_gone(p2)
    time.sleep(1.0)
    print("C%d 残留=%s 重启清扫=%d -> %s" % (
        i + 1, bool(left and left.get("boot_id") == boot), swept,
        "PASS" if swept >= 1 else "FAIL"))
    if swept >= 1:
        results["c_recovered"] += 1
    else:
        results["c_lost"] += 1

print()
print("汇总:", json.dumps(results, ensure_ascii=False))
