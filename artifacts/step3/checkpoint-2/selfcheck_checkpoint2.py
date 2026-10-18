"""Real frozen-engine integration. No Python engine launch, no shell=True, no new packages.

Fixture preparation and final hygiene belong to this acceptance tool, never the shell.
All judgment is made before hygiene. Canonical binaries are read-only throughout.
"""
import ctypes
import base64
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(r'E:\AI_Agent')
HERE = Path(__file__).resolve().parent
CANONICAL = ROOT / 'artifacts/step2/dist/app'
DATA = Path(os.environ['LOCALAPPDATA']) / 'SpectrumAgent'
HS = DATA / 'run/handshake.json'
CURL = Path(r'C:\Windows\System32\curl.exe')
SESSION = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
OUT = HERE / f'evidence-{SESSION}'
FIXTURES = ROOT / 'src-tauri/target/checkpoint2-fixtures' / SESSION
TOKENS = set()
PROBES = []
KNOWN_BYTES = set()
CURRENT = 'preflight'


def safe(text):
    for token in TOKENS:
        text = text.replace(token, '<redacted>')
    return text


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.write_text(safe(text), encoding='utf-8', newline='')


def say(text):
    print(safe(text), flush=True)
    with (OUT / 'raw-output.txt').open('a', encoding='utf-8', newline='') as stream:
        stream.write(safe(text) + '\n')


def check(condition, message):
    if not condition:
        raise AssertionError(f'{CURRENT}: {message}')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(directory):
    rows = [dict(path=p.relative_to(directory).as_posix(), bytes=p.stat().st_size,
                 sha256=digest(p.read_bytes()))
            for p in sorted(directory.rglob('*')) if p.is_file()]
    return sorted(rows, key=lambda row: row['path'])


KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
KERNEL.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
KERNEL.OpenProcess.restype = wintypes.HANDLE
KERNEL.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
KERNEL.GetProcessTimes.restype = wintypes.BOOL
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]


def process_time(pid):
    handle = KERNEL.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        status = wintypes.DWORD()
        if not KERNEL.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value != 259:
            return None
        values = [wintypes.FILETIME() for _ in range(4)]
        if not KERNEL.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            raise ctypes.WinError(ctypes.get_last_error())
        ticks = (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime
        return ticks // 10000 - 11644473600000
    finally:
        KERNEL.CloseHandle(handle)


def load_hs():
    raw = HS.read_bytes()
    KNOWN_BYTES.add(raw)
    value = json.loads(raw)
    TOKENS.add(value['token'])
    return value


def hygiene():
    # Explicit test hygiene, never the basis for a passing lifecycle assertion.
    if HS.exists():
        raw = HS.read_bytes()
        check(raw in KNOWN_BYTES, 'refusing to remove unknown handshake')
        try:
            owner = json.loads(raw)['pid']
        except (ValueError, KeyError, TypeError):
            owner = None
        check(owner is None or process_time(owner) is None, 'refusing to remove live owner handshake')
        HS.unlink()
        say('测试卫生（不作为通过依据）：移除本脚本已存档且 owner 已退出的握手/故障夹具。')


def seed(raw):
    hygiene()
    HS.parent.mkdir(parents=True, exist_ok=True)
    KNOWN_BYTES.add(raw)
    HS.write_bytes(raw)
    say(f'测试夹具准备：handshake bytes={len(raw)} sha256={digest(raw)}')


def offsets():
    return {p.name: p.stat().st_size for p in (DATA / 'logs').glob('*') if p.is_file()}


def tail_logs(base):
    result = {}
    for p in (DATA / 'logs').glob('*'):
        if p.is_file() and (p.name.startswith('engine-') or p.name.startswith('shell-')):
            with p.open('rb') as stream:
                stream.seek(base.get(p.name, 0))
                content = stream.read()
            if content:
                result[p.name] = content.decode('utf-8', errors='replace')
    return result


class Probe:
    def __init__(self, name, *, release=False, injected=None, dev=None):
        self.name = name
        self.base = offsets()
        self.rows = []
        self.events = queue.Queue()
        self.started = time.perf_counter()
        self.stopped = False
        self.failure_archive = 0
        profile = 'release' if release else 'debug'
        exe = ROOT / f'src-tauri/target/{profile}/supervisor-probe.exe'
        args = [str(exe), '--resource-exe', str(CANONICAL / 'app.exe')]
        if injected:
            args += ['--injected-exe', str(injected)]
        env = os.environ.copy()
        env.pop('SPECTRUM_ENGINE_EXE', None)
        if dev is not None:
            env['SPECTRUM_ENGINE_EXE'] = str(dev)
        self.stderr_path = OUT / f'{name}.probe.stderr.txt'
        self.stderr = self.stderr_path.open('wb')
        self.proc = subprocess.Popen(args, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, env=env, cwd=ROOT, text=True, encoding='utf-8')
        save(f'{name}.launch.json', {'command': args, 'shell': False, 'probe_pid': self.proc.pid,
                                   'SPECTRUM_ENGINE_EXE': dev and str(dev), 'log_baseline_offsets': self.base})
        PROBES.append(self)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        say(f'\n[{name}] command={subprocess.list2cmdline(args)}\nSPECTRUM_ENGINE_EXE={dev} probe_pid={self.proc.pid}')

    def read(self):
        for line in self.proc.stdout:
            self.rows.append(line)
            try:
                self.events.put(json.loads(line))
            except ValueError:
                self.events.put({'invalid_probe_output': line})
        self.events.put({'probe_eof': True})

    def wait(self, phase, generation=1, timeout=35):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = self.events.get(timeout=max(0.01, end - time.monotonic()))
            if 'Status' in value:
                status = value['Status']
                if status['phase'] == 'Failed':
                    # Persist internal errors BEFORE classification/assertion/analysis.
                    self.failure_archive += 1
                    self.archive(f'failure-observed-{self.failure_archive}')
                    reason = status['failure']['exit_reason']
                    check(reason.get('ProcessExit', {}).get('code') != 70,
                          '真实引擎 exit code=70：内部证据已落盘，停止验收后分析')
                if status['phase'] == phase and status['generation_id'] == generation:
                    if phase != 'Failed' or status['cleanup_complete']:
                        elapsed = round((time.perf_counter() - self.started) * 1000, 3)
                        say(json.dumps({'elapsed_ms': elapsed, 'snapshot': status}, ensure_ascii=False))
                        return status, elapsed
                if status['phase'] == 'Failed' and phase == 'Ready':
                    raise AssertionError(f'{self.name}: engine Failed; evidence saved before analysis')
            check('probe_eof' not in value, f'{self.name}: probe exited before {phase}')
        raise TimeoutError(f'{self.name}: waiting for {phase}')

    def command(self, command):
        self.proc.stdin.write(command + '\n')
        self.proc.stdin.flush()

    def archive(self, suffix='final'):
        save(f'{self.name}.{suffix}.events.jsonl', ''.join(self.rows))
        for name, content in tail_logs(self.base).items():
            save(f'{self.name}.{suffix}.{name}', content)
            if name.startswith('shell-'):
                rows = [json.loads(line) for line in content.splitlines()]
                identities = {row['generation_id']: row for row in rows if row.get('event') == 'process_identity_recorded'}
                times = []
                for row in rows:
                    if row.get('event') == 'state_transition' and row.get('to') in ('Ready', 'Failed'):
                        identity = identities.get(row['generation_id'])
                        if identity:
                            stamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                            delta = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
                            end_ms = (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000
                            times.append({'generation_id': row['generation_id'], 'pid': identity['pid'],
                                          'to': row['to'], 'process_created_at_ms': identity['process_created_at_ms'],
                                          'transition_at_ms': end_ms, 'spawn_to_transition_ms': end_ms - identity['process_created_at_ms']})
                save(f'{self.name}.{suffix}.timing.json', times)
        if HS.exists():
            raw = HS.read_bytes()
            KNOWN_BYTES.add(raw)
            try:
                value = json.loads(raw)
                if isinstance(value, dict) and isinstance(value.get('token'), str):
                    TOKENS.add(value['token'])
                    value['token'] = '<redacted>'
                save(f'{self.name}.{suffix}.handshake.json', value)
            except ValueError:
                save(f'{self.name}.{suffix}.handshake-invalid.txt', raw.decode('utf-8', errors='replace'))

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        if self.proc.poll() is None:
            self.command('stop')
            self.proc.wait(timeout=12)
        self.reader.join(timeout=3)
        self.stderr.close()
        self.archive()
        check(self.proc.returncode == 0, f'{self.name}: probe returncode {self.proc.returncode}')


def curl(name, hs, route, authorized=False):
    config = f'url = "http://127.0.0.1:{hs["port"]}{route}"\n'
    if authorized:
        config += f'header = "Authorization: Bearer {hs["token"]}"\n'
    args = [str(CURL), '--noproxy', '*', '--silent', '--show-error', '--max-time', '15',
            '--write-out', '\nHTTP_STATUS=%{http_code}\n', '--config', '-']
    result = subprocess.run(args, input=config, text=True, encoding='utf-8', capture_output=True, shell=False)
    save(f'{name}.curl.txt', result.stdout + result.stderr)
    say(f'curl.exe {route} auth={authorized} (token 经 stdin 配置传入)\n{result.stdout}{result.stderr}')
    check(result.returncode == 0, f'curl error {result.returncode}')
    body, code = result.stdout.rsplit('\nHTTP_STATUS=', 1)
    return json.loads(body), int(code)


def identity(probe, ready, *, smoke=False):
    hs = load_hs()
    actual = process_time(hs['pid'])
    stamp_time = datetime.fromisoformat(hs['process_created_at'].replace('Z', '+00:00'))
    delta = stamp_time - datetime(1970, 1, 1, tzinfo=timezone.utc)
    stamp = (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000
    check(hs['pid'] == ready['pid'] and hs['boot_id'] == ready['boot_id'], 'snapshot identity mismatch')
    check(actual == stamp, f'GetProcessTimes {actual} != handshake {stamp}')
    save(f'{probe.name}.handshake.json', hs)
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId = {hs['pid']}' | Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json -Compress"
    cim = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True, shell=False)
    save(f'{probe.name}.cim.txt', cim.stdout + cim.stderr)
    say('Get-CimInstance:\n' + cim.stdout + cim.stderr)
    row = json.loads(cim.stdout)
    check(row['ParentProcessId'] == probe.proc.pid, 'actual child parent != supervisor probe')
    listing = subprocess.run([r'C:\Windows\System32\tasklist.exe', '/FI', 'IMAGENAME eq app.exe'], capture_output=True, text=True, shell=False)
    save(f'{probe.name}.tasklist.txt', listing.stdout + listing.stderr)
    say(listing.stdout)
    say(f'GetProcessTimes UTC ms={actual}; handshake UTC ms={stamp}; pid/boot/created_at=matched')
    body, code = curl(probe.name + '.health', hs, '/health')
    check(code == 200 and body['boot_id'] == hs['boot_id'] and body['pid'] == hs['pid'], 'health identity')
    if smoke:
        _, code = curl(probe.name + '.unauthorized', hs, '/smoke')
        check(code == 401, 'unauthorized must be 401')
        for label, route in [('smoke', '/smoke'), ('blocks8', '/smoke?blocks=8')]:
            body, code = curl(probe.name + '.' + label, hs, route, True)
            check(code == 200 and {'nan_ratio', 'reflectance_range', 'bands', 'shape', 'elapsed_ms'} <= body.keys(), 'smoke fields/status')
    probe.archive('ready')
    return hs


def assert_dead(hs):
    check(process_time(hs['pid']) is None, 'engine still alive')
    with socket.socket() as client:
        check(client.connect_ex(('127.0.0.1', hs['port'])) != 0, 'engine port still listening')
    say(f'判断前状态：pid={hs["pid"]} absent=true port={hs["port"]} closed=true handshake_present={HS.exists()}')


def failure(snapshot, kind, engine_error=None):
    value = snapshot['failure']
    check(value['kind'] == kind, f'kind={value["kind"]} wanted={kind}')
    check(value['engine_error'] == engine_error, 'wrong engine_error')
    check(snapshot['cleanup_complete'], 'cleanup incomplete')
    return value


def main():
    global CURRENT
    OUT.mkdir(parents=True)
    say(f'输出目录={OUT}\npython={sys.executable}\nCARGO_HOME={os.environ.get("CARGO_HOME")}\nCARGO_TARGET_DIR={os.environ.get("CARGO_TARGET_DIR")}')
    check(not HS.exists(), 'pre-existing handshake: refuse destructive fixture preparation')
    manifest = json.loads((ROOT / 'artifacts/step2/product-manifest.json').read_text(encoding='utf-8-sig'))
    manifest['files'].sort(key=lambda row: row['path'])
    before = inventory(CANONICAL)
    check(before == manifest['files'], 'canonical differs from authoritative manifest')
    save('canonical-before.json', {'files': len(before), 'bytes': sum(f['bytes'] for f in before), 'manifest_match': True})
    bad = ROOT / 'src-tauri/target/checkpoint2-absent/app.exe'

    CURRENT = 'dev-ready'
    p = Probe(CURRENT, dev=CANONICAL / 'app.exe')
    ready, elapsed = p.wait('Ready')
    hs = identity(p, ready, smoke=True)
    p.stop()
    assert_dead(hs)
    # Keep the actual kill residue for the stale-handshake test below, no hygiene here.
    check(HS.exists(), 'expected hard Job termination to leave handshake for recovery test')
    check(HS.read_bytes() in KNOWN_BYTES, 'unexpected handshake change')

    CURRENT = 'stale-recovery'
    class Fake(BaseHTTPRequestHandler):
        count = 0

        def do_GET(self):
            type(self).count += 1
            body = json.dumps({'status': 'ok', 'boot_id': hs['boot_id'], 'pid': hs['pid'], 'version': '0.1.0'}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', hs['port']), Fake)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        _, code = curl('stale-port-control', hs, '/health')
        check(code == 200, 'old port fake health control')
        count = Fake.count
        p = Probe(CURRENT, dev=CANONICAL / 'app.exe')
        ready, _ = p.wait('Ready')
        new = identity(p, ready)
        check(new['boot_id'] != hs['boot_id'] and new['port'] != hs['port'], 'stale identity not replaced')
        check(Fake.count == count, 'supervisor contacted stale port')
        logs = tail_logs(p.base)
        rows = [json.loads(line) for name, text in logs.items() if name.startswith('engine-') for line in text.splitlines()]
        check(any(r.get('event') == 'stale_handshake_removed' and r.get('old_pid') == hs['pid'] for r in rows), 'no engine-owned stale removal evidence')
        say(f'陈旧恢复：old_pid={hs["pid"]} old_boot={hs["boot_id"]} old_port={hs["port"]}; new_pid={new["pid"]} new_boot={new["boot_id"]} new_port={new["port"]}; fake_old_health_calls_delta={Fake.count-count}')
        p.stop()
        assert_dead(new)
    finally:
        server.shutdown()
        server.server_close()
    hygiene()

    CURRENT = 'dev-invalid-path'
    p = Probe(CURRENT, dev=bad)
    failed, delay = p.wait('Failed', timeout=3)
    value = failure(failed, 'SpawnFailed')
    check(value['exit_reason']['Win32']['code'] == 2 and failed['pid'] is None and delay < 2000, 'not immediate missing path error')
    p.stop()

    CURRENT = 'injection-precedes-env'
    p = Probe(CURRENT, injected=CANONICAL / 'app.exe', dev=bad)
    ready, _ = p.wait('Ready')
    own = identity(p, ready)
    p.stop()
    assert_dead(own)
    hygiene()

    CURRENT = 'release-ignores-env-library-proof'
    p = Probe(CURRENT, release=True, dev=bad)
    ready, _ = p.wait('Ready')
    own = identity(p, ready)
    p.stop()
    assert_dead(own)
    hygiene()
    say('边界：release probe 验证库的编译分支；Tauri resource resolver/--no-bundle 布局尚未验证。')

    for name, raw, error in [('invalid-json', b'{invalid_json', 'HANDSHAKE_INVALID_JSON'),
                             ('missing-fields', b'{"boot_id":"12345678"}', 'HANDSHAKE_INVALID_FIELDS')]:
        CURRENT = name
        seed(raw)
        p = Probe(CURRENT, dev=CANONICAL / 'app.exe')
        failed, _ = p.wait('Failed')
        value = failure(failed, 'HandshakeInvalid', error)
        check(value['exit_reason'] == {'ProcessExit': {'code': 1}}, 'unexpected handshake rejection exit code')
        check(value['preexisting_handshake_invalid'] is not None, 'diagnostic lost')
        check(HS.read_bytes() == raw, 'invalid handshake rewritten')
        logs = tail_logs(p.base)
        rows = [json.loads(line) for n, t in logs.items() if n.startswith('engine-') for line in t.splitlines()]
        causal = [r for r in rows if r.get('event') == 'handshake_error' and r.get('pid') == failed['pid']]
        check(causal and all(r.get('boot_id') and r.get('error') == error for r in causal), 'missing attributable engine line')
        say('本代 handshake_error 原始行：\n' + '\n'.join(json.dumps(r, ensure_ascii=False) for r in causal))
        if name == 'invalid-json':
            p.command('retry')
            retry, _ = p.wait('Failed', generation=2)
            failure(retry, 'HandshakeInvalid', error)
            check(retry['pid'] != failed['pid'] and HS.read_bytes() == raw, 'retry identity/readonly')
        p.stop()
        say(f'非法握手原字节未变：sha256={digest(raw)}')
        hygiene()

    CURRENT = 'missing-dll-with-invalid-old-handshake'
    fixture = FIXTURES / 'app'
    shutil.copytree(CANONICAL, fixture)
    check(inventory(fixture) == before, 'fixture copy mismatch before fault')
    dll = (fixture / '_internal/python312.dll').resolve()
    check(dll.is_relative_to(FIXTURES.resolve()), 'unsafe fault path')
    dll.unlink()
    expected = [f for f in before if f['path'] != '_internal/python312.dll']
    check(inventory(fixture) == expected, 'fault delta is not exactly python312.dll')
    save('fault-fixture-manifest-check.json', {'fixture': str(fixture), 'missing': ['_internal/python312.dll'], 'extra': [], 'changed': [], 'other_files_exact': True})
    raw = b'{invalid_json'
    seed(raw)
    p = Probe(CURRENT, injected=fixture / 'app.exe')
    failed, _ = p.wait('Failed')
    value = failure(failed, 'ExitedBeforeReady')
    check(value['preexisting_handshake_invalid'] == 'InvalidJson', 'invalid-old diagnostic lost')
    check(HS.read_bytes() == raw, 'missing DLL changed old handshake')
    check(not any(n.startswith('engine-') for n in tail_logs(p.base)), 'Python unexpectedly ran in missing-DLL fixture')
    p.stop()
    # Independent control launch to capture bootloader stderr; NOT claimed to be Rust launch stderr.
    result = subprocess.run([str(fixture / 'app.exe')], shell=False, cwd=fixture, capture_output=True, timeout=10)
    control = result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace')
    save('missing-dll-standalone-control-bytes.json', {
        'stdout_base64': base64.b64encode(result.stdout).decode('ascii'),
        'stderr_base64': base64.b64encode(result.stderr).decode('ascii'),
        'exit_code': result.returncode,
        'capture_scope': 'independent control launch, not the supervisor launch stderr'})
    save('missing-dll-standalone-control.txt', f'exit_code={result.returncode}\n{control}')
    say(f'缺 DLL 独立对照（非监督器原次 stderr）：exit_code={result.returncode}\n{control}')
    check('python312.dll' in control and 'Failed to load Python DLL' in control, 'no readable bootloader diagnostic')
    hygiene()

    CURRENT = 'exit-after-ready'
    p = Probe(CURRENT, dev=CANONICAL / 'app.exe')
    ready, _ = p.wait('Ready')
    own = identity(p, ready)
    check(process_time(own['pid']) is not None, 'cannot kill unowned/dead process')
    result = subprocess.run([r'C:\Windows\System32\taskkill.exe', '/F', '/PID', str(own['pid'])], shell=False, capture_output=True, text=True)
    say('taskkill /F /PID ' + str(own['pid']) + '\n' + result.stdout + result.stderr)
    check(result.returncode == 0, 'taskkill failed')
    failed, _ = p.wait('Failed')
    failure(failed, 'EngineExitedAfterReady')
    rows = [json.loads(line) for n, text in tail_logs(p.base).items() if n.startswith('shell-') for line in text.splitlines()]
    count = sum(r.get('event') == 'state_transition' and r.get('from') == 'Ready' and r.get('to') == 'Failed' for r in rows)
    check(count == 1, 'Ready->Failed transition not exactly once')
    p.stop()
    assert_dead(own)
    hygiene()

    CURRENT = 'final-integrity'
    after = inventory(CANONICAL)
    check(after == before == manifest['files'], 'canonical changed during tests')
    # Scan original runtime bytes BEFORE any archival redaction. Scanning only
    # safe()/redacted copies would hide a shell logging defect.
    runtime_source = tail_logs(PROBES[0].base)
    source_token_leaks = [(name, digest(token.encode())) for name, text in runtime_source.items()
                          for token in TOKENS if token in text]
    check(not source_token_leaks, f'original runtime token leakage: {source_token_leaks}')
    leaks = []
    for path in OUT.rglob('*'):
        if path.is_file():
            content = path.read_text(encoding='utf-8', errors='replace')
            if any(token in content for token in TOKENS):
                leaks.append(path.name)
    check(not leaks, f'token leakage in evidence: {leaks}')
    for p in PROBES:
        check(p.proc.poll() == 0, f'probe {p.name} still running/failed')
    shell_rows = []
    for p in PROBES:
        for name, content in tail_logs(p.base).items():
            if name.startswith('shell-'):
                shell_rows.extend(json.loads(line) for line in content.splitlines())
    check(all('token' not in row for row in shell_rows), 'shell logged token key/full handshake')
    receipt = {'result': 'passed', 'canonical_file_count': len(after), 'canonical_bytes': sum(f['bytes'] for f in after),
               'canonical_manifest_match_before_and_after': True, 'actual_tokens_scanned': len(TOKENS),
               'token_leaks': len(leaks), 'actual_token_sha256': sorted(digest(t.encode()) for t in TOKENS),
               'original_runtime_log_token_leaks': len(source_token_leaks),
               'original_runtime_logs_scanned': sorted(runtime_source),
               'original_runtime_append_sha256': {name: digest(text.encode('utf-8')) for name, text in runtime_source.items()},
               'shell_json_lines_valid': True, 'shell_token_key_count': 0,
               'probe_residual_count': 0, 'handshake_absent_after_test_hygiene': not HS.exists(),
               'step2_status': '待实机验证', 'initial_stub_exit70_internal_cause': '未验证',
               'tauri_resource_layout_and_ui': '未验证', 'dev_ready_elapsed_ms_probe_to_snapshot': elapsed}
    save('receipt.json', receipt)
    say(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        OUT.mkdir(parents=True, exist_ok=True)
        save('FAILURE.txt', traceback.format_exc())
        say(f'检查失败：{CURRENT}；内部错误/原始证据先落盘：{OUT}。')
        raise
    finally:
        for running in PROBES:
            try:
                running.stop()
            except Exception as error:
                save(f'{running.name}.cleanup-error.txt', repr(error))
        if OUT.exists():
            hygiene()
        if FIXTURES.exists():
            check(FIXTURES.resolve().is_relative_to((ROOT / 'src-tauri/target/checkpoint2-fixtures').resolve()), 'unsafe fixture cleanup')
            shutil.rmtree(FIXTURES)
            say('测试卫生（不作为通过依据）：删除本轮 target 内的 DLL 故障副本。')
