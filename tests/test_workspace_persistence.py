"""Real process restarts must retain the workflow, not just in-memory caches."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.labels import LabelStore, SimpleLabelRequest
from spectrumagent.preprocess.recipes import RecipeStore
from spectrumagent.storage import guard


def worker(phase, folder):
    temp = folder / 'system-temp'
    temp.mkdir(exist_ok=True)
    tempfile.tempdir = str(temp)
    paths = AppPaths(folder / 'app')
    paths.create_directories()
    app = create_app(paths, EngineIdentity())
    registry, sessions = app.state.dataset_registry, app.state.annotation_sessions
    recipes = RecipeStore(paths.database)
    ledger = folder / 'references.json'
    if phase == 'save':
        from spectral.io import envi
        source = folder / 'source'
        source.mkdir()
        cube = np.random.default_rng(71).uniform(.1, .8, (8, 8, 8)).astype(np.float32)
        envi.save_image(str(source / 'sample.hdr'), cube, interleave='bip', ext='.dat',
                        metadata={'wavelength': list(range(1100, 1180, 10))})
        imported = registry.import_path(str(source / 'sample.hdr'))
        cube_id = str(imported.datasets[0].id)
        with connect_database(paths.database) as db:
            project_id = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cube_id,)).fetchone()[0]
        label = LabelStore(paths.database).add(SimpleLabelRequest(
            project_id=project_id, name='测试材料', color_hex='#3388cc'))
        app.state.superpixel_engine.prepare(cube_id, sessions,
                                           Parameters(n_segments=8, pca_components=3, block_size=8))
        mask = np.zeros((8, 8), dtype=bool)
        mask[:4] = True
        sessions.edit(cube_id, mask, action='confirm', label_id=label['id'], confidence='high')
        saved = sessions.save(cube_id, note='重启验证')
        version_id = saved['id']
        recipe = recipes.create('restart-test', '重启配方', None,
                                {'steps': [{'op': 'snv', 'version': 1, 'params': {}}]})
        recipe_version = recipe['versions'][0]['id']
        run = app.state.preprocess_runner.run(cube_id, version_id, recipe_version)
        assert run['status'] == 'succeeded', run
        owner = app.state.agent_sessions.create()['id']
        app.state.agent_sessions.select(owner, cube_id)
        from spectrumagent.agent.state import AgentStore
        AgentStore(paths.database).new_round(owner, '保留这条处理记录', [], status='done')
        from test_experiments import config_for
        from spectrumagent.experiments.schema import ExperimentConfig
        experiment = app.state.experiments.run(ExperimentConfig.model_validate(config_for(folder)))
        # Abandon one preprocess attempt and a training receipt as a killed engine would.
        abandoned, job, completed_job, committed_job = (str(uuid4()) for _ in range(4))
        training_rows = {status: str(uuid4()) for status in ('pending', 'running', 'succeeded', 'failed', 'cancelled')}
        inference_rows = {status: str(uuid4()) for status in ('pending', 'running', 'succeeded', 'failed')}
        receipt = {'job_id': job, 'status': 'running', 'snapshot_version': 3, 'phase': 'cv',
                   'completed_folds': [0], 'run_id': None, 'engine_boot_id': 'old-boot'}
        with connect_database(paths.database) as db:
            for status, identifier in training_rows.items():
                db.execute('INSERT INTO training_run '
                           '(id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,cv_folds,seed,status,created_at) '
                           "VALUES (?,?,?,?,'classification','label','group_kfold',2,17,?,'before-restart')",
                           (identifier, json.dumps([cube_id]), json.dumps([version_id]), json.dumps([run['id']]), status))
            schema = db.execute('SELECT schema_id FROM label WHERE id=?', (label['id'],)).fetchone()[0]
            model_id = str(uuid4())
            db.execute('INSERT INTO model_registry '
                       '(id,run_id,name,version,target_schema_id,data_fingerprint,applicability,calibration,created_at) '
                       "VALUES (?,?,'saved model',1,?,'fingerprint','{}','{}','before-restart')",
                       (model_id, training_rows['succeeded'], schema))
            for status, identifier in inference_rows.items():
                db.execute('INSERT INTO inference_run '
                           '(id,model_id,cube_id,preprocess_run_id,annotation_version_id,status,created_at) '
                           "VALUES (?,?,?,?,?,?,'before-restart')",
                           (identifier, model_id, cube_id, run['id'], version_id, status))
            db.execute('INSERT INTO preprocess_run '
                       '(id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,created_at) '
                       "VALUES (?,?,?,?,'passthrough',?,'running','before-restart')",
                       (abandoned, cube_id, version_id, recipe_version, 'a' * 64))
            db.execute('INSERT INTO training_job VALUES (?,?,?,?,?,?,?,?)',
                       (job, 'old-boot', owner, 'request', '{}', '{}', json.dumps(receipt), 'before-restart'))
            done = {**receipt, 'job_id': completed_job, 'status': 'succeeded'}
            db.execute('INSERT INTO training_job VALUES (?,?,?,?,?,?,?,?)',
                       (completed_job, 'old-boot', owner, 'done', '{}', '{}', json.dumps(done), 'before-restart'))
            committed = {**receipt, 'job_id': committed_job, 'run_id': training_rows['succeeded']}
            db.execute('INSERT INTO training_job VALUES (?,?,?,?,?,?,?,?)',
                       (committed_job, 'old-boot', owner, 'committed', '{}', '{}', json.dumps(committed), 'before-restart'))
            db.execute("INSERT INTO experiment_dialogue(session_id,run_status) VALUES (?,'running')", (owner,))
        refs = dict(cube=cube_id, label=label['id'], annotation=version_id, recipe=recipe['id'],
                    run=run['id'], owner=owner,
                    experiment=experiment['experiment_id'], abandoned=abandoned, job=job, completed_job=completed_job,
                    committed_job=committed_job, training_rows=training_rows, inference_rows=inference_rows)
        # Record all durable output bytes before the process fully exits.
        refs['artifacts'] = {str(p.relative_to(paths.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for base in (paths.snapshots, paths.preprocessed, paths.experiment_archive)
                            for p in base.rglob('*') if p.is_file()}
        ledger.write_text(json.dumps(refs), encoding='utf-8')
    else:
        refs = json.loads(ledger.read_text('utf-8'))
        labels = [label for schema in LabelStore(paths.database).tree(
            LabelStore(paths.database).projects()[0]['id']) for label in schema['labels']]
        assert [(label['id'], label['name']) for label in labels] == [(refs['label'], '测试材料')]
        for relative, digest in refs['artifacts'].items():
            assert hashlib.sha256((paths.root / relative).read_bytes()).hexdigest() == digest
        assert registry.record(refs['cube']).id
        working = sessions.working(refs['cube'])
        assert working['statistics']['labeled_pixels'] == (32 if phase == 'restore' else 40)
        snapshot = sessions.read_version(refs['annotation'])
        assert int((snapshot['label_map'] >= 0).sum()) == 32
        assert recipes.get(refs['recipe'])['versions'][0]['id']
        assert app.state.preprocess_runner.get(refs['run'])['status'] == 'succeeded'
        from spectrumagent.preprocess.current import CurrentWorkspace
        member = CurrentWorkspace(sessions, app.state.preprocess_runner).state()['members'][0]
        # The second restart keeps an unsaved edit; its old processing result must
        # become unavailable until the new annotation has been processed.
        assert member['status'] == ('ready' if phase == 'restore' else 'need_preprocess')
        assert app.state.agent_sessions.detail(refs['owner'])['canvas_focus']['cube_id'] == refs['cube']
        assert app.state.agent_sessions.list(kind='global')['sessions'][0]['id'] == refs['owner']
        from spectrumagent.agent.state import AgentStore
        assert AgentStore(paths.database).rounds(refs['owner'])
        assert app.state.experiments.get(refs['experiment'])['status'] == 'succeeded'
        assert app.state.experiments.archive.load_model(refs['experiment'])
        abandoned = app.state.preprocess_runner.get(refs['abandoned'])
        assert abandoned['status'] == 'failed' and abandoned['error']['error'] == 'ENGINE_INTERRUPTED'
        from spectrumagent.modeling.training_jobs import jobs_for
        jobs = jobs_for(registry, paths)
        receipt = jobs.status(refs['job'], owner=refs['owner'])
        assert receipt['status'] == 'failed' and receipt['completed_folds'] == [0]
        assert receipt['snapshot_version'] == 4
        assert jobs.status(refs['completed_job'])['status'] == 'succeeded'
        assert jobs.status(refs['committed_job'])['status'] == 'succeeded'
        assert jobs.status(refs['committed_job'])['result_status'] == 'complete'
        assert refs['job'] in [r['job_id'] for r in jobs.list(owner=refs['owner'])['items']]
        from spectrumagent.modeling import ModelingError
        with pytest.raises(ModelingError):
            jobs.status(refs['job'], owner='someone-else')
        with connect_database(paths.database) as db:
            for table, rows in (('training_run', refs['training_rows']), ('inference_run', refs['inference_rows'])):
                for previous, identifier in rows.items():
                    row = db.execute(f'SELECT status,error FROM {table} WHERE id=?', (identifier,)).fetchone()
                    assert row[0] == ('failed' if previous in ('pending', 'running') else previous)
                    if previous in ('pending', 'running'):
                        assert json.loads(row[1])['error'] == 'ENGINE_INTERRUPTED'
            assert db.execute('SELECT run_status FROM experiment_dialogue WHERE session_id=?',
                              (refs['owner'],)).fetchone()[0] == 'failed'
        # Continue editing the restored authoritative draft in the new process.
        mask = np.zeros((8, 8), dtype=bool)
        mask[4:5] = True
        sessions.edit(refs['cube'], mask, action='confirm', label_id=refs['label'], confidence='high')
        assert sessions.working(refs['cube'])['statistics']['labeled_pixels'] == 40
    for instance in guard._guards.values():
        instance.close()


def test_workflow_survives_a_full_process_restart(tmp_path):
    env = {**os.environ, 'SPECTRUMAGENT_DATA_ROOT': str(tmp_path / 'app'),
           'SPECTRUMAGENT_PERMANENT_ROOT': str(tmp_path / 'app'), 'PYTHONUTF8': '1'}
    for phase in ('save', 'restore', 'restore-again'):
        # The second restore also verifies startup reconciliation is idempotent.
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), phase, str(tmp_path)],
                                cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr


if __name__ == '__main__':
    worker(sys.argv[1], Path(sys.argv[2]))
