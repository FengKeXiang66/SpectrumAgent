"""Keep archive objects alive: closing inputs must not depend on garbage collection."""
import time

import numpy as np
import pytest

from test_experiment_conversation import application, workspace
from test_experiment_inference import train, input_file, prepare, wait
from test_inference_draft_lifecycle import completed
from spectrumagent.agent.state import AgentStore
from spectrumagent.experiments.inference import npz_values
from spectrumagent.data import DataError


@pytest.fixture
def archives(monkeypatch):
    original = np.load
    retained = []
    def load(*args, **kwargs):
        archive = original(*args, **kwargs)
        if isinstance(archive, np.lib.npyio.NpzFile):
            retained.append(archive)
        return archive
    monkeypatch.setattr(np, 'load', load)
    return retained


def test_npz_training_review_and_inference_close_files_before_gc(application, tmp_path, archives):
    model, dialogue = train(application, tmp_path)
    path, _, _ = input_file(tmp_path)
    owner = AgentStore(dialogue.database).create_session()['id']
    prepare(dialogue, owner, model, path)
    result = dialogue.confirm(owner, '确认推理', 'confirm')
    assert wait(dialogue.service, model, result['inference_run_id'])['status'] == 'succeeded'
    assert archives and all(archive.zip is None for archive in archives)
    # Deliberately retain every NpzFile above; no gc.collect or retry here.
    for source in (path, tmp_path/'train.npz', tmp_path/'test.npz'):
        moved = source.with_name('moved-'+source.name)
        source.rename(moved)
        moved.rename(source)


def test_npz_validation_error_also_closes_file(application, tmp_path, archives):
    model, dialogue = train(application, tmp_path)
    path, _, waves = input_file(tmp_path)
    owner = AgentStore(dialogue.database).create_session()['id']
    prepare(dialogue, owner, model, path)
    with pytest.raises(DataError):
        npz_values(path, dialogue.config(owner).input, waves+1)
    assert archives and all(archive.zip is None for archive in archives)
    moved = path.with_name('moved.npz')
    path.rename(moved)
    moved.rename(path)


def test_envi_inference_releases_source_before_gc(application, tmp_path):
    model, dialogue, owner, header, run, _ = completed(application, tmp_path)
    deadline = time.monotonic()+5
    while (model, run) in dialogue.service.active:
        assert time.monotonic() < deadline
        time.sleep(.01)
    # The raw ENVI was read by inference, not imported/pinned in a viewer.
    for source in (header, header.with_suffix('.img')):
        moved = source.with_name('moved-'+source.name)
        source.rename(moved)
        moved.rename(source)
