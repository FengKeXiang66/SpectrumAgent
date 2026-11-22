"""Imports never infer categories; only explicit label creation changes the palette."""
from pathlib import Path
import hashlib
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from test_experiments import workspace
from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.labels import LabelStore, SimpleLabelRequest
from spectrumagent.annotation.aliases import add as add_alias, resolve


@pytest.mark.parametrize('entry', ['desktop', 'assistant'])
def test_import_does_not_create_or_assign_labels(workspace, tmp_path, entry):
    from spectral.io import envi
    source = tmp_path / 'PP'  # A catalog material name must still have no meaning.
    source.mkdir()
    envi.save_image(str(source / 'sample.hdr'), np.ones((4, 4, 4), np.float32), ext='.dat')
    identity = EngineIdentity()
    app = create_app(workspace, identity)
    with TestClient(app, headers={'Authorization': 'Bearer ' + identity.token}) as client:
        project = client.get('/api/v1/projects').json()[0]['id']

        def palette():
            response = client.get('/api/v1/labels', params={'project_id': project})
            assert response.status_code == 200, response.text
            return [label for schema in response.json() for label in schema['labels']]

        assert palette() == []  # Opening the app creates neither material nor BG.

        def import_data():
            if entry == 'desktop':
                # Old clients cannot reactivate the retired opt-in behavior.
                response = client.post('/api/v1/datasets/import', json={'path': str(source)},
                                       headers={'X-SpectrumAgent-Folder-Label': '1'})
                assert response.status_code == 200, response.text
            else:
                tools = app.state.agent_tools
                tools.invoke('projects.paths_set', {'project_id': project,
                             'source_path': str(source), 'output_root': str(workspace.root)})
                sources = tools.invoke('sources.list', {})
                result = tools.invoke('datasets.import', {'source_ref': sources['source_1_ref']})
                assert result['status'] == 'imported', result

        import_data()
        assert palette() == []
        with connect_database(workspace.database) as db:
            assert db.execute('SELECT count(*) FROM sample_label').fetchone()[0] == 0
            cube = db.execute('SELECT id FROM dataset_registry').fetchone()[0]
        assert app.state.annotation_sessions.working(cube)['label_index'] == {}
        label = client.post('/api/v1/labels', json={'project_id': project,
                            'name': '手动材料', 'color_hex': '#123456'})
        assert label.status_code == 201, label.text
        import_data()  # Re-import must not append categories or relabel samples.
        assert [row['name'] for row in palette()] == ['手动材料']
        app.state.agent_tools.invoke('annotations.ensure_labels',
                                    {'project_id': project, 'class_names': ['第二类']})
        assert [row['name'] for row in palette()] == ['手动材料', '第二类']
        with connect_database(workspace.database) as db:
            assert db.execute('SELECT count(*) FROM sample_label').fetchone()[0] == 0


def test_labels_are_managed_without_import_and_deletion_survives_restart(workspace):
    identity = EngineIdentity()
    app = create_app(workspace, identity)
    with TestClient(app, headers={'Authorization': 'Bearer ' + identity.token}) as client:
        project = client.get('/api/v1/projects').json()[0]['id']
        created = client.post('/api/v1/labels', json={'project_id': project, 'name': '独立标签', 'color_hex': '#123456'})
        assert created.status_code == 201
        identifier = created.json()['id']
        assert app.state.dataset_registry.catalog()['total'] == 0
        assert client.delete(f'/api/v1/labels/{identifier}').status_code == 409
        assert len(LabelStore(workspace.database).tree(project)[0]['labels']) == 1
        assert client.request('DELETE', f'/api/v1/labels/{identifier}', json={'confirm': True}).status_code == 200
    restarted = create_app(workspace, EngineIdentity())
    assert LabelStore(workspace.database).tree(project)[0]['labels'] == []
    assert restarted.state.dataset_registry.catalog()['total'] == 0
    replacement = LabelStore(workspace.database).add(SimpleLabelRequest(
        project_id=project, name='独立标签', color_hex='#123456'))
    assert replacement['id'] != identifier


def test_delete_clears_working_annotations_but_preserves_saved_json_and_classes(workspace, tmp_path):
    from spectral.io import envi
    identity = EngineIdentity()
    app = create_app(workspace, identity)
    registry, sessions = app.state.dataset_registry, app.state.annotation_sessions
    project = LabelStore(workspace.database).projects()[0]['id']
    store = LabelStore(workspace.database)
    removed, retained = [store.add(SimpleLabelRequest(project_id=project, name=name, color_hex=color))
                         for name, color in [('删除类', '#123456'), ('保留类', '#abcdef')]]
    source = tmp_path / 'source'
    source.mkdir()
    cubes = []
    for index in range(2):
        envi.save_image(str(source / f'sample{index}.hdr'), np.random.default_rng(index).random((8, 8, 8)).astype(np.float32), ext='.dat')
        cube = str(registry.import_path(str(source / f'sample{index}.hdr')).datasets[0].id)
        cubes.append(cube)
        app.state.superpixel_engine.prepare(cube, sessions, Parameters(n_segments=4, pca_components=3))
        sessions.edit(cube, np.ones((8, 8), bool), action='confirm', label_id=retained['id'])
        left = np.zeros((8, 8), bool); left[:, :4] = True
        sessions.edit(cube, left, action='confirm', label_id=removed['id'])
    saved = sessions.save(cubes[0])
    snapshots = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                 for base in (workspace.snapshots, workspace.exports) for path in base.rglob('*') if path.is_file()}
    sessions.assign_samples(project, cubes, removed['id'], 'manual')
    add_alias(workspace.database, project, '要删的', removed['code'])
    before = sessions.read_version(saved['id'])['label_map'].copy()
    with TestClient(app, headers={'Authorization': 'Bearer ' + identity.token}) as client:
        route = f'/api/v1/labels/{removed["id"]}'
        rejected = client.delete(route)
        assert rejected.status_code == 409 and rejected.json()['error'] == 'LABEL_DELETE_CONFIRM_REQUIRED'
        assert np.array_equal(sessions.read_version(saved['id'])['label_map'], before)
        deleted = client.request('DELETE', route, json={'confirm': True})
        assert deleted.status_code == 200, deleted.text
        assert [row['id'] for row in store.tree(project)[0]['labels']] == [retained['id']]
        for cube in cubes:
            working = sessions.working(cube)
            assert list(working['label_index'].values()) == [retained['id']]
            assert np.all(working['label_map'][:, :4] == -1)  # No old overlapping class revealed.
            assert np.all(working['label_map'][:, 4:] == 0)
            assert all(item['code'] != removed['code'] for item in sessions.drafts.get(cube)['document']['classes'])
            while sessions._states[cube].undo_stack:
                sessions.undo(cube)
                assert removed['id'] not in sessions.working(cube)['label_index'].values()
        assert sessions.sample_labels(project) == {}
        assert resolve(workspace.database, project, '要删的') is None
        assert client.patch(route, json={'name': '复活'}).status_code >= 400
    assert snapshots == {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                         for base in (workspace.snapshots, workspace.exports) for path in base.rglob('*') if path.is_file()}
    assert np.array_equal(sessions.read_version(saved['id'])['label_map'], before)
    assert removed['code'] in {item['code'] for item in sessions.read_version(saved['id'])['document']['classes']}
    with connect_database(workspace.database) as db:
        assert db.execute('SELECT name FROM label WHERE id=?', (removed['id'],)).fetchone()[0] == removed['name']
        assert db.execute('SELECT count(*) FROM annotation WHERE label_id=?', (removed['id'],)).fetchone()[0] > 0
    restarted = create_app(workspace, EngineIdentity())
    assert [row['id'] for row in store.tree(project)[0]['labels']] == [retained['id']]
    assert removed['id'] not in restarted.state.annotation_sessions.working(cubes[0])['label_index'].values()
    registry.import_path(str(source))
    assert [row['id'] for row in store.tree(project)[0]['labels']] == [retained['id']]
