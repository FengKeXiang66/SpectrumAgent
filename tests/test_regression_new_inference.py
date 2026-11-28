"""A deployable regression snapshot must predict new, unannotated ENVI data."""
import json
from uuid import uuid4

import numpy as np
import pytest
from spectral.io import envi

from test_experiment_conversation import application, workspace, machine_for, tool
from test_regression_plan import prepared
from backend.database import connect_database
from spectrumagent.agent.llm import ChatResult
from spectrumagent.modeling import ModelingError
from spectrumagent.preprocess.fitted import transform
from spectrumagent.preprocess.registry import OperatorRegistry
from spectrumagent.modeling.regression import predict


def registered(p):
    app = p['app']
    run = app.state.training_runs.regress(preprocess_run_ids=p['runs'], target_schema_id=p['schema'],
                                         cv_folds=2, n_components=1, max_components=1)
    model = app.state.model_registry.register(run['run_id'], '新数据推理测试')
    return app.state.model_registry.get(model['id'], calibration=True)


def new_cube(p, tmp_path, *, bands=6, wavelengths=None, name='new'):
    pixels = np.random.default_rng(1234).uniform(.2, .7, (8, 8, bands)).astype(np.float32)
    folder = tmp_path / '预测数据'
    folder.mkdir(exist_ok=True)
    header = folder / (name+'.hdr')
    envi.save_image(str(header), pixels, ext='.dat', metadata={
        'wavelength': list(range(1000, 1000+bands*10, 10)) if wavelengths is None else wavelengths,
        'wavelength units': 'nm'})
    cube = str(p['app'].state.dataset_registry.import_path(str(header)).datasets[0].id)
    return cube, pixels


def test_training_snapshot_predicts_unannotated_new_cube(prepared, tmp_path, monkeypatch):
    p = prepared
    model = registered(p)
    cube, pixels = new_cube(p, tmp_path)
    with connect_database(p['plans'].database) as db:
        assert not db.execute('SELECT id FROM annotation_version WHERE cube_id=?', (cube,)).fetchall()
        assert not db.execute('SELECT id FROM preprocess_run WHERE cube_id=?', (cube,)).fetchall()
    def forbidden(*args, **kwargs):
        pytest.fail('deployment must never fit a recipe')
    with monkeypatch.context() as blocked:
        blocked.setattr('spectrumagent.preprocess.fitted.fit', forbidden)
        blocked.setattr(OperatorRegistry, 'run', forbidden)
        result = p['app'].state.inference_runs.create(model['id'], cube, None, None)
        training_prediction = p['app'].state.inference_runs.create(model['id'], p['cubes'][0])
    assert result['status'] == 'succeeded'
    assert result['preprocess_run_id'] is None and result['annotation_version_id'] is None
    assert result['stats']['statistics_scope'] == 'whole_image'
    assert result['stats']['n_foreground'] == 64
    state = model['calibration']
    expected = predict(transform(state, state['pipeline'], pixels.reshape(-1, 6)), state['model']).reshape(8, 8)
    saved = np.load(p['app'].state.training_runs.paths.root / 'inferences' / result['id'] / 'prediction.npy')
    np.testing.assert_array_equal(saved, expected)
    raw_mean = sum((row.sum(axis=0, dtype=np.float64) for row in pixels), np.zeros(6))/64
    assert result['stats']['sample_prediction'] == predict(transform(state, state['pipeline'], raw_mean[None]), state['model'])[0]
    # Re-opened results and maps retain scope and source evidence.
    assert p['app'].state.inference_runs.map(result['id'])['stats']['statistics_scope'] == 'whole_image'
    assert set(result['stats']['input_source_hashes']) == {'header', 'data'}
    original = p['app'].state.training_runs.artifact(model['run_id'], 'predictions')
    assert training_prediction['stats']['sample_prediction'] == next(row['y_pred'] for row in original if row['cube_id'] == p['cubes'][0])
    response = p['client'].post('/api/v1/models/inference-runs', json={'model_id': model['id'], 'cube_id': cube})
    assert response.status_code == 200, response.text
    assert response.json()['stats']['sample_prediction'] == result['stats']['sample_prediction']


def test_snapshot_gate_axis_checks_and_optional_real_mask(prepared, tmp_path, monkeypatch):
    import copy
    p = prepared
    model = registered(p)
    engine = p['app'].state.inference_runs
    cube, _ = new_cube(p, tmp_path)
    bad_bands, _ = new_cube(p, tmp_path, bands=5, name='bad-bands')
    bad_axis, _ = new_cube(p, tmp_path, wavelengths=list(range(2000, 2060, 10)), name='bad-axis')
    for identifier, code in ((bad_bands, 'FEATURE_COUNT_MISMATCH'), (bad_axis, 'WAVELENGTH_AXIS_MISMATCH')):
        with pytest.raises(ModelingError) as error:
            engine.create(model['id'], identifier)
        assert error.value.code == code
    with connect_database(p['plans'].database) as db:
        annotation = db.execute('SELECT annotation_version_id FROM preprocess_run WHERE id=?', (p['runs'][0],)).fetchone()[0]
    with pytest.raises(ModelingError) as error:
        engine.create(model['id'], cube, None, annotation)
    assert error.value.code == 'VERSION_CUBE_MISMATCH'
    with pytest.raises(ModelingError) as error:
        engine.create(model['id'], cube, p['runs'][0])
    assert error.value.code == 'PREPROCESS_RUN_NOT_READY'
    masked = engine.create(model['id'], p['cubes'][0], annotation_version_id=annotation)
    assert masked['preprocess_run_id'] is None and masked['stats']['statistics_scope'] == 'annotated_foreground'
    def tampered(change):
        value = copy.deepcopy(model)
        change(value)
        return value
    for altered, code in (
        (tampered(lambda v: v['calibration'].update(training_run_id=str(uuid4()))), 'CALIBRATION_MISMATCH'),
        (tampered(lambda v: v['calibration']['provenance'].pop('fitted_on')), 'CALIBRATION_PROVENANCE_UNAVAILABLE'),
        (tampered(lambda v: v['calibration'].update(origin='registration_reconstruction')), 'CALIBRATION_MISMATCH'),
    ):
        with monkeypatch.context() as blocked:
            blocked.setattr(engine.models, 'get', lambda *a, **k: altered)
            with pytest.raises(ModelingError) as error:
                engine.create(model['id'], cube)
            assert error.value.code == code


def test_conversation_predicts_new_data_and_queries_result_without_classification_route(prepared, tmp_path):
    p = prepared
    model = registered(p)
    cube, _ = new_cube(p, tmp_path)
    class Model:
        def __init__(self, response): self.responses = [response, ChatResult(content='已完成。', finish_reason='stop')]
        def chat(self, *args): return self.responses.pop(0)
        def route_chat(self, *args, **kwargs):
            pytest.fail('a named regression model must never enter classification inference')
    script = Model(tool('modeling.infer', dict(model_id=model['id'], cube_id=cube)))
    events = list(machine_for(p['app'], p['sid'], script).message(content=f"用模型 {model['id']} 对未标注新数据 {cube} 推理"))
    check = next(event for kind, event in events if kind == 'human_check')
    events += list(machine_for(p['app'], p['sid'], script).message(check_id=check['check_id'], decision='approve'))
    successes = [event['result_summary'] for kind, event in events if kind == 'step' and event['tool'] == 'modeling.infer' and event['status'] == 'ok']
    assert successes, events
    actual = successes[-1]
    assert actual['statistics_scope'] == 'whole_image'
    query = Model(tool('modeling.inference', dict(run_id=actual['inference_run_id'])))
    events = list(machine_for(p['app'], p['sid'], query).message(content='查看刚完成的新数据推理结果'))
    queried = [event['result_summary'] for kind, event in events if kind == 'step' and event['tool'] == 'modeling.inference' and event['status'] == 'ok']
    assert queried and queried[-1]['statistics_scope'] == 'whole_image', events
    assert queried[-1]['stats_sample_prediction'] == actual['sample_prediction']
    from spectrumagent.agent.router import regression_inference
    machine = machine_for(p['app'], p['sid'], query)
    assert not regression_inference(machine, f'使用模型 {uuid4()} 对新数据推理')
    assert regression_inference(machine, f'预测新数据 {cube}')


def test_nullable_inference_migration_preserves_old_results_and_artifacts(prepared, tmp_path):
    from spectrumagent.modeling.migrations import migrate
    p = prepared
    model = registered(p)
    engine = p['app'].state.inference_runs
    with connect_database(p['plans'].database) as db:
        annotation = db.execute('SELECT annotation_version_id FROM preprocess_run WHERE id=?', (p['runs'][0],)).fetchone()[0]
    old = engine.create(model['id'], p['cubes'][0], p['runs'][0], annotation)
    with connect_database(p['plans'].database) as db:
        rows = db.execute('SELECT * FROM inference_run').fetchall()
        artifacts = db.execute('SELECT * FROM inference_artifact').fetchall()
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE name='inference_run'").fetchone()[0]
        ddl = ddl.replace('inference_run', 'inference_run_old', 1).replace('preprocess_run_id TEXT REFERENCES', 'preprocess_run_id TEXT NOT NULL REFERENCES').replace('annotation_version_id TEXT REFERENCES', 'annotation_version_id TEXT NOT NULL REFERENCES')
        ddl = ddl.replace(',\n CHECK(preprocess_run_id IS NULL OR annotation_version_id IS NOT NULL)', '')
        db.execute(ddl)
        db.execute('INSERT INTO inference_run_old SELECT * FROM inference_run')
        db.execute('PRAGMA defer_foreign_keys=ON')
        db.execute('DROP TABLE inference_run')
        db.execute('ALTER TABLE inference_run_old RENAME TO inference_run')
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        db.execute('PRAGMA defer_foreign_keys=OFF')
    with connect_database(p['plans'].database) as db:
        migrate(db); migrate(db)
        assert db.execute('SELECT * FROM inference_run').fetchall() == rows
        assert db.execute('SELECT * FROM inference_artifact').fetchall() == artifacts
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert next(row for row in db.execute('PRAGMA foreign_key_list(inference_artifact)') if row[3] == 'run_id')[2] == 'inference_run'
    assert engine.map(old['id'])['stats']['statistics_scope'] == 'annotated_foreground'
    cube, _ = new_cube(p, tmp_path)
    assert engine.create(model['id'], cube)['status'] == 'succeeded'
