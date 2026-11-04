from storage_paths import runtime_path
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

from backend.database import connect_database
from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.session import SessionStore


@pytest.fixture(params=[False, True])
def mat_case(tmp_path, request):
    values = np.arange(6 * 4 * 3, dtype=np.uint16).reshape(6, 4, 3) + 100
    header = tmp_path / "original.hdr"
    header.with_suffix(".img").write_bytes(values.astype(">u2").tobytes())
    header.write_text("ENVI\nsamples=4\nlines=6\nbands=3\ndata type=12\ninterleave=bip\nbyte order=1\nreflectance scale factor=10000\n" +
                      ("wavelength={450,550,650}\n" if request.param else ""), "utf-8")
    paths = AppPaths(runtime_path(tmp_path, tmp_path / "app"))
    registry = DatasetRegistry(paths.database)
    cube = str(registry.import_path(str(header), raw=False).datasets[0].id)
    store = SessionStore(registry, paths)
    segments = np.indices((6, 4))[0].astype(np.int32)
    store.set_segmentation(cube, SimpleNamespace(segments=segments, report={"params": asdict(Parameters())}))
    with connect_database(paths.database) as db:
        labels = dict(db.execute("SELECT code,id FROM label"))
    mask = np.indices((6, 4))[0] % 2 == 0
    store.edit(cube, mask, action="confirm", label_id=labels["PP"])
    store.edit(cube, np.indices((6, 4))[0] == 1, action="uncertain")
    yield SimpleNamespace(paths=paths, registry=registry, store=store, cube=cube, values=values,
                          wavelengths=request.param, mask=mask, header=header)
