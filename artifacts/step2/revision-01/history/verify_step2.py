import json
import os
import subprocess
import sys
import time

APP = r"E:\AI_Agent\artifacts\step2\dist\app\app.exe"
HS = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run", "handshake.json")
LOGDIR = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "logs")


def curl(url, token=None):
    cmd = ["curl.exe", "--noproxy", "*", "-s", "-o", "-", "-w", "\n%{http_code}", url]
    if token:
        cmd[3:3] = ["-H", "Authorization: Bearer " + token]
    out = subprocess.run(cmd, capture_output=True)
    text = out.stdout.decode("utf-8", "replace").strip()
    body, _, code = text.rpartition("\n")
    return code.strip(), body.strip()


def wait_handshake(timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(HS):
            try:
                with open(HS, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                pass
        time.sleep(0.05)
    return None


def main():
    if os.path.exists(HS):
        os.remove(HS)
    log_before = set(os.listdir(LOGDIR)) if os.path.isdir(LOGDIR) else set()
    print("log files before:", sorted(log_before))

    p = subprocess.Popen([APP], cwd=os.path.dirname(APP))
    t0 = time.time()
    hs = wait_handshake()
    if not hs:
        print("RESULT=FAIL no handshake")
        return 1
    print("spawn_pid=%d handshake_pid=%s" % (p.pid, hs["pid"]))
    print("boot_id=%s port=%s protocol=%s version=%s" % (hs["boot_id"], hs["port"], hs["protocol"], hs["version"]))
    print("has_started_at=%s has_process_created_at=%s token_len=%d" % (
        "started_at" in hs, "process_created_at" in hs, len(hs.get("token", ""))))

    url = "http://127.0.0.1:%s" % hs["port"]
    code, body = curl(url + "/health")
    print("health  ->", code, body)
    code, body = curl(url + "/smoke")
    print("smoke   ->", code, body)
    code, body = curl(url + "/smoke", token=hs["token"])
    print("smoke+T ->", code, body)
    code, body = curl(url + "/smoke?blocks=8", token=hs["token"])
    print("blocks8 ->", code, body)
    code, body = curl(url + "/health")
    hb = json.loads(body)
    print("health echoes boot_id =", hb.get("boot_id") == hs["boot_id"])

    print("--- process list ---")
    print(subprocess.run(["tasklist", "/FI", "IMAGENAME eq app.exe"],
                         capture_output=True).stdout.decode("gbk", "replace"))

    print("--- geotiff selfcheck (frozen) ---")
    g = subprocess.run([APP, "--selfcheck-geotiff"], capture_output=True)
    print("exit_code=", g.returncode)
    print(g.stdout.decode("utf-8", "replace").strip()[:600])
    if g.stderr:
        print("stderr:", g.stderr.decode("utf-8", "replace").strip()[:300])

    print("--- log token leak check ---")
    token = hs["token"]
    new_files = sorted(set(os.listdir(LOGDIR)) - log_before) if os.path.isdir(LOGDIR) else []
    print("new log files:", new_files)
    leaks = 0
    json_bad = 0
    total = 0
    for name in new_files:
        path = os.path.join(LOGDIR, name)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total += 1
                if token in line:
                    leaks += 1
                try:
                    json.loads(line)
                except Exception:
                    json_bad += 1
    print("log lines=%d token_leaks=%d non_json=%d" % (total, leaks, json_bad))

    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()
    time.sleep(0.8)
    print("--- after normal exit ---")
    print("process alive =", p.poll() is None)
    print("handshake exists =", os.path.exists(HS))
    print("RESULT=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
