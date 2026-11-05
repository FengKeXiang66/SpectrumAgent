"""Workbench badge: disk truth for the cube's published JSON annotation file."""
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from spectrumagent.annotation.projection_io import read_projection_status, write_projection
from test_routes import http_annotation, ready_http

CUBE = "00000000-0000-0000-0000-000000000001"
ABSENT = {"exists": False, "path": None, "filename": None,
          "generated_at": None, "version_no": None, "reason": None}


def paths(tmp_path):
    root = tmp_path / "exports"
    root.mkdir()
    return SimpleNamespace(exports=root)


def publish_manifest(root, cube, filename="sample.json", **extra):
    folder = root.exports / cube
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps(
        {"cube_id": cube, "filename": filename, "generated_at": "2026-11-05 10:00:00",
         "version_no": 2, **extra}), "utf-8")
    return folder


def test_no_manifest_is_absent(tmp_path):
    assert read_projection_status(paths(tmp_path), CUBE) == {**ABSENT, "reason": "no_manifest"}


def test_published_json_is_present_with_manifest_provenance(tmp_path):
    root = paths(tmp_path)
    folder = publish_manifest(root, CUBE)
    (folder / "sample.json").write_text("{}", "utf-8")
    assert read_projection_status(root, CUBE) == {
        "exists": True, "path": str(folder / "sample.json"), "filename": "sample.json",
        "generated_at": "2026-11-05 10:00:00", "version_no": 2, "reason": None}


@pytest.mark.parametrize("payload", [
    "not json",
    [],
    {"cube_id": CUBE},
    {"cube_id": CUBE, "filename": None},
    {"cube_id": str(uuid4()), "filename": "sample.json"},
    {"cube_id": CUBE, "filename": "../../outside.json"},
    {"cube_id": CUBE, "filename": "C:\\outside.json"},
    {"cube_id": CUBE, "filename": "manifest.json"},
])
def test_invalid_or_escaping_manifest_never_leaves_the_cube_folder(tmp_path, payload):
    root = paths(tmp_path)
    (root.exports / "outside.json").write_text("{}", "utf-8")
    folder = root.exports / CUBE
    folder.mkdir()
    (folder / "manifest.json").write_text(payload if isinstance(payload, str) else json.dumps(payload), "utf-8")
    assert read_projection_status(root, CUBE) == {**ABSENT, "reason": "invalid_manifest"}


def test_manifest_pointing_at_a_missing_json_is_absent(tmp_path):
    root = paths(tmp_path)
    publish_manifest(root, CUBE)
    assert read_projection_status(root, CUBE) == {**ABSENT, "filename": "sample.json",
                                                  "reason": "missing_json"}


def test_invalid_cube_id_is_absent_and_never_raises(tmp_path):
    assert read_projection_status(paths(tmp_path), "../etc") == {**ABSENT, "reason": "invalid_cube_id"}


def test_real_write_projection_then_status(annotation_case):
    c = annotation_case
    path, _ = write_projection(c.paths, c.identifier, c.project, c.header, 3,
                               np.zeros((2, 3), np.int32), {"0": "PE"})
    status = read_projection_status(c.paths, c.identifier)
    assert status["exists"] and status["path"] == path
    assert status["filename"] == "sample.json" and status["version_no"] == 3
    assert status["generated_at"] and status["reason"] is None
    (c.paths.exports / c.identifier / "sample.json").unlink()
    assert read_projection_status(c.paths, c.identifier)["reason"] == "missing_json"


def test_versions_endpoint_reports_status_from_absent_to_present(ready_http):
    h = ready_http
    listing = h.client.get(h.base + "/annotations").json()
    assert listing["json_projection"]["exists"] is False
    assert listing["json_projection"]["reason"] == "no_manifest"
    h.sessions.edit(h.case.identifier, h.sessions._state(h.case.identifier).segments == 0,
                    action="confirm", label_id=h.case.labels["PE"])
    saved = h.client.post(h.base + "/annotations/save", json={}).json()
    status = h.client.get(h.base + "/annotations").json()["json_projection"]
    assert status["exists"] is True and status["path"] == saved["export"]["path"]
    assert status["filename"] == "sample.json" and status["version_no"] == 1
    assert len(h.client.get(h.base + "/annotations").json()["versions"]) == 1
