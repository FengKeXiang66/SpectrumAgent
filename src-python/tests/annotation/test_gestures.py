"""12.8 service tests: no HTTP/tool layer and no second geometry implementation."""
from copy import deepcopy
import json
import re
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.annotation.engines.diffusion import prompt_superpixels
from spectrumagent.annotation.gestures import region_from_gesture, select_candidates
from spectrumagent.annotation.raster import decode_rle
from spectrumagent.annotation.session import SessionStore
from spectrumagent.data import DataError


def fake_diffusion(c, minimum=.9):
    candidate = {"superpixels": [0, 1], "min_similarity": minimum, "avg_similarity": .95}
    def generate(cube, seed, *, threshold, queue_min_similarity):
        admitted = minimum >= queue_min_similarity
        if admitted:
            c.store._state(cube).candidates.append(deepcopy(candidate))
        return {"candidate": candidate, "enqueued": admitted, "params": {"threshold": threshold, "queue_min_similarity": queue_min_similarity}}
    return SimpleNamespace(superpixels=SimpleNamespace(lock=RLock()), generate=Mock(side_effect=generate))


def test_gesture_storage_copies_unique_refs_and_does_not_persist(annotation_case):
    c = annotation_case
    seed = {"doodle": [[1, 2], [30, 9]]}
    first = c.store.store_gesture(c.identifier, seed)
    second = c.store.store_gesture(c.identifier, seed)
    assert first != second and re.fullmatch(r"g-[0-9a-f]{32}", first)
    seed["doodle"][0][0] = 99
    resolved = c.store.resolve_gesture(c.identifier, first)
    assert resolved == {"doodle": [[1, 2], [30, 9]]}
    resolved["doodle"].clear()
    assert c.store.resolve_gesture(c.identifier, first)["doodle"]
    assert c.store.drafts.get(c.identifier) is None
    with connect_database(c.paths.database) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE '%gesture%'").fetchall()
    with pytest.raises(DataError) as error:
        SessionStore(c.registry, c.paths).resolve_gesture(c.identifier, first)
    assert (error.value.code, error.value.status_code) == ("GESTURE_NOT_FOUND", 404)


def test_gesture_ref_is_cube_scoped(annotation_case):
    c = annotation_case
    ref = c.store.store_gesture(c.identifier, {"point": [1, 1]})
    other = str(c.registry.import_path(str(c.header), raw=False).datasets[0].id)
    with pytest.raises(DataError) as error:
        c.store.resolve_gesture(other, ref)
    assert error.value.code == "GESTURE_NOT_FOUND" and error.value.status_code == 404


@pytest.mark.parametrize("seed", [{"point": [2, 3]}, {"box": [0, 30, 0, 8]}, {"doodle": [[1, 1], [35, 10]]}])
@pytest.mark.parametrize("op,confidence", [("add", None), ("add", "medium"), ("add", "low"), ("uncertain", None), ("erase", None)])
def test_region_absorbs_only_prompt_superpixels_and_records_manual_source(annotation_case, seed, op, confidence):
    c = annotation_case
    ref = c.store.store_gesture(c.identifier, seed)
    expected = prompt_superpixels(c.segments, seed)
    result = region_from_gesture(c.store, c.identifier, ref, op=op, class_code="PE" if op == "add" else None,
                                 confidence=confidence, expected_revision=0)
    row = c.store.drafts.get(c.identifier)
    region = row["document"]["regions"][-1]
    np.testing.assert_array_equal(decode_rle(region["geometry"]["rows"], c.segments.shape), np.isin(c.segments, expected))
    assert result["region_id"] == region["region_id"] and result["revision"] == 1
    assert result["n_superpixels"] == len(expected) and result["pixel_count"] == int(np.isin(c.segments, expected).sum())
    assert region["source"] == "manual" and region["geometry"]["type"] == "pixel_set"
    assert "gesture_ref" not in json.dumps(row["document"])
    if op == "add":
        assert region["confidence"] == (confidence or "high")
    else:
        assert "confidence" not in region and "class_index" not in region
    assert len(c.store._state(c.identifier).undo_stack) == 1
    c.store.undo(c.identifier)
    assert c.store.drafts.get(c.identifier)["document"]["regions"] == []


@pytest.mark.parametrize("kind", ["revision", "missing", "bounds", "label", "segmentation"])
def test_region_failures_do_not_write_document(annotation_case, kind):
    c = annotation_case
    ref = c.store.store_gesture(c.identifier, {"point": [-1, 1] if kind == "bounds" else [1, 1]})
    if kind == "segmentation":
        c.store._state(c.identifier).segments = None
    with pytest.raises(DataError) as error:
        region_from_gesture(c.store, c.identifier, "unknown" if kind == "missing" else ref, op="add",
                            class_code="missing" if kind == "label" else "PE", expected_revision=1 if kind == "revision" else 0)
    assert error.value.code == {"revision": "DRAFT_REVISION_CONFLICT", "missing": "GESTURE_NOT_FOUND",
        "bounds": "INVALID_DIFFUSION_PROMPT", "label": "LABEL_NOT_FOUND", "segmentation": "SUPERPIXELS_REQUIRED"}[kind]
    assert c.store.drafts.get(c.identifier) is None


@pytest.mark.parametrize("floor,confidence", [(.8, "medium"), (.99, "low")])
def test_sam_queue_floor_writes_region_consumes_queue_and_reports_floor(annotation_case, floor, confidence):
    c = annotation_case
    ref = c.store.store_gesture(c.identifier, {"point": [1, 1]})
    diffusion = fake_diffusion(c)
    result = select_candidates(c.store, diffusion, c.identifier, method="SAM", class_code="PE",
                              params=SimpleNamespace(gesture_ref=ref, threshold=.5, queue_min_similarity=floor), expected_revision=0)
    region = c.store.drafts.get(c.identifier)["document"]["regions"][-1]
    assert region["source"] == "algorithm" and region["confidence"] == confidence
    assert c.store._state(c.identifier).candidates == []
    assert result["queue_min_similarity"] == floor and result["below_queue_floor"] == (confidence == "low")
    assert (str(floor) in result["queue_note"]) if confidence == "low" else result["queue_note"] is None
    assert result["region_id"] == region["region_id"] and result["revision"] == 1
    diffusion.generate.assert_called_once_with(c.identifier, {"point": [1, 1]}, threshold=.5, queue_min_similarity=floor)


@pytest.mark.parametrize("kind", ["revision", "missing", "label", "segmentation", "SLIC"])
def test_sam_preflight_refuses_without_generating_or_mutating(annotation_case, kind):
    c = annotation_case
    ref = c.store.store_gesture(c.identifier, {"point": [1, 1]})
    diffusion = fake_diffusion(c)
    if kind == "segmentation":
        c.store._state(c.identifier).segments = None
    with pytest.raises(DataError) as error:
        select_candidates(c.store, diffusion, c.identifier, method="SLIC" if kind == "SLIC" else "SAM",
                          class_code="missing" if kind == "label" else "PE", expected_revision=1 if kind == "revision" else 0,
                          params=SimpleNamespace(gesture_ref="unknown" if kind == "missing" else ref, threshold=.5, queue_min_similarity=.8))
    assert error.value.code == {"revision": "DRAFT_REVISION_CONFLICT", "missing": "GESTURE_NOT_FOUND",
        "label": "LABEL_NOT_FOUND", "segmentation": "SUPERPIXELS_REQUIRED", "SLIC": "TOOL_NOT_IMPLEMENTED"}[kind]
    diffusion.generate.assert_not_called()
    assert c.store.drafts.get(c.identifier) is None
