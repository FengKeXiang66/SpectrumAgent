"""Real services for the dialogue workflow, with no provider or material oracle."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.agent.llm import _egress_blocked
from spectrumagent.agent.tools import build_registry
from spectrumagent.annotation.engines.diffusion import DiffusionEngine
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine
from spectrumagent.annotation.session import SessionStore
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError
from spectrumagent.preprocess.run import RunEngine
from spectrumagent.preprocess.compare import CompareEngine


@pytest.fixture
def workflow_case(gateway_case, tmp_path):
    c = gateway_case
    datasets = DatasetRegistry(c.database)
    header = tmp_path / "081.hdr"
    rng = np.random.default_rng(11)
    x = .01 + rng.random((16, 16, 20)).astype(np.float32) * .003
    x[:8, :, :8] += .6
    x[8:, :, 12:] += .6
    header.with_suffix(".img").write_bytes(x.tobytes())
    header.write_text("ENVI\nsamples=16\nlines=16\nbands=20\ndata type=4\ninterleave=bip\nbyte order=0\n", "utf-8")
    cube_id = str(datasets.import_path(str(header), raw=True).datasets[0].id)
    sessions = SessionStore(datasets, c.paths)
    diffusion = DiffusionEngine(SuperpixelEngine(datasets), sessions)
    runner = RunEngine(datasets, c.paths)
    tools = build_registry(datasets=datasets, sessions=sessions, diffusion=diffusion, runner=runner,
                           comparison=CompareEngine(runner), catalogue_version=2)
    return SimpleNamespace(**vars(c), datasets=datasets, cube_id=cube_id, sessions=sessions,
                           diffusion=diffusion, runner=runner, tools=tools)


def invoke(c, name, **arguments):
    result = c.tools.invoke(name, arguments)
    assert all(value is None or type(value) in (str, int, bool, float) for value in result.values())
    assert not _egress_blocked(result), result
    return result


def test_v1_snapshot_kept_and_v2_catalogue_safe():
    one, two = build_registry(), build_registry(catalogue_version=2)
    assert len(one.snapshot()) == 10
    assert "annotations.draft_select_candidates" in {t["function"]["name"] for t in one.snapshot()}
    assert "annotations.draft_add_region" in {t["function"]["name"] for t in one.snapshot()}
    assert "annotations.draft_select_candidates" not in {t["function"]["name"] for t in two.snapshot()}
    assert "annotations.draft_add_region" not in {t["function"]["name"] for t in two.snapshot()}
    assert two.resolve("annotations.draft_add_region").adapter.json_schema() == one.resolve("annotations.draft_add_region").adapter.json_schema()
    assert two.catalogue_version == 2 and not _egress_blocked(two.snapshot())


def test_readable_catalogue_name_prefix_ordinal_and_ambiguity(workflow_case):
    c = workflow_case
    listing = invoke(c, "datasets.list")
    assert listing["dataset_count"] == 1 and listing["dataset_1_name"] == "081"
    assert listing["dataset_1_ref"] == "D1"
    for query in ("081", "08", "D1", "第一项", "第一个", c.cube_id[:8]):
        found = invoke(c, "datasets.resolve", query=query)
        assert found["status"] == "resolved" and found["cube_id"] == c.cube_id
    with connect_database(c.database) as db:
        row = db.execute("SELECT header_key,payload,project_id FROM dataset_registry WHERE id=?", (c.cube_id,)).fetchone()
        db.execute("INSERT INTO dataset_registry (id,header_key,raw,payload,project_id) VALUES (?,?,?,?,?)",
                   ("duplicate", row[0] + "-copy", 1, row[1], row[2]))
    assert invoke(c, "datasets.resolve", query="081")["status"] == "ambiguous"
    assert invoke(c, "datasets.resolve", query="unavailable")["status"] == "not_found"


def test_missing_seed_never_creates_pp_or_background(workflow_case):
    c = workflow_case
    context = invoke(c, "annotations.context", cube_id=c.cube_id)
    assert context["revision"] == 0 and context["n_classes"] == 4 and context["labeled_pixels"] == 0
    assert "last_gesture_ref" not in context
    prepared = invoke(c, "annotations.prepare", cube_id=c.cube_id)
    assert prepared["pca_components"] == 5 and prepared["n_segments"] == 800
    assert invoke(c, "annotations.propose", cube_id=c.cube_id, class_code="PP")["status"] == "need_seed"
    assert invoke(c, "annotations.set_background", cube_id=c.cube_id, revision=0)["status"] == "need_seed"
    assert c.sessions.drafts.get(c.cube_id) is None


def preview(c):
    invoke(c, "annotations.ensure_labels", cube_id=c.cube_id, class_codes=["PP"], include_background=True)
    invoke(c, "annotations.prepare", cube_id=c.cube_id)
    gesture = c.sessions.store_gesture(c.cube_id, {"point": [2, 2]})
    proposal = invoke(c, "annotations.propose", cube_id=c.cube_id, class_code="PP")
    assert proposal["status"] == "preview" and proposal["revision"] == 0
    assert c.sessions.drafts.get(c.cube_id) is None
    assert invoke(c, "annotations.context", cube_id=c.cube_id)["last_gesture_ref"] == gesture
    assert 0 < proposal["pixel_count"] < 256
    return proposal


def test_preview_accept_first_edit_background_undo_and_save(workflow_case):
    c = workflow_case
    proposal = preview(c)
    applied = invoke(c, "annotations.apply_candidate", cube_id=c.cube_id,
                     candidate_ref=proposal["candidate_ref"], revision=0)
    assert applied["revision"] == 1 and applied["labeled_pixels"] == proposal["pixel_count"]
    first_region = applied["region_id"]
    relabel = invoke(c, "annotations.edit_region", cube_id=c.cube_id, region_id=first_region,
                     revision=1, action="relabel", class_code="PE")
    assert relabel["revision"] == 2 and relabel["region_1_class_code"] == "PE"
    undone = invoke(c, "annotations.undo", cube_id=c.cube_id, revision=2)
    assert undone["revision"] == 3 and undone["region_1_class_code"] == "PP"
    background = invoke(c, "annotations.set_background", cube_id=c.cube_id, revision=3)
    assert background["revision"] == 4 and background["labeled_pixels"] == 256
    assert background["background_added_pixels"] == 256 - proposal["pixel_count"]
    saved = invoke(c, "annotations.draft_confirm", cube_id=c.cube_id, revision=4)
    assert saved["version_id"] and saved["n_spectra"] == 256
    assert invoke(c, "annotations.context", cube_id=c.cube_id)["latest_annotation_version_id"] == saved["version_id"]


def test_background_preserves_uncertain_and_existing_foreground(workflow_case):
    c = workflow_case
    proposal = preview(c)
    invoke(c, "annotations.apply_candidate", cube_id=c.cube_id, candidate_ref=proposal["candidate_ref"], revision=0)
    state = c.sessions._state(c.cube_id)
    uncertain = np.zeros(state.label_map.shape, dtype=bool)
    uncertain[-1, -1] = True
    c.sessions.edit(c.cube_id, uncertain, action="uncertain")
    before = c.sessions.working(c.cube_id)["label_map"].copy()
    result = invoke(c, "annotations.set_background", cube_id=c.cube_id, revision=2)
    after = c.sessions.working(c.cube_id)["label_map"]
    assert result["uncertain_pixels"] == 1 and after[-1, -1] == -2
    np.testing.assert_array_equal(after[before >= 0], before[before >= 0])


def test_prepare_keeps_existing_draft_and_labels_idempotent(workflow_case):
    c = workflow_case
    proposal = preview(c)
    invoke(c, "annotations.apply_candidate", cube_id=c.cube_id, candidate_ref=proposal["candidate_ref"], revision=0)
    before = c.sessions.drafts.get(c.cube_id)
    pixels = c.sessions.working(c.cube_id)["label_map"].copy()
    invoke(c, "annotations.prepare", cube_id=c.cube_id)
    result = invoke(c, "annotations.ensure_labels", cube_id=c.cube_id, class_codes=["PP"], include_background=True)
    assert result["created_label_count"] == 0
    assert before == c.sessions.drafts.get(c.cube_id)
    np.testing.assert_array_equal(pixels, c.sessions.working(c.cube_id)["label_map"])


def test_template_content_verified_and_unknown_material_never_created(workflow_case):
    c = workflow_case
    recipe = c.runner.recipes.create("conversation-snv-v1", "共享代号", None, {"steps": []})
    chosen = invoke(c, "preprocess.recipe_ensure", profile="snv")
    assert chosen["recipe_version_no"] == 2
    versions = c.runner.recipes.get(recipe["id"])["versions"]
    assert versions[0]["pipeline"] == {"steps": []}
    assert versions[1]["pipeline"]["steps"][0]["op"] == "snv"
    before = len(c.sessions.drafts.labels(c.cube_id))
    with pytest.raises(DataError) as caught:
        c.tools.invoke("annotations.ensure_labels", {"cube_id": c.cube_id, "class_codes": ["unproven-material"]})
    assert caught.value.code == "LABEL_NOT_FOUND" and len(c.sessions.drafts.labels(c.cube_id)) == before


def test_stale_preview_and_wrong_cube_reject_without_mutation(workflow_case):
    c = workflow_case
    proposal = preview(c)
    with pytest.raises(DataError, match="草稿已变化|DRAFT_REVISION_CONFLICT"):
        c.tools.invoke("annotations.apply_candidate", {"cube_id": c.cube_id,
            "candidate_ref": proposal["candidate_ref"], "revision": 1})
    assert c.sessions.drafts.get(c.cube_id) is None
    state = c.sessions._state(c.cube_id)
    state.segments = np.roll(state.segments, 1, axis=0)
    with pytest.raises(DataError) as caught:
        c.tools.invoke("annotations.apply_candidate", {"cube_id": c.cube_id,
            "candidate_ref": proposal["candidate_ref"], "revision": 0})
    assert caught.value.code == "SEGMENTATION_STALE" and c.sessions.drafts.get(c.cube_id) is None


def test_reject_candidate_clears_preview_without_draft(workflow_case):
    c = workflow_case
    proposal = preview(c)
    assert invoke(c, "annotations.context", cube_id=c.cube_id)["latest_candidate_ref"] == proposal["candidate_ref"]
    result = invoke(c, "annotations.reject_candidate", cube_id=c.cube_id, candidate_ref=proposal["candidate_ref"])
    assert result["status"] == "rejected" and result["revision"] == 0
    assert c.sessions.drafts.get(c.cube_id) is None
    assert "latest_candidate_ref" not in invoke(c, "annotations.context", cube_id=c.cube_id)
    assert all(item.get("candidate_ref") != proposal["candidate_ref"] for item in c.sessions._state(c.cube_id).candidates)


def test_below_queue_floor_has_no_applicable_reference_or_invisible_acceptance(workflow_case, monkeypatch):
    c = workflow_case
    previous = preview(c)
    state = c.sessions._state(c.cube_id)
    # This fixture isolates the queue-policy boundary from growth arithmetic:
    # the engine reports a low seed-reference similarity and withholds preview.
    candidate = {"pixel_count": 128, "min_similarity": .5, "superpixels": [0]}
    monkeypatch.setattr(c.diffusion, "generate", lambda *args, **kwargs: {"candidate": candidate, "enqueued": False})
    result = invoke(c, "annotations.propose", cube_id=c.cube_id, class_code="PP")
    assert result["status"] == "need_seed" and result["below_queue_floor"] is True
    assert result["min_similarity"] == .5 and "candidate_ref" not in result
    assert c.sessions.drafts.get(c.cube_id) is None
    assert "latest_candidate_ref" not in invoke(c, "annotations.context", cube_id=c.cube_id)
    assert all(item.get("candidate_ref") != previous["candidate_ref"] for item in state.candidates)
    with pytest.raises(DataError) as caught:
        c.tools.invoke("annotations.apply_candidate", {"cube_id": c.cube_id,
            "candidate_ref": previous["candidate_ref"], "revision": 0})
    assert caught.value.code == "CANDIDATE_NOT_FOUND"
    assert c.sessions.drafts.get(c.cube_id) is None


@pytest.mark.parametrize("action,expected", [("uncertain", -2), ("erase", -1)])
def test_mark_current_gesture_supports_first_revision_and_three_state_semantics(workflow_case, action, expected):
    c = workflow_case
    invoke(c, "annotations.prepare", cube_id=c.cube_id)
    gesture = c.sessions.store_gesture(c.cube_id, {"point": [2, 2]})
    result = invoke(c, "annotations.mark_region", cube_id=c.cube_id,
                    revision=0, gesture_ref=gesture, action=action)
    assert result["revision"] == 1 and result["op"] == action and result["marked_pixels"] > 0
    assert c.sessions.working(c.cube_id)["label_map"][2, 2] == expected
    region = c.sessions.drafts.get(c.cube_id)["document"]["regions"][-1]
    assert region["op"] == action and "class_index" not in region and "confidence" not in region


def test_mark_rejects_old_gesture_and_material_or_confidence_fields(workflow_case):
    c = workflow_case
    invoke(c, "annotations.prepare", cube_id=c.cube_id)
    old = c.sessions.store_gesture(c.cube_id, {"point": [2, 2]})
    current = c.sessions.store_gesture(c.cube_id, {"point": [12, 12]})
    with pytest.raises(DataError) as caught:
        c.tools.invoke("annotations.mark_region", {"cube_id": c.cube_id,
            "revision": 0, "gesture_ref": old, "action": "uncertain"})
    assert caught.value.code == "GESTURE_NOT_CURRENT" and c.sessions.drafts.get(c.cube_id) is None
    for extra in ({"class_code": "PP"}, {"confidence": "high"}, {"point": [2, 2]}):
        with pytest.raises(DataError) as caught:
            c.tools.invoke("annotations.mark_region", {"cube_id": c.cube_id,
                "revision": 0, "gesture_ref": current, "action": "uncertain", **extra})
        assert caught.value.code == "TOOL_ARGS_INVALID"
    assert c.sessions.drafts.get(c.cube_id) is None


def test_preprocess_defaults_discovery_real_comparison_and_no_paths(workflow_case):
    c = workflow_case
    missing = invoke(c, "preprocess.run_default", cube_id=c.cube_id)
    assert missing["status"] == "need_version" and missing["missing"] == "annotation_version"
    proposal = preview(c)
    invoke(c, "annotations.apply_candidate", cube_id=c.cube_id, candidate_ref=proposal["candidate_ref"], revision=0)
    invoke(c, "annotations.set_background", cube_id=c.cube_id, revision=1)
    saved = invoke(c, "annotations.draft_confirm", cube_id=c.cube_id, revision=2)
    recipe = invoke(c, "preprocess.recipe_ensure", profile="snv_sg1")
    default = invoke(c, "preprocess.run_default", cube_id=c.cube_id,
                     annotation_version_id=saved["version_id"], recipe_version_id=recipe["recipe_version_id"])
    assert default["status"] == "succeeded" and default["annotation_version_id"] == saved["version_id"]
    assert default["step_1_op"] == "snv" and default["step_2_op"] == "sg_derivative"
    query = invoke(c, "preprocess.run_get", run_id=default["run_id"])
    assert query["status"] == "succeeded" and "boundary_1" in query
    snv = invoke(c, "preprocess.recipe_ensure", profile="snv")
    assert snv == invoke(c, "preprocess.recipe_ensure", profile="snv")
    listing = invoke(c, "preprocess.recipes")
    assert listing["recipe_count"] == 2
    compared = invoke(c, "preprocess.compare", cube_id=c.cube_id, annotation_version_id=saved["version_id"],
                      recipe_version_ids=[default["recipe_version_id"], snv["recipe_version_id"]])
    assert compared["run_count"] == 2 and "boundary_1" in compared and "selection_rule" in compared
    assert "SNR" in compared["boundary_1"]
    assert compared["run_1_step_2_op"] == "sg_derivative" and compared["run_2_step_1_op"] == "snv"


@pytest.mark.parametrize("tool,arguments", [
    ("annotations.propose", {"cube_id": "x", "class_code": "PP", "point": [1, 2]}),
    ("annotations.edit_region", {"cube_id": "x", "revision": 0, "region_id": "r-0001", "action": "delete", "class_code": "PP"}),
    ("preprocess.recipe_ensure", {"profile": "guess_best"}),
])
def test_new_schemas_never_accept_geometry_or_invented_profile(tool, arguments):
    with pytest.raises(DataError) as caught:
        build_registry(catalogue_version=2).validate(tool, arguments)
    assert caught.value.code == "TOOL_ARGS_INVALID"
