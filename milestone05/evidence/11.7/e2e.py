"""TASK-05 11.7: real pe / independent sidecar / authenticated HTTP / shipped Rust.

Repository-root .venv/Scripts/python.exe milestone05/evidence/11.7/e2e.py.
No TestClient, engine stubs, original-cube materialization, or source writes.
The rectangular labels are integration fixtures, NOT human annotation quality.
"""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
from uuid import uuid4

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT/'src-python')]
from backend.identity import process_created_at_for_pid
from backend.paths import AppPaths

SEED_SHA256 = '388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2'
SG1 = {'steps': [{'op': 'snv', 'version': 1, 'params': {}},
                 {'op': 'sg_derivative', 'version': 1, 'params': {'order': 1, 'window': 15, 'polyorder': 2}}]}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def write_json(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', 'utf-8')


def compare_json(expected, actual, differences):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and expected.keys() == actual.keys()
        for key in expected:
            compare_json(expected[key], actual[key], differences)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual)
        for a, b in zip(expected, actual):
            compare_json(a, b, differences)
    elif isinstance(expected, float):
        # Extra numeric check reuses TASK-05 §5 reproducibility tolerance, not a new IPC promise.
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)
        if actual != expected:
            differences.append(abs(actual-expected))
    else:
        assert actual == expected and type(actual) is type(expected)


def environment():
    return {'python': sys.version, 'python_executable': sys.executable, 'platform': platform.platform(),
            'machine': platform.machine(), 'processor': platform.processor(), 'logical_cpus': os.cpu_count(),
            'libraries': {name: importlib.metadata.version(name) for name in
                          ('numpy', 'scipy', 'scikit-learn', 'scikit-image', 'httpx', 'fastapi')},
            'thread_environment': {name: os.environ.get(name) for name in
                                   ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')},
            'storage': {'workspace': str(ROOT), 'runtime_drive': ROOT.drive,
                        'free_bytes_before': shutil.disk_usage(ROOT).free}}


def compile_probe(runtime):
    log = runtime/'probe-cargo.jsonl'
    command = ['cargo', 'build', '--lib', '--offline', '--message-format=json']
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=ROOT/'src-tauri', stdout=stream, stderr=subprocess.STDOUT, check=False)
    assert result.returncode == 0, 'probe dependency build failed; see runtime/probe-cargo.jsonl'
    libraries = {}
    for line in log.read_text('utf-8').splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get('reason') == 'compiler-artifact' and entry['target']['name'] in ('spectrum_agent', 'serde_json'):
            libraries[entry['target']['name']] = next(p for p in entry['filenames'] if p.endswith('.rlib'))
    assert set(libraries) == {'spectrum_agent', 'serde_json'}
    target = runtime/'ipc-probe.exe'
    dependencies = Path(libraries['serde_json']).parent
    command = ['rustc', '--edition=2024', str(OUT/'ipc_probe.rs'), '-o', str(target),
               '-L', 'dependency='+str(dependencies)]
    for name, path in libraries.items():
        command.extend(['--extern', name+'='+path])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (runtime/'probe-rustc.txt').write_text(result.stdout+result.stderr, 'utf-8')
    assert result.returncode == 0, 'Rust evidence probe compilation failed; see runtime/probe-rustc.txt'
    return target, {'cargo_exit_code': 0, 'rustc_exit_code': 0, 'libraries': libraries,
                    'level': 'real shipped parse_request/forward + real sidecar; NOT WebView invoke'}


def performance(report):
    singles = report['single_runs']
    comparison = report['compare']
    maximum = max(item['http_seconds'] for item in singles)
    sampling_trigger = maximum > 30 or comparison['http_seconds_per_recipe_mean'] > 30
    async_trigger = maximum > 60 or comparison['n'] > 5
    result = {'source_level': 'implementation measurement, one session/CPU, not a cross-machine promise',
              'environment': report['environment'], 'header': report['header'], 'shape': report['shape'],
              'environment_supplement': 'environment.json: read-only Windows CIM hardware metadata captured after timed e2e',
              'annotation_purpose': report['annotation_purpose'], 'labeled_pixels': report['labeled_pixels'],
              'defaults': {'block_size': 32, 'guard': 'clip'},
              'timing_definitions': {'http_seconds': 'perf_counter request→response; includes preflight and response; trigger lines use this',
                  'lifecycle_seconds': 'finished_at-created_at: persisted lifecycle after preflight, excludes source hashes and other prechecks',
                  'peak_rss_bytes': 'report sidecar process lifetime peak; includes preceding annotation/SLIC work, not a per-run delta',
                  'compare_per_recipe': 'HTTP total / N; an arithmetic cost mean, not individual HTTP spans'},
              'measurement_mode': 'e2e before parallel regression/compile gates; no parameter tuning or spectrum sampling',
              'single_runs': singles, 'compare': comparison,
              'thresholds': {'risk_1': {'source': 'TASK-05 §8 风险1', 'seconds': 30, 'triggered': sampling_trigger,
                  'conclusion': '需回卡议采样策略' if sampling_trigger else '未触发，维持同步'},
                  'r13': {'source': 'TASK-05 §12 R13', 'seconds': 60, 'compare_n_limit': 5, 'triggered': async_trigger,
                  'conclusion': '需回卡议异步执行' if async_trigger else '未触发，维持同步'}},
              'limitations': ['仅本机、本次已标注像素集；不代表全图全标注或跨机性能。',
                              'compare 未提供逐步骤 HTTP spans；总/3 与各单独控制 run 明确分列。',
                              '无聚合谱替代逐像素；触发阈值只回报，不改产品。']}
    write_json('performance.json', result)
    rows = '\n'.join(f"| {r['recipe_code']} | {r['http_seconds']:.6f} | {r['lifecycle_seconds']:.6f} | {r['peak_rss_bytes']} | {r['temporary_bytes']} | {r['artifact_bytes']['sample_spectra']} / {r['artifact_bytes']['report']} |" for r in singles)
    (OUT/'performance.md').write_text(
        '# 11.7 性能实测\n\n来源与层级：实现层、本机真实 pe/独立 sidecar/CPU/默认参数单次测量，不构成跨机承诺。软件/线程/磁盘环境见 performance.json；沙箱平台字段为空的 CPU/架构/内存由 environment.json 中运行后只读 Windows CIM 取证补齐，非计时计数器。\n\n'
        f"输入：{report['header']}，{report['shape']}；已标 {report['labeled_pixels']} 像素。标注为集成夹具，不代表人工质量。block_size=32、guard=clip；未调参、未改采样。\n\n"
        'HTTP 全程为 request→response（包含预检），触发线按此判。落库生命周期=finished_at-created_at，明确从预检后开始。峰值 RSS 来自 report，为 sidecar 自启动以来的峰值，含前序标注/SLIC，不是每 run 增量。\n\n'
        '| 配方 | HTTP 秒 | 落库生命周期秒（预检后） | 峰值 RSS 字节 | 暂存字节 | NPZ / report 字节 |\n|---|---:|---:|---:|---:|---:|\n'+rows+
        f"\n\ncompare N={comparison['n']}：HTTP 总 {comparison['http_seconds']:.6f}s；逐配方平均成本（总/N）{comparison['http_seconds_per_recipe_mean']:.6f}s，不冒充单个配方的独立 HTTP span。各单独控制 run 见上表。\n\n"
        f"- §8 风险1（单配方 >30s）：{result['thresholds']['risk_1']['conclusion']}。\n"
        f"- §12 R13（单 run >60s 或 compare N>5）：{result['thresholds']['r13']['conclusion']}。\n\n"
        '两条线分别判断；只回报结论，未改同步执行、默认参数或逐像素输入。原始立方体不全量物化。\n', 'utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runtime = ROOT/'.runtime/m05-11.7'/uuid4().hex
    (runtime/'tmp').mkdir(parents=True)
    os.environ.update(TEMP=str(runtime/'tmp'), TMP=str(runtime/'tmp'), PYTHONIOENCODING='utf-8', CARGO_NET_OFFLINE='true')
    paths = AppPaths(runtime)
    header_lines = (ROOT/'milestone04/evidence/calibration/cubes_11.txt').read_text('utf-8').splitlines()
    header = Path(header_lines[0])
    seeds = ROOT/'milestone04/evidence/seeds_20.json'
    assert digest(seeds).upper() == SEED_SHA256
    result = {'started_at': datetime.now(timezone.utc).isoformat(), 'environment': environment(),
              'runtime': str(runtime), 'header': str(header), 'events': [], 'passed': False,
              'annotation_purpose': 'scripted synthetic integration regions on real cube; NOT human annotation quality',
              'single_runs': [], 'source_files': {}}
    process = None
    identity = None
    token = None
    try:
        # Compile first, outside the performance measurement window; never alter product Rust.
        probe, result['probe_build'] = compile_probe(runtime)
        with (runtime/'sidecar-stdio.txt').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'backend', '--data-root', str(runtime)], cwd=ROOT,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            deadline = time.monotonic()+40  # Evidence harness startup bound, not a product default.
            while not paths.handshake.exists():
                assert process.poll() is None, 'sidecar exited before handshake'
                assert time.monotonic() < deadline, 'handshake startup deadline'
                time.sleep(.05)
            identity = json.loads(paths.handshake.read_text('utf-8'))
            token = identity['token']
            assert process_created_at_for_pid(identity['pid']) == identity['process_created_at']
            result['sidecar'] = {k: identity[k] for k in ('pid', 'boot_id', 'port', 'version', 'protocol')}
            with httpx.Client(base_url=f"http://127.0.0.1:{identity['port']}", headers={'Authorization': 'Bearer '+token},
                              trust_env=False, timeout=300) as client:
                def call(method, route, body=None, status=200, binary=False):
                    started = time.perf_counter()
                    response = client.request(method, route, **({'json': body} if body is not None else {}))
                    elapsed = time.perf_counter()-started
                    assert token.encode() not in response.content
                    assert response.status_code == status, (route, response.status_code, response.text[:800])
                    if route == '/health':
                        assert response.json()['boot_id'] == identity['boot_id'] and response.json()['pid'] == identity['pid']
                    else:
                        assert response.headers['X-SpectrumAgent-Boot-Id'] == identity['boot_id']
                        assert int(response.headers['X-SpectrumAgent-Pid']) == identity['pid']
                    assert len(response.content) <= 8*1024*1024
                    result['events'].append({'method': method, 'path': route, 'status': status,
                                             'http_seconds': elapsed, 'response_bytes': len(response.content)})
                    if binary:
                        return response
                    value = response.json() if status != 204 else None
                    assert token not in json.dumps(value)
                    return value

                assert call('GET', '/health')['version'] == '0.1.0'
                imported = call('POST', '/api/v1/datasets/import', {'path': str(header)})['datasets'][0]
                cube = imported['id']
                base = '/api/v1/datasets/'+cube
                result.update(cube_id=cube, shape=imported['dataset']['shape'])
                assert result['shape'] == [231, 640, 200]
                def remember_sources(record):
                    for key in ('header_path', 'data_path'):
                        path = Path(record['dataset'][key])
                        result['source_files'][str(path)] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
                remember_sources(imported)
                segmented = call('POST', base+'/superpixels', {})
                assert {k: segmented['params'][k] for k in ('n_segments', 'compactness', 'pca_components')} == {'n_segments': 800, 'compactness': .5, 'pca_components': 5}
                working = call('GET', base+'/annotations/working')
                project = working['project_id']
                schemas = call('GET', '/api/v1/labels?project_id='+project)
                labels = {label['code']: label['id'] for schema in schemas for label in schema['labels']}
                for code, bounds in [('PE', (10, 60, 20, 140)), ('PET', (85, 135, 240, 360)), ('PP', (155, 205, 480, 600))]:
                    l0, l1, s0, s1 = bounds
                    working = call('POST', base+'/annotations/regions', {'label_id': labels[code], 'action': 'confirm',
                        'geometry': {'polygon': [[l0, s0], [l0, s1], [l1, s1], [l1, s0]]}})
                saved = call('POST', base+'/annotations/save', {'note': '11.7 integration fixture; not human annotation quality'})
                annotation = saved['id']
                result['annotation_version_id'] = annotation
                result['labeled_pixels'] = working['statistics']['labeled_pixels']
                assert result['labeled_pixels'] == 18000
                library = call('GET', '/api/v1/preprocess/recipes')
                builtin = next(recipe for recipe in library if recipe['code'] == 'plastic-snv-sg1')
                version = builtin['versions'][0]
                assert version['version_no'] == 1 and version['pipeline'] == SG1 and builtin['builtin'] == 1
                def create(code, pipeline):
                    return call('POST', '/api/v1/preprocess/recipes', {'code': code, 'name': code, 'description': '11.7 e2e', 'pipeline': pipeline}, status=201)
                created = create('e2e-snv-sg1', SG1)
                assert created['versions'][0]['version_no'] == 1 and created['versions'][0]['pipeline'] == SG1

                def audit_run(row):
                    assert row['status'] == 'succeeded' and row['error'] is None and row['b01_branch'] == 'scale'
                    assert {'mean', 'median', 'p10', 'p90'} <= row['metrics']['snr'].keys()
                    assert 'fisher' in row['metrics'] and len(row['metrics']['boundaries']) == 3
                    assert {a['kind'] for a in row['artifacts']} == {'sample_spectra', 'report'} and len(row['artifacts']) == 2
                    reports, artifacts = None, []
                    with sqlite3.connect(paths.database) as db:
                        db.row_factory = sqlite3.Row
                        records = [dict(r) for r in db.execute('SELECT * FROM preprocess_artifact WHERE run_id=?', (row['id'],))]
                    assert {a['id'] for a in records} == {a['id'] for a in row['artifacts']}
                    for artifact in records:
                        relative = PurePosixPath(artifact['relative_path'])
                        assert not relative.is_absolute() and '..' not in relative.parts and '\\' not in str(relative)
                        path = paths.preprocessed.joinpath(*relative.parts)
                        response = call('GET', f"/api/v1/preprocess/runs/{row['id']}/artifacts/{artifact['kind']}", binary=True)
                        assert digest(path) == artifact['sha256'] == hashlib.sha256(response.content).hexdigest()
                        assert len(response.content) == path.stat().st_size
                        if artifact['kind'] == 'report':
                            assert response.headers['content-type'].startswith('application/json')
                            reports = response.json()
                        else:
                            assert response.headers['content-type'] == 'application/octet-stream'
                        artifacts.append({**artifact, 'bytes': path.stat().st_size, 'download_bytes': len(response.content),
                                          'sha256_matches_db': True, 'size_scope': 'evidence; DB has no size column'})
                    assert reports['run_id'] == row['id'] and reports['metrics'] == row['metrics']
                    curves = reports['curves']
                    assert curves['labeled'] is True and sum(c['count'] for c in curves['classes']) == result['labeled_pixels']
                    for curve in curves['classes']:
                        assert curve['after'] is not None and 0 < len(curve['before']) <= 512 and 0 < len(curve['after']) <= 512
                        for curve_key, axis_key in [('before', 'wavelengths_in'), ('after', 'wavelengths_out')]:
                            assert curves[axis_key] is None or len(curve[curve_key]) == len(curves[axis_key])
                    return reports, artifacts

                result['artifact_audits'] = {}
                def single(recipe, record_measurement=True):
                    row = call('POST', base+'/preprocess/runs', {'annotation_version_id': annotation, 'recipe_version_id': recipe['versions'][0]['id']})
                    elapsed = result['events'][-1]['http_seconds']
                    data, artifacts = audit_run(row)
                    result['artifact_audits'][row['id']] = artifacts
                    if record_measurement:
                        result['single_runs'].append({'run_id': row['id'], 'recipe_code': recipe['code'], 'http_seconds': elapsed,
                            'lifecycle_seconds': (datetime.fromisoformat(row['finished_at'])-datetime.fromisoformat(row['created_at'])).total_seconds(),
                            'peak_rss_bytes': data['peak_rss_bytes'], 'temporary_bytes': data['temporary_bytes'],
                            'temporary_peak_bytes': data['temporary_peak_bytes'], 'artifact_bytes': {a['kind']: a['bytes'] for a in artifacts}})
                    return row, data
                first, first_report = single(builtin)
                second, second_report = single(builtin)
                assert first['input_fingerprint'] == second['input_fingerprint']
                assert second_report['input_fingerprint_matches_previous'] is True
                def spectra_path(row):
                    return paths.preprocessed/next(a['relative_path'] for a in row['artifacts'] if a['kind'] == 'sample_spectra')
                max_difference = 0.
                with np.load(spectra_path(first), allow_pickle=False) as a, np.load(spectra_path(second), allow_pickle=False) as b:
                    assert set(a.files) == set(b.files)
                    for key in a.files:
                        np.testing.assert_allclose(a[key], b[key], rtol=0, atol=1e-12)
                        max_difference = max(max_difference, float(np.max(np.abs(a[key]-b[key]))))
                result['reproduction'] = {'input_fingerprint': first['input_fingerprint'], 'run_ids': [first['id'], second['id']], 'max_absolute_difference': max_difference, 'atol': 1e-12}
                only_snv = create('e2e-snv', {'steps': [{'op': 'snv', 'version': 1, 'params': {}}]})
                standard = create('e2e-standard', {'steps': [{'op': 'standardize', 'version': 1, 'params': {'method': 'standard'}}]})
                compared = call('POST', base+'/preprocess/compare', {'annotation_version_id': annotation,
                    'recipe_version_ids': [recipe['versions'][0]['id'] for recipe in (builtin, only_snv, standard)]})
                compare_seconds = result['events'][-1]['http_seconds']
                ranked = compared['ranking']
                assert [r['fisher'] for r in ranked] == sorted((r['fisher'] for r in ranked), reverse=True)
                assert {r['run_id'] for r in ranked} == {r['id'] for r in compared['runs'] if r['metrics'].get('fisher') is not None and r['status'] == 'succeeded'}
                assert len(compared['boundaries']) == 3 and compared['selection']
                compare_runs = []
                for row in compared['runs']:
                    data, artifacts = audit_run(row)
                    result['artifact_audits'][row['id']] = artifacts
                    compare_runs.append({'run_id': row['id'], 'recipe_version_id': row['recipe_version_id'],
                        'lifecycle_seconds': (datetime.fromisoformat(row['finished_at'])-datetime.fromisoformat(row['created_at'])).total_seconds(),
                        'peak_rss_bytes': data['peak_rss_bytes'], 'temporary_bytes': data['temporary_bytes'],
                        'artifact_bytes': {a['kind']: a['bytes'] for a in artifacts}})
                result['compare'] = {'n': 3, 'http_seconds': compare_seconds, 'http_seconds_per_recipe_mean': compare_seconds/3,
                    'runs': compare_runs, 'ranking': ranked, 'boundaries': compared['boundaries'], 'selection': compared['selection']}
                # Independent full HTTP costs for the two other recipes, no inferred individual spans.
                single(only_snv)
                single(standard)
                before_recipe = call('GET', '/api/v1/preprocess/recipes/'+created['id'])
                association = f"/api/v1/preprocess/projects/{project}/recipes/{created['id']}"
                call('POST', association)
                assert any(r['id'] == created['id'] for r in call('GET', f'/api/v1/preprocess/projects/{project}/recipes'))
                call('DELETE', association, status=204)
                call('DELETE', association, status=204)
                assert all(r['id'] != created['id'] for r in call('GET', f'/api/v1/preprocess/projects/{project}/recipes'))
                assert call('GET', '/api/v1/preprocess/recipes/'+created['id']) == before_recipe
                result['project_selection_preserves_recipe_and_versions'] = True
                # Genuine live Rust forwarding; no stub server, not a claim of WebView invoke.
                request_file = runtime/'ipc-request.json'
                request_file.write_text(json.dumps({'op': 'get_artifact', 'run_id': first['id'], 'kind': 'report'}), 'utf-8')
                probe_result = subprocess.run([str(probe), str(paths.handshake), str(request_file), str(runtime/'ipc-report.json')],
                                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=310)
                assert probe_result.returncode == 0, probe_result.stderr
                ipc_report = json.loads((runtime/'ipc-report.json').read_text('utf-8'))
                differences = []
                compare_json(first_report, ipc_report, differences)
                assert 'body_base64' not in ipc_report
                result['ipc_probe'] = {'exit_code': 0, 'level': result['probe_build']['level'], 'structure_and_exact_metadata_match': True,
                                       'numeric_roundtrip': {'atol': 1e-12, 'rtol': 0, 'source': 'extra check using TASK-05 §5 reproducibility tolerance',
                                                             'changed_float_count': len(differences), 'max_absolute_difference': max(differences, default=0.)},
                                       'body_base64_absent': True, 'stdout': probe_result.stdout.strip()}
                invalid = create('e2e-forbidden-reflectance', {'steps': [{'op': 'reflectance', 'version': 1, 'params': {'hdr': {}}}]})
                error = call('POST', base+'/preprocess/runs', {'annotation_version_id': annotation, 'recipe_version_id': invalid['versions'][0]['id']}, status=400)
                assert error['error'] == 'INVALID_OPERATOR_PARAMS'
                other = call('POST', '/api/v1/datasets/import', {'path': header_lines[1]})['datasets'][0]
                remember_sources(other)
                error = call('POST', f"/api/v1/datasets/{other['id']}/preprocess/runs", {'annotation_version_id': annotation, 'recipe_version_id': version['id']}, status=404)
                assert error['error'] == 'VERSION_NOT_FOUND'
                result['negative_paths'] = {'recipe_reflectance': 'INVALID_OPERATOR_PARAMS/400', 'foreign_cube_annotation': 'VERSION_NOT_FOUND/404'}
                with sqlite3.connect(paths.database) as db:
                    db.row_factory = sqlite3.Row
                    lineage = [dict(row) for row in db.execute('SELECT r.id AS run_id,r.cube_id,r.annotation_version_id,a.snapshot_ref,r.recipe_version_id,v.recipe_id '
                        'FROM preprocess_run r JOIN annotation_version a ON a.id=r.annotation_version_id JOIN preprocess_recipe_version v ON v.id=r.recipe_version_id JOIN preprocess_recipe p ON p.id=v.recipe_id')]
                    assert len(lineage) == 7 and db.execute('SELECT count(*) FROM preprocess_run WHERE status != "succeeded"').fetchone()[0] == 0
                    for row in lineage:
                        assert row['cube_id'] == cube and row['annotation_version_id'] == annotation
                        assert (paths.snapshots/row['snapshot_ref']/'label_map.npz').is_file()
                    assert db.execute('SELECT count(*) FROM sample_spectrum WHERE version_id=?', (annotation,)).fetchone()[0] == 3
                result['lineage'] = lineage
                result['builtin_recipe_id'] = builtin['id']
                result['created_recipe_id'] = created['id']
                result['source_and_seed_unchanged'] = digest(seeds).upper() == SEED_SHA256 and all(
                    Path(path).stat().st_size == info['bytes'] and digest(path) == info['sha256'] for path, info in result['source_files'].items())
                assert result['source_and_seed_unchanged']
                performance(result)
        result['passed'] = True
    except BaseException as error:
        result['failure'] = {'type': type(error).__name__, 'detail': str(error), 'traceback': traceback.format_exc()}
        raise
    finally:
        if process is not None:
            if identity and process_created_at_for_pid(identity['pid']) == identity['process_created_at']:
                os.kill(identity['pid'], signal.SIGTERM)
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
            result['sidecar_stopped'] = process.poll() is not None and (not identity or process_created_at_for_pid(identity['pid']) is None)
        if token:
            logs = [runtime/'sidecar-stdio.txt', *(p for p in paths.logs.rglob('*') if p.is_file())]
            result['token_absent_from_logs'] = all(token not in path.read_text('utf-8', errors='replace') for path in logs)
            if not result['token_absent_from_logs']:
                result['passed'] = False
        write_json('e2e-result.json', result)
    assert result['passed'] and result['sidecar_stopped'] and result['token_absent_from_logs']
    print(json.dumps({'passed': True, 'http_calls': len(result['events']), 'runtime': str(runtime),
                      'reproduction': result['reproduction'], 'ipc': result['ipc_probe'],
                      'performance': 'performance.json'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
