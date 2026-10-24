"""12.6 test-first contract: confirmation, overlap arbitration and MAT download."""
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app


@pytest.fixture
def confirm_api(annotation_case):
    c = annotation_case
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    sessions = app.state.annotation_sessions
    sessions.set_segmentation(c.identifier, SimpleNamespace(segments=c.segments, report={"params": c.params}))
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield SimpleNamespace(c=c, sessions=sessions, client=client, identity=identity,
                              base=f"/api/v1/annotations/{c.identifier}")


def add(h, revision, code="PE", op="add"):
    body = {"revision": revision, "op": op, "geometry": {
        "type": "polygon", "points": [[0, 0], [0, 6], [6, 6], [6, 0]]}}
    if op == "add":
        body["class_code"] = code
    response = h.client.post(h.base + "/draft/regions", json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("repair", ["erase", "uncertain", "delete", "class"])
def test_overlap_locations_and_four_arbitrations(confirm_api, repair):
    h = confirm_api
    add(h, 0)
    add(h, 1, "PET")
    conflict = h.client.post(h.base + "/draft/confirm", json={"revision": 2})
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "OVERLAP_UNRESOLVED"
    assert conflict.json()["context"] == {"conflict_count": 36,
        "sample_pixels": [[r, c] for r in range(6) for c in range(6)][:20],
        "bbox": {"min_row": 0, "min_col": 0, "max_row": 5, "max_col": 5}}
    if repair in ("erase", "uncertain"):
        add(h, 2, op=repair)
    else:
        patch = {"deleted": True} if repair == "delete" else {"class_code": "PE"}
        response = h.client.post(h.base + "/draft/regions/r-0002", json={"revision": 2, **patch})
        assert response.status_code == 200
    result = h.client.post(h.base + "/draft/confirm", json={"revision": 3})
    assert result.status_code == 200, result.text
    assert result.json()["overlap_conflicts"] == 0 and result.json()["training_mat_id"]
    assert h.client.get(h.base + "/draft").json()["revision"] == 3


def test_strong_classes_check_precedes_auto_remap(confirm_api):
    h = confirm_api
    add(h, 0)
    with connect_database(h.c.paths.database) as db:
        document = json.loads(db.execute("SELECT document_json FROM annotation_draft WHERE cube_id=?", (h.c.identifier,)).fetchone()[0])
        document["classes"][1]["code"], document["classes"][2]["code"] = document["classes"][2]["code"], document["classes"][1]["code"]
        db.execute("UPDATE annotation_draft SET document_json=? WHERE cube_id=?", (json.dumps(document), h.c.identifier))
    response = h.client.post(h.base + "/draft/confirm", json={"revision": 1})
    assert response.status_code == 400 and response.json()["error"] == "LABEL_INDEX_MISMATCH"
    with connect_database(h.c.paths.database) as db:
        assert json.loads(db.execute("SELECT document_json FROM annotation_draft").fetchone()[0]) == document
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0


def test_overwrite_three_states_and_repeated_readonly_confirmation(confirm_api):
    h = confirm_api
    assert h.client.post(h.base + "/draft/confirm", json={"revision": 0, "overwrite": True}).status_code == 409
    add(h, 0)
    first = h.client.post(h.base + "/draft/confirm", json={"revision": 1}).json()
    second = h.client.post(h.base + "/draft/confirm", json={"revision": 1}).json()
    assert first["version_id"] != second["version_id"]
    assert (first["version_no"], second["version_no"]) == (1, 2)
    before = h.sessions.drafts.get(h.c.identifier)
    with connect_database(h.c.paths.database) as db:
        created = db.execute("SELECT created_at FROM annotation_version WHERE id=?", (second["version_id"],)).fetchone()[0]
    add(h, 1, op="uncertain")
    overwritten = h.client.post(h.base + "/draft/confirm", json={"revision": 2, "overwrite": True}).json()
    assert overwritten["version_id"] == second["version_id"] and overwritten["version_no"] == 2
    with connect_database(h.c.paths.database) as db:
        assert db.execute("SELECT created_at FROM annotation_version WHERE id=?", (second["version_id"],)).fetchone()[0] == created
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 2
    assert h.sessions.read_version(second["version_id"])["document"]["regions"] != before["document"]["regions"]


def test_mat_failure_keeps_confirmed_version(confirm_api, monkeypatch):
    from spectrumagent.agent import mat
    h = confirm_api
    def fail(*args, **kwargs):
        raise OSError("injected savemat failure")
    monkeypatch.setattr(mat, "savemat", fail)
    result = h.client.post(h.base + "/draft/confirm", json={"revision": 0})
    assert result.status_code == 200
    body = result.json()
    assert body["training_mat_id"] is None and "injected savemat failure" in body["mat_error"]
    with connect_database(h.c.paths.database) as db:
        assert db.execute("SELECT id FROM annotation_version").fetchone()[0] == body["version_id"]
        assert db.execute("SELECT count(*) FROM training_mat").fetchone()[0] == 0
    assert h.sessions.read_version(body["version_id"])["document"]["regions"] == []


def test_empty_confirmation_stale_revision_and_body_validation(confirm_api):
    h = confirm_api
    for body in [{}, {"revision": True}, {"revision": 0, "extra": 1}]:
        invalid = h.client.post(h.base + "/draft/confirm", json=body)
        assert invalid.status_code == 400 and invalid.json()["error"] == "TOOL_ARGS_INVALID"
    empty = h.client.post(h.base + "/draft/confirm", json={"revision": 0})
    assert empty.status_code == 200 and empty.json()["n_spectra"] == 0
    assert h.sessions.drafts.get(h.c.identifier) is None
    add(h, 0)
    stale = h.client.post(h.base + "/draft/confirm", json={"revision": 0})
    assert stale.status_code == 409 and stale.json()["error"] == "DRAFT_REVISION_CONFLICT"


def test_segmentation_required_and_mat_download_errors(confirm_api):
    h = confirm_api
    h.sessions._states[h.c.identifier].segments = None
    missing = h.client.post(h.base + "/draft/confirm", json={"revision": 0})
    assert missing.status_code == 400 and missing.json()["error"] == "SUPERPIXELS_REQUIRED"
    path = h.base + f"/versions/{uuid4()}/training-mat"
    assert h.client.get(path).status_code == 404 and h.client.get(path).json()["error"] == "VERSION_NOT_FOUND"
    h.sessions.set_segmentation(h.c.identifier, SimpleNamespace(segments=h.c.segments, report={"params": h.c.params}))
    legacy = h.sessions.save(h.c.identifier)
    path = h.base + f"/versions/{legacy['id']}/training-mat"
    assert h.client.get(path).status_code == 404 and h.client.get(path).json()["error"] == "MAT_NOT_FOUND"
    saved = h.client.post(h.base + "/draft/confirm", json={"revision": 0}).json()
    response = h.client.get(h.base + f"/versions/{saved['version_id']}/training-mat")
    assert response.status_code == 200 and response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"] == 'attachment; filename="training_mat.mat"'
    assert response.content.startswith(b"MATLAB 5.0 MAT-file")
    assert response.headers["X-SpectrumAgent-Boot-Id"] == h.identity.boot_id


def assert_mat_missing(h, version):
    from spectrumagent.agent.tools import build_registry
    from spectrumagent.data import DataError
    response = h.client.get(h.base + f"/versions/{version}/training-mat")
    assert response.status_code == 404 and response.json()["error"] == "MAT_NOT_FOUND"
    with pytest.raises(DataError) as error:
        build_registry(sessions=h.sessions).invoke("training_mat.export", {"cube_id": h.c.identifier, "version_id": version})
    assert error.value.code == "MAT_NOT_FOUND"


def test_legacy_overwrite_invalidates_mat_even_if_file_cleanup_fails_and_rebuild_inserts(confirm_api, monkeypatch, caplog):
    from pathlib import Path
    from scipy.io import loadmat
    from spectrumagent.agent.mat import MatStore
    h = confirm_api
    add(h, 0)
    first_response = h.client.post(h.base + "/draft/confirm", json={"revision": 1})
    assert first_response.status_code == 200
    first = first_response.json()
    mats = MatStore(h.sessions.registry, h.c.paths)
    old = mats.get(h.c.identifier, first["version_id"])
    old_file = mats.file(old)
    assert set(np.unique(loadmat(old_file)["labels"])) == {1}
    assert h.client.post(h.base + "/draft/regions/r-0001", json={"revision": 1, "class_code": "PP"}).status_code == 200
    unlink = Path.unlink
    def blocked_cleanup(path, *args, **kwargs):
        if path == old_file:
            raise PermissionError("injected cleanup failure")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", blocked_cleanup)
        saved = h.sessions.save(h.c.identifier, overwrite=True, confirm=True)
    assert saved["id"] == first["version_id"]
    assert set(np.unique(h.sessions.read_version(saved["id"])["label_map"])) == {-1, 3}
    assert_mat_missing(h, saved["id"])
    assert old_file.exists()  # File deletion is best effort; the DB is authority.
    assert "MAT_CLEANUP_FAILED" in caplog.text
    with connect_database(h.c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM training_mat").fetchone()[0] == 0
    rebuilt = mats.rebuild(h.c.identifier, saved["id"])
    assert rebuilt["id"] != old["id"] and rebuilt["n_spectra"] == 36
    assert set(np.unique(loadmat(mats.file(rebuilt))["labels"])) == {3}
    with connect_database(h.c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM training_mat WHERE annotation_version_id=?", (saved["id"],)).fetchone()[0] == 1
    assert h.client.get(h.base + f"/versions/{saved['id']}/training-mat").status_code == 200
    mats.discard_invalidated(h.c.identifier, saved["id"])
    assert mats.file(rebuilt).is_file()  # Cleanup cannot delete an already rebuilt export.
    # Invalidation must roll back together with the version on later SQL failure.
    with connect_database(h.c.paths.database) as db:
        db.execute("CREATE TRIGGER reject_mat_overwrite BEFORE INSERT ON sample_spectrum "
                   "BEGIN SELECT RAISE(ABORT,'injected overwrite rollback'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError, match="injected overwrite rollback"):
        h.sessions.save(h.c.identifier, overwrite=True, confirm=True)
    assert mats.get(h.c.identifier, saved["id"])["id"] == rebuilt["id"]
    assert mats.file(rebuilt).is_file()


def test_failed_confirm_overwrite_invalidates_old_mat_without_rolling_back_version(confirm_api, monkeypatch):
    from spectrumagent.agent import mat
    h = confirm_api
    add(h, 0)
    first_response = h.client.post(h.base + "/draft/confirm", json={"revision": 1})
    assert first_response.status_code == 200
    first = first_response.json()
    mats = mat.MatStore(h.sessions.registry, h.c.paths)
    old_file = mats.file(mats.get(h.c.identifier, first["version_id"]))
    assert h.client.post(h.base + "/draft/regions/r-0001", json={"revision": 1, "class_code": "PP"}).status_code == 200
    def fail(*args, **kwargs):
        raise OSError("injected overwrite savemat failure")
    monkeypatch.setattr(mat, "savemat", fail)
    response = h.client.post(h.base + "/draft/confirm", json={"revision": 2, "overwrite": True})
    assert response.status_code == 200
    result = response.json()
    assert result["version_id"] == first["version_id"] and result["version_no"] == first["version_no"]
    assert result["training_mat_id"] is None and "injected overwrite savemat failure" in result["mat_error"]
    assert set(np.unique(h.sessions.read_version(result["version_id"])["label_map"])) == {-1, 3}
    assert_mat_missing(h, result["version_id"])
    assert not old_file.exists()
    with connect_database(h.c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM training_mat").fetchone()[0] == 0
