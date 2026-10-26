"""R14 service binding, frozen schemas and geometric egress regressions."""
import json
import re
from types import SimpleNamespace

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.annotation.engines.superpixels import Parameters, SuperpixelEngine
from spectrumagent.annotation.engines.diffusion import DiffusionEngine
from unittest.mock import Mock
from dataclasses import asdict

from spectrumagent.agent.llm import _json
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.tools import build_registry
from spectrumagent.annotation.session import SessionStore
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError
from .test_state import FakeLLM, call, reply


@pytest.fixture
def draft_tools(gateway_case, tmp_path):
    c = gateway_case
    registry = DatasetRegistry(c.database)
    header = tmp_path / "tool.hdr"
    header.with_suffix(".img").write_bytes(np.arange(48, dtype=np.float32).tobytes())
    header.write_text("ENVI\nsamples=4\nlines=4\nbands=3\ndata type=4\ninterleave=bip\nbyte order=0\n", "utf-8")
    cube_id = str(registry.import_path(str(header), raw=True).datasets[0].id)
    sessions = SessionStore(registry, c.paths)
    diffusion = DiffusionEngine(SuperpixelEngine(registry), sessions)
    tools = build_registry(sessions=sessions, diffusion=diffusion)
    return SimpleNamespace(database=c.database, cube_id=cube_id, sessions=sessions, tools=tools, diffusion=diffusion)


@pytest.mark.parametrize("present", [False, True])
def test_real_draft_get_replays_only_scalar_summary_with_size(draft_tools, present):
    c = draft_tools
    if present:
        c.sessions.drafts.add(c.cube_id, 0, geometry={"type": "polygon", "points": [[0, 0], [0, 2], [2, 2], [2, 0]]}, class_code="PE")
    store = AgentStore(c.database)
    session = store.create_session()
    fake = FakeLLM(reply(calls=[call("annotations.draft_get", _json({"cube_id": c.cube_id}))]), reply("已读取草稿摘要"))
    state = StateMachine(store, session["id"], fake, c.tools)
    events = list(state.message(content="读取当前草稿"))
    assert [name for name, _ in events] == ["step", "done"]
    messages, tools, _ = fake.calls[-1]
    assert tools is None
    text = _json(messages)
    assert "[[" not in text and not re.search(r"\b(points|polygon|sample_pixels|bbox|document)\b", text)
    result = json.loads(next(message["content"] for message in messages if message["role"] == "tool"))
    assert set(result) == {"cube_id", "revision", "n_regions", "n_classes", "updated_at", "estimated_mat_bytes"}
    assert result["cube_id"] == c.cube_id and result["estimated_mat_bytes"] == (48 if present else 0)
    assert result["revision"] == result["n_regions"] == int(present)
    assert result["n_classes"] == (4 if present else 0)
    assert all(value is None or type(value) in (str, int, float, bool) for value in result.values())
    step, = store.steps(session["id"])
    assert step["status"] == "ok" and json.loads(step["result_summary"]) == result


def test_frozen_schema_and_ready_handlers_keep_slic_explicitly_unimplemented(draft_tools):
    c = draft_tools
    assert c.tools.snapshot() == build_registry().snapshot()
    for name in ["annotations.draft_add_region", "annotations.draft_select_candidates"]:
        assert c.tools.resolve(name).ready
    with pytest.raises(DataError) as error:
        c.tools.invoke("annotations.draft_select_candidates", {"cube_id": c.cube_id, "class_code": "PE", "method": "SLIC",
            "params": {"n_segments": 3, "compactness": .5, "pca_components": 2}})
    assert error.value.code == "TOOL_NOT_IMPLEMENTED"
    assert c.sessions.drafts.get(c.cube_id) is None


def prepare_confirm(c, overlap=False):
    c.sessions.set_segmentation(c.cube_id, SimpleNamespace(segments=np.zeros((4, 4), dtype=np.int32), report={"params": asdict(Parameters())}))
    geometry = {"type": "polygon", "points": [[0, 0], [0, 2], [2, 2], [2, 0]]}
    c.sessions.drafts.add(c.cube_id, 0, geometry=geometry, class_code="PE")
    if overlap:
        c.sessions.drafts.add(c.cube_id, 1, geometry=geometry, class_code="PET")
    return 2 if overlap else 1


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_confirm_real_human_gate_and_export_eight_scalars(draft_tools, decision, monkeypatch):
    c = draft_tools
    revision = prepare_confirm(c)
    store = AgentStore(c.database)
    session = store.create_session()
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", _json({"cube_id": c.cube_id, "revision": revision}))]), reply("确认完成"))
    original, executions = c.sessions.confirm, []
    def execute(*args, **kwargs):
        executions.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(c.sessions, "confirm", execute)
    events = list(StateMachine(store, session["id"], fake, c.tools).message(content="确认标注版本"))
    assert [name for name, _ in events] == ["human_check"] and executions == []
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0
    resumed = list(StateMachine(store, session["id"], fake, c.tools).message(check_id=events[0][1]["check_id"], decision=decision))
    assert [name for name, _ in resumed] == ["step", "done"]
    step, = store.steps(session["id"])
    assert len(executions) == int(decision == "approve")
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == int(decision == "approve")
        assert db.execute("SELECT status FROM agent_round").fetchone()[0] == "done"
    if decision == "reject":
        assert step["status"] == "rejected"
        return
    result = json.loads(step["result_summary"])
    assert result["training_mat_id"] and result["overlap_conflicts"] == 0
    assert set(result) == {"version_id", "version_no", "training_mat_id", "overlap_conflicts", "n_spectra"}
    export = c.tools.invoke("training_mat.export", {"cube_id": c.cube_id, "version_id": result["version_id"]})
    assert set(export) == {"cube_id", "version_id", "training_mat_id", "n_spectra", "n_bands", "n_classes", "sha256", "status"}
    assert (export["n_spectra"], export["n_bands"], export["n_classes"], export["status"]) == (4, 3, 4, "ready")
    assert all(type(v) in (str, int) for v in export.values())
    text = _json(fake.calls[-1][0])
    assert "[[" not in text and not re.search(r"\b(points|polygon|sample_pixels|bbox|document)\b", text)


def test_probe7_real_overlap_interpret_is_count_and_prose_only(draft_tools):
    c = draft_tools
    revision = prepare_confirm(c, overlap=True)
    store = AgentStore(c.database)
    session = store.create_session()
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", _json({"cube_id": c.cube_id, "revision": revision}))]), reply("请处理跨类重叠"))
    pending = list(StateMachine(store, session["id"], fake, c.tools).message(content="确认"))
    events = list(StateMachine(store, session["id"], fake, c.tools).message(check_id=pending[0][1]["check_id"], decision="approve"))
    assert [name for name, _ in events] == ["step", "done"]
    messages, tools, _ = fake.calls[-1]
    assert tools is None
    text = _json(messages)
    assert "[[" not in text and not re.search(r"\b(points|polygon|sample_pixels|bbox|document)\b", text)
    summary = json.loads(next(m["content"] for m in messages if m["role"] == "tool"))
    assert summary["overlap_conflicts"] == 4 and summary["error"] == "OVERLAP_UNRESOLVED"
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0


def test_export_missing_mat_is_explicit(draft_tools):
    c = draft_tools
    prepare_confirm(c)
    saved = c.sessions.save(c.cube_id)
    with pytest.raises(DataError) as error:
        c.tools.invoke("training_mat.export", {"cube_id": c.cube_id, "version_id": saved["id"]})
    assert error.value.code == "MAT_NOT_FOUND"


def test_coordinates_still_rejected_before_handler_and_recorded(draft_tools):
    c = draft_tools
    store = AgentStore(c.database)
    session = store.create_session()
    fake = FakeLLM(reply(calls=[call("annotations.draft_add_region", _json({"cube_id": c.cube_id,
        "revision": 1, "class_code": "PE", "geometry": {"points": [[1, 2], [3, 4]]}}))]), reply("参数不合法"))
    state = StateMachine(store, session["id"], fake, c.tools)
    events = list(state.message(content="编辑草稿"))
    assert [name for name, _ in events] == ["step", "done"]
    step, = store.steps(session["id"])
    assert step["status"] == "rejected" and step["result_digest"] is None
    assert json.loads(step["result_summary"]) == {"error": "TOOL_ARGS_INVALID"}
    assert c.sessions.drafts.get(c.cube_id) is None


@pytest.mark.parametrize("op,confidence", [("add", None), ("add", "medium"), ("add", "low"), ("uncertain", None), ("erase", None)])
def test_gesture_tools_replay_three_ops_and_scalar_summaries(draft_tools, op, confidence):
    c = draft_tools
    revision = prepare_confirm(c)
    ref = c.sessions.store_gesture(c.cube_id, {"doodle": [[0, 0], [3, 3]]})
    body = {"cube_id": c.cube_id, "revision": revision, "op": op, "geometry": {"gesture_ref": ref}}
    if op == "add":
        body["class_code"] = "PE"
        if confidence is not None:
            body["confidence"] = confidence
    store = AgentStore(c.database)
    session = store.create_session()
    fake = FakeLLM(reply(calls=[call("annotations.draft_add_region", _json(body))]), reply("完成"))
    events = list(StateMachine(store, session["id"], fake, c.tools).message(content="按手势编辑"))
    assert [kind for kind, _ in events] == ["step", "done"] and events[0][1]["status"] == "ok"
    summary = events[0][1]["result_summary"]
    assert set(summary) == {"cube_id", "revision", "region_id", "op", "n_superpixels", "pixel_count"} | ({"class_code"} if op == "add" else set())
    assert all(value is None or type(value) in (str, bool, int, float) for value in summary.values())
    region = c.sessions.drafts.get(c.cube_id)["document"]["regions"][-1]
    assert region["source"] == "manual" and region["geometry"]["type"] == "pixel_set"
    assert summary["region_id"] == region["region_id"]
    if op == "add":
        assert region["confidence"] == (confidence or "high")
    else:
        assert "class_index" not in region and "confidence" not in region
    text = _json(fake.calls[-1][0])
    assert "[[" not in text and not re.search(r"\b(points|polygon|sample_pixels|bbox|document)\b", text)


def test_gesture_tool_stale_revision_is_step_error_without_document_change(draft_tools):
    c = draft_tools
    prepare_confirm(c)
    before = c.sessions.drafts.get(c.cube_id)
    ref = c.sessions.store_gesture(c.cube_id, {"point": [1, 1]})
    c.sessions.drafts.add(c.cube_id, 1, geometry={"type": "polygon", "points": [[0, 0], [0, 1], [1, 1]]}, class_code="PE")
    before = c.sessions.drafts.get(c.cube_id)
    store = AgentStore(c.database); session = store.create_session()
    fake = FakeLLM(reply(calls=[call("annotations.draft_add_region", _json({"cube_id": c.cube_id, "revision": 1,
        "class_code": "PE", "geometry": {"gesture_ref": ref}}))]))
    events = list(StateMachine(store, session["id"], fake, c.tools).message(content="旧 revision"))
    assert [kind for kind, _ in events] == ["step", "error"]
    assert events[0][1]["status"] == "error" and events[-1][1]["code"] == "DRAFT_REVISION_CONFLICT"
    assert c.sessions.drafts.get(c.cube_id) == before


@pytest.mark.parametrize("floor", [.8, .99])
def test_sam_tool_reports_queue_floor_confidence_and_no_ghost(draft_tools, monkeypatch, floor):
    c = draft_tools
    prepare_confirm(c)
    ref = c.sessions.store_gesture(c.cube_id, {"point": [1, 1]})
    def generate(cube, seed, *, threshold, queue_min_similarity):
        candidate = {"superpixels": [0], "min_similarity": .9, "avg_similarity": .95}
        if .9 >= queue_min_similarity:
            c.sessions._state(cube).candidates.append(candidate)
        return {"candidate": candidate, "enqueued": .9 >= queue_min_similarity,
                "params": {"threshold": threshold, "queue_min_similarity": queue_min_similarity}}
    monkeypatch.setattr(c.diffusion, "generate", generate)
    result = c.tools.invoke("annotations.draft_select_candidates", {"cube_id": c.cube_id, "class_code": "PE", "method": "SAM",
        "params": {"gesture_ref": ref, "threshold": .5, "queue_min_similarity": floor}})
    assert set(result) == {"cube_id", "revision", "region_id", "method", "class_code", "n_superpixels", "pixel_count",
                           "min_similarity", "queue_min_similarity", "below_queue_floor", "queue_note"}
    assert all(value is None or type(value) in (str, bool, int, float) for value in result.values())
    assert result["queue_min_similarity"] == floor and result["below_queue_floor"] == (floor > .9)
    assert str(floor) in result["queue_note"] if floor > .9 else result["queue_note"] is None
    region = c.sessions.drafts.get(c.cube_id)["document"]["regions"][-1]
    assert region["source"] == "algorithm" and region["confidence"] == ("low" if floor > .9 else "medium")
    assert c.sessions._state(c.cube_id).candidates == []


def test_empty_draft_tool_rejects_before_handler_then_rest_bootstraps_same_gesture(draft_tools, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.identity import EngineIdentity
    from spectrumagent.app import create_app
    c = draft_tools
    identity = EngineIdentity()
    app = create_app(c.sessions.paths, identity)
    sessions = app.state.annotation_sessions
    sessions.set_segmentation(c.cube_id, SimpleNamespace(segments=np.zeros((4, 4), dtype=np.int32), report={"params": asdict(Parameters())}))
    edit = Mock(wraps=sessions.edit)
    monkeypatch.setattr(sessions, "edit", edit)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        ref = client.post(f"/api/v1/annotations/{c.cube_id}/gestures", json={"seed": {"point": [1, 1]}}).json()["gesture_ref"]
        body = {"cube_id": c.cube_id, "revision": 0, "class_code": "PE", "geometry": {"gesture_ref": ref}}
        with pytest.raises(DataError) as error:
            app.state.agent_tools.invoke("annotations.draft_add_region", body)
        assert error.value.code == "TOOL_ARGS_INVALID"
        edit.assert_not_called(); assert sessions.drafts.get(c.cube_id) is None
        response = client.post(f"/api/v1/annotations/{c.cube_id}/draft/regions", json={key: value for key, value in body.items() if key != "cube_id"})
        assert response.status_code == 200 and response.json()["revision"] == 1
        body["revision"] = 1
        assert app.state.agent_tools.invoke("annotations.draft_add_region", body)["revision"] == 2
        assert edit.call_count == 2


def test_optional_missing_diffusion_refuses_sam_cleanly(draft_tools):
    c = draft_tools
    tools = build_registry(sessions=c.sessions)
    with pytest.raises(DataError) as error:
        tools.invoke("annotations.draft_select_candidates", {"cube_id": c.cube_id, "class_code": "PE", "method": "SAM",
            "params": {"gesture_ref": "g-1", "threshold": .5, "queue_min_similarity": .8}})
    assert error.value.code == "TOOL_NOT_IMPLEMENTED"
