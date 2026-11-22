"""Budget admission and lossless undo under cache pressure, without changing algorithms."""
from contextlib import nullcontext
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import sys

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]
from spectrumagent.annotation import segmentation_resources as resource_module
from spectrumagent.annotation.segmentation_resources import SegmentationResources
from spectrumagent.data import DataError


def test_report_sized_edit_is_admitted_with_bounded_row_workspace(monkeypatch,tmp_path):
    shape=(231,640,200)
    registry=SimpleNamespace(get=lambda cube:(SimpleNamespace(shape=shape),False),
                             recycle=SimpleNamespace(coordinator=SimpleNamespace(job=nullcontext)))
    engine=SimpleNamespace(registry=registry,lock=RLock(),cache={})
    sessions=SimpleNamespace(_lock=RLock(),_states={})
    store=SimpleNamespace(access={},pins={})
    resources=SegmentationResources(None,engine,sessions,store=store)
    monkeypatch.setattr(resource_module,'memory_bytes',lambda:(600*1024**2,600*1024**2))
    from spectrumagent.annotation import prepare_batch
    monkeypatch.setattr(prepare_batch,'physical_memory_bytes',lambda:2*1024**3)
    with resources.lease('cube',required=False,restore=False):
        assert resources._temporary<120*1024**2
    assert resources._temporary==0
    resources.legacy_memory=True
    with pytest.raises(DataError) as rejected:
        with resources.lease('cube',required=False,restore=False):pass
    assert rejected.value.code=='CACHE_MEMORY_BUDGET'
    assert resources._temporary==0 and not resources._pins


def test_evicted_undo_maps_are_reconstructed_exactly(tmp_path,monkeypatch):
    # Use the real services and authoritative draft, with a small deterministic cube.
    import tempfile
    from backend.paths import AppPaths
    from backend.identity import EngineIdentity
    from backend.database import connect_database
    from spectrumagent.app import create_app
    from spectrumagent.storage import guard
    from spectrumagent.annotation.labels import LabelStore,SimpleLabelRequest
    from spectrumagent.annotation.engines.superpixels import Parameters
    temp=tmp_path/'temp';temp.mkdir()
    monkeypatch.setattr(tempfile,'tempdir',str(temp))
    monkeypatch.setattr(guard,'_guards',{});monkeypatch.setattr(guard,'_current',None)
    monkeypatch.setenv('SPECTRUMAGENT_PERMANENT_ROOT',str(tmp_path/'app'))
    paths=AppPaths(tmp_path/'app');paths.create_directories()
    try:
        app=create_app(paths,EngineIdentity())
        from spectral.io import envi
        source=tmp_path/'source';source.mkdir()
        envi.save_image(str(source/'cube.hdr'),np.random.default_rng(15).uniform(.1,.8,(12,12,8)).astype('float32'),ext='.dat')
        registry=app.state.dataset_registry;sessions=app.state.annotation_sessions;resources=app.state.segmentation_resources
        cube=str(registry.import_path(str(source/'cube.hdr')).datasets[0].id)
        with connect_database(paths.database) as db:
            project=db.execute('SELECT project_id FROM dataset_registry WHERE id=?',(cube,)).fetchone()[0]
        label=LabelStore(paths.database).add(SimpleLabelRequest(project_id=project,name='验证',color_hex='#123456'))
        resources.prepare(cube,Parameters(n_segments=8,pca_components=5))
        from spectrumagent.annotation import session as session_module
        original_rasterize=session_module.rasterize
        raster_calls=[]
        def count(*args,**kwargs):
            raster_calls.append(1)
            return original_rasterize(*args,**kwargs)
        monkeypatch.setattr(session_module,'rasterize',count)
        for _ in range(3):sessions.working(cube)
        assert not raster_calls
        expected=[]
        mask=np.zeros((12,12),bool)
        for row in range(34):
            expected.append(sessions.working(cube)['label_map'])
            mask.fill(False);mask[row%12]=True
            sessions.edit(cube,mask,action='confirm',label_id=label['id'],confidence='high')
        assert resources._evict(cube)
        assert all(array is None for _,array in sessions._states[cube].undo_stack)
        for previous in reversed(expected[-30:]):
            np.testing.assert_array_equal(sessions.undo(cube)['label_map'],previous)
        assert not sessions._states[cube].undo_stack
        assert raster_calls  # Changes and evicted maps still use the frozen rasterizer.
    finally:
        for instance in guard._guards.values():instance.close()
