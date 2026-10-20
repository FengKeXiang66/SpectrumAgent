import json
from pathlib import PurePosixPath
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.annotation.labels import CatalogRequest, CustomRequest, LabelStore
from spectrumagent.annotation.session import AnnotationConflict, SessionStore, aggregate_spectra
from spectrumagent.data import DataError, SpectrumDataSet


def manual_state(case):
    """Manual fixture: full PE block, mixed PET/PP block, blank and uncertain."""
    for code, mask in (("PE", case.segments == 0),
                       ("PET", (case.segments == 1) & (np.indices(case.segments.shape)[1] < 6)),
                       ("PP", (case.segments == 1) & (np.indices(case.segments.shape)[1] >= 6))):
        case.store.edit(case.identifier, mask, action="confirm", label_id=case.labels[code])
    case.store.edit(case.identifier, case.segments == 5, action="uncertain")
    return case.store.working(case.identifier)


def rows(case, table, version_id=None):
    with connect_database(case.paths.database) as db:
        db.row_factory = sqlite3.Row
        query = f"SELECT * FROM {table}"
        args = ()
        if version_id is not None:
            query += " WHERE version_id=?"
            args = (version_id,)
        return [dict(row) for row in db.execute(query, args)]


def test_snapshot_replay_spectra_counts_params_and_lineage(annotation_case):
    c = annotation_case
    working = manual_state(c)
    saved = c.store.save(c.identifier)
    replay = c.store.read_version(saved["id"])
    np.testing.assert_array_equal(replay["label_map"], working["label_map"])
    assert replay["label_map"].dtype == np.int32
    assert replay["label_index"] == working["label_index"]
    annotations = rows(c, "annotation", saved["id"])
    samples = rows(c, "sample_spectrum", saved["id"])
    version = rows(c, "annotation_version")[0]
    assert json.loads(version["params"]) == c.params
    assert version["n_pixels"] == 480 and version["labeled_pixels"] == 160
    assert version["auto_ratio"] == 0 and version["note"] is None
    assert len(annotations) == len(samples) == 3
    for i, label_id in working["label_index"].items():
        mask = working["label_map"] == int(i)
        if not mask.any():
            assert f"mean_{i}" not in replay["spectra"]
            continue
        pixels = c.values[mask]
        for kind, expected in (("mean", pixels.mean(axis=0)), ("std", pixels.std(axis=0))):
            spectrum = replay["spectra"][f"{kind}_{i}"]
            assert spectrum.dtype == np.float64
            np.testing.assert_allclose(spectrum, expected, rtol=0, atol=1e-10)
        annotation = next(row for row in annotations if row["label_id"] == label_id)
        sample = next(row for row in samples if row["label_id"] == label_id)
        assert annotation["pixel_count"] == sample["n_pixels"] == int(mask.sum())
        assert annotation["granularity"] == "sample" and annotation["source"] == "manual"
        assert all(annotation[key] is None for key in ("confidence", "evidence", "annotator_id", "label_value"))
        assert sample["sample_code"] == "sample"
        assert sample["mean_ref"] == f"mean_{i}" and sample["std_ref"] == f"std_{i}"
        assert sample["cube_id"] == version["cube_id"] == c.identifier
        assert sample["version_id"] == annotation["version_id"] == version["id"]
        assert json.loads(annotation["geometry"])["superpixels"] == ([0] if label_id == c.labels["PE"] else [])
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM annotation WHERE granularity='scene'").fetchone()[0] == 0
        for table in ("annotation_version", "annotation", "sample_spectrum"):
            required = [column[1] for column in db.execute(f"PRAGMA table_info({table})") if column[3]]
            for row in rows(c, table):
                assert all(row[key] is not None for key in required)
    assert saved["quality"] == c.store.validate(c.identifier)
    assert saved["transaction_seconds"] < saved["elapsed_seconds"]


def test_relative_snapshot_path_three_files_and_no_source_writes(annotation_case):
    c = annotation_case
    before = {p.name: p.read_bytes() for p in c.header.parent.glob("sample.*")}
    saved = c.store.save(c.identifier)
    relative = PurePosixPath(saved["snapshot_ref"])
    assert not relative.is_absolute() and "\\" not in saved["snapshot_ref"]
    assert relative == PurePosixPath(c.identifier, "v1")
    assert c.paths.snapshots == c.paths.root / "annotations"
    assert {p.name for p in (c.paths.snapshots / c.identifier / "v1").iterdir()} == {
        "label_map.npz", "label_index.json", "spectra.npz"}
    assert before == {p.name: p.read_bytes() for p in c.header.parent.glob("sample.*")}


def test_aggregate_bounded_reflectance_shared_io_no_full_cube(annotation_case, monkeypatch):
    c = annotation_case
    working = manual_state(c)
    original = SpectrumDataSet.read_region
    reads = []
    def bounded(dataset, l0, l1, s0, s1):
        assert l1-l0 <= 32
        assert dataset.metadata["value_mode"] == "reflectance"
        reads.append((l0, l1))
        return original(dataset, l0, l1, s0, s1)
    monkeypatch.setattr(SpectrumDataSet, "read_region", bounded)
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("full original cube"))
    aggregates = aggregate_spectra(c.registry, c.identifier, working["label_map"], segments=c.segments)
    assert reads == [(0, 32), (32, 40)]
    assert sum(moment.count for moment in aggregates.labels.values()) == 160
    reads.clear()
    c.store.save(c.identifier)
    # One shared label/part pass, one §5.2 high-variance pass. No old spectra read.
    assert reads == [(0, 32), (32, 40)] * 2


@pytest.mark.parametrize("block_size", [1, 7, 32])
def test_spectra_cross_row_blocks_mean_std_match_pixels_1e10(annotation_case, block_size):
    c = annotation_case
    mask = (c.segments == 0) | (c.segments == 3) | (c.segments == 4)
    c.store.edit(c.identifier, mask, action="confirm", label_id=c.labels["PE"])
    working = c.store.working(c.identifier)["label_map"]
    result = aggregate_spectra(c.registry, c.identifier, working, block_size=block_size)
    moment = result.labels[1]
    pixels = c.values[mask]
    assert moment.count == 240
    np.testing.assert_allclose(moment.mean, pixels.mean(axis=0), rtol=0, atol=1e-10)
    np.testing.assert_allclose(moment.std, pixels.std(axis=0), rtol=0, atol=1e-10)


def test_five_undos_deep_copy_statistics_and_edit_after_restore(annotation_case):
    c = annotation_case
    expected = []
    for i in range(6):
        expected.append(c.store.working(c.identifier)["label_map"])
        mask = np.zeros(c.segments.shape, dtype=bool)
        mask.flat[i] = True
        c.store.edit(c.identifier, mask, action="uncertain" if i % 2 else "confirm", label_id=c.labels["PE"])
    for old in reversed(expected[1:]):
        working = c.store.undo(c.identifier)
        np.testing.assert_array_equal(working["label_map"], old)
        assert working["statistics"]["uncertain_pixels"] == np.count_nonzero(old == -2)
        assert working["statistics"]["labeled_pixels"] == np.count_nonzero(old >= 0)
        working["label_map"].fill(99)  # Caller cannot corrupt state or undo buffers.
    with pytest.raises(AnnotationConflict) as error:
        c.store.undo(c.identifier)
    assert error.value.status_code == 409
    restored = c.store.working(c.identifier)["label_map"]
    mask = c.segments == 4
    c.store.edit(c.identifier, mask, action="confirm", label_id=c.labels["PP"])
    np.testing.assert_array_equal(c.store.working(c.identifier)["label_map"][~mask], restored[~mask])
    np.testing.assert_array_equal(c.store.undo(c.identifier)["label_map"], restored)


@pytest.mark.parametrize("key,value", [("n_segments", 400), ("compactness", 1), ("pca_components", 3)])
def test_parameter_change_preserves_three_states_clears_candidates(annotation_case, key, value):
    c = annotation_case
    before = manual_state(c)
    state = c.store._state(c.identifier)
    state.candidates.extend([{"superpixels": [2, 3]}, {"superpixels": [3, 4]}])
    assert c.store.working(c.identifier)["statistics"]["pending_pixels"] == 240
    params = {**c.params, key: value}
    c.store.set_segmentation(c.identifier, SimpleNamespace(segments=c.segments[::-1], report={"params": params}))
    after = c.store.working(c.identifier)
    np.testing.assert_array_equal(before["label_map"], after["label_map"])
    assert after["statistics"]["pending_pixels"] == 0
    saved = c.store.save(c.identifier)
    assert json.loads(rows(c, "annotation_version")[0]["params"]) == params
    assert saved["version_no"] == 1


def test_label_tie_order_history_frozen_and_working_undo_remapped(annotation_case):
    c = annotation_case
    labels = LabelStore(c.paths.database)
    custom = labels.add(CustomRequest(project_id=c.project, code="ZZZ", name="test",
                                     tree_path="材料/塑料/ZZZ", color_hex="#123456"))
    c.store.edit(c.identifier, c.segments == 0, action="confirm", label_id=custom["id"])
    first = c.store.save(c.identifier)
    frozen = c.store.read_version(first["id"])
    assert frozen["label_index"]["4"] == custom["id"]
    catalog = labels.add(CatalogRequest(project_id=c.project, from_catalog="plastic", codes=["PS"]))[0]
    current = c.store.working(c.identifier)
    assert current["label_index"]["4"] == catalog["id"]
    assert current["label_index"]["5"] == custom["id"]
    assert np.all(current["label_map"][c.segments == 0] == 5)
    second = c.store.save(c.identifier)
    assert second["version_no"] == 2
    again = c.store.read_version(first["id"])
    assert again["label_index"] == frozen["label_index"]
    np.testing.assert_array_equal(again["label_map"], frozen["label_map"])
    assert c.store.undo(c.identifier)["statistics"]["labeled_pixels"] == 0


def test_overwrite_latest_deletes_stale_rows_updates_note_keeps_created_at(annotation_case):
    c = annotation_case
    manual_state(c)
    first = c.store.save(c.identifier)
    second = c.store.save(c.identifier)
    old_created = second["created_at"]
    stale = {r["id"] for r in rows(c, "annotation", second["id"]) + rows(c, "sample_spectrum", second["id"])}
    c.store.edit(c.identifier, np.ones(c.segments.shape, dtype=bool), action="confirm", label_id=c.labels["BG"])
    changed = {**c.params, "n_segments": 400}
    c.store.set_segmentation(c.identifier, SimpleNamespace(segments=c.segments, report={"params": changed}))
    result = c.store.save(c.identifier, overwrite=True, confirm=True)
    assert result["id"] == second["id"] and result["version_no"] == 2
    assert result["created_at"] == old_created
    note = json.loads(result["note"])
    assert note["event"] == "overwrite" and note["at"].endswith("+00:00")
    assert len(rows(c, "annotation_version")) == 2
    for table in ("annotation", "sample_spectrum"):
        current = rows(c, table, result["id"])
        assert len(current) == 1 and current[0]["label_id"] == c.labels["BG"]
        assert current[0]["id"] not in stale
        assert len(rows(c, table, first["id"])) == 3
    version = next(r for r in rows(c, "annotation_version") if r["id"] == result["id"])
    assert json.loads(version["note"])["event"] == "overwrite"
    assert version["labeled_pixels"] == 480 and version["created_at"] == old_created
    assert json.loads(version["params"]) == changed
    np.testing.assert_array_equal(c.store.read_version(result["id"])["label_map"], c.store.working(c.identifier)["label_map"])


@pytest.mark.parametrize("existing,confirm", [(False, False), (False, True), (True, False)])
def test_overwrite_conflicts_no_version_or_missing_confirm(annotation_case, existing, confirm):
    c = annotation_case
    if existing:
        c.store.save(c.identifier)
    with pytest.raises(AnnotationConflict) as error:
        c.store.save(c.identifier, overwrite=True, confirm=confirm)
    assert error.value.status_code == 409
    assert len(rows(c, "annotation_version")) == int(existing)


@pytest.mark.parametrize("overwrite", [False, True])
def test_db_failure_rolls_back_rows_and_snapshot_publication(annotation_case, monkeypatch, overwrite):
    c = annotation_case
    manual_state(c)
    first = c.store.save(c.identifier)
    folder = c.paths.snapshots / c.identifier / "v1"
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    c.store.edit(c.identifier, c.segments == 0, action="uncertain")
    with connect_database(c.paths.database) as db:
        db.execute("CREATE TRIGGER reject_sample BEFORE INSERT ON sample_spectrum "
                   "BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        c.store.save(c.identifier, overwrite=overwrite, confirm=True)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert len(rows(c, "annotation_version")) == 1
    assert len(rows(c, "annotation", first["id"])) == len(rows(c, "sample_spectrum", first["id"])) == 3
    assert {p.name for p in folder.parent.iterdir()} == {"v1"}


def test_snapshot_write_failure_never_publishes_or_inserts(annotation_case, monkeypatch):
    c = annotation_case
    def fail(*_):
        raise OSError("injected disk failure")
    monkeypatch.setattr(c.store, "_write_snapshot", fail)
    with pytest.raises(OSError, match="disk failure"):
        c.store.save(c.identifier)
    assert rows(c, "annotation_version") == []
    assert list((c.paths.snapshots / c.identifier).iterdir()) == []


def test_working_memory_only_and_empty_snapshot_three_states(annotation_case):
    c = annotation_case
    assert c.store.working(c.identifier)["statistics"]["dominant_label_id"] is None
    c.store.edit(c.identifier, c.segments == 0, action="uncertain")
    saved = c.store.save(c.identifier)
    assert rows(c, "annotation") == rows(c, "sample_spectrum") == []
    assert rows(c, "annotation_version")[0]["labeled_pixels"] == 0
    assert c.store.read_version(saved["id"])["spectra"] == {}
    fresh = SessionStore(c.registry, c.paths)
    assert fresh.working(c.identifier)["statistics"]["blank_pixels"] == 480
    assert fresh.working(c.identifier)["params"] is None
    with pytest.raises(DataError, match="请先生成超像素"):
        fresh.save(c.identifier)
    with pytest.raises(AnnotationConflict):
        fresh.undo(c.identifier)


def test_source_changed_during_save_is_not_hidden_by_working_cache(annotation_case):
    c = annotation_case
    manual_state(c)
    c.header.unlink()
    with pytest.raises(DataError) as error:
        c.store.save(c.identifier)
    assert error.value.code == "SOURCE_CHANGED"
    assert rows(c, "annotation_version") == []


def test_save_reads_before_write_transaction_and_publishes_tmp(annotation_case, monkeypatch):
    c = annotation_case
    manual_state(c)
    original_read = SpectrumDataSet.read_region
    reads = []
    def no_write_lock(dataset, *args):
        with connect_database(c.paths.database, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")  # Would fail if save held its write txn.
            db.rollback()
        reads.append(args)
        return original_read(dataset, *args)
    monkeypatch.setattr(SpectrumDataSet, "read_region", no_write_lock)
    from spectrumagent.annotation import session
    original_replace = session.os.replace
    publications = []
    def replace(source, target):
        publications.append((source.name, target.name))
        assert source.name.endswith(".tmp") and target.name == "v1"
        assert {p.name for p in source.iterdir()} == {"label_map.npz", "label_index.json", "spectra.npz"}
        return original_replace(source, target)
    monkeypatch.setattr(session.os, "replace", replace)
    c.store.save(c.identifier)
    assert len(reads) == 4 and len(publications) == 1


def test_cube_working_states_and_candidate_queues_are_independent(annotation_case):
    c = annotation_case
    other = str(c.registry.import_path(str(c.header), raw=False).datasets[0].id)
    assert other != c.identifier
    manual_state(c)
    c.store._state(c.identifier).candidates.append({"superpixels": [2]})
    original = c.store.working(c.identifier)
    fresh = c.store.working(other)
    assert fresh["statistics"]["blank_pixels"] == 480
    assert fresh["statistics"]["pending_pixels"] == 0
    assert original["statistics"]["labeled_pixels"] == 160
    assert original["statistics"]["pending_pixels"] == 80
    assert c.store.working(other)["params"] is None
