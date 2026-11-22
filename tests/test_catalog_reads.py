"""Catalog availability uses the page snapshot and still notices source changes."""
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]
from test_experiments import workspace


def test_catalog_checks_sources_without_per_item_database_reads(workspace,tmp_path,monkeypatch):
    from spectral.io import envi
    from spectrumagent.api.registry import DatasetRegistry
    registry=DatasetRegistry(workspace.database)
    source=tmp_path/'source';source.mkdir()
    for index in range(4):
        envi.save_image(str(source/f'{index}.hdr'),np.ones((8,8,8),np.float32)*.5,ext='.dat')
    registry.import_path(str(source))
    def forbidden(*args):raise AssertionError('catalog must use its existing page snapshot')
    monkeypatch.setattr(registry,'get',forbidden)
    before=registry.catalog()
    assert before['total']==4 and all(r['available'] for r in before['datasets'])
    (source/'1.dat').unlink()
    after=registry.catalog()
    assert [r['available'] for r in after['datasets']].count(False)==1
