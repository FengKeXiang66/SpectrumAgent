"""L0 A-K contracts; remote-provider acceptance is run separately over real HTTP."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3

import pytest

from spectrumagent.agent import context as memory
from spectrumagent.agent.task import CONTEXT_KEYS, TASK_RESULTS, TASK_SCHEMA_VERSION, evaluate_task, normalize_context
from spectrumagent.agent.workflow import RECOVERABLE


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("e2e_task10_l0", ROOT / "scripts" / "e2e_task10.py")
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


@pytest.mark.parametrize("state,artifacts,expected", [
    ({"dataset_catalog": [{"id": "c1"}]}, {}, "working"),  # C: a list is not an annotation.
    ({"candidate_ref": "c2", "accepted_candidate_ref": "c1"}, {}, "needs_review"),  # D
    ({"candidate_ref": "c1"}, {}, "needs_review"),
    ({"candidate_ref": "c1", "accepted_candidate_ref": "c1"}, {}, "working"),
    ({"stage": "annotation"}, {}, "needs_review"),
    ({"annotation_version_id": "v1"}, {}, "succeeded"),
    ({"annotation_version_id": "v1", "last_run_id": "r1"}, {"run_status": "succeeded"}, "succeeded"),
    ({"annotation_version_id": "v1", "last_run_id": "r1"}, {"run_status": "failed"}, "working"),
    ({"annotation_version_id": "v1", "last_run_id": "r1"}, {}, "working"),
    ({"cancelled": True, "last_error": "AGENT_FAILED"}, {}, "cancelled"),
    ({"next_action": "need_seed"}, {}, "needs_input"),  # I, source 1
    ({}, {"last_status": "need_annotation"}, "needs_input"),  # I, source 2
    ({"last_error": "GESTURE_EXPIRED"}, {}, "needs_input"),  # I, source 3
    ({"last_error": "CANDIDATE_STALE"}, {}, "working"),  # J
    ({"last_error": "AGENT_BUDGET_EXCEEDED"}, {}, "failed"),  # K
    ({"last_error": "AGENT_FAILED", "next_action": "need_seed"}, {}, "failed"),
    ({"annotation_version_id": "v1", "candidate_ref": "c1"}, {}, "needs_review"),
    ({"annotation_version_id": "v1", "next_action": "need_seed"}, {}, "needs_input"),
])
def test_task_outcome_order_and_counterexamples(state, artifacts, expected):
    before = deepcopy((state, artifacts))
    assert evaluate_task(state, artifacts) == expected
    assert evaluate_task(state, artifacts) == expected
    assert (state, artifacts) == before
    assert expected in TASK_RESULTS


def test_all_six_results_are_strings_and_reuse_the_recoverable_constant():
    from spectrumagent.agent import task
    cases = [({}, {}), ({"next_action": "need_seed"}, {}), ({"stage": "annotation"}, {}),
             ({"annotation_version_id": "v"}, {}), ({"last_error": "BAD"}, {}), ({"cancelled": True}, {})]
    assert {evaluate_task(*case) for case in cases} == set(TASK_RESULTS)
    assert task.RECOVERABLE is RECOVERABLE
    assert evaluate_task({"last_error": "CANDIDATE_STALE"}, {}) == "working"


def test_evaluate_and_normalize_do_not_read_database(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pure task rules must not open the database")
    monkeypatch.setattr("backend.database.connect_database", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert evaluate_task({"annotation_version_id": "v", "last_run_id": "r"}, {"run_status": "succeeded"}) == "succeeded"
    assert normalize_context({"selected_cube_id": "c", "future": True}) == {
        "selected_cube_id": "c", "task_schema_version": TASK_SCHEMA_VERSION}


@pytest.mark.parametrize("context", [None, [], "invalid", 2, {"selected_cube_id": "c", "unknown": 5, "task_schema_version": -1}])
def test_normalize_projects_without_changing_input_or_throwing(context):
    before = deepcopy(context)
    result = normalize_context(context)
    assert context == before
    assert result["task_schema_version"] == TASK_SCHEMA_VERSION
    assert set(result) <= CONTEXT_KEYS | {"task_schema_version"}
    assert "unknown" not in result


def test_context_literal_write_keys_are_registered():
    source = Path(memory.__file__).read_text("utf-8")
    written = set(re.findall(r'state\["([a-z_]+)"\]\s*=(?!=)', source))
    assert written and written <= CONTEXT_KEYS, written - CONTEXT_KEYS
    assert "cancelled" in CONTEXT_KEYS and "cancelled" not in written


def test_context_observed_write_keys_are_registered():
    states = []
    state = memory.observe({}, "datasets.list", {}, {"dataset_count": 1, "dataset_1_id": "c1", "dataset_1_name": "样品"})
    states.append(state)
    for text, workspace in [
        ("对第一个标注PP，其余背景，参数默认，自动执行，保存", {"cube_id": "c1", "gesture_ref": "g1"}),
        ("不接受候选，不要保存，不要自动，不用默认", None),
        ("接受候选", None),
    ]:
        states.append(memory.remember_user({**state, "candidate_ref": "p1"}, text, workspace))
    for tool, arguments, result in [
        ("annotations.context", {}, {"cube_id": "c1", "display_name": "样品", "revision": 1,
            "latest_annotation_version_id": "v1", "last_gesture_ref": "g1", "latest_candidate_ref": "p1"}),
        ("annotations.ensure_labels", {"class_codes": ["PP"]}, {}),
        ("annotations.propose", {}, {"status": "need_seed"}),
        ("annotations.propose", {}, {"status": "preview", "candidate_ref": "p1"}),
        ("annotations.draft_confirm", {}, {"version_id": "v1"}),
        ("preprocess.run_default", {}, {"run_id": "r1", "status": "succeeded", "recipe_version_id": "rv1"}),
        ("annotations.propose", {}, {"error": "GESTURE_EXPIRED"}),
    ]:
        states.append(memory.observe(state, tool, arguments, result))
    actual = set().union(*(set(state) for state in states))
    assert actual <= CONTEXT_KEYS, actual - CONTEXT_KEYS
    # The two paths cover every literal write, not only empty/no-op inputs.
    literals = set(re.findall(r'state\["([a-z_]+)"\]\s*=(?!=)', Path(memory.__file__).read_text("utf-8")))
    assert literals <= actual


def test_normalize_is_not_called_by_runtime(gateway_case, monkeypatch):
    from spectrumagent.agent import task
    from spectrumagent.agent.skill import ensure_workflow_skill
    from spectrumagent.agent.state import AgentStore, StateMachine
    from spectrumagent.agent.tools import build_registry
    from backend.database import connect_database
    from .test_state import FakeLLM, reply
    tools = build_registry(catalogue_version=2)
    with connect_database(gateway_case.database) as db:
        ensure_workflow_skill(db, tools)
    store = AgentStore(gateway_case.database)
    session = store.create_session()["id"]
    store.save_context(session, {"future_l2_key": "must survive"})
    def forbidden(*args):
        raise AssertionError("L0 must not project runtime memory")
    monkeypatch.setattr(task, "normalize_context", forbidden)
    events = list(StateMachine(store, session, FakeLLM(reply("已完成")), tools).message(content="你好"))
    assert events[-1][1]["task_result"] == "working"
    assert store.context(session)["future_l2_key"] == "must survive"


def test_message_url_and_sse_frames_use_one_api_prefix(monkeypatch, capsys):
    requests = []
    def response(request, **kwargs):
        requests.append(request)
        return io.BytesIO('event: step\ndata: {"tool":"annotations.prepare"}\n\nevent: done\ndata: {"task_result":"needs_input"}\n\n'.encode())
    monkeypatch.setattr(acceptance.urllib.request, "urlopen", response)
    events = acceptance.send_message("http://127.0.0.1:1234", "synthetic-auth", "s1", "synthetic prompt")
    assert requests[0].full_url == "http://127.0.0.1:1234/api/v1/agent/sessions/s1/messages"
    assert [name for name, _ in events] == ["step", "done"]
    assert events[-1][1]["task_result"] == "needs_input"
    assert "SSE step" in capsys.readouterr().out


@pytest.fixture
def script_case(tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(acceptance, "REPORT_PATH", report_path)
    monkeypatch.setattr(acceptance, "read_handshake", lambda _: {"port": 1234, "token": "synthetic-auth"})
    calls = []

    def api(base, token, path, payload=None, method="GET", timeout=180):
        calls.append((base, path))
        assert base == "http://127.0.0.1:1234"
        assert path.startswith("/api/v1/") and path.count("/api/v1") == 1
        return {"/api/v1/agent/runtime": {"skill_name": "conversation-workflows-v2"},
                "/api/v1/settings/llm": {"has_key": True}, "/api/v1/agent/sessions": {"id": "session"}}[path]

    monkeypatch.setattr(acceptance, "call_api", api)
    monkeypatch.setattr(acceptance, "baseline_of", lambda _: {"versions": {}, "run_count": 0, "run_ids": set()})
    return tmp_path, report_path, calls


def test_no_key_stops_at_l1_without_creating_a_session(script_case, monkeypatch, capsys):
    root, report_path, calls = script_case
    api = acceptance.call_api
    monkeypatch.setattr(acceptance, "call_api", lambda base, token, path, **kwargs:
        {"has_key": False} if path.endswith("/llm") else api(base, token, path, **kwargs))
    assert acceptance.main(["--data-root", str(root)]) == 1
    report = json.loads(report_path.read_text("utf-8"))
    assert list(report["evidence_levels"]) == ["L1"]
    assert report["session_id"] is None
    output = capsys.readouterr().out
    assert "RUNTIME:" in output and "conversation-workflows-v2" in output
    assert "FAIL at L1" in output and "编排通过" not in output
    assert len(calls) == 1  # The settings stub is deliberately not recorded.


def test_runtime_failure_reports_full_url_without_retry(script_case, monkeypatch, capsys):
    root, _, calls = script_case
    def fail(base, token, path):
        calls.append((base, path))
        raise OSError("synthetic failure")
    monkeypatch.setattr(acceptance, "call_api", fail)
    assert acceptance.main(["--data-root", str(root)]) == 1
    assert len(calls) == 1
    assert "http://127.0.0.1:1234/api/v1/agent/runtime" in capsys.readouterr().out


@pytest.mark.parametrize("stop", ["L2", "L3", "L4", None])
def test_four_evidence_levels_never_confuse_offered_with_executed(script_case, monkeypatch, stop):
    root, report_path, _ = script_case
    turns = []
    def send(base, token, session, content):
        turns.append(content)
        return [("clarify", {"question": "synthetic reply", "task_result": "needs_input"})]
    monkeypatch.setattr(acceptance, "send_message", send)
    evidence = {"catalogue_offered": [] if stop == "L2" else ["annotations.prepare"],
                "native_tool_sequence": [] if stop in {"L2", "L3"} else [{"seq": 1, "tool": "annotations.prepare", "status": "ok"}],
                "new_annotation_versions": [{"id": "v"}] if stop is None else [],
                "paired_succeeded_runs": [{"id": "r"}] if stop is None else [], "task_result": "working"}
    monkeypatch.setattr(acceptance, "session_evidence", lambda *args: evidence)
    assert acceptance.main(["--data-root", str(root)]) == (1 if stop else 0)
    report = json.loads(report_path.read_text("utf-8"))
    assert turns == [acceptance.DEFAULT_MESSAGE, "继续"]
    assert list(report["evidence_levels"]) == ["L1", "L2", "L3", "L4"][:int(stop[1]) if stop else 4]
    assert report["task_result"] == "needs_input"
    assert "tools_used" not in report and "message" not in report
    assert "synthetic-auth" not in report_path.read_text("utf-8")


def test_native_evidence_and_new_artifacts_are_bound_to_this_session(tmp_path):
    database = tmp_path / "evidence.sqlite3"
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE dataset_registry(id TEXT);
            CREATE TABLE annotation_version(id TEXT,cube_id TEXT,version_no INTEGER);
            CREATE TABLE preprocess_run(id TEXT,cube_id TEXT,annotation_version_id TEXT,status TEXT);
            CREATE TABLE llm_call(session_id TEXT,tool_names TEXT);
            CREATE TABLE agent_session(id TEXT,context_json TEXT);
            CREATE TABLE agent_step(session_id TEXT,seq INTEGER,tool TEXT,status TEXT,
                                    tool_call_id TEXT,result_summary TEXT);
            INSERT INTO dataset_registry VALUES ('cube');
            INSERT INTO annotation_version VALUES ('old-version','cube',1);
            INSERT INTO preprocess_run VALUES ('old-run','cube','old-version','succeeded');
            INSERT INTO agent_session VALUES ('session','{}');
            INSERT INTO llm_call VALUES ('other','["annotations.prepare"]');
        """)
    baseline = acceptance.baseline_of(database)
    assert baseline["versions"] == {"cube": 1} and baseline["run_count"] == 1
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO llm_call VALUES (?,?)", ("session", '["annotations.prepare"]'))
        db.execute("INSERT INTO agent_step VALUES (?,?,?,?,?,?)", ("session", 1, "annotations.prepare", "rejected", "bad", '{}'))
        db.execute("INSERT INTO annotation_version VALUES ('unrelated','cube',2)")
        db.execute("INSERT INTO preprocess_run VALUES ('unrelated-run','cube','unrelated','succeeded')")
        db.execute("INSERT INTO agent_step VALUES (?,?,?,?,?,?)", ("session", 2, "preprocess.run_get", "ok", "read-only",
                   '{"run_id":"unrelated-run","status":"succeeded"}'))
    offered_only = acceptance.session_evidence(database, "session", baseline)
    assert offered_only["catalogue_offered"] == ["annotations.prepare"]
    assert [row["tool"] for row in offered_only["native_tool_sequence"]] == ["preprocess.run_get"]
    assert offered_only["new_annotation_versions"] == offered_only["new_runs"] == []
    with sqlite3.connect(database) as db:
        for seq, tool, summary in [(3, "annotations.draft_confirm", {"version_id": "own-version"}),
                                   (4, "preprocess.run_default", {"run_id": "own-run", "status": "succeeded"})]:
            db.execute("INSERT INTO agent_step VALUES (?,?,?,?,?,?)", ("session", seq, tool, "ok", str(seq), json.dumps(summary)))
        db.execute("INSERT INTO annotation_version VALUES ('own-version','cube',3)")
        db.execute("INSERT INTO preprocess_run VALUES ('own-run','cube','own-version','failed')")
    assert acceptance.session_evidence(database, "session", baseline)["paired_succeeded_runs"] == []
    with sqlite3.connect(database) as db:
        db.execute("UPDATE preprocess_run SET status='succeeded' WHERE id='own-run'")
    evidence = acceptance.session_evidence(database, "session", baseline)
    assert [row["id"] for row in evidence["new_annotation_versions"]] == ["own-version"]
    assert [row["id"] for row in evidence["paired_succeeded_runs"]] == ["own-run"]
