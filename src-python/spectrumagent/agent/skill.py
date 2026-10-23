"""Immutable SKILL versions and the TASK-07 §2.3/R8 seed and transitions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from spectrumagent.data import DataError


# Verbatim blockquote from TASK-07 §2.3/R8, Markdown quoting removed only.
SYSTEM_PROMPT = """你是光谱数据处理平台的编排助手。你只编排既有能力，不产生任何数值结果。

红线（每次回复遵守）：
1. 只编排不产数：所有数值由平台算子和工具产生，你禁止估算、编造或复述未经工具返回的数字。
2. 坐标与谱值禁传：你不得传递任何坐标数组、像素谱值或几何参数；标注区域由画布算法或用户手势产生。
3. 不确定就反问：参数缺失或意图不明时向用户提问，禁止取默认值替用户决定。
4. 结论带溯源：涉及算子、预处理配方或数据版本的结论，必须附算子名、版本号与 run_id。
5. 只说标识不说路径：对话中只出现数据集、区域、版本的 id，禁止出现文件路径。

工作流知识：
- 处理顺序不回退：标注 → 预处理 → 建模，按此顺序推进，不跳步、不反向。
- 标注五步（S05）：超像素分割 → 扩散 → 逐类确认 → 聚合 → 保存。
- 配方对比：基于 preprocess.compare 的返回逐项说明各配方的指标差异与适用场景，结论带算子名与版本号。"""
SEED_NAME = "initial-orchestrator"  # Name chosen for the initial orchestration skill.
_COLUMNS = ("id", "version_no", "name", "system_prompt", "tools_json", "examples_json", "status", "note", "created_at")
_TRANSITIONS = {("draft", "active"), ("draft", "retired"), ("active", "retired")}


def install_guards(db):
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS skill_one_active ON skill_version(status) WHERE status='active'")
    # Reject touching any content column, including assigning its existing value.
    immutable = ",".join(name for name in _COLUMNS if name != "status")
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS skill_content_immutable
        BEFORE UPDATE OF {immutable} ON skill_version
        BEGIN SELECT RAISE(ABORT, 'SKILL_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS skill_state_transition
        BEFORE UPDATE OF status ON skill_version
        WHEN NOT ((OLD.status='draft' AND NEW.status IN ('active','retired'))
                  OR (OLD.status='active' AND NEW.status='retired'))
        BEGIN SELECT RAISE(ABORT, 'SKILL_TRANSITION_INVALID'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS skill_state_insert
        BEFORE INSERT ON skill_version WHEN NEW.status NOT IN ('draft','active','retired')
        BEGIN SELECT RAISE(ABORT, 'SKILL_TRANSITION_INVALID'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS skill_no_delete
        BEFORE DELETE ON skill_version
        BEGIN SELECT RAISE(ABORT, 'SKILL_IMMUTABLE'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS skill_no_replace
        BEFORE INSERT ON skill_version
        WHEN EXISTS (SELECT 1 FROM skill_version WHERE id=NEW.id OR version_no=NEW.version_no)
        BEGIN SELECT RAISE(ABORT, 'SKILL_IMMUTABLE'); END""")


@contextmanager
def _write(db):
    """Serialize writers; retain an existing caller transaction and rollback scope."""
    owns_transaction = not db.in_transaction
    if owns_transaction:
        db.execute("BEGIN IMMEDIATE")
    savepoint = "skill_" + uuid4().hex
    db.execute(f"SAVEPOINT {savepoint}")
    try:
        yield
    except BaseException:
        db.execute(f"ROLLBACK TO {savepoint}")
        db.execute(f"RELEASE {savepoint}")
        if owns_transaction:
            db.rollback()
        raise
    else:
        db.execute(f"RELEASE {savepoint}")
        if owns_transaction:
            db.commit()


def _get(db, identifier):
    row = db.execute("SELECT " + ",".join(_COLUMNS) + " FROM skill_version WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise DataError("SKILL_NOT_FOUND", "SKILL 版本不存在")
    return dict(zip(_COLUMNS, row))


def active_skill(db):
    row = db.execute("SELECT id FROM skill_version WHERE status='active'").fetchone()
    if row is None:
        raise DataError("SKILL_NOT_ACTIVE", "没有 active SKILL，拒绝创建会话")
    return _get(db, row[0])


def _insert(db, *, version_no, name, system_prompt, tools_json, examples_json, status, note):
    identifier = str(uuid4())
    db.execute("INSERT INTO skill_version (" + ",".join(_COLUMNS) + ") VALUES (?,?,?,?,?,?,?,?,?)",
               (identifier, version_no, name, system_prompt, tools_json, examples_json, status, note,
                datetime.now(timezone.utc).isoformat()))
    return _get(db, identifier)


def ensure_seeded(db):
    from .tools import build_registry
    with _write(db):
        existing = db.execute("SELECT id FROM skill_version WHERE version_no=1").fetchone()
        if existing is not None:
            return _get(db, existing[0])
        # R8: v1, active and [] are explicit seed data, not runtime defaults.
        return _insert(db, version_no=1, name=SEED_NAME, system_prompt=SYSTEM_PROMPT,
                       tools_json=json.dumps(build_registry().snapshot(), ensure_ascii=False, separators=(",", ":")),
                       examples_json="[]", status="active", note=None)


def append_draft(db, *, name, system_prompt, tools_json, examples_json, note=None):
    """All new content is supplied explicitly; version/id/time are server rules."""
    from .tools import validate_snapshot
    if not all(isinstance(value, str) and value.strip() for value in (name, system_prompt)):
        raise DataError("SKILL_CONTENT_INVALID", "SKILL 名称与正文必须显式提供且非空")
    try:
        validate_snapshot(json.loads(tools_json))
        if not isinstance(json.loads(examples_json), list):
            raise ValueError("examples must be a list")
    except (TypeError, ValueError, KeyError):
        raise DataError("SKILL_CONTENT_INVALID", "SKILL 快照参数不合法") from None
    with _write(db):
        version = db.execute("SELECT COALESCE(MAX(version_no),0)+1 FROM skill_version").fetchone()[0]
        return _insert(db, version_no=version, name=name, system_prompt=system_prompt,
                       tools_json=tools_json, examples_json=examples_json, status="draft", note=note)


def transition(db, identifier, target):
    """Single validator for the complete R8 transition set, including activation."""
    with _write(db):
        current = _get(db, identifier)
        if (current["status"], target) not in _TRANSITIONS:
            raise DataError("SKILL_TRANSITION_INVALID", "SKILL 状态迁移不合法")
        if target == "active" and db.execute("SELECT 1 FROM skill_version WHERE status='active'").fetchone():
            raise DataError("SKILL_ACTIVE_EXISTS", "已有 active SKILL，激活被拒绝")
        try:
            db.execute("UPDATE skill_version SET status=? WHERE id=? AND status=?",
                       (target, identifier, current["status"]))
        except sqlite3.IntegrityError:
            raise DataError("SKILL_TRANSITION_INVALID", "SKILL 状态迁移被数据库约束拒绝") from None
        return _get(db, identifier)


def activate(db, identifier):
    return transition(db, identifier, "active")


def switch(db, identifier):
    with _write(db):
        if _get(db, identifier)["status"] != "draft":
            raise DataError("SKILL_TRANSITION_INVALID", "切换目标必须为 draft SKILL")
        old = active_skill(db)
        transition(db, old["id"], "retired")
        return activate(db, identifier)
