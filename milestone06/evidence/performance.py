"""Actual source sidecar + loopback HTTP; real PE; no TestClient or mock.

Timings are single-machine observations, not cross-machine guarantees. Numeric
selection is our TASK-06 algorithm, not a claimed reproduction of SHIS's DLL.
"""
import base64
import hashlib
from itertools import combinations
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
import uuid

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'src-python')]
from backend.paths import AppPaths
from backend.identity import process_created_at_for_pid
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.display.falsecolor import select_feature_bands


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'd4'
    output = Path(__file__).parent
    runtime = ROOT/'.runtime'/('task06-http-'+uuid.uuid4().hex)
    runtime.mkdir()
    env = dict(os.environ, TEMP=str(runtime), TMP=str(runtime), PYTHONIOENCODING='utf-8')
    header = (ROOT/'milestone04/evidence/calibration/cubes_11.txt').read_text('utf-8').splitlines()[0]
    result = {'mode': 'actual independent python -m backend; real loopback HTTP with Bearer + boot_id/pid each response; default algorithm/stretches; isolated E runtime',
              'environment': {'platform': platform.platform(), 'python': sys.version, 'numpy': np.__version__, 'logical_cpus': os.cpu_count()},
              'source': header, 'runtime': str(runtime), 'passed': False, 'http_ms': {}}
    with (runtime/'stdio.txt').open('w', encoding='utf-8') as log:
        identity = None
        proc = subprocess.Popen([sys.executable, '-m', 'backend', '--data-root', str(runtime/'data')],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            handshake = runtime/'data/run/handshake.json'
            deadline = time.perf_counter()+60
            while not handshake.exists():
                assert proc.poll() is None, 'sidecar exited before readiness'
                assert time.perf_counter() < deadline, 'readiness timeout'
                time.sleep(.05)
            identity = json.loads(handshake.read_text('utf-8'))
            # On Windows the venv launcher can start a distinct python child.
            assert process_created_at_for_pid(identity['pid']) == identity['process_created_at']
            with httpx.Client(base_url=f"http://127.0.0.1:{identity['port']}", timeout=30, trust_env=False,
                              headers={'Authorization': 'Bearer '+identity['token']}) as client:
                def call(method, path, body=None, timing=None):
                    start = time.perf_counter()
                    response = client.request(method, path, **({'json': body} if body is not None else {}))
                    elapsed = (time.perf_counter()-start)*1000
                    assert response.status_code == 200, (path, response.status_code, response.text[:300])
                    assert response.headers['X-SpectrumAgent-Boot-Id'] == identity['boot_id']
                    assert int(response.headers['X-SpectrumAgent-Pid']) == identity['pid']
                    assert identity['token'].encode() not in response.content
                    if timing:
                        result['http_ms'][timing] = elapsed
                    return response.json()
                imported = call('POST', '/api/v1/datasets/import', {'path': header})['datasets'][0]
                base = '/api/v1/datasets/'+imported['id']
                hashes = {imported['dataset'][key]: digest(imported['dataset'][key]) for key in ('header_path', 'data_path')}
                manual = call('GET', base+'/preview?bands=186,124,62&stretch=auto&size=full', timing='manual_rgb_cold')
                auto = call('GET', base+'/preview?bands=auto&size=full', timing='auto_cold')
                warm = call('GET', base+'/preview?bands=auto&size=full', timing='auto_warm')
                assert manual['width'] == auto['width'] == 640 and manual['height'] == auto['height'] == 231
                assert auto['bands'] == warm['bands'] and auto['png_base64'] == warm['png_base64']
                for name, item in [('manual-rgb', manual), ('auto-rgb', auto)]:
                    (output/(phase+'-'+name+'.png')).write_bytes(base64.b64decode(item['png_base64']))
                legacy = call('GET', base+'/preview?band=0&stretch=none')
                reference = json.loads((output/'preflight-output.json').read_text('utf-8'))
                result['legacy_none_png_sha256'] = hashlib.sha256(base64.b64decode(legacy['png_base64'])).hexdigest()
                assert result['legacy_none_png_sha256'] == reference['head_png_sha256']
                registry = DatasetRegistry(AppPaths(runtime/'data').database)
                ds, _ = registry.readable(imported['id'], raw=False)
                before_working = call('GET', base+'/annotations/working')
                before_versions = call('GET', base+'/annotations')
                point = call('POST', base+'/spectra/mean', {'l0': 29, 'l1': 30, 's0': 64, 's1': 65, 'raw': True}, timing='point_spectrum')
                region = call('POST', base+'/spectra/mean', {'l0': 12, 'l1': 20, 's0': 20, 's1': 30}, timing='region_mean')
                point_error = float(np.max(np.abs(np.asarray(point['mean'])-ds.read_pixel(29, 64))))
                region_error = float(np.max(np.abs(np.asarray(region['mean'])-ds.read_region(12, 20, 20, 30).mean(axis=(0, 1)))))
                assert point['count'] == 1 and region['count'] == 80
                assert point_error <= 1e-9 and region_error <= 1e-9
                assert call('GET', base+'/annotations/working') == before_working
                assert call('GET', base+'/annotations') == before_versions
                result.update(point_max_abs_error=point_error, region_max_abs_error=region_error,
                              point_count=point['count'], region_count=region['count'], working_and_versions_unchanged=True)
                independent = [select_feature_bands(ds, ds.shape, ds.wavelengths) for _ in range(3)]
                assert independent[0] == independent[1] == independent[2]
                assert list(independent[0][:3]) == auto['bands']
                step = max(1, math.ceil(ds.shape[0]/128))
                sample = ds.read_subimage(list(range(0, ds.shape[0], step)), list(range(0, ds.shape[1], step)), list(range(ds.shape[2])))
                flat = sample.reshape(-1, ds.shape[2])
                rho = sample.std(axis=(0, 1))/(np.diff(sample, axis=1).std(axis=(0, 1))/np.sqrt(2)+1e-12)
                candidates = np.flatnonzero(rho >= np.median(rho))
                candidate_corr = np.abs(np.corrcoef(flat[:, candidates].T))
                assert candidate_corr.shape == (len(candidates), len(candidates))
                corr_full = np.abs(np.corrcoef(flat.T))
                best, score = None, -np.inf
                for a, b, c in combinations(candidates, 3):
                    if ds.wavelengths[c]-ds.wavelengths[a] < .15*(ds.wavelengths[-1]-ds.wavelengths[0]):
                        continue
                    value = rho[a]+rho[b]+rho[c]-2.5*np.mean([corr_full[a, b], corr_full[a, c], corr_full[b, c]])
                    if value > score:
                        best, score = (int(c), int(b), int(a)), float(value)
                assert list(best) == auto['bands']
                selected = corr_full[np.ix_(auto['bands'], auto['bands'])]
                max_corr = float(selected[np.triu_indices(3, 1)].max())
                assert max_corr < .75
                assert all(digest(path) == before for path, before in hashes.items())
                result.update(cube_shape=list(ds.shape), sampling_step=step, sample_shape=list(sample.shape),
                    candidate_count=len(candidates), corr_shape=list(candidate_corr.shape), bands=auto['bands'], wavelengths=auto['wavelengths'],
                    fallback=auto['fallback'], max_abs_corr=max_corr, selected_corr=selected.tolist(), score=score,
                    independent_three_runs_equal=True, full_band_matrix_crosscheck=True, sources_unchanged=True,
                    manual_png_bytes=len(base64.b64decode(manual['png_base64'])), auto_png_bytes=len(base64.b64decode(auto['png_base64'])))
                assert result['http_ms']['manual_rgb_cold'] < 100
                assert result['http_ms']['auto_cold'] < 1500
                result['passed'] = True
        finally:
            if identity and process_created_at_for_pid(identity['pid']) == identity['process_created_at']:
                os.kill(identity['pid'], signal.SIGTERM)
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=15)
            result['stopped'] = not identity or process_created_at_for_pid(identity['pid']) is None
            (output/(phase+'-performance.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
