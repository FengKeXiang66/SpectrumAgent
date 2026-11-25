"""Session-owned directory roles for conversational, read-only ENVI pairing."""
import json
from pathlib import Path
import re

from backend.database import connect_database
from . import pairing
from .conversation import PATHS


ORDINAL = re.compile(r'第\s*(\d+|[一二三四五六七八九十])\s*(?:个|项|条|处)(?:目录|文件夹|路径)?')
CHECK_NOW = re.compile(r'(?:帮我|请|直接|先)(?:核对|检查|预览|扫描|配对)')


def draft(database, owner):
    with connect_database(database) as db:
        row = db.execute('SELECT document FROM experiment_pairing_intake WHERE session_id=?', (owner,)).fetchone()
    return json.loads(row[0]) if row else {}


def save(database, owner, state):
    with connect_database(database) as db:
        if state:
            db.execute('INSERT OR REPLACE INTO experiment_pairing_intake VALUES (?,?)',
                       (owner, json.dumps(state, ensure_ascii=False)))
        else:
            db.execute('DELETE FROM experiment_pairing_intake WHERE session_id=?', (owner,))


def route(dialogue, owner, content):
    text = PATHS.sub(' ', content).strip(' ，,。！!？?\n')
    state = draft(dialogue.database, owner)
    has_paths = bool(PATHS.search(content))
    check_requested = CHECK_NOW.search(text) and not re.search(r'不要|先不|先别|能否|能不能|可以吗|等我',text)
    if state.get('listening'):
        if pairing.DISMISS.fullmatch(text):
            return 'cancel'
        if pairing.ACCEPT.fullmatch(text) or text == '配对预览':
            return 'accept'
        if text == pairing.EDIT:
            return 'edit'
        if ((has_paths or pairing.SOURCE.search(text) or ORDINAL.search(text)) and
            (not text or pairing.ROLE_FIELD.search(text) or re.search(r'目录|文件夹',text))
            and not re.search(r'推理|寻优|划分|\.npz',content,re.I)):
            return 'inspect' if check_requested else 'collect'
    loose_directories = ('标注' in text and ('训练' in text or '测试' in text)
                         and re.search(r'对应标注|原图目录|ENVI.{0,4}目录',text,re.I))
    individual_files = any(Path(match['quoted'] or match['bare']).suffix.lower() in ('.hdr','.img','.npz')
                           for match in PATHS.finditer(content))
    natural = not individual_files and (loose_directories or pairing.external_annotations(text))
    if natural and (has_paths or not pairing.requested(content, PATHS)):
        if has_paths and check_requested:
            return 'inspect'
        return 'collect'
    if text == '配对预览' or re.search(r'(?:检查|配对).*(?:之前|刚才|上面).*目录|(?:刚才|上面|之前).*目录.*(?:配对|检查)|共用训练标注',text):
        return 'recover'
    if state.get('listening'):
        state.update(listening=False, ready=False)
        save(dialogue.database, owner, state)
    return None


def respond(dialogue, store, owner, content, action):
    state = draft(dialogue.database, owner)
    if action == 'cancel':
        save(dialogue.database, owner, {})
        return '已取消本次目录配对。', False
    if action == 'edit':
        state['ready'] = False
        save(dialogue.database, owner, state)
        return '请指出要调整的用途与目录编号，例如“测试标注用 S7”。', False
    fields = state.get('fields', {})
    sources = (dialogue._read(owner) or {}).get('sources', {})
    def inspect():
        paths = {key:[Path(sources[ref]).resolve() for ref in values] for key,values in fields.items()}
        result = dialogue.pairing_answer(owner, content, fields=paths)
        if result.startswith('ENVI 原图与标注配对预览'):
            save(dialogue.database, owner, {})
        return result, False
    if action == 'accept' and state.get('ready'):
        return inspect()

    safe = dialogue.capture(owner, content, pairing=True)
    sources = dialogue._read(owner)['sources']
    order = state.get('order', [])
    def ordinal(match):
        value = match[1]
        index = int(value) if value.isdigit() else '一二三四五六七八九十'.index(value)+1
        return ' '+order[index-1]+' ' if 0 < index <= len(order) else ' S0 '
    if order:
        safe = ORDINAL.sub(ordinal,safe)
    if action == 'recover' and not fields:
        for previous in reversed(store.rounds(owner, limit=8)):
            message = dialogue.redact(owner, previous['user_message'])
            if pairing.DISMISS.fullmatch(message.strip(' 。！!')):
                break
            if pairing.external_annotations(message) and pairing.SOURCE.search(message):
                safe = message
                break
    updates = pairing.mentioned_roles(safe)
    if len(updates.get(None, [])) == 1 and len(updates) == 1:
        trailing = safe[pairing.SOURCE.search(safe).end():]
        updates = pairing.mentioned_roles(trailing+' '+updates[None][0])
    if any(ref not in sources for values in updates.values() for ref in values):
        state['ready'] = False
        save(dialogue.database, owner, state)
        return '请使用当前会话列出的目录编号，或选择该目录。', False
    pending = state.get('unassigned', [])
    if all(key in updates for key in pairing.DIRECTORY_KEYS):
        fields, pending, order = {}, [], []
    for key, values in updates.items():
        if key is None:
            continue
        for other in fields:
            if other != key and other not in updates:
                fields[other] = [ref for ref in fields[other] if ref not in values]
        fields[key] = list(dict.fromkeys(values))
    assigned = {ref for values in fields.values() for ref in values}
    unassigned = list(dict.fromkeys(ref for ref in pending+updates.get(None,[]) if ref not in assigned))
    missing = [key for key in pairing.DIRECTORY_KEYS if not fields.get(key)]
    ready = not missing and not unassigned and len(fields.get('清单',[]))<=1
    order = list(dict.fromkeys([*order,*(ref[0].upper() for ref in pairing.SOURCE.finditer(safe))]))
    save(dialogue.database, owner, dict(fields=fields,unassigned=unassigned,order=order,ready=ready,listening=True))
    if ready and action=='inspect':
        return inspect()
    if not assigned and not unassigned:
        return pairing.CAPABILITY+' 请告诉我原图和标注放在哪里，以及是否已有训练、测试划分。', False
    def describe(values):
        return '、'.join(f'{ref}（{Path(sources[ref]).name}）' for ref in values)
    lines = ['原图与标注目录用途']
    lines.extend(key+'：'+describe(values) for key,values in fields.items() if values)
    if unassigned:
        lines.append('待指定用途：'+describe(unassigned))
    if ready:
        lines.append('我可以按 JSON 核对原图、区域和材料标签，列出缺失和异常。回复“对，先检查”或指出要调整的用途。')
    else:
        if missing:
            lines.append('还需指定：'+'、'.join(missing)+'。')
        lines.append('可以继续选择目录，或用上面列出的编号指定用途，例如“训练标注用 S4”。')
    return '\n'.join(lines), ready
