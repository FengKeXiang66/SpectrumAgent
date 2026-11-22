"""Repeatable source-runtime measurements; never writes to the input dataset."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]


def application(root):
    os.environ['SPECTRUMAGENT_PERMANENT_ROOT'] = str(root)
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
    from backend.paths import AppPaths
    from backend.identity import EngineIdentity
    from spectrumagent.app import create_app
    paths = AppPaths(root)
    paths.create_directories()
    return create_app(paths, EngineIdentity())


def digest(array):
    return hashlib.sha256(array.tobytes(order='C')).hexdigest()


def run(args):
    started = time.perf_counter()
    if args.child:
        app = application(args.output / 'app')
        print(json.dumps({'app_ready_s': time.perf_counter() - started, 'routes': len(app.routes)}), flush=True)
        return
    args.output.mkdir(parents=True, exist_ok=args.reuse)
    startup = []
    for index in range(3):
        wall = time.perf_counter()
        command = [sys.executable, __file__, '--child', '--output', str(args.output / f'boot-{index}')]
        if args.code_root:command += ['--code-root',str(args.code_root)]
        result = subprocess.run(command,
                                capture_output=True, text=True, encoding='utf-8', check=True)
        startup.append({**json.loads(result.stdout.splitlines()[-1]), 'process_wall_s': time.perf_counter() - wall})
    results = {'startup': startup, 'startup_median_s': statistics.median(r['process_wall_s'] for r in startup),
               'scope': 'Fresh Python processes with normal OS file cache; not a reboot/cold-disk measurement.'}
    if args.source:
        import numpy as np
        from threadpoolctl import threadpool_limits
        from spectrumagent.annotation.engines.superpixels import memory_bytes, Parameters
        from spectrumagent.annotation.labels import LabelStore, SimpleLabelRequest
        from backend.database import connect_database
        import spectrumagent.preprocess.run as runs
        app = application(args.output / 'app')
        registry, resources, sessions = app.state.dataset_registry, app.state.segmentation_resources, app.state.annotation_sessions
        records = registry.import_path(str(args.source)).datasets
        with connect_database(registry.database) as db:
            project = db.execute('SELECT project_id FROM dataset_registry LIMIT 1').fetchone()[0]
        if args.reuse:
            with connect_database(registry.database) as db:
                label={'id':db.execute("SELECT id FROM label WHERE project_id=? AND name='性能验证'",(project,)).fetchone()[0]}
        else:
            label = LabelStore(registry.database).add(SimpleLabelRequest(project_id=project, name='性能验证', color_hex='#3388cc'))
        samples, hashes = [], {'calls': 0, 'bytes': 0}
        original = runs.file_sha256
        def count(path):
            hashes['calls'] += 1
            hashes['bytes'] += Path(path).stat().st_size
            return original(path)
        runs.file_sha256 = count
        stop = threading.Event()
        peak = [memory_bytes()[0]]
        def sample():
            while not stop.wait(.02):
                peak[0] = max(peak[0], memory_bytes()[0])
        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        try:
            with threadpool_limits(limits=2):
                begin = time.perf_counter()
                for record in records:
                    cube = str(record.id)
                    t = time.perf_counter()
                    segmentation, action = resources.prepare(cube)
                    key = Path(record.dataset.header_path).stem
                    samples.append({'name': key, 'shape': list(record.dataset.shape), 'source_bytes': Path(record.dataset.data_path).stat().st_size,
                                    'prepare_s': time.perf_counter()-t, 'action': action,
                                    'segments': digest(segmentation.segments), 'initial_segments': digest(segmentation.initial_segments),
                                    'mean_spectra': digest(segmentation.mean_spectra), 'std_spectra': digest(segmentation.std_spectra),
                                    'feature_zscore': digest(segmentation.features.zscore)})
                    print(json.dumps({'prepared': len(samples), 'name': key, 'seconds': samples[-1]['prepare_s']}), flush=True)
                results['batch_s'] = time.perf_counter()-begin
                results['generation_source_hashing'] = dict(hashes)
                hashes.update(calls=0, bytes=0)
                for record, item in zip(records, samples):
                    cube = str(record.id)
                    resources.prepare(cube)
                    mask = np.zeros(record.dataset.shape[:2], dtype=bool)
                    mask[20:30, 20:40] = True
                    t = time.perf_counter()
                    for index in range(5):
                        sessions.edit(cube, mask, action='confirm' if index % 2 == 0 else 'uncertain',
                                      label_id=label['id'], confidence='high' if index % 2 == 0 else None)
                    item['edit_median_s'] = (time.perf_counter()-t) / 5
                    version = sessions.save(cube)
                    frozen = sessions.read_version(version['id'])
                    item['label_map'] = digest(frozen['label_map'])
                    item['spectra'] = {k: digest(v) for k,v in frozen['spectra'].items()}
                results['annotation_source_hashing'] = dict(hashes)
                results['samples'] = samples
                results['edit_median_s'] = statistics.median(s['edit_median_s'] for s in samples)
                results['resources'] = resources.metrics()
                results['params'] = Parameters().__dict__
                results['sampled_peak_rss_bytes'] = peak[0]
                t = time.perf_counter()
                for _ in range(3):
                    registry.catalog()
                results['catalog_mean_s'] = (time.perf_counter()-t)/3
        finally:
            stop.set(); thread.join()
            runs.file_sha256 = original
    results['reused_existing_disk_cache']=args.reuse
    (args.output / ('response-results.json' if args.reuse else 'results.json')).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in results.items() if k not in ('samples',)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--reuse',action='store_true')
    parser.add_argument('--code-root',type=Path)
    args=parser.parse_args()
    if args.code_root:sys.path[:0]=[str(args.code_root),str(args.code_root/'src-python')]
    run(args)
