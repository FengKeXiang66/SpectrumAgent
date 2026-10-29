import json
from pathlib import Path
import sys

from backend.database import connect_database
from spectrumagent.agent.state import AgentStore
from spectrumagent.api.registry import DatasetRegistry
from .test_conversation_workflows import _events
from .test_state import FakeLLM, call, reply

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from display_catalog import seed_catalog


def test_api_and_all_four_assistant_consumers_share_names(settings_api, tmp_path):
    c = settings_api
    records = seed_catalog(DatasetRegistry(c.database), tmp_path / "sources")
    with connect_database(c.database) as db:
        before = db.execute("SELECT id,payload FROM dataset_registry ORDER BY rowid").fetchall()
    listing = c.app.state.agent_tools.invoke("datasets.list", {})
    assert listing["dataset_8_name"] != listing["dataset_12_name"]
    evidence = {}
    for i, record in enumerate(records, 1):
        identifier = str(record.id)
        response = c.client.get(f"/api/v1/datasets/{identifier}")
        assert response.status_code == 200
        name = response.json()["display_name"]
        assert listing[f"dataset_{i}_name"] == name == record.display_name
        if i in (8, 12):
            description = c.app.state.agent_tools.invoke("datasets.describe", {"dataset_id": identifier})
            context = c.app.state.agent_tools.invoke("annotations.context", {"cube_id": identifier})
            resolved = c.app.state.agent_tools.invoke("datasets.resolve", {"query": name})
            assert description["display_name"] == context["display_name"] == resolved["display_name"] == name
            assert resolved["cube_id"] == identifier and resolved["dataset_ref"] == f"D{i}"
            evidence[f"D{i}"] = {"id": identifier, "api_display_name": name,
                                  "assistant_name": listing[f"dataset_{i}_name"]}
    with connect_database(c.database) as db:
        assert db.execute("SELECT id,payload FROM dataset_registry ORDER BY rowid").fetchall() == before
    print("E", json.dumps(evidence, ensure_ascii=False))


def test_new_session_lists_distinct_names_then_selects_twelfth(settings_api, tmp_path):
    c = settings_api
    records = seed_catalog(DatasetRegistry(c.database), tmp_path / "sources")
    names = [records[i - 1].display_name for i in (8, 12)]
    provider = FakeLLM(reply(calls=[call("datasets.list", "{}", "list-names")]),
                       reply(f"D8：{names[0]}；D12：{names[1]}。"))
    c.app.state.agent_llm_factory = lambda _: provider
    created = c.client.post("/api/v1/agent/sessions", json={})
    assert created.status_code == 200
    session_id = created.json()["id"]
    listed = _events(c.client, session_id, "有哪些数据")
    assert not any(kind == "error" for kind, _ in listed)
    assert listed[-1][0] == "done" and all(name in listed[-1][1]["content"] for name in names)
    selected = _events(c.client, session_id, "第 12 个")
    assert not any(kind == "error" for kind, _ in selected)
    state = AgentStore(c.database).context(session_id)
    assert state["selected_cube_id"] == str(records[11].id)
    assert names[1] in selected[-1][1]["content"] and "D12" in selected[-1][1]["content"]
    assert len(provider.calls) == 2  # Ordinal selection is resolved by the real controller.
    print("F", json.dumps({"list_events": listed, "select_events": selected}, ensure_ascii=False))
