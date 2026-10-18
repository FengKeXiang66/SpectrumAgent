import json
import os
import signal
import subprocess
import sys
import time

APP = r"E:\AI_Agent\artifacts\step2\dist\app\app.exe"
RUN = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run")
HS = os.path.join(RUN, "handshake.json")
LOGDIR = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "logs")
LOGFILE = os.path.join(LOGDIR, "engine-20261018.jsonl")

NEWGROUP = subprocess.CREATE_NEW_PROCESS_GROUP


def read_hs():
    if not os.path.exists(HS):
        return None
    try:
        with open(HS, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"unreadable": True}


def start():
    return subprocess.Popen(
        [APP], cwd=os.path.dirname(APP),
        creationflags=NEWGROUP,
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


def graceful(p, timeout=20.0):
    try:
        os.kill(p.pid, signal.CTRL_BREAK_EVENT)
    except Exception as exc:
        print("   (signal failed:", exc, ")")
    end = time.time() + timeout
    while time.time() < end:
        if p.poll() is not None:
            return p.returncode
        time.sleep(0.1)
    p.kill()
    return None


def leak_check(token):
    if not os.path.exists(LOGFILE):
        return "no log file"
    size = os.path.getsize(LOGFILE)
    leaks = bad = total = 0
    with open(LOGFILE, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            total += 1
            if token and token in line:
                leaks += 1
            try:
                json.loads(line)
            except Exception:
                bad += 1
    return "size=%d lines=%d token_leaks=%d non_json=%d" % (size, total, leaks, bad)


def main():
    print("=== Scenario A: 单引擎优雅退出 x3 ===")
    for i in range(3):
        if os.path.exists(HS):
            os.remove(HS)
        p = start()
        hs = wait_hs()
        if not hs:
            print("A%d FAIL no handshake" % (i + 1))
            p.kill()
            continue
        code = graceful(p)
        time.sleep(1.0)
        remain = read_hs()
        print("A%d exit=%s alive=%s handshake=%s residual_boot=%s" % (
            i + 1, code, p.poll() is None,
            "present" if remain else "absent",
            (remain or {}).get("boot_id")))

    print()
    print("=== Scenario B: 两个引擎并存，各自优雅退出 ===")
    for i in range(2):
        if os.path.exists(HS):
            os.remove(HS)
        a = start()
        ha = wait_hs()
        b = start()
        time.sleep(2.5)
        hb = read_hs()
        print("B%d A_boot=%s B_boot=%s  A=%s B=%s" % (
            i + 1, ha and ha["boot_id"], hb and hb.get("boot_id"),
            ha and ha["pid"], hb and hb.get("pid")))
        ca = graceful(a)
        time.sleep(1.2)
        mid = read_hs()
        print("   after A exit=%s handshake=%s boot=%s" % (
            ca, "present" if mid else "absent", (mid or {}).get("boot_id")))
        cb = graceful(b)
        time.sleep(1.2)
        end = read_hs()
        print("   after B exit=%s handshake=%s boot=%s" % (
            cb, "present" if end else "absent", (end or {}).get("boot_id")))

    print()
    print("=== token 泄漏检查（全量日志）===")
    print(leak_check(read_hs() and None))
    if os.path.exists(HS):
        with open(HS, "r", encoding="utf-8") as fh:
            token = json.load(fh).get("token")
        print("log scan:", leak_check(token))

    print()
    print("=== 残留进程 ===")
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq app.exe"],
                         capture_output=True).stdout.decode("gbk", "replace")
    print(out.strip()[-200:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
