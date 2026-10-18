import ctypes, json, os, subprocess, time

APP = r"E:/AI_Agent/artifacts/step2/dist/app/app.exe"
HS = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "run", "handshake.json")
LOGDIR = os.path.join(os.environ["LOCALAPPDATA"], "SpectrumAgent", "logs")
NEWGROUP = subprocess.CREATE_NEW_PROCESS_GROUP

def rh():
    try:
        with open(HS, encoding="utf-8") as f: return json.load(f)
    except Exception: return None

def start():
    return subprocess.Popen([APP], cwd=os.path.dirname(APP), creationflags=NEWGROUP,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_hs(timeout=30):
    end=time.time()+timeout
    while time.time()<end:
        d=rh()
        if d and "boot_id" in d: return d
        time.sleep(0.05)

def wait_new(prev, timeout=30):
    end=time.time()+timeout
    while time.time()<end:
        d=rh()
        if d and d.get("boot_id")!=prev: return d
        time.sleep(0.05)

def bl(boot):
    out=[]
    for n in sorted(os.listdir(LOGDIR)):
        for ln in open(os.path.join(LOGDIR,n),encoding="utf-8",errors="replace"):
            ln=ln.strip()
            if not ln: continue
            try: d=json.loads(ln)
            except Exception: continue
            if d.get("boot_id")==boot: out.append(d)
    return out

def send(pid,ev): return bool(ctypes.windll.kernel32.GenerateConsoleCtrlEvent(ev,pid))
def gone(p,t=25):
    end=time.time()+t
    while time.time()<end:
        if p.poll() is not None: return True
        time.sleep(0.1)
    return False

if os.path.exists(HS): os.remove(HS)
p=start(); a=wait_hs(); boot_a=a["boot_id"]; time.sleep(0.8)
print("A boot=%s pid=%d" % (boot_a,a["pid"]))
send(p.pid,1); gone(p); time.sleep(1.2)
l=rh()
print("CTRL_BREAK 退出后残留=%s" % (l and l.get("boot_id")==boot_a))
print("  本代 engine_stopped=%d cleanup_phase=%s" % (
    sum(1 for d in bl(boot_a) if d.get("event")=="engine_stopped"),
    [d.get("cleanup_phase") for d in bl(boot_a) if d.get("event")=="engine_stopped"]))

# 重新启动，等到 boot_id 变化
p2=start(); b=wait_new(boot_a); time.sleep(0.8)
print("重启后新 boot=%s pid=%s (等到了 boot_id 变化)" % (b["boot_id"], b["pid"]))
lb=bl(b["boot_id"])
print("  新引擎 stale_handshake_removed=%d" % sum(1 for d in lb if d.get("event")=="stale_handshake_removed"))
for d in lb:
    if d.get("event")=="stale_handshake_removed":
        print("   ", json.dumps({k:d[k] for k in d if k!="token"}, ensure_ascii=False))
send(p2.pid,1); gone(p2); time.sleep(1.0)
ln=bl(b["boot_id"])
tail=rh()
print("  CTRL_BREAK 关闭后残留本代=%s 本代 engine_stopped=%d" % (
    tail and tail.get("boot_id")==b["boot_id"],
    sum(1 for d in ln if d.get("event")=="engine_stopped")))
