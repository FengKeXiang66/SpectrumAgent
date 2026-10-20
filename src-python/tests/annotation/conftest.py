import pytest
from fastapi.testclient import TestClient

from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app


@pytest.fixture
def label_api(tmp_path):
    paths = AppPaths(tmp_path / "app")
    identity = EngineIdentity()
    app = create_app(paths, identity)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        project_id = client.get("/api/v1/projects").json()[0]["id"]
        yield client, paths, project_id
