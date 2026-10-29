"""Script acceptance against synthetic HTTP frames and a real isolated ledger."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("e2e_task10_seeds", ROOT / "scripts/e2e_task10.py")
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)
BASELINE = Path(__file__).parents[1] / "fixtures" / "e2e_task10_single_seed.json"


class Engine:
    def __init__(self, root, statuses):
        self.database = root / "db" / "spectrum-agent.sqlite3"
        self.database.parent.mkdir(parents=True)
        (root / "run").mkdir()
        (root / "run" / "handshake.json").write_text(
            json.dumps({"port": 1234, "token": "synthetic-auth"}), encoding="utf-8")
        with sqlite3.connect(self.database) as db:
            db.executescript("""
                CREATE TABLE dataset_registry(id TEXT);
                CREATE TABLE annotation_version(id TEXT,cube_id TEXT,version_no INTEGER);
                CREATE TABLE preprocess_run(id TEXT,cube_id TEXT,annotation_version_id TEXT,status TEXT);
                CREATE TABLE llm_call(session_id TEXT,tool_names TEXT);
                CREATE TABLE agent_session(id TEXT,context_json TEXT);
                CREATE TABLE agent_step(session_id TEXT,seq INTEGER,tool TEXT,status TEXT,
                                        tool_call_id TEXT,result_summary TEXT);
                INSERT INTO dataset_registry VALUES ('cube');
                INSERT INTO annotation_version VALUES ('old','cube',1);
            """)
        self.statuses, self.requests, self.events = list(statuses), [], []
        self.messages = self.gestures = self.proposals = self.seq = 0
        self.preview = self.saved = False

    def step(self, tool, summary, status="ok"):
        self.seq += 1
        with sqlite3.connect(self.database) as db:
            db.execute("INSERT INTO agent_step VALUES (?,?,?,?,?,?)",
                       ("session", self.seq, tool, status, str(self.seq), json.dumps(summary)))
        return ("step", {"seq": self.seq, "tool": tool, "status": status, "result_summary": summary})

    def send(self):
        self.messages += 1
        with sqlite3.connect(self.database) as db:
            db.execute("INSERT INTO llm_call VALUES (?,?)", ("session", '["annotations.propose"]'))
        if self.messages == 1:
            return [("workspace", {"cube_id": "cube"}),
                    ("done", {"content": "请继续", "task_result": "working"})]
        if self.preview:
            if self.saved:
                return [("done", {"task_result": "succeeded"})]
            self.saved = True
            with sqlite3.connect(self.database) as db:
                db.execute("INSERT INTO annotation_version VALUES ('new','cube',2)")
                db.execute("INSERT INTO preprocess_run VALUES ('run','cube','new','succeeded')")
                db.execute("UPDATE agent_session SET context_json=?",
                           (json.dumps({"annotation_version_id": "new", "last_run_id": "run"}),))
            return [self.step("annotations.draft_confirm", {"version_id": "new"}),
                    self.step("preprocess.run_default", {"run_id": "run", "status": "succeeded"}),
                    ("done", {"task_result": "succeeded"})]
        status = self.statuses[min(self.proposals, len(self.statuses) - 1)]
        self.proposals += 1
        if status == "transport_error":
            raise OSError("private-provider-body")
        if status == "sse_error":
            return [("error", {"code": "TEST_ERROR", "task_result": "failed"})]
        if status is None:
            return [("done", {"task_result": "needs_input"})]
        if status == "propose_error":
            return [self.step("annotations.propose", {"status": "need_seed"}, "error"),
                    ("done", {"task_result": "failed"})]
        self.preview = status == "preview"
        return [self.step("annotations.propose", {"status": status}),
                ("done", {"task_result": "needs_review" if self.preview else "needs_input"})]

    def urlopen(self, request, **kwargs):
        path = urlsplit(request.full_url).path
        body = json.loads(request.data) if request.data is not None else None
        self.requests.append({"method": request.get_method(), "path": path, "body": body})
        if path == "/api/v1/agent/runtime":
            result = {"skill_name": "conversation-workflows-v2"}
        elif path == "/api/v1/settings/llm":
            result = {"has_key": True}
        elif path == "/api/v1/agent/sessions":
            with sqlite3.connect(self.database) as db:
                db.execute("INSERT INTO agent_session VALUES ('session','{}')")
            result = {"id": "session"}
        elif path == "/api/v1/datasets/cube":
            result = {"dataset": {"shape": [200, 500, 20]}}
        elif path == "/api/v1/annotations/cube/gestures":
            assert request.get_method() == "POST" and set(body) == {"seed"}
            self.gestures += 1
            result = {"gesture_ref": f"g-{self.gestures}"}
        elif path == "/api/v1/agent/sessions/session/messages":
            frames = self.send()
            self.events.extend(deepcopy(frames))
            return io.BytesIO("".join(f"event: {name}\ndata: {json.dumps(data)}\n\n"
                                     for name, data in frames).encode())
        else:
            raise AssertionError(path)
        return io.BytesIO(json.dumps(result).encode())


def run_script(module, root, monkeypatch, statuses, arguments):
    engine = Engine(root, statuses)
    report_path = root / "report.json"
    with monkeypatch.context() as patch:
        patch.setattr(module, "REPORT_PATH", report_path)
        patch.setattr(module.urllib.request, "urlopen", engine.urlopen)
        output = io.StringIO()
        with redirect_stdout(output):
            code = module.main(["--data-root", str(root), *arguments])
    return {"exit_code": code, "requests": engine.requests,
            "events": json.loads(json.dumps(engine.events)),
            "stdout": output.getvalue().replace(str(report_path), "<REPORT>"),
            "report": json.loads(report_path.read_text("utf-8"))}


@pytest.mark.parametrize("case", json.loads(BASELINE.read_text("utf-8")), ids=lambda case: case["name"])
def test_single_seed_matches_6194250_event_for_event(tmp_path, monkeypatch, case):
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch, case["statuses"], case["arguments"])
    report = actual["report"]
    assert report.pop("seeds_tried") == [[115, 320]]
    expected_used = [115, 320] if case["name"].startswith("preview") and case["name"] != "preview-one-turn" else None
    assert report.pop("seed_used") == expected_used
    assert actual == case["expected"]
    print("B1", case["name"], json.dumps(actual, ensure_ascii=False))


def seed_arguments(count=3):
    return [item for i in range(count) for item in ("--seed", f"{10 + i},{20 + i}")]


@pytest.mark.parametrize("retry", [None, "重新指认，请生成候选"])
def test_need_seed_retries_only_remaining_seeds_then_accepts_in_original_turn(tmp_path, monkeypatch, retry):
    arguments = seed_arguments(4) + ["--accept-message", "确认保存并预处理"]
    if retry:
        arguments += ["--retry-message", retry]
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch,
                        ["need_seed", "need_seed", "preview"], arguments)
    report = actual["report"]
    assert actual["exit_code"] == 0
    assert report["seeds_tried"] == [[10, 20], [11, 21], [12, 22]]
    assert report["seed_used"] == [12, 22] and report["turns_sent"] == 5
    messages = [request["body"] for request in actual["requests"] if request["path"].endswith("/messages")]
    assert [message["content"] for message in messages] == [
        acceptance.DEFAULT_MESSAGE, "继续", retry or "换了个位置，再试一次",
        retry or "换了个位置，再试一次", "确认保存并预处理"]
    assert [message["workspace"]["gesture_ref"] for message in messages[1:]] == ["g-1", "g-2", "g-3", "g-3"]
    gestures = [request for request in actual["requests"] if request["path"].endswith("/gestures")]
    assert [request["body"]["seed"]["point"] for request in gestures] == report["seeds_tried"]
    assert report["evidence_levels"]["L4"]["passed"] is True
    print("B3", json.dumps(actual, ensure_ascii=False))


def test_first_seed_preview_does_not_consume_unused_seeds(tmp_path, monkeypatch):
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch, ["preview"], seed_arguments())
    assert actual["exit_code"] == 0
    assert actual["report"]["seeds_tried"] == [[10, 20]]
    assert actual["report"]["seed_used"] == [10, 20]
    assert actual["report"]["turns_sent"] == 3


def test_all_need_seed_reports_l4_failure_and_no_used_seed(tmp_path, monkeypatch):
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch, ["need_seed"], seed_arguments())
    report = actual["report"]
    assert actual["exit_code"] == 1
    assert report["seeds_tried"] == [[10, 20], [11, 21], [12, 22]]
    assert report["seed_used"] is None
    assert report["new_annotation_versions"] == report["paired_succeeded_runs"] == []
    assert report["stop_reason"].startswith("FAIL at L4")
    print("B4", json.dumps(report, ensure_ascii=False))


@pytest.mark.parametrize("status", [None, "not_ready", "propose_error", "sse_error", "transport_error"])
def test_other_results_never_trigger_seed_retry(tmp_path, monkeypatch, status):
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch, [status], seed_arguments())
    assert actual["report"]["seeds_tried"] == [[10, 20]]
    assert actual["report"]["seed_used"] is None
    assert "private-provider-body" not in actual["stdout"]


def test_missing_proposal_does_not_reuse_earlier_need_seed(tmp_path, monkeypatch):
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch,
                        ["need_seed", None, "preview"], seed_arguments())
    assert actual["report"]["seeds_tried"] == [[10, 20], [11, 21]]
    assert actual["report"]["seed_used"] == [11, 21]
    assert actual["report"]["turns_sent"] == 4
    assert actual["exit_code"] == 1  # Preview alone is not a saved/preprocessed result.


def test_retry_does_not_add_an_accept_turn_beyond_explicit_turns(tmp_path, monkeypatch):
    actual = run_script(acceptance, tmp_path / "engine", monkeypatch,
                        ["need_seed", "preview"], seed_arguments() + ["--turns", "2"])
    assert actual["report"]["turns_sent"] == 3
    assert actual["report"]["seed_used"] == [11, 21]
    assert actual["exit_code"] == 1
    assert not actual["report"]["new_annotation_versions"]
