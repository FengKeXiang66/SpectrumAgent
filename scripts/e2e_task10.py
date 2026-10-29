"""Real-provider acceptance with four ordered, independently sourced evidence levels.

Usage: .venv/Scripts/python.exe scripts/e2e_task10.py --data-root <absolute root>
Credentials are configured in the application settings and stay in engine memory.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src-python"))
sys.path.insert(0, str(ROOT))

from spectrumagent.agent.task import evaluate_task


V2_TOOLS = frozenset({
    "datasets.resolve", "annotations.context", "annotations.prepare", "annotations.ensure_labels",
    "annotations.propose", "annotations.apply_candidate", "annotations.reject_candidate",
    "annotations.set_background", "annotations.mark_region", "annotations.edit_region", "annotations.undo",
    "preprocess.recipes", "preprocess.recipe_ensure", "preprocess.run_default", "preprocess.run_get",
})
REPORT_PATH = ROOT / ".runtime" / "e2e_task10_report.json"
DEFAULT_MESSAGE = "对第一个数据标注 PP，其余背景，参数默认，保存后做预处理"


def read_handshake(data_root):
    for _ in range(60):
        path = Path(data_root) / "run" / "handshake.json"
        if path.exists():
            try:
                return json.loads(path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        time.sleep(1)
    raise RuntimeError("no handshake: start the engine first")


def call_api(base, token, path, payload=None, method="GET", timeout=180):
    url = f"{base}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None


def send_message(base, token, session_id, content, workspace=None, timeout=240):
    """Collect and print each SSE frame, including follow-up turns."""
    url = f"{base}/api/v1/agent/sessions/{session_id}/messages"
    body = {"content": content}
    if workspace:
        body["workspace"] = workspace
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    events, event, lines = [], None, []

    def frame():
        if event and lines:
            data = json.loads("\n".join(lines))
            events.append((event, data))
            print("SSE", event, json.dumps(data, ensure_ascii=False), flush=True)

    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8").rstrip("\r\n")
            if not line:
                frame()
                event, lines = None, []
            elif line.startswith("event:"):
                event = line[6:].lstrip()
            elif line.startswith("data:"):
                lines.append(line[5:].lstrip())
        frame()
    return events


def read_db(database, sql, parameters=()):
    """Acceptance only observes the database; it never creates or migrates it."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(sql, parameters)]


def baseline_of(database):
    cubes = read_db(database, "SELECT id FROM dataset_registry ORDER BY rowid")
    versions = {cube["id"]: read_db(database,
        "SELECT COALESCE(MAX(version_no),0) AS n FROM annotation_version WHERE cube_id=?",
        (cube["id"],))[0]["n"] for cube in cubes}
    return {"versions": versions,
            "run_count": read_db(database, "SELECT COUNT(*) AS n FROM preprocess_run")[0]["n"],
            "run_ids": {row["id"] for row in read_db(database, "SELECT id FROM preprocess_run")}}


def session_evidence(database, session_id, baseline):
    """Separate offered names, native executed calls, and this session's new outputs."""
    audits = read_db(database, "SELECT tool_names FROM llm_call WHERE session_id=? ORDER BY rowid", (session_id,))
    offered = sorted({name for row in audits for name in json.loads(row["tool_names"] or "[]")})
    steps = read_db(database, "SELECT * FROM agent_step WHERE session_id=? ORDER BY seq", (session_id,))
    executed = [row for row in steps if row["status"] in {"ok", "error"} and row["tool_call_id"]]
    summaries = [(row, json.loads(row["result_summary"] or "{}")) for row in executed]
    saved_ids = {data["version_id"] for row, data in summaries
                 if row["status"] == "ok" and row["tool"] == "annotations.draft_confirm" and data.get("version_id")}
    run_ids = set()
    for row, data in summaries:
        if row["status"] != "ok":
            continue
        if row["tool"] in {"preprocess.run", "preprocess.run_default"} and data.get("run_id"):
            run_ids.add(data["run_id"])
        elif row["tool"] == "preprocess.compare":
            run_ids.update(value for key, value in data.items() if re.fullmatch(r"run_\d+_run_id", key))
    versions = [row for row in read_db(database, "SELECT id,cube_id,version_no FROM annotation_version")
                if row["id"] in saved_ids and row["version_no"] > baseline["versions"].get(row["cube_id"], 0)]
    versions_by_id = {row["id"]: row for row in versions}
    runs = [row for row in read_db(database,
            "SELECT id,cube_id,annotation_version_id,status FROM preprocess_run")
            if row["id"] in run_ids - baseline["run_ids"]]
    paired = [row for row in runs if row["status"] == "succeeded"
              and row["annotation_version_id"] in versions_by_id
              and row["cube_id"] == versions_by_id[row["annotation_version_id"]]["cube_id"]]
    state = json.loads(read_db(database, "SELECT context_json FROM agent_session WHERE id=?", (session_id,))[0]["context_json"] or "{}")
    last_status = summaries[-1][1].get("status") if summaries else None
    last_run = read_db(database, "SELECT status FROM preprocess_run WHERE id=?", (state.get("last_run_id"),))
    return {"catalogue_offered": offered,
            "native_tool_sequence": [{"seq": row["seq"], "tool": row["tool"], "status": row["status"]} for row in executed],
            "new_annotation_versions": versions, "new_runs": runs, "paired_succeeded_runs": paired,
            "run_count_before": baseline["run_count"],
            "run_count_after": read_db(database, "SELECT COUNT(*) AS n FROM preprocess_run")[0]["n"],
            "task_result": evaluate_task(state, {"last_status": last_status,
                "run_status": last_run[0]["status"] if last_run else None})}


def parse_seed(value):
    if not re.fullmatch(r"\s*[+-]?\d+\s*,\s*[+-]?\d+\s*", value):
        raise argparse.ArgumentTypeError("seed must be row,col with two non-negative integers")
    row, col = (int(part.strip()) for part in value.split(","))
    if row < 0 or col < 0:
        raise argparse.ArgumentTypeError("seed must be row,col with two non-negative integers")
    return [row, col]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--follow-up", default="继续")
    parser.add_argument("--seed", type=parse_seed, action="append")
    parser.add_argument("--retry-message", default="换了个位置，再试一次")
    parser.add_argument("--accept-message", default="接受候选，其余背景，保存后做预处理")
    parser.add_argument("--turns", type=int)
    args = parser.parse_args(argv)
    if args.turns is None:
        args.turns = 3 if args.seed is not None else 2
    if args.turns < 1:
        parser.error("--turns must be >= 1")
    report = {"evidence_levels": {}, "task_result": "working", "stop_reason": None, "session_id": None,
              "seed": args.seed[0] if args.seed else None, "gesture_ref": None, "turns_sent": 0,
              "seeds_tried": [], "seed_used": None}

    def finish(level=None, reason=None):
        if level:
            report["evidence_levels"][level] = {"passed": False, "reason": reason}
            report["stop_reason"] = f"FAIL at {level}: {reason}"
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report["stop_reason"] or "PASS", flush=True)
        print("REPORT:", REPORT_PATH, flush=True)
        return 1 if level else 0

    def passed(level):
        report["evidence_levels"][level] = {"passed": True}
        print(level, "PASS", flush=True)

    current_level = "L1"
    try:
        handshake = read_handshake(args.data_root.resolve())
        base, token = f"http://127.0.0.1:{handshake['port']}", handshake["token"]
        runtime_url = f"{base}/api/v1/agent/runtime"
        print("RUNTIME_URL:", runtime_url, flush=True)
        try:
            runtime = call_api(base, token, "/api/v1/agent/runtime")
        except (OSError, ValueError) as exc:
            return finish("L1", f"runtime request failed: {runtime_url} ({type(exc).__name__})")
        print("RUNTIME:", json.dumps(runtime, ensure_ascii=False), flush=True)
        report["runtime"] = runtime
        settings = call_api(base, token, "/api/v1/settings/llm")
        if not settings.get("has_key"):
            return finish("L1", "has_key=false; configure credentials in application settings")
        passed("L1")
        current_level = "L2"
        session = call_api(base, token, "/api/v1/agent/sessions", {}, method="POST")
        report["session_id"] = session["id"]
        database = args.data_root.resolve() / "db" / "spectrum-agent.sqlite3"
        baseline = baseline_of(database)
        events, transport_error, workspace = [], None, None
        preview_seen = False

        def use_seed(seed, cube_id, shape):
            if seed[0] >= shape[0] or seed[1] >= shape[1]:
                parser.error(f"--seed is outside cube bounds: rows [0,{shape[0]}), cols [0,{shape[1]})")
            gesture = call_api(base, token, f"/api/v1/annotations/{cube_id}/gestures",
                               {"seed": {"point": seed}}, method="POST")
            report["gesture_ref"] = gesture["gesture_ref"]
            report["seeds_tried"].append(seed)
            current_workspace = {"cube_id": cube_id, "gesture_ref": report["gesture_ref"]}
            print("SEED:", json.dumps({"seed": seed, **current_workspace}, ensure_ascii=False), flush=True)
            return current_workspace

        def proposal_status(round_events):
            nonlocal preview_seen
            status = None
            for name, data in round_events:
                if name == "step" and data.get("tool") == "annotations.propose" and data.get("status") == "ok":
                    status = data.get("result_summary", {}).get("status")
                    if status == "preview" and not preview_seen:
                        preview_seen = True
                        report["seed_used"] = report["seeds_tried"][-1] if report["seeds_tried"] else None
            return status

        for turn in range(args.turns):
            print("TURN", report["turns_sent"] + 1, flush=True)
            try:
                content = (args.message if turn == 0 else args.accept_message
                           if args.seed is not None and turn == 2 else args.follow_up)
                report["turns_sent"] += 1
                if workspace:
                    round_events = send_message(base, token, session["id"], content, workspace=workspace)
                else:
                    round_events = send_message(base, token, session["id"], content)
                events.extend(round_events)
            except (OSError, ValueError) as exc:
                transport_error = type(exc).__name__
                break
            if events and events[-1][0] == "error":
                break
            status = proposal_status(round_events)
            if turn == 0 and args.seed is not None:
                first_workspace = next((data for name, data in reversed(events) if name == "workspace"), None)
                if not first_workspace or not first_workspace.get("cube_id"):
                    return finish(current_level, "cannot register seed: first turn has no workspace cube_id")
                cube_id = first_workspace["cube_id"]
                shape = call_api(base, token, f"/api/v1/datasets/{cube_id}")["dataset"]["shape"]
                workspace = use_seed(args.seed[0], cube_id, shape)
                continue
            # Retry messages are extra attempts, not replacements for normal
            # turns (including the original third-turn accept message).
            while (args.seed and not preview_seen and status == "need_seed"
                   and len(report["seeds_tried"]) < len(args.seed)
                   and not any(name == "error" for name, _ in round_events)):
                workspace = use_seed(args.seed[len(report["seeds_tried"])], cube_id, shape)
                print("TURN", report["turns_sent"] + 1, flush=True)
                try:
                    report["turns_sent"] += 1
                    round_events = send_message(base, token, session["id"], args.retry_message, workspace=workspace)
                    events.extend(round_events)
                except (OSError, ValueError) as exc:
                    transport_error = type(exc).__name__
                    break
                status = proposal_status(round_events)
            if transport_error or events and events[-1][0] == "error":
                break
        report["event_kinds"] = [name for name, _ in events]
        evidence = session_evidence(database, session["id"], baseline)
        report.update(evidence)
        for name, data in reversed(events):
            if name in {"done", "clarify", "error"} and data.get("task_result"):
                report["task_result"] = data["task_result"]
                break
        # Evaluate levels in order; a catalogue is never counted as an execution.
        if not V2_TOOLS.intersection(evidence["catalogue_offered"]):
            return finish("L2", "no v2 catalogue offered" + (f"; stream failed ({transport_error})" if transport_error else ""))
        passed("L2")
        current_level = "L3"
        sequence = evidence["native_tool_sequence"]
        print("NATIVE_TOOL_SEQUENCE:", json.dumps(sequence, ensure_ascii=False), flush=True)
        if not any(row["tool"] in V2_TOOLS for row in sequence):
            return finish("L3", "模型未选择 v2 工具; native_tool_sequence=" + json.dumps(sequence, ensure_ascii=False))
        passed("L3")
        current_level = "L4"
        if not evidence["new_annotation_versions"] or not evidence["paired_succeeded_runs"]:
            reason = "no new saved annotation paired with a new succeeded preprocessing run"
            if transport_error:
                reason += f"; stream failed ({transport_error})"
            errors = [data.get("code") for name, data in events if name == "error"]
            if errors:
                reason += "; SSE errors=" + json.dumps(errors)
            return finish("L4", reason)
        if transport_error or any(name == "error" for name, _ in events):
            return finish("L4", "stream failed after producing artifacts")
        passed("L4")
        return finish()
    except (OSError, ValueError, KeyError, sqlite3.Error, RuntimeError) as exc:
        # Do not print exception bodies: HTTP/provider errors can contain secrets.
        return finish(current_level, f"evidence collection failed ({type(exc).__name__})")


if __name__ == "__main__":
    raise SystemExit(main())
