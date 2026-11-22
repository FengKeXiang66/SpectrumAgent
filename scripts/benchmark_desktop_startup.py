"""Isolated desktop start probes; closes only processes created by this script."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'.runtime'/'perf'/'desktop'


def records(path):
    if not path.exists():return []
    result=[]
    for line in path.read_text('utf-8').splitlines():
        try:result.append(json.loads(line))
        except ValueError:pass
    return result


def interactive_samples(root):
    return [r['elapsed_ms'] for path in (root/'SpectrumAgent'/'acceptance').glob('dom-*.jsonl')
            for r in records(path) if r.get('document',{}).get('phase')=='Ready'
            and any(f.get('id') in ('composer-message','agent-input') and f.get('disabled') is False
                    for f in r['document'].get('fields',[]))]


def main():
    OUTPUT.mkdir(parents=True,exist_ok=False)
    server=None
    with socket.socket() as sock:present=sock.connect_ex(('127.0.0.1',1420))==0
    log=(OUTPUT/'vite.log').open('w',encoding='utf-8')
    if not present:
        server=subprocess.Popen([shutil.which('node'),str(ROOT/'node_modules/vite/bin/vite.js')],cwd=ROOT,
                                stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(2)
    results={}
    try:
        for mode in ('0','1'):
            root=OUTPUT/('early-'+mode)
            root.mkdir()
            env={**os.environ,'LOCALAPPDATA':str(root),'WEBVIEW2_USER_DATA_FOLDER':str(root/'webview'),
                 'SPECTRUM_ACCEPTANCE_PROBE':'1','SPECTRUMAGENT_EARLY_WINDOW':mode}
            with (root/'desktop.log').open('w',encoding='utf-8') as desktop_log:
                launched=datetime.now(timezone.utc)
                process=subprocess.Popen([str(ROOT/'src-tauri/target/debug/spectrum-agent.exe')],cwd=ROOT,env=env,
                    stdout=desktop_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    deadline=time.monotonic()+40
                    observed=[]
                    while time.monotonic()<deadline and process.poll() is None:
                        observed=[r for path in (root/'SpectrumAgent'/'logs').glob('shell-*.log') for r in records(path)]
                        if interactive_samples(root):break
                        time.sleep(.1)
                    windows=[r for r in observed if r.get('event')=='window_shown' and r.get('success')]
                    interactive=interactive_samples(root)
                    visible=[r['elapsed_ms'] for r in observed if r.get('event')=='acceptance_heartbeat' and r.get('visible')]
                    results[mode]={'first_window_s':(datetime.fromisoformat(windows[0]['timestamp'].replace('Z','+00:00'))-launched).total_seconds() if windows else None,
                                   'first_interactive_ms':min(interactive) if interactive else None,
                                   'first_visible_heartbeat_ms':min(visible) if visible else None,
                                   'starting_dom_observed':any(r.get('phase')=='Starting' for r in observed if r.get('event')=='acceptance_dom_audit'),
                                   'process_exit':process.poll()}
                    print(json.dumps({mode:results[mode]}),flush=True)
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=False)
                        process.wait(10)
    finally:
        if server is not None:server.terminate();server.wait(10)
        log.close()
    (OUTPUT/'results.json').write_text(json.dumps(results,indent=2),'utf-8')


if __name__=='__main__':main()
