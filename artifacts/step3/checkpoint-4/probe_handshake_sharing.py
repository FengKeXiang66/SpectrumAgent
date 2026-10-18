from pathlib import Path
import subprocess,time,json,os
root=Path(r'E:\AI_Agent\artifacts\step3\checkpoint-4')
output=[]
for mode in ['GetContent','DeleteSharing']:
    folder=root/'temp'/f'sharing-{mode}-{time.time_ns()}'
    folder.mkdir()
    fixture=folder/'handshake.json';stop=folder/'stop';fixture.write_bytes(b'x'*65536)
    reader=subprocess.Popen([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-File',str(root/'share-reader.ps1'),'-Path',str(fixture),'-Mode',mode,'-StopFile',str(stop)],creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    failures=[]
    try:
        for index in range(1000):
            try:fixture.unlink()
            except OSError as error:failures.append({'iteration':index,'winerror':error.winerror})
            if not fixture.exists():fixture.write_bytes(b'x'*65536)
    finally:
        stop.touch();reader.wait(10)
    output.append({'reader':mode,'attempts':1000,'delete_failures':len(failures),'errors':failures})
path=root/'handshake-sharing-probe.json';path.write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
