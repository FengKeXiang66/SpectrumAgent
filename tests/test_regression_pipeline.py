"""Fold isolation, numerical oracles, immutable snapshots and legacy compatibility."""
import copy
import importlib
import json

import numpy as np
import pytest
from sklearn.cross_decomposition import PLSRegression

from test_experiments import workspace
from test_experiment_conversation import application
from test_data_intake import source
from backend.database import connect_database
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.fitted import fit, transform
from spectrumagent.preprocess.registry import OperatorRegistry
from spectrumagent.modeling import ModelingError
from spectrumagent.modeling import regression
from spectrumagent.modeling.cv import plan_folds
from spectrumagent.data import DataError


def data_for(steps):
    x = np.random.default_rng(45).uniform(.2, 2, (40, 9))
    ids = np.array([f'sample-{i:02}' for i in range(len(x))])
    pipeline = {'steps': steps}
    return dict(X_raw=x, y=3*x[:, 0]+.2*x[:, 2], groups=ids, wavelengths=np.arange(1100., 1190., 10),
                preprocess_run_ids=['run-'+i for i in ids], meta={'cubes': [dict(cube_id=i,
                    pipeline=pipeline, input_fingerprint='hash-'+i, recipe_version_id='version', source_hashes={}) for i in ids]})


def step(op, **params):
    return {'op': op, 'version': 1, 'params': params}


@pytest.mark.parametrize('steps', [[], [step('sg_smooth', window=5, polyorder=2)],
    [step('sg_derivative', window=5, polyorder=2, order=1)], [step('snv')],
    *[[step('standardize', method=method)] for method in ('standard', 'minmax', 'area', 'vector')],
    [step('pca', n_components=2)], [step('mnf', n_components=2)], [step('ica', n_components=2)],
    [step('crop', source=list(np.arange(1100., 1190., 10)), range=[1120., 1160.])],
    [step('resample', source=list(np.arange(1100., 1190., 10)), target=[1110., 1135., 1170.], method='linear')],
    [step('continuum', method='convex_hull')],
    [step('standardize', method='standard'), step('pca', n_components=2)],
    [step('pca', n_components=2), step('standardize', method='standard')]])
def test_existing_kernels_match_frozen_replay_without_any_fit_entry(steps, monkeypatch):
    data = data_for(steps)
    x, wave = data['X_raw'], data['wavelengths']
    expected = builtin_registry().run(x, {'steps': steps}, wavelengths=wave).spectra
    state = fit(x, {'steps': steps}, wavelengths=wave, sample_ids=data['groups'].tolist())
    before = copy.deepcopy(state)
    def forbidden(*args, **kwargs):
        pytest.fail('transform must not execute any fit entry')
    monkeypatch.setattr(OperatorRegistry, 'run', forbidden)
    for module, name in [('pca', 'fit_pca'), ('mnf', 'fit_mnf'), ('ica', 'fit_ica')]:
        monkeypatch.setattr(importlib.import_module('spectrumagent.preprocess.operators.'+module), name, forbidden)
    actual = transform(state, state['pipeline'], x)
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-12)
    split = np.concatenate([transform(state, state['pipeline'], row[None]) for row in x])
    np.testing.assert_array_equal(actual, split)
    assert state == before


def test_fold_scopes_and_held_out_perturbation_do_not_change_training_state(monkeypatch):
    data = data_for([step('standardize', method='standard'), step('pca', n_components=2)])
    train, test = np.arange(28), np.arange(28, 40)
    inner = plan_folds(data['y'][train], data['groups'][train], task='regression', strategy='kfold', folds=4, seed=17)
    calls, actual_fit = [], regression.fit
    def observe(x, pipeline, **kwargs):
        calls.append(kwargs['sample_ids'])
        return actual_fit(x, pipeline, **kwargs)
    monkeypatch.setattr(regression, 'fit', observe)
    sweep, states = regression.select(data, train, inner, n_components=1, max_components=2)
    for call, fold, saved in zip(calls, inner, states):
        expected_ids = data['groups'][train[fold['train_idx']]].tolist()
        assert call == expected_ids == saved['preprocessing']['fit_sample_ids']
        assert not set(call) & set(saved['validation_cube_ids'])
        expected_mean = data['X_raw'][train[fold['train_idx']]].mean(axis=0)
        np.testing.assert_array_equal([v['mean'] for v in saved['preprocessing']['steps'][0]['meta']['fitted']], expected_mean)
    a, b = train[inner[0]['train_idx']], train[inner[0]['test_idx']]
    reference = actual_fit(data['X_raw'][a], data['meta']['cubes'][0]['pipeline'], wavelengths=data['wavelengths'], sample_ids=data['groups'][a].tolist())
    changed = copy.deepcopy(data)
    changed['X_raw'][np.r_[b, test]] += 5000
    changed['y'][test] *= -10
    repeated = actual_fit(changed['X_raw'][a], changed['meta']['cubes'][0]['pipeline'], wavelengths=data['wavelengths'], sample_ids=data['groups'][a].tolist())
    assert repeated == reference
    model, snapshot, _, _ = regression.final_fit(data, train, test, 1, 'same-run')
    # Final training excludes outer test; only validation data belongs to training.
    unchanged_outer = copy.deepcopy(data)
    unchanged_outer['X_raw'][test] += 10000
    unchanged_outer['y'][test] -= 100
    model3, snapshot3, _, _ = regression.final_fit(unchanged_outer, train, test, 1, 'same-run')
    assert model == model3 and snapshot == snapshot3


@pytest.mark.parametrize('steps', [[], [step('sg_smooth', window=5, polyorder=2)]])
def test_fixed_input_baselines_match_direct_sklearn_on_the_same_split(steps):
    data = data_for(steps)
    a, b = np.arange(28), np.arange(28, 40)
    transformed = builtin_registry().run(data['X_raw'], {'steps': steps}).spectra
    expected = PLSRegression(n_components=1).fit(transformed[a], data['y'][a]).predict(transformed[b]).ravel()
    _, _, _, actual = regression.final_fit(data, a, b, 1, 'baseline')
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_reference_and_axis_failures_do_not_fall_back_to_full_fit():
    data = data_for([])
    x, wave, ids = data['X_raw'], data['wavelengths'], data['groups'].tolist()
    for s in (step('reflectance', hdr={}), step('msc', reference=x[0].tolist()), step('emsc', reference=x[0].tolist())):
        with pytest.raises(DataError) as error:
            fit(x, {'steps': [s]}, wavelengths=wave, sample_ids=ids)
        assert error.value.code == 'STRICT_PREPROCESS_UNSUPPORTED'
    with pytest.raises(DataError, match='物理波长轴'):
        fit(x, {'steps': [step('pca', n_components=2), step('resample', source=[1., 2.], target=[1., 2.], method='linear')]},
            wavelengths=wave, sample_ids=ids)
    with pytest.raises(DataError) as error:
        fit(x[:2], {'steps': [step('pca', n_components=2)]}, wavelengths=wave, sample_ids=ids[:2])
    assert error.value.code == 'INVALID_COMPONENT_COUNT'


def test_training_scales_are_frozen_and_zero_rules_are_preserved():
    x = np.array([[1., 3.], [3., 3.], [5., 3.]])
    state = fit(x, {'steps': [step('standardize', method='minmax')]}, sample_ids=['a', 'b', 'c'])
    np.testing.assert_array_equal(transform(state, state['pipeline'], [[9., 30.]]), [[2., 0.]])
    with pytest.raises(DataError) as error:
        fit(x, {'steps': [step('standardize', method='standard', zero_std='error')]}, sample_ids=['a', 'b', 'c'])
    assert error.value.code == 'NORMALIZATION_DEGENERATE'


def test_real_training_registration_inference_and_legacy_reads(application, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    registry, sessions, runner = application.state.dataset_registry, application.state.annotation_sessions, application.state.preprocess_runner
    images, _ = source(tmp_path, 10)
    cubes = [str(registry.import_path(str(images/f'plastic{i}.hdr')).datasets[0].id) for i in range(10)]
    with connect_database(runner.database) as db:
        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cubes[0],)).fetchone()[0]
    label = LabelStore(runner.database).ensure_names(project, ['PE'])[0]['id']
    recipe = runner.recipes.create('regression-state', '回归状态', None,
        {'steps': [step('standardize', method='standard'), step('pca', n_components=2)]})
    runs, versions = [], []
    for cube in cubes:
        application.state.segmentation_resources.prepare(cube, Parameters(n_segments=4, pca_components=3))
        sessions.edit(cube, np.ones((8, 8), bool), action='confirm', label_id=label)
        from spectrumagent.preprocess.current import CurrentWorkspace
        result = CurrentWorkspace(sessions, runner).process(cube, recipe['id'])
        runs.append(result['id']); versions.append(result['annotation_version_id'])
    with TestClient(application, headers={'Authorization': 'Bearer '+application.state.testing_identity.token}) as client:
        response = client.post('/api/v1/labels', json={'project_id': project, 'schema': {
            'name': 'amount', 'tree_path': 'amount', 'field_type': 'continuous', 'unit': '%', 'config': {}}})
        assert response.status_code < 300, response.text
        schema = response.json()['id']
        for i, cube in enumerate(cubes):
            assert client.put(f'/api/v1/models/sample-targets/{cube}/{schema}', json={'value': float(i+1)}).status_code == 200
    training = application.state.training_runs
    result = training.regress(preprocess_run_ids=runs, target_schema_id=schema, cv_folds=2, n_components=1, max_components=1)
    assert result['training_protocol'] == regression.PROTOCOL
    state = training.artifact(result['run_id'], 'calibration')
    replay = training.artifact(result['run_id'], 'replay')
    split = training.artifact(result['run_id'], 'split')
    assert split['split_input'] == 'raw_sample_mean'
    indices = [replay['cube_ids'].index(i) for i in split['train_cube_ids']]
    np.testing.assert_array_equal([r['mean'] for r in state['steps'][0]['meta']['fitted']], np.asarray(replay['X_raw'])[indices].mean(axis=0))
    def forbidden(*args, **kwargs):
        pytest.fail('registration and inference must never reopen training sources or fit')
    with monkeypatch.context() as blocked:
        blocked.setattr(registry, 'readable', forbidden)
        blocked.setattr(OperatorRegistry, 'run', forbidden)
        registered = application.state.model_registry.register(result['run_id'], '冻结回归')
    stored = application.state.model_registry.get(registered['id'], calibration=True)
    assert stored['calibration'] == state
    with pytest.raises(ModelingError) as error:
        application.state.inference_runs.create(registered['id'], cubes[0], runs[0], versions[1])
    assert error.value.code == 'VERSION_CUBE_MISMATCH'
    with monkeypatch.context() as blocked:
        blocked.setattr(OperatorRegistry, 'run', forbidden)
        prediction = application.state.inference_runs.create(registered['id'], cubes[0], runs[0], versions[0])
    expected = next(row['y_pred'] for row in result['predictions'] if row['cube_id'] == cubes[0])
    assert prediction['stats']['sample_prediction'] == expected
    assert prediction['stats']['calibration_origin'] == 'training_snapshot'
    # Missing/tampered new state cannot silently take the legacy reconstruction path.
    with connect_database(runner.database) as db:
        db.execute("DELETE FROM model_artifact WHERE run_id=? AND kind='calibration'", (result['run_id'],))
    with pytest.raises(ModelingError) as error:
        application.state.model_registry.register(result['run_id'], '缺失状态')
    assert error.value.code == 'ARTIFACT_NOT_FOUND'
    # A no-op recipe reproduces the old mathematical contract; exercise its reader.
    empty = runner.recipes.create('regression-legacy', '历史基线', None, {'steps': []})
    from spectrumagent.preprocess.current import CurrentWorkspace
    old_runs = [CurrentWorkspace(sessions, runner).process(c, empty['id'])['id'] for c in cubes]
    old = training.regress(preprocess_run_ids=old_runs, target_schema_id=schema, cv_folds=2, n_components=1, max_components=1)
    with connect_database(runner.database) as db:
        params = json.loads(db.execute('SELECT model_params FROM training_run WHERE id=?', (old['run_id'],)).fetchone()[0])
        params.pop('training_protocol')
        db.execute('UPDATE training_run SET model_params=? WHERE id=?', (json.dumps(params), old['run_id']))
    legacy = application.state.model_registry.register(old['run_id'], '历史回归')
    assert application.state.model_registry.get(legacy['id'], calibration=True)['calibration']['origin'] == 'registration_reconstruction'
    with pytest.raises(ModelingError) as error:
        application.state.inference_runs.create(legacy['id'], cubes[0])
    assert error.value.code == 'VERSION_CUBE_MISMATCH'
    old_input = runner.get(old_runs[0])
    assert application.state.inference_runs.create(legacy['id'], cubes[0], old_runs[0], old_input['annotation_version_id'])['status'] == 'succeeded'
    assert training.get(old['run_id'])['training_protocol'] == regression.LEGACY_PROTOCOL
    from spectrumagent.agent.tools.modeling import ModelingMetricsArguments
    comparison = application.state.agent_tools.modeling.invoke('modeling.metrics',
        ModelingMetricsArguments(run_id=result['run_id'], comparison_run_id=old['run_id']))
    assert comparison['same_training_protocol'] is False
    assert comparison['comparable'] is False


def test_artifact_allowlist_migration_preserves_old_rows_and_foreign_keys(application):
    from spectrumagent.modeling.migrations import migrate
    with connect_database(application.state.preprocess_runner.database) as db:
        db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,cv_folds,seed,status,created_at) VALUES ('old-run','[]','[]','[]','classification','label','group_kfold',2,17,'succeeded','now')")
        db.execute("INSERT INTO model_artifact VALUES ('old-artifact','old-run','model','old/model.json','old-hash','now')")
        before = db.execute('SELECT * FROM model_artifact').fetchall()
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE name='model_artifact'").fetchone()[0]
        ddl = ddl.replace('model_artifact', 'model_artifact_old', 1).replace(",'calibration','split','replay'", '')
        db.execute(ddl)
        db.execute('INSERT INTO model_artifact_old SELECT * FROM model_artifact')
        db.execute('DROP TABLE model_artifact')
        db.execute('ALTER TABLE model_artifact_old RENAME TO model_artifact')
        migrate(db); migrate(db)
        assert db.execute('SELECT * FROM model_artifact').fetchall() == before
        db.execute("INSERT INTO model_artifact VALUES ('new-artifact','old-run','calibration','old/calibration.json','new-hash','now')")
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
