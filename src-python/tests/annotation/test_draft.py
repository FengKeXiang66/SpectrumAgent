"""Draft authority: strict documents, atomic CAS, provenance and durable IDs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.annotation.draft import DraftStore
from spectrumagent.annotation.raster import decode_rle, encode_rle, rasterize_with_conflicts_v1
from spectrumagent.data import DataError


POLYGON = {"type": "polygon", "points": [[0, 0], [0, 4], [4, 4], [4, 0]]}


def add(c, revision=0, **kwargs):
    return c.store.drafts.add(c.identifier, revision, geometry=deepcopy(POLYGON), class_code="PE", **kwargs)


def test_create_read_update_delete_and_id_never_reused(annotation_case):
    c = annotation_case
    drafts = c.store.drafts
    assert drafts.get(c.identifier) is None
    first = add(c)
    assert first["revision"] == 1 and first["region_id"] == "r-0001"
    second = add(c, 1)
    assert second["region_id"] == "r-0002"
    changed = drafts.patch(c.identifier, "r-0001", 2, {"class_code": "PP", "confidence": "low"})
    row = changed["document"]["regions"][0]
    assert row["class_index"] == next(cl["index"] for cl in changed["document"]["classes"] if cl["code"] == "PP")
    assert row["confidence"] == "low" and row["created_at"] == first["document"]["regions"][0]["created_at"]
    drafts.patch(c.identifier, "r-0002", 3, {"deleted": True})
    new = add(c, 4)
    assert new["revision"] == 5 and new["region_id"] == "r-0005"
    assert [r["region_id"] for r in drafts.get(c.identifier)["document"]["regions"]] == ["r-0001", "r-0005"]
    assert row["source"] == "manual"
    assert first["document"]["regions"][0]["confidence"] == "high"


@pytest.mark.parametrize("revision", [0, None, -1, True, "1"])
def test_stale_missing_or_invalid_revision_changes_nothing(annotation_case, revision):
    c = annotation_case
    add(c)
    before = c.store.drafts.get(c.identifier)
    with pytest.raises(DataError) as error:
        add(c, revision)
    assert error.value.code == ("DRAFT_REVISION_CONFLICT" if revision == 0 and type(revision) is int else "TOOL_ARGS_INVALID")
    if error.value.code == "DRAFT_REVISION_CONFLICT":
        assert error.value.status_code == 409
    assert c.store.drafts.get(c.identifier) == before


def test_same_revision_replay_second_write_fails(annotation_case):
    c = annotation_case
    first = add(c)
    add(c, first["revision"])
    with pytest.raises(DataError) as error:
        add(c, first["revision"])
    assert error.value.code == "DRAFT_REVISION_CONFLICT" and error.value.status_code == 409
    assert c.store.drafts.get(c.identifier)["revision"] == 2


def test_ten_concurrent_connections_have_one_winner_and_monotonic_revision(annotation_case):
    c = annotation_case
    add(c)
    barrier = Barrier(10)
    def write(_):
        store = DraftStore(c.paths.database, c.registry)
        barrier.wait(timeout=10)
        try:
            return store.add(c.identifier, 1, geometry=POLYGON, class_code="PE")["revision"]
        except DataError as error:
            assert error.code == "DRAFT_REVISION_CONFLICT" and error.status_code == 409
            return "409"
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(write, range(10)))
    successes = sorted(r for r in results if r != "409")
    assert len(successes) + results.count("409") == 10
    assert successes == [2] and results.count("409") == 9
    assert c.store.drafts.get(c.identifier)["revision"] == 1 + len(successes)


@pytest.mark.parametrize("field", ["source", "region_id", "created_at", "op", "arbitrary"])
def test_patch_provenance_and_identity_are_immutable(annotation_case, field):
    c = annotation_case
    add(c)
    before = c.store.drafts.get(c.identifier)
    with pytest.raises(DataError, match="白名单"):
        c.store.drafts.patch(c.identifier, "r-0001", 1, {field: "forged"})
    assert c.store.drafts.get(c.identifier) == before


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=2),
    lambda d: d.update(schema_version=True),
    lambda d: d.update(schema_version=1.0),
    lambda d: d.update(raster_rule_version=True),
    lambda d: d.update(raster_rule_version=2),
    lambda d: d.update(extra="forbidden"),
    lambda d: d["regions"][0].update(confidence="unknown"),
    lambda d: d["regions"][0].update(source="forged"),
    lambda d: d["regions"][0].update(created_at="not-a-timestamp"),
    lambda d: d["regions"][0].update(class_index=999),
    lambda d: d["regions"][0].update(op="uncertain"),
    lambda d: d["regions"][0].update(op="erase"),
    lambda d: d["regions"].append(deepcopy(d["regions"][0])),
    lambda d: d["regions"][0].update(geometry={"type": "pixel_set", "rows": [[0, 11, 2]], "segments_fingerprint": None}),
    lambda d: d["regions"][0]["geometry"].update(points=[[False, 0], [0, 2], [2, 2]]),
])
def test_invalid_schema_or_bounds_roll_back_without_disk_change(annotation_case, mutation):
    c = annotation_case
    add(c)
    before = c.store.drafts.get(c.identifier)
    document = deepcopy(before["document"])
    mutation(document)
    with pytest.raises(DataError) as error:
        c.store.drafts.replace(c.identifier, document, 1)
    assert error.value.code == "TOOL_ARGS_INVALID"
    assert c.store.drafts.get(c.identifier) == before


def test_invalid_initial_document_does_not_create_row(annotation_case):
    c = annotation_case
    bad = c.store.drafts.empty(c.identifier)
    bad["cube_id"] = "other"
    with pytest.raises(DataError):
        c.store.drafts.replace(c.identifier, bad, 0)
    assert c.store.drafts.get(c.identifier) is None


def test_rle_fingerprint_classes_and_all_not_null_values_are_explicit(annotation_case):
    c = annotation_case
    c.store.edit(c.identifier, c.segments == 0, action="confirm", label_id=c.labels["PE"])
    row = c.store.drafts.get(c.identifier)
    geometry = row["document"]["regions"][0]["geometry"]
    assert geometry["segments_fingerprint"] == c.params
    np.testing.assert_array_equal(decode_rle(geometry["rows"], c.segments.shape), c.segments == 0)
    assert encode_rle(c.segments == 0) == geometry["rows"]
    with connect_database(c.paths.database) as db:
        stored, = db.execute("SELECT cube_id,revision,document_json,schema_version,raster_rule_version,updated_at FROM annotation_draft").fetchall()
        labels = db.execute("SELECT code,name,color_hex FROM label ORDER BY sort_order,code").fetchall()
    assert all(value is not None for value in stored) and stored[1] == stored[3] == stored[4] == 1
    assert json.loads(stored[2]) == row["document"]
    assert [(cl["code"], cl["name"], cl["color"]) for cl in row["document"]["classes"]] == labels


def test_conflict_is_sticky_until_erase_or_uncertain_and_recomputed(annotation_case):
    c = annotation_case
    first = add(c)
    second = c.store.drafts.add(c.identifier, 1, geometry=POLYGON, class_code="PP")
    third = c.store.drafts.add(c.identifier, 2, geometry=POLYGON, class_code="PP")
    assert c.store.drafts.statistics(c.identifier, second["document"])["overlap_conflicts"] == 16
    assert c.store.drafts.statistics(c.identifier, third["document"])["overlap_conflicts"] == 16
    for op, value in [("erase", -1), ("uncertain", -2)]:
        doc = deepcopy(third["document"])
        doc["regions"].append({"op": op, "geometry": POLYGON})
        label_map, conflict_map = rasterize_with_conflicts_v1(doc, c.segments.shape)
        assert not conflict_map.any() and label_map[0, 0] == value
    changed = c.store.drafts.patch(c.identifier, "r-0002", 3, {"class_code": "PE"})
    assert c.store.drafts.statistics(c.identifier, changed["document"])["overlap_conflicts"] == 16  # third region remains PP
    c.store.drafts.patch(c.identifier, "r-0003", 4, {"deleted": True})
    assert c.store.drafts.statistics(c.identifier, c.store.drafts.get(c.identifier)["document"])["overlap_conflicts"] == 0
    assert first["document"]["regions"][0]["class_index"] != second["document"]["regions"][1]["class_index"]
