"""Bounded model memory projected from the authoritative conversation journal.

Display cards are observations, never executable instructions or authorization.
Only scalar tool summaries cross this boundary; geometry and capability tokens
remain local. Recent request groups are retained whole, including interruptions.
"""
import json

from backend.database import connect_database
from .llm import _egress_blocked, _json


HISTORY_CHAR_BUDGET = 48000


def _scalar_summary(value):
    return {key: item for key, item in value.items()
            if (item is None or type(item) in (str, int, float, bool))
            and key not in {'path', 'filename', 'partial_confirmation_token', 'geometry', 'spectra'}
            and not _egress_blocked({key: item})}


def _message(kind, payload):
    if kind in {'user', 'done', 'clarify'}:
        content = payload.get('question' if kind == 'clarify' else 'content')
        if isinstance(content, str) and content:
            return {'role': 'user' if kind == 'user' else 'assistant', 'content': content}
    elif kind == 'step':
        return {'role': 'system', 'content': _json({'recorded_tool_result': {
            'tool': payload.get('tool'), 'status': payload.get('status'),
            'summary': _scalar_summary(payload.get('result_summary') or {})}})}
    elif kind in {'error', 'decision', 'human_check', 'plan'}:
        summary = _scalar_summary(payload)
        if kind == 'error':
            summary['execution_policy'] = '已完成结果保留；未知结果先核对，不得自动重复写操作。'
        return {'role': 'system', 'content': _json({'conversation_event': kind, 'summary': summary})}
    return None


def journal_messages(database, session_id, current_request=None, *, budget=HISTORY_CHAR_BUDGET, machine=None):
    groups, group, key, size, found, truncated = [], [], None, 0, False, False
    included_rounds = set()
    with connect_database(database) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_session_event'").fetchone():
            return None
        cursor = db.execute('SELECT e.request_id,e.kind,e.payload_json,r.status FROM agent_session_event e '
                            'LEFT JOIN agent_session_request r ON r.session_id=e.session_id AND r.request_id=e.request_id '
                            'WHERE e.session_id=? AND (? IS NULL OR e.request_id IS NULL OR e.request_id<>?) '
                            'ORDER BY e.seq DESC', (session_id, current_request, current_request))
        for request, kind, raw, status in cursor:
            found = True
            # Legacy projections lack request IDs. Keep their adjacent events in
            # one bounded sequence rather than duplicating the execution ledger.
            identity = request or 'legacy'
            if key is not None and identity != key:
                groups.append(list(reversed(group)))
                group = []
            if identity != key and status in {'failed', 'interrupted'}:
                note = {'role': 'system', 'content': _json({'prior_request_status': status,
                    'execution_policy': '该请求未完整结束；已完成操作保留，未知结果须先查询，不得自动重复写操作。'})}
                group.append(note)
                size += len(_json(note))
            key = identity
            payload = json.loads(raw)
            projected = None
            if kind == 'step' and machine is not None and not payload.get('operation_receipt'):
                row = db.execute('SELECT r.id FROM agent_step s JOIN agent_round r ON r.id=s.round_id '
                                 'WHERE s.session_id=? AND s.seq=? AND s.tool_call_id IS NOT NULL',
                                 (session_id, payload.get('seq'))).fetchone()
                if row:
                    if row[0] in included_rounds:continue
                    included_rounds.add(row[0])
                    projected = machine._round_messages({'id': row[0]})
                    for message in projected:
                        if message['role'] == 'tool':
                            message['content'] = _json(_scalar_summary(json.loads(message['content'])))
            message = _message(kind, payload) if projected is None else None
            batch = projected if projected is not None else [message] if message else []
            if not batch:
                continue
            length = len(_json(batch))
            if size + length > budget:
                truncated = True
                # Never leave a historical tool result without its user input.
                group = []
                break
            group.extend(reversed(batch))
            size += length
        if group:
            groups.append(list(reversed(group)))
    if not found:
        return None
    messages = [message for request in reversed(groups) for message in request]
    if truncated:
        messages.insert(0, {'role': 'system', 'content': '较早对话超出上下文预算；当前任务引用与实时状态另行提供。缺少的信息应查询或澄清，不得猜测。'})
    return messages
