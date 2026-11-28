"""Persist explicitly numbered user instructions; release one step at a time."""
import json
import re

from backend.database import connect_database
from spectrumagent.data import DataError


MARKER = re.compile(r'【第\s*([0-9一二三四五六七八九十]+)\s*步】')
NEXT = re.compile(r'(?:请)?(?:确认(?:第[0-9一二三四五六七八九十]+步)?[，,、\s]*(?:继续(?:下一步)?)?|继续(?:下一步)?|下一步|进入第[0-9一二三四五六七八九十]+步)[。！!\s]*')


def number(text):
    return int(text) if text.isdigit() else {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}.get(text)


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS agent_step_plan (
        session_id TEXT PRIMARY KEY REFERENCES agent_session(id), document_json TEXT NOT NULL,
        current_step INTEGER NOT NULL DEFAULT 0, waiting INTEGER NOT NULL DEFAULT 0,
        revision INTEGER NOT NULL DEFAULT 1)''')


def read(database, sid):
    with connect_database(database) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='agent_step_plan'").fetchone():
            return None
        row = db.execute('SELECT document_json,current_step,waiting,revision FROM agent_step_plan WHERE session_id=?', (sid,)).fetchone()
    return dict(document=json.loads(row[0]), step=row[1], waiting=bool(row[2]), revision=row[3]) if row else None


def prepare(database, sid, content, busy=False):
    if content is None:
        return content, read(database, sid)
    markers = list(MARKER.finditer(content))
    if len(markers) >= 2 and re.search(r'每.*步.*(?:确认|停)|不要跳步|逐步.*确认', content):
        if busy:
            raise DataError('PLAN_BUSY', '当前任务尚未完成，请先核对任务状态')
        if [number(m[1]) for m in markers] != list(range(1,len(markers)+1)):
            raise DataError('INVALID_STEP_PLAN', '步骤编号须从第1步开始连续且唯一；未执行')
        document = dict(preamble=content[:markers[0].start()], steps=[
            content[m.end():markers[i+1].start() if i+1 < len(markers) else len(content)].strip()
            for i,m in enumerate(markers)], no_defaults=bool(re.search(r'不要.*默认|不用默认|不使用默认', content)))
        with connect_database(database) as db:
            db.execute('INSERT INTO agent_step_plan(session_id,document_json) VALUES(?,?) '
                       'ON CONFLICT(session_id) DO UPDATE SET document_json=excluded.document_json,current_step=0,waiting=0,revision=revision+1',
                       (sid, json.dumps(document, ensure_ascii=False)))
        record = read(database, sid)
        return document['steps'][0], record
    record = read(database, sid)
    if not record:
        return content, None
    if content.strip().rstrip('。！!') in {'取消逐步计划', '取消分步计划'}:
        with connect_database(database) as db:
            db.execute('DELETE FROM agent_step_plan WHERE session_id=?', (sid,))
        return '逐步计划已取消。', None
    if record['waiting'] and NEXT.fullmatch(content.strip()):
        if busy:
            raise DataError('PLAN_BUSY', '本步后台任务尚未结束，请先核对任务状态；没有进入下一步')
        next_step = record['step']+1
        requested = re.search(r'进入第([0-9一二三四五六七八九十]+)步', content)
        if requested and number(requested[1]) != next_step+1:
            raise DataError('PLAN_STEP_BOUNDARY', '请先确认并完成当前步骤，不能跳步')
        steps = record['document']['steps']
        if next_step >= len(steps):
            raise DataError('PLAN_FINISHED', '已到最后一步，没有后续步骤')
        with connect_database(database) as db:
            db.execute('UPDATE agent_step_plan SET current_step=?,waiting=0,revision=revision+1 WHERE session_id=? AND revision=?',
                       (next_step, sid, record['revision']))
        record = read(database, sid)
        return steps[next_step], record
    # Further details/questions refine the current step. They never release a
    # later numbered instruction merely because a future keyword appears.
    return content, record


def wait(database, sid, record):
    if record:
        with connect_database(database) as db:
            db.execute('UPDATE agent_step_plan SET waiting=1 WHERE session_id=? AND revision=?', (sid, record['revision']))


def validate_tool(database, sid, name):
    record = read(database, sid)
    if not record:
        return
    text = record['document']['steps'][record['step']]
    study_write = name in {'experiments.study_execute', 'experiments.study_submit'}
    training_write = name in {'modeling.regress', 'modeling.regression_plan_execute', 'workspace.preprocess'}
    if study_write and not re.search(r'发起|执行|开始|运行', text) or training_write and re.search(r'不(?:执行|训练)|只.*(?:保存|草稿)|新建.*方案', text):
        raise DataError('PLAN_STEP_BOUNDARY', '该操作超出当前获准步骤；没有执行')


def validate_operation(database, sid, flow):
    """Native numerical submission paths obey the gate too, not just tools."""
    record = read(database, sid)
    if not record:
        return
    text = record['document']['steps'][record['step']]
    patterns = {'study': r'(?:发起|执行|开始|运行).*寻优',
                'experiment': r'(?:正式训练|执行训练|确认训练|开始训练|训练并测试)',
                'inference': r'(?:推理|预测)'}
    if not re.search(patterns[flow], text) or re.search(r'不(?:执行|训练|推理)|只.*(?:保存|草稿)', text):
        raise DataError('PLAN_STEP_BOUNDARY', '数值任务超出当前获准步骤；没有提交')
