"""TASK-07 R9/R10: linear orchestration and SQLite-authoritative continuations."""
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re
import sqlite3
from time import perf_counter_ns
from uuid import uuid4

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.data.validation import safe_error, PARAMETER_ERRORS, INPUT_ERRORS, parameter_answer
from .llm import LLMClient, _json
from .skill import _write, active_skill
from . import context as memory
from .execution import RequestCancelled, numerical_confirmation
from .open_access import MAX_TOOL_CALLS, MAX_WORKFLOW_BATCHES, MAX_WORKFLOW_STEPS


RAW_BYTES = 4 * 1024  # TASK-07 §3 rejected-arguments excerpt limit.

# TASK-07b R3: session-level opt-in to skip all confirmation gates.
_AUTO_CONFIRM_ON = ("自动执行", "自动帮我执行", "无需确认", "不用确认", "跳过确认")
_AUTO_CONFIRM_OFF = ("恢复确认", "需要确认", "不要自动", "停止自动", "取消自动")


def _auto_confirm_directive(content):
    """Return 1 to enable, 0 to disable, or None if the message is not a directive."""
    if not content:
        return None
    for phrase in _AUTO_CONFIRM_OFF:
        if phrase in content:
            return 0
    for phrase in _AUTO_CONFIRM_ON:
        if phrase in content:
            return 1
    return None


class State(str, Enum):
    IDLE = "IDLE"
    PARSE = "PARSE"
    CALL_TOOL = "CALL_TOOL"
    INTERPRET = "INTERPRET"
    DONE = "DONE"
    CLARIFY = "CLARIFY"
    HUMAN_CHECK = "HUMAN_CHECK"
    PLAN_CHECK = "PLAN_CHECK"
    ERROR = "ERROR"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _failure(code, detail, status=400):
    error = DataError(code, detail)
    error.status_code = status
    return error


def install_guards(db):
    for table, columns in (
        ("agent_session", "id,created_at"),
        ("agent_round", "id,session_id,seq,user_message,calls_json,created_at,turn_id"),
        ("agent_step", "id,session_id,round_id,seq,tool,arguments_json,created_at,tool_call_id"),
        ("agent_plan_action", "id,session_id,round_id,action,seq_ref,reason,created_at"),
    ):
        db.execute(f"DROP TRIGGER IF EXISTS {table}_immutable")
        db.execute(f"""CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OF {columns} ON {table}
            BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    # skill_version_id moves only through the sanctioned built-in v1 -> v2 upgrade.
    # It is guarded separately: the update is allowed only while the upgrade guard row
    # exists and only toward the active built-in skill. Every other attempt aborts.
    db.execute("""CREATE TABLE IF NOT EXISTS skill_upgrade_guard (
        id INTEGER PRIMARY KEY CHECK (id = 1))""")
    db.execute("DROP TRIGGER IF EXISTS agent_session_skill_upgrade")
    db.execute("""CREATE TRIGGER agent_session_skill_upgrade
        BEFORE UPDATE OF skill_version_id ON agent_session
        WHEN NOT EXISTS (SELECT 1 FROM skill_upgrade_guard)
          OR NEW.skill_version_id NOT IN (SELECT id FROM skill_version WHERE status='active')
        BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS skill_upgrade_guard_once
        BEFORE INSERT ON skill_upgrade_guard
        WHEN (SELECT COUNT(*) FROM skill_upgrade_guard) >= 1
        BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS agent_title_once BEFORE UPDATE OF title ON agent_session
        WHEN NOT (OLD.title='' AND NEW.title IS NOT NULL AND length(NEW.title)>0)
        BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS agent_step_transition
        BEFORE UPDATE OF status,result_digest,result_summary,latency_ms ON agent_step
        WHEN NOT (OLD.status='human_check_pending' AND NEW.status IN ('ok','rejected','error'))
        BEGIN SELECT RAISE(ABORT,'AGENT_TRANSITION_INVALID'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS agent_answer_once
        BEFORE UPDATE OF assistant_content ON agent_round
        WHEN OLD.assistant_content IS NOT NULL OR NEW.assistant_content IS NULL
        BEGIN SELECT RAISE(ABORT,'AGENT_IMMUTABLE'); END""")
    db.execute("DROP TRIGGER IF EXISTS agent_round_transition")
    db.execute("""CREATE TRIGGER agent_round_transition BEFORE UPDATE OF status ON agent_round
        WHEN NOT ((OLD.status='running' AND NEW.status IN ('human_check','done','error'))
               OR (OLD.status='human_check' AND NEW.status IN ('running','done','error'))
               OR (OLD.status='plan_check' AND NEW.status IN ('running','done','error')))
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
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_session_scope'").fetchone():
                db.execute("INSERT INTO agent_session_scope(session_id,scope_kind,member_count) VALUES (?,'global',0)", (identifier,))
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

    def rounds(self, session_id, *, exclude_round_id=None, limit=None, include_incomplete=False):
        """Latest completed user turns, including all their dependent batches."""
        self.session(session_id)
        with connect_database(self.database) as db:
            status_filter = "" if include_incomplete else " AND status='done'"
            sql = "SELECT * FROM agent_round WHERE session_id=?" + status_filter
            args = [session_id]
            if exclude_round_id is not None:
                sql += " AND id<>?"
                args.append(exclude_round_id)
            if limit is not None:
                sql += " AND COALESCE(turn_id,id) IN (SELECT COALESCE(turn_id,id) FROM agent_round WHERE session_id=?" + status_filter + " GROUP BY COALESCE(turn_id,id) ORDER BY MAX(seq) DESC LIMIT ?)"
                args.extend((session_id, max(0, int(limit))))
            return _rows(db, sql + " ORDER BY seq", args)

    def context(self, session_id):
        return json.loads(self.session(session_id)["context_json"])

    def save_context(self, session_id, context):
        value = _json(context)
        if len(value.encode("utf-8")) > 65536:
            raise _failure("AGENT_CONTEXT_LIMIT", "任务上下文过大，请缩小数据范围")
        with connect_database(self.database) as db, _write(db):
            db.execute("UPDATE agent_session SET context_json=? WHERE id=?", (value, session_id))

    def save_answer(self, round_id, content):
        with connect_database(self.database) as db, _write(db):
            db.execute("UPDATE agent_round SET assistant_content=? WHERE id=? AND assistant_content IS NULL", (content, round_id))

    def turn_rounds(self, session_id, turn_id):
        with connect_database(self.database) as db:
            return _rows(db, "SELECT * FROM agent_round WHERE session_id=? AND COALESCE(turn_id,id)=? ORDER BY seq", (session_id, turn_id))

    def set_auto_confirm(self, session_id, value):
        """TASK-07b R3: persist the session-level confirmation opt-in."""
        with connect_database(self.database) as db, _write(db):
            db.execute("UPDATE agent_session SET auto_confirm=? WHERE id=?", (int(value), session_id))

    def preflight(self, session_id, check_id=None, plan_id=None):
        self.session(session_id)
        with connect_database(self.database) as db:
            rounds = _rows(db, "SELECT * FROM agent_round WHERE session_id=? AND status IN ('running','human_check','plan_check') ORDER BY seq", (session_id,))
            if plan_id is not None:
                if not rounds or rounds[0]["id"] != plan_id or rounds[0]["status"] != "plan_check":
                    raise _failure("INVALID_REQUEST", "确认引用不存在或已处理")
                return rounds[0], None
            if check_id is None:
                if rounds:
                    raise _failure("INVALID_REQUEST", "本轮尚未结束，只接受待确认应答")
                return None
            pending = _rows(db, "SELECT * FROM agent_step WHERE id=? AND session_id=? AND status='human_check_pending'", (check_id, session_id))
        if not pending or not rounds or rounds[0]["id"] != pending[0]["round_id"] or rounds[0]["status"] != "human_check":
            raise _failure("INVALID_REQUEST", "确认引用不存在或已处理")
        return rounds[0], pending[0]

    def pending(self, session_id):
        self.session(session_id)
        with connect_database(self.database) as db:
            rows = _rows(db, "SELECT * FROM agent_round WHERE session_id=? AND status IN ('human_check','plan_check') ORDER BY seq LIMIT 1", (session_id,))
            if not rows:
                return None
            steps = _rows(db, "SELECT id FROM agent_step WHERE round_id=? AND status='human_check_pending' ORDER BY seq LIMIT 1", (rows[0]["id"],))
            return rows[0], steps[0]["id"] if steps else None

    def new_round(self, session_id, content, calls, status="running", *, turn_id=None):
        with connect_database(self.database) as db, _write(db):
            if db.execute("SELECT 1 FROM agent_round WHERE session_id=? AND status IN ('running','human_check','plan_check')", (session_id,)).fetchone():
                raise _failure("INVALID_REQUEST", "本轮尚未结束")
            identifier, timestamp = str(uuid4()), _now()
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM agent_round WHERE session_id=?", (session_id,)).fetchone()[0]
            db.execute("INSERT INTO agent_round (id,session_id,seq,user_message,calls_json,status,created_at,turn_id) VALUES (?,?,?,?,?,?,?,?)",
                       (identifier, session_id, seq, content, _json(calls), status, timestamp, turn_id or identifier))
            if content and db.execute("SELECT title FROM agent_session WHERE id=?", (session_id,)).fetchone()[0] == "":
                db.execute("UPDATE agent_session SET title=? WHERE id=?", (' '.join(content.split())[:40], session_id))
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

    def claim_plan(self, round_id):
        with connect_database(self.database) as db, _write(db):
            row = db.execute("UPDATE agent_round SET status='running' WHERE id=? AND status='plan_check'", (round_id,))
            if row.rowcount != 1:
                raise _failure("INVALID_REQUEST", "确认已处理")

    def add_plan_action(self, round_, action, seq_ref, reason):
        with connect_database(self.database) as db, _write(db):
            db.execute("INSERT INTO agent_plan_action (id,session_id,round_id,action,seq_ref,reason,created_at) VALUES (?,?,?,?,?,?,?)",
                       (str(uuid4()), round_["session_id"], round_["id"], action, seq_ref, reason, _now()))

    def effective_calls(self, round_id):
        with connect_database(self.database) as db:
            calls = json.loads(db.execute("SELECT calls_json FROM agent_round WHERE id=?", (round_id,)).fetchone()[0])
            actions = _rows(db, "SELECT * FROM agent_plan_action WHERE round_id=? ORDER BY rowid DESC LIMIT 1", (round_id,))
        action = actions[0] if actions else None
        start, stop = 0, len(calls)
        if action:
            if action["action"] == "reject":
                stop = 0
            elif action["action"] == "skip":
                stop = action["seq_ref"] - 1
            elif action["action"] == "rollback":
                start = action["seq_ref"] - 1
        skipped = [{"seq": index + 1, "tool": call["name"]} for index, call in enumerate(calls) if not start <= index < stop]
        return calls[start:stop], {"skipped": skipped,
            "rolled_back_from": action["seq_ref"] if action and action["action"] == "rollback" else None}

    def cancel_running(self, round_id):
        with connect_database(self.database) as db, _write(db):
            row = db.execute("UPDATE agent_round SET status='error' WHERE id=? AND status='running'", (round_id,))
            if row.rowcount:
                db.execute("UPDATE agent_session SET updated_at=? WHERE id=(SELECT session_id FROM agent_round WHERE id=?)", (_now(), round_id))

    def add_step(self, round_, tool, arguments, status, summary, latency, *, tool_call_id=None):
        with connect_database(self.database) as db, _write(db):
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM agent_step WHERE session_id=?", (round_["session_id"],)).fetchone()[0]
            identifier = str(uuid4())
            text = _json(summary)
            digest = None if status == "rejected" else sha256(text.encode("utf-8")).hexdigest()
            db.execute("INSERT INTO agent_step (id,session_id,round_id,seq,tool,arguments_json,result_digest,result_summary,status,latency_ms,created_at,tool_call_id) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (identifier, round_["session_id"], round_["id"], seq, tool,
                        _json(arguments), digest, text, status, latency, _now(), tool_call_id))
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

    def _workflow_enabled(self):
        """Decide the execution path from the tool catalogue actually in use.

        The catalogue is what the model may call, so it is the only honest source of
        truth. Reading the stored skill's tools_json instead would let a stale skill
        row disagree with the live registry and silently pick the wrong state machine.
        """
        return any(tool["function"]["name"] == "annotations.prepare"
                   for tool in self.tools.snapshot())

    def message(self, *, content=None, check_id=None, decision=None, plan_id=None, action=None, step_ref=None, reason=None, workspace=None):
        if hasattr(self.tools, 'check_workspace'):
            self.tools.check_workspace(workspace)
        if plan_id is not None and content is None and check_id is None and decision is None:
            if action not in {"approve", "reject", "skip", "rollback"}:
                raise _failure("INVALID_REQUEST", "计划动作不合法")
            if action == "approve":
                if step_ref is not None or reason is not None:
                    raise _failure("INVALID_REQUEST", "批准不能携带步骤或原因")
            elif not isinstance(reason, str) or not reason.strip():
                raise _failure("INVALID_REQUEST", "计划动作必须填写原因")
            continuation = self.store.preflight(self.session_id, plan_id=plan_id)
            if action in {"skip", "rollback"}:
                if type(step_ref) is not int or not 1 <= step_ref <= len(json.loads(continuation[0]["calls_json"])):
                    raise _failure("INVALID_REQUEST", "计划步骤引用不合法")
            elif step_ref is not None:
                raise _failure("INVALID_REQUEST", "计划动作不接受步骤引用")
            return self._dispatch(continuation=continuation, plan=(action, step_ref, reason))
        if any(value is not None for value in (plan_id, action, step_ref, reason)):
            raise _failure("INVALID_REQUEST", "消息形态不合法")
        if content is not None and check_id is None and decision is None:
            if self._workflow_enabled():
                pending = self.store.pending(self.session_id)
                if pending:
                    text = content.strip().strip("。！! ")
                    approve = re.fullmatch(r"(?:请)?(?:批准(?:执行)?|同意(?:执行)?|确认(?:保存|执行)?|继续(?:执行)?|保存(?:这一版)?|可以(?:执行)?|好(?:的)?|是)", text)
                    reject = re.fullmatch(r"(?:请)?(?:拒绝|取消|不同意|不批准|停止|不要(?:执行|保存)?|先别(?:执行|保存))", text)
                    if approve or reject:
                        row, pending_id = pending
                        if row["status"] == "plan_check":
                            return self.message(plan_id=row["id"], action="approve" if approve else "reject",
                                                reason=None if approve else content)
                        return self.message(check_id=pending_id, decision="approve" if approve else "reject")
                    def clarify_pending():
                        yield "clarify", {"question": "当前操作正在等待你的确认。可以回复“批准执行”“确认保存”或“取消”；也可以使用下方操作卡。", "keep_pending": True}
                    return clarify_pending()
            self.store.preflight(self.session_id)
            return self._dispatch(content=content, workspace=workspace)
        if content is None and check_id is not None and decision in {"approve", "reject"}:
            continuation = self.store.preflight(self.session_id, check_id)
            return self._dispatch(continuation=continuation, decision=decision)
        raise _failure("INVALID_REQUEST", "消息形态不合法")

    def _dispatch(self, **kwargs):
        if self._workflow_enabled():
            intake = getattr(self.tools, 'data_intake', None)
            if intake and kwargs.get('content'):
                routed = intake.route(self, kwargs['content'])
                if routed is not None:
                    return routed
            dialogue = getattr(self.tools, 'experiment_dialogue', None)
            if dialogue and kwargs.get('content'):
                from .router import dispatch
                routed = dispatch(self, dialogue, kwargs['content'], kwargs.get('workspace'))
                if routed is not None:
                    return routed
            from .workflow import generate
            def with_reply_state():
                events=generate(self,**kwargs)
                try:
                    for kind,payload in events:
                        if kind in {'done','clarify','plan','human_check'}:
                            payload={'request_status':'finished','reply_status':
                                     'needs_confirmation' if kind in {'plan','human_check'} else 'needs_input' if kind=='clarify' else 'replied',**payload}
                        yield kind,payload
                finally:
                    events.close()
            return with_reply_state()
        kwargs.pop("workspace", None)
        return self._generate(**kwargs)

    @staticmethod
    def _step_event(step):
        return "step", {"seq": step["seq"], "tool": step["tool"], "status": step["status"], "result_summary": json.loads(step["result_summary"])}

    def _round_messages(self, round_):
        calls, plan_summary = self.store.effective_calls(round_["id"])
        remaining = self.store.steps(self.session_id, round_["id"])
        pairs = []
        for call in calls:
            step = next((step for step in remaining if step.get("tool_call_id") == call["id"]), None)
            if step is None:
                # Legacy rows have no call id. Match name AND validated args;
                # rejected raw-argument audit rows can never steal this slot.
                step = next((step for step in remaining if step.get("tool_call_id") is None
                             and step["tool"] == call["name"]
                             and json.loads(step["arguments_json"]) == call["arguments"]), None)
            if step is not None and step["status"] != "human_check_pending":
                pairs.append((call, step))
                remaining.remove(step)
        messages = []
        if pairs:
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": call["id"], "type": "function", "function": {"name": call["name"],
                 "arguments": _json(call["arguments"])}} for call, _ in pairs]})
            messages.extend({"role": "tool", "tool_call_id": call["id"], "content": step["result_summary"]}
                            for call, step in pairs)
        rejected = [{"tool": step["tool"], **json.loads(step["result_summary"])} for step in remaining if step["status"] == "rejected"]
        if rejected:
            messages.append({"role": "system", "content": _json({"rejected": rejected})})
        if plan_summary["skipped"] or plan_summary["rolled_back_from"] is not None:
            messages.append({"role": "system", "content": _json(plan_summary)})
        return messages

    def _history_messages(self, version, *, exclude_round_id=None, exclude_turn_id=None, limit=10):
        """Replay actual answers and only complete call/result pairs."""
        from .conversation import journal_messages
        journal = journal_messages(self.store.database, self.session_id, getattr(self, 'request_id', None), machine=self)
        if journal is not None:
            return self._pairing_history(journal)
        prior = self.store.rounds(self.session_id, exclude_round_id=exclude_round_id, limit=limit, include_incomplete=True)
        messages = []
        seen_turns = set()
        for prior_round in prior:
            turn_id = prior_round.get("turn_id") or prior_round["id"]
            if turn_id == exclude_turn_id:
                continue
            if turn_id not in seen_turns:
                messages.append({"role": "user", "content": prior_round["user_message"]})
                seen_turns.add(turn_id)
            messages.extend(self._round_messages(prior_round))
            if prior_round.get("assistant_content"):
                messages.append({"role": "assistant", "content": prior_round["assistant_content"]})
            if prior_round['status'] == 'error':
                messages.append({'role': 'system', 'content': '该轮失败或中断；已记录的工具结果保留，未记录的结果未知。重试前须核对真实状态，不得自动重复写操作。'})
        return self._pairing_history(messages)

    @staticmethod
    def _pairing_history(messages):
        # These local inventory pages include user paths and discovered filenames.
        from spectrumagent.experiments.conversation import PATHS
        from spectrumagent.experiments.pairing import requested
        from spectrumagent.experiments.group_split import requested as split_requested
        for message in messages:
            text = message.get('content')
            if not isinstance(text, str):
                continue
            if message['role'] == 'user' and (requested(text, PATHS) or split_requested(text, PATHS)):
                message['content'] = '查看本地原图与标注配对预览'
            elif message['role'] == 'assistant' and text.startswith((
                    'ENVI 原图与标注配对预览', '配对明细 ·', '未配对原图 ·', '配对异常 ·', '未生成新的配对预览。',
                    '中心取谱核验通过', '中心取谱核验未完成', '数据划分 ·','原图与标注目录用途')):
                message['content'] = '本地配对信息已展示给用户。'
            elif message['role'] == 'user' and PATHS.search(text):
                message['content'] = PATHS.sub('本地输入源', text)
        return messages

    def _chat(self, messages, tools):
        control = getattr(self, 'control', None)
        if control is not None:
            control.begin('model')
            cancellable = getattr(self.llm, 'chat_cancellable', None)
            result = cancellable(messages, tools, control) if callable(cancellable) else self.llm.chat(messages, tools)
            control.check()
            return result
        return self.llm.chat(messages, tools)

    def _execute(self, round_, call, pending=None):
        if getattr(self, 'control', None) is not None:
            self.control.begin('tool')
        started = perf_counter_ns()
        try:
            if hasattr(self.tools, 'begin_call'):
                self.tools.begin_call(round_, call)
            summary = self.tools.invoke(call["name"], call["arguments"])
            status, error = "ok", None
        except Exception as exc:
            error = exc if isinstance(exc, DataError) else DataError("TOOL_FAILED", "工具执行失败")
            status, summary = "error", safe_error(error)
            if error.code == 'SESSION_RESULT_SCOPE_MISMATCH':
                summary.update(handler_completed=True, effects_rolled_back=False)
        elapsed = (perf_counter_ns() - started) // 1_000_000
        if pending is None:
            step = self.store.add_step(round_, call["name"], call["arguments"], status, summary, elapsed, tool_call_id=call["id"])
        else:
            step = self.store.finish_step(pending, status, summary, elapsed)
        return step, error

    def _generate(self, *, content=None, continuation=None, decision=None, plan=None):
        round_ = None
        round_creation_attempted = False
        try:
            version = self.store.skill(self.session_id)
            auto_confirm = self.store.session(self.session_id)["auto_confirm"]
            if continuation is None:
                self.state = State.PARSE
                history = self._history_messages(version)
                if getattr(self, 'control', None) is not None:
                    yield 'progress', {'phase': 'model'}
                parsed = self._chat([{"role": "system", "content": version["system_prompt"]},
                                        *history, {"role": "user", "content": content}],
                                       self.tools.snapshot())
                from .llm import validate_tool_response
                validate_tool_response(parsed)
                directive = _auto_confirm_directive(content)
                if directive is not None:
                    self.store.set_auto_confirm(self.session_id, directive)
                    auto_confirm = directive
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
                            "_raw_bytes": len(raw)}, exc,
                            (perf_counter_ns() - started) // 1_000_000))
                if hasattr(self.tools, 'preflight_group'):
                    if any(error.code=='SESSION_SCOPE_MISMATCH' for _,_,error,_ in rejected):
                        raise DataError('SESSION_SCOPE_MISMATCH','本组包含范围外操作，整组未执行')
                    if not any(error.code in PARAMETER_ERRORS for _,_,error,_ in rejected):
                        self.tools.preflight_group(calls)
                round_creation_attempted = True
                needs_plan = len(calls) >= 2 and not auto_confirm
                status = "plan_check" if needs_plan else "running" if parsed.tool_calls else "done"
                round_ = self.store.new_round(self.session_id, content, calls, status)
                if not parsed.tool_calls:
                    self.state = State.CLARIFY
                    self.store.save_answer(round_["id"], parsed.content or "")
                    yield "clarify", {"question": parsed.content or ""}
                    return
                # PARSE rejects are audited immediately. Only validated calls
                # enter the immutable continuation, in their original order.
                for name, arguments, error, elapsed in rejected:
                    step = self.store.add_step(round_, name, arguments, "rejected", safe_error(error), elapsed)
                    yield self._step_event(step)
                invalid = next((error for _,_,error,_ in rejected if error.code in PARAMETER_ERRORS),None)
                if invalid:
                    if needs_plan:
                        self.store.claim_plan(round_['id'])
                    answer = parameter_answer(invalid)
                    self.store.save_answer(round_['id'],answer)
                    self.store.round_status(round_['id'],'done')
                    yield 'clarify',{'question':answer,'task_result':'needs_input','request_status':'finished','reply_status':'needs_input'}
                    return
                if needs_plan:
                    self.state = State.PLAN_CHECK
                    yield "plan", {"plan_id": round_["id"], "steps": [{"seq": index, "tool": call["name"],
                        "summary": {key: value for key, value in call["arguments"].items()
                            if key in {"cube_id", "version_id", "revision", "class_code", "overwrite"}
                            and value is not None and isinstance(value, (str, int, float, bool))},
                        "gpu": self.tools.resolve(call["name"]).gpu, "estimate_ms": self.tools.resolve(call["name"]).estimate_ms}
                        for index, call in enumerate(calls, 1)], "reason": "执行计划待确认"}
                    return
                offset = 0
            elif plan is not None:
                resume_round, _ = continuation
                if plan[0]!='reject' and hasattr(self.tools,'preflight_group'):
                    effective,_=self.store.effective_calls(resume_round['id'])
                    self.tools.preflight_group(effective)
                self.store.claim_plan(resume_round["id"])
                round_ = resume_round
                action, step_ref, reason = plan
                if action != "approve":
                    self.store.add_plan_action(round_, action, step_ref, reason)
                if action == "reject":
                    self.store.round_status(round_["id"], "done")
                    self.state = State.DONE
                    yield "done", {"content": "计划已拒绝、未执行", "step_count": 0}
                    return
                calls, _ = self.store.effective_calls(round_["id"])
                offset = 0
            else:
                resume_round, pending = continuation
                if decision!='reject' and hasattr(self.tools,'preflight_group'):
                    effective,_=self.store.effective_calls(resume_round['id'])
                    self.tools.preflight_group(effective)
                self.store.claim(resume_round["id"])
                round_ = resume_round
                calls, _ = self.store.effective_calls(round_["id"])
                if decision == "reject":
                    step = self.store.finish_step(pending, "rejected", {"error": "HUMAN_REJECTED"}, 0)
                    yield self._step_event(step)
                    self.state = State.DONE
                    yield "done", {"content": "已拒绝、未执行", "step_count": len(self.store.steps(self.session_id, round_["id"]))}
                    return
                executed = [step for step in self.store.steps(self.session_id, round_["id"]) if step["status"] != "rejected"]
                offset = len(executed)
                self.state = State.CALL_TOOL
                if getattr(self, 'control', None) is not None:
                    yield 'progress', {'phase': 'tool', 'tool': calls[offset - 1]['name']}
                step, error = self._execute(round_, calls[offset - 1], pending)
                yield self._step_event(step)
                if error is not None:
                    raise error
            self.state = State.CALL_TOOL
            for call in calls[offset:]:
                tool = self.tools.resolve(call["name"])
                numerical = numerical_confirmation(call)
                if numerical is not None or tool.human_check and not auto_confirm:
                    summary = {key: value for key, value in call["arguments"].items()
                               if key in {"cube_id", "version_id", "revision", "class_code", "overwrite"} and value is not None}
                    reason = "标注版本确认"
                    if numerical is not None:
                        summary.update(numerical)
                        reason = "请核对训练或推理输入，确认后提交。"
                    step = self.store.add_step(round_, call["name"], call["arguments"], "human_check_pending", summary, 0, tool_call_id=call["id"])
                    self.state = State.HUMAN_CHECK
                    yield "human_check", {"check_id": step["id"], "tool": call["name"], "summary": summary, "reason": reason}
                    return
                if getattr(self, 'control', None) is not None:
                    yield 'progress', {'phase': 'tool', 'tool': call['name']}
                step, error = self._execute(round_, call)
                yield self._step_event(step)
                if error is not None:
                    raise error
            self.state = State.INTERPRET
            steps = self.store.steps(self.session_id, round_["id"])
            calls, plan_summary = self.store.effective_calls(round_["id"])
            history = self._history_messages(version, exclude_round_id=round_["id"])
            messages = [{"role": "system", "content": version["system_prompt"]}, *history,
                        {"role": "user", "content": round_["user_message"]}]
            if calls:
                messages.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": _json(call["arguments"])}} for call in calls]})
                completed = [step for step in steps if step["status"] != "rejected"]
                messages.extend({"role": "tool", "tool_call_id": call["id"], "content": step["result_summary"]}
                                for call, step in zip(calls, completed))
            rejections = [{"tool": step["tool"], **json.loads(step["result_summary"])} for step in steps if step["status"] == "rejected"]
            if rejections:
                messages.append({"role": "system", "content": _json({"rejected": rejections})})
            if plan_summary["skipped"] or plan_summary["rolled_back_from"] is not None:
                messages.append({"role": "system", "content": _json(plan_summary)})
            if getattr(self, 'control', None) is not None:
                yield 'progress', {'phase': 'model'}
            final = self._chat(messages, None)
            from .llm import validate_tool_response
            validate_tool_response(final)
            if final.tool_calls:
                raise DataError("LLM_UNEXPECTED_TOOL_CALL", "解读阶段禁止工具调用")
            self.store.round_status(round_["id"], "done")
            self.store.save_answer(round_["id"], final.content or "")
            self.state = State.DONE
            yield "done", {"content": final.content or "", "step_count": len(steps)}
        except (GeneratorExit, RequestCancelled):
            if round_ is not None:
                # Closing a suspended HUMAN_CHECK stream retains its pending
                # round; an interrupted running round releases the session.
                self.store.cancel_running(round_["id"])
            raise
        except Exception as exc:
            self.state = State.ERROR
            error = exc if isinstance(exc, DataError) else DataError("AGENT_FAILED", "编排执行失败")
            if error.code in INPUT_ERRORS and round_ is not None:
                answer = parameter_answer(error) + '。此前完成项已保留。'
                self.store.save_answer(round_['id'],answer)
                self.store.round_status(round_['id'],'done')
                yield 'clarify',{'question':answer,'task_result':'needs_input','request_status':'finished','reply_status':'needs_input'}
                return
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
