"""TASK-07 R9/R10: linear orchestration and SQLite-authoritative continuations."""
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import sqlite3
from time import perf_counter_ns
from uuid import uuid4

from backend.database import connect_database
from spectrumagent.data import DataError
from .llm import LLMClient, _json
from .skill import _write, active_skill


MAX_TOOL_CALLS = 8  # TASK-07 §10-4, per PARSE response.
RAW_BYTES = 4 * 1024  # TASK-07 §3 rejected-arguments excerpt limit.


class State(str, Enum):
    IDLE = "IDLE"
    PARSE = "PARSE"
    CALL_TOOL = "CALL_TOOL"
    INTERPRET = "INTERPRET"
    DONE = "DONE"
    CLARIFY = "CLARIFY"
    HUMAN_CHECK = "HUMAN_CHECK"
    ERROR = "ERROR"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _failure(code, detail, status=400):
    error = DataError(code, detail)
    error.status_code = status
    return error


def install_guards(db):
    for table, columns in (
        ("agent_session", "id,skill_version_id,created_at"),
        ("agent_round", "id,session_id,seq,user_message,calls_json,created_at"),
        ("agent_step", "id,session_id,round_id,seq,tool,arguments_json,created_at"),
    ):
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable
            BEFORE UPDATE OF {columns} ON {table}
            BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS agent_title_once BEFORE UPDATE OF title ON agent_session
        WHEN NOT (OLD.title='' AND NEW.title IS NOT NULL AND length(NEW.title)>0)
        BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS agent_round_transition BEFORE UPDATE OF status ON agent_round
        WHEN NOT ((OLD.status='running' AND NEW.status IN ('human_check','done','error'))
               OR (OLD.status='human_check' AND NEW.status IN ('running','done','error')))
        BEGIN SELECT RAISE(ABORT,'AGENT_TRANSITION_INVALID'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS agent_step_transition
        BEFORE UPDATE OF status,result_digest,result_summary,latency_ms ON agent_step
        WHEN NOT (OLD.status='human_check_pending' AND NEW.status IN ('ok','rejected','error'))
        BEGIN SELECT RAISE(ABORT,'AGENT_TRANSITION_INVALID'); END""")


def _rows(db, sql, args=()):
    cursor = db.execute(sql, args)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor]


class AgentStore:
    def __init__(self, database):
        self.database = database

    def session(self, identifier):
        with connect_database(self.database) as db:
            rows = _rows(db, "SELECT * FROM agent_session WHERE id=?", (identifier,))
        if not rows:
            raise _failure("SESSION_NOT_FOUND", "会话不存在", 404)
        return rows[0]

    def create_session(self):
        with connect_database(self.database) as db, _write(db):
            try:
                version = active_skill(db)
            except DataError as error:
                error.status_code = 409
                raise
            identifier, timestamp = str(uuid4()), _now()
            db.execute("INSERT INTO agent_session (id,title,skill_version_id,created_at,updated_at) VALUES (?,?,?,?,?)",
                       (identifier, "", version["id"], timestamp, timestamp))
        return {"id": identifier, "title": "", "skill_version_id": version["id"], "created_at": timestamp}

    def skill(self, session_id):
        session = self.session(session_id)
        with connect_database(self.database) as db:
            return _rows(db, "SELECT * FROM skill_version WHERE id=?", (session["skill_version_id"],))[0]

    def steps(self, session_id, round_id=None):
        self.session(session_id)
        with connect_database(self.database) as db:
            if round_id is not None:
                return _rows(db, "SELECT * FROM agent_step WHERE session_id=? AND round_id=? ORDER BY seq", (session_id, round_id))
            return _rows(db, "SELECT * FROM agent_step WHERE session_id=? ORDER BY seq", (session_id,))

    def preflight(self, session_id, check_id=None):
        self.session(session_id)
        with connect_database(self.database) as db:
            rounds = _rows(db, "SELECT * FROM agent_round WHERE session_id=? AND status IN ('running','human_check') ORDER BY seq", (session_id,))
            if check_id is None:
                if rounds:
                    raise _failure("INVALID_REQUEST", "本轮尚未结束，只接受待确认应答")
                return None
            pending = _rows(db, "SELECT * FROM agent_step WHERE id=? AND session_id=? AND status='human_check_pending'", (check_id, session_id))
        if not pending or not rounds or rounds[0]["id"] != pending[0]["round_id"] or rounds[0]["status"] != "human_check":
            raise _failure("INVALID_REQUEST", "确认引用不存在或已处理")
        return rounds[0], pending[0]

    def new_round(self, session_id, content, calls, status="running"):
        with connect_database(self.database) as db, _write(db):
            if db.execute("SELECT 1 FROM agent_round WHERE session_id=? AND status IN ('running','human_check')", (session_id,)).fetchone():
                raise _failure("INVALID_REQUEST", "本轮尚未结束")
            identifier, timestamp = str(uuid4()), _now()
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM agent_round WHERE session_id=?", (session_id,)).fetchone()[0]
            db.execute("INSERT INTO agent_round (id,session_id,seq,user_message,calls_json,status,created_at) VALUES (?,?,?,?,?,?,?)",
                       (identifier, session_id, seq, content, _json(calls), status, timestamp))
            if content and db.execute("SELECT title FROM agent_session WHERE id=?", (session_id,)).fetchone()[0] == "":
                db.execute("UPDATE agent_session SET title=? WHERE id=?", (content[:40], session_id))
            db.execute("UPDATE agent_session SET updated_at=? WHERE id=?", (timestamp, session_id))
            return _rows(db, "SELECT * FROM agent_round WHERE id=?", (identifier,))[0]

    def round_status(self, round_id, status):
        with connect_database(self.database) as db, _write(db):
            db.execute("UPDATE agent_round SET status=? WHERE id=?", (status, round_id))
            db.execute("UPDATE agent_session SET updated_at=? WHERE id=(SELECT session_id FROM agent_round WHERE id=?)", (_now(), round_id))

    def claim(self, round_id):
        with connect_database(self.database) as db, _write(db):
            row = db.execute("UPDATE agent_round SET status='running' WHERE id=? AND status='human_check'", (round_id,))
            if row.rowcount != 1:
                raise _failure("INVALID_REQUEST", "确认已处理")

    def cancel_running(self, round_id):
        with connect_database(self.database) as db, _write(db):
            row = db.execute("UPDATE agent_round SET status='error' WHERE id=? AND status='running'", (round_id,))
            if row.rowcount:
                db.execute("UPDATE agent_session SET updated_at=? WHERE id=(SELECT session_id FROM agent_round WHERE id=?)", (_now(), round_id))

    def add_step(self, round_, tool, arguments, status, summary, latency):
        with connect_database(self.database) as db, _write(db):
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM agent_step WHERE session_id=?", (round_["session_id"],)).fetchone()[0]
            identifier = str(uuid4())
            text = _json(summary)
            digest = None if status == "rejected" else sha256(text.encode("utf-8")).hexdigest()
            db.execute("INSERT INTO agent_step (id,session_id,round_id,seq,tool,arguments_json,result_digest,result_summary,status,latency_ms,created_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (identifier, round_["session_id"], round_["id"], seq, tool,
                        _json(arguments), digest, text, status, latency, _now()))
            if status == "human_check_pending":
                db.execute("UPDATE agent_round SET status='human_check' WHERE id=?", (round_["id"],))
                db.execute("UPDATE agent_session SET updated_at=? WHERE id=?", (_now(), round_["session_id"]))
            return _rows(db, "SELECT * FROM agent_step WHERE id=?", (identifier,))[0]

    def finish_step(self, step, status, summary, latency):
        text = _json(summary)
        digest = None if status == "rejected" else sha256(text.encode("utf-8")).hexdigest()
        with connect_database(self.database) as db, _write(db):
            row = db.execute("UPDATE agent_step SET status=?,result_summary=?,result_digest=?,latency_ms=? WHERE id=? AND status='human_check_pending'",
                             (status, text, digest, latency, step["id"]))
            if row.rowcount != 1:
                raise _failure("INVALID_REQUEST", "确认已处理")
            if status == "rejected":
                db.execute("UPDATE agent_round SET status='done' WHERE id=?", (step["round_id"],))
                db.execute("UPDATE agent_session SET updated_at=? WHERE id=?", (_now(), step["session_id"]))
            return _rows(db, "SELECT * FROM agent_step WHERE id=?", (step["id"],))[0]


class StateMachine:
    def __init__(self, store: AgentStore, session_id: str, llm: LLMClient, tools):
        self.store, self.session_id, self.llm, self.tools = store, session_id, llm, tools
        self.state = State.IDLE  # Request-local execution phase, never a recovery source.

    def message(self, *, content=None, check_id=None, decision=None):
        if content is not None and check_id is None and decision is None:
            self.store.preflight(self.session_id)
            return self._generate(content=content)
        if content is None and check_id is not None and decision in {"approve", "reject"}:
            continuation = self.store.preflight(self.session_id, check_id)
            return self._generate(continuation=continuation, decision=decision)
        raise _failure("INVALID_REQUEST", "消息形态不合法")

    @staticmethod
    def _step_event(step):
        return "step", {"seq": step["seq"], "tool": step["tool"], "status": step["status"], "result_summary": json.loads(step["result_summary"])}

    def _execute(self, round_, call, pending=None):
        started = perf_counter_ns()
        try:
            summary = self.tools.invoke(call["name"], call["arguments"])
            status, error = "ok", None
        except Exception as exc:
            error = exc if isinstance(exc, DataError) else DataError("TOOL_FAILED", "工具执行失败")
            status, summary = "error", {"error": error.code}
        elapsed = (perf_counter_ns() - started) // 1_000_000
        if pending is None:
            step = self.store.add_step(round_, call["name"], call["arguments"], status, summary, elapsed)
        else:
            step = self.store.finish_step(pending, status, summary, elapsed)
        return step, error

    def _generate(self, *, content=None, continuation=None, decision=None):
        round_ = None
        round_creation_attempted = False
        try:
            version = self.store.skill(self.session_id)
            if continuation is None:
                self.state = State.PARSE
                parsed = self.llm.chat([{"role": "system", "content": version["system_prompt"]}, {"role": "user", "content": content}],
                                       json.loads(version["tools_json"]))
                calls, rejected = [], []
                for index, call in enumerate(parsed.tool_calls):
                    started = perf_counter_ns()
                    try:
                        if index >= MAX_TOOL_CALLS:
                            raise DataError("TOOL_SEQUENCE_LIMIT", "工具序列超限")
                        arguments = self.tools.validate(call.name, call.arguments_json)
                        calls.append({"id": call.id, "name": call.name, "arguments": arguments.model_dump(mode="json")})
                    except DataError as exc:
                        raw = call.arguments_json.encode("utf-8")
                        rejected.append((call.name, {"_raw_sha256": sha256(raw).hexdigest(),
                            "_raw_truncated": raw[:RAW_BYTES].decode("utf-8", errors="ignore")}, exc.code,
                            (perf_counter_ns() - started) // 1_000_000))
                round_creation_attempted = True
                round_ = self.store.new_round(self.session_id, content, calls, "running" if parsed.tool_calls else "done")
                if not parsed.tool_calls:
                    self.state = State.CLARIFY
                    yield "clarify", {"question": parsed.content or ""}
                    return
                # PARSE rejects are audited immediately. Only validated calls
                # enter the immutable continuation, in their original order.
                for name, arguments, code, elapsed in rejected:
                    step = self.store.add_step(round_, name, arguments, "rejected", {"error": code}, elapsed)
                    yield self._step_event(step)
                offset = 0
            else:
                resume_round, pending = continuation
                self.store.claim(resume_round["id"])
                round_ = resume_round
                calls = json.loads(round_["calls_json"])
                if decision == "reject":
                    step = self.store.finish_step(pending, "rejected", {"error": "HUMAN_REJECTED"}, 0)
                    yield self._step_event(step)
                    self.state = State.DONE
                    yield "done", {"content": "已拒绝、未执行", "step_count": len(self.store.steps(self.session_id, round_["id"]))}
                    return
                executed = [step for step in self.store.steps(self.session_id, round_["id"]) if step["status"] != "rejected"]
                offset = len(executed)
                self.state = State.CALL_TOOL
                step, error = self._execute(round_, calls[offset - 1], pending)
                yield self._step_event(step)
                if error is not None:
                    raise error
            self.state = State.CALL_TOOL
            for call in calls[offset:]:
                tool = self.tools.resolve(call["name"])
                if tool.human_check:
                    summary = {key: value for key, value in call["arguments"].items()
                               if key in {"cube_id", "version_id", "revision", "class_code", "overwrite"} and value is not None}
                    step = self.store.add_step(round_, call["name"], call["arguments"], "human_check_pending", summary, 0)
                    self.state = State.HUMAN_CHECK
                    yield "human_check", {"check_id": step["id"], "tool": call["name"], "summary": summary, "reason": "标注版本确认"}
                    return
                step, error = self._execute(round_, call)
                yield self._step_event(step)
                if error is not None:
                    raise error
            self.state = State.INTERPRET
            steps = self.store.steps(self.session_id, round_["id"])
            messages = [{"role": "system", "content": version["system_prompt"]}, {"role": "user", "content": round_["user_message"]}]
            if calls:
                messages.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": _json(call["arguments"])}} for call in calls]})
                completed = [step for step in steps if step["status"] != "rejected"]
                messages.extend({"role": "tool", "tool_call_id": call["id"], "content": step["result_summary"]}
                                for call, step in zip(calls, completed))
            rejections = [{"tool": step["tool"], **json.loads(step["result_summary"])} for step in steps if step["status"] == "rejected"]
            if rejections:
                messages.append({"role": "system", "content": _json({"rejected": rejections})})
            final = self.llm.chat(messages, None)
            if final.tool_calls:
                raise DataError("LLM_UNEXPECTED_TOOL_CALL", "解读阶段禁止工具调用")
            self.store.round_status(round_["id"], "done")
            self.state = State.DONE
            yield "done", {"content": final.content or "", "step_count": len(steps)}
        except GeneratorExit:
            if round_ is not None:
                # Closing a suspended HUMAN_CHECK stream retains its pending
                # round; an interrupted running round releases the session.
                self.store.cancel_running(round_["id"])
            raise
        except Exception as exc:
            self.state = State.ERROR
            error = exc if isinstance(exc, DataError) else DataError("AGENT_FAILED", "编排执行失败")
            try:
                if round_ is None and content is not None and not round_creation_attempted:
                    self.store.new_round(self.session_id, content, [], "error")
                elif round_ is not None:
                    self.store.round_status(round_["id"], "error")
            except (sqlite3.Error, DataError):
                error = DataError("AGENT_STORAGE", "编排留痕存储失败")
            yield "error", {"code": error.code, "detail": error.payload.detail}
        finally:
            self.state = State.IDLE
