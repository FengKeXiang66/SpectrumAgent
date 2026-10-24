"""R14 service binding, frozen schemas and geometric egress regressions."""
import json
import re
from types import SimpleNamespace

import numpy as np
import pytest

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
    tools = build_registry(sessions=sessions)
    return SimpleNamespace(database=c.database, cube_id=cube_id, sessions=sessions, tools=tools)


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


def test_frozen_schema_and_pending_handlers_remain_unchanged(draft_tools):
    c = draft_tools
    assert c.tools.snapshot() == build_registry().snapshot()
    for name, arguments in [
        ("annotations.draft_add_region", {"cube_id": c.cube_id, "revision": 1, "geometry": {"gesture_ref": "g-1"}, "class_code": "PE"}),
        ("annotations.draft_select_candidates", {"cube_id": c.cube_id, "class_code": "PE", "method": "SLIC", "params": {"n_segments": 3, "compactness": .5, "pca_components": 2}}),
        ("annotations.draft_select_candidates", {"cube_id": c.cube_id, "class_code": "PE", "method": "SAM", "params": {"gesture_ref": "g-1", "threshold": .8, "queue_min_similarity": .9}}),
        ("annotations.draft_confirm", {"cube_id": c.cube_id, "revision": 1}),
        ("training_mat.export", {"cube_id": c.cube_id, "version_id": "v-1"}),
    ]:
        with pytest.raises(DataError) as error:
            c.tools.invoke(name, arguments)
        assert error.value.code == "TOOL_NOT_IMPLEMENTED"
        assert not c.tools.resolve(name).ready
    assert c.sessions.drafts.get(c.cube_id) is None


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
