from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.session import SessionStore


@pytest.fixture
def label_api(tmp_path):
    paths = AppPaths(tmp_path / "app")
    identity = EngineIdentity()
    app = create_app(paths, identity)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        project_id = client.get("/api/v1/projects").json()[0]["id"]
        yield client, paths, project_id


@pytest.fixture
def annotation_case(tmp_path):
    """Tiny original 200-band BIL fixture, explicit manual masks in tests."""
    values = np.random.default_rng(17).integers(1000, 6000, (40, 12, 200), dtype=np.uint16)
    values[:, :4, :100] += 20000
    values[:, 8:, 100:] += 30000
    header = tmp_path / "sample.hdr"
    header.with_suffix(".img").write_bytes(values.transpose(0, 2, 1).tobytes())
    header.write_text("ENVI\nsamples=12\nlines=40\nbands=200\ndata type=12\n"
                      "interleave=bil\nbyte order=0\nreflectance scale factor=65535\n", "utf-8")
    paths = AppPaths(tmp_path / "app")
    registry = DatasetRegistry(paths.database)
    identifier = str(registry.import_path(str(header), raw=True).datasets[0].id)
    segments = (np.indices((40, 12))[0] // 20 * 3 + np.indices((40, 12))[1] // 4).astype(np.int32)
    params = {**asdict(Parameters()), "pca_batch_size": 32 * 12}
    store = SessionStore(registry, paths)
    store.set_segmentation(identifier, SimpleNamespace(segments=segments, report={"params": params}))
    with connect_database(paths.database) as db:
        labels = dict(db.execute("SELECT code,id FROM label"))
        project = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (identifier,)).fetchone()[0]
    return SimpleNamespace(store=store, registry=registry, identifier=identifier, paths=paths,
                           values=values.astype(np.float64)/65535, segments=segments, params=params,
                           labels=labels, project=project, header=header)
