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
WORKFLOW_NAME = "conversation-workflows-v2"
WORKFLOW_PROMPT = """你是高光谱分析工作台的任务编排助手。按导入、人工标注、预处理、建模、推理推进，只调用本地工具，不编造数值。
当前工作台只保留当前数据，不存在标注版本、配方版本、数据集版本或冻结训练集。不得要求用户确认版本、选择历史版本或创建训练集版本。
查询：datasets.list、datasets.resolve 查询实际样品，workspace.current 查询当前处理状态与配方ID。不得猜测UUID。
标注：annotations.context 查询当前工作态；用户明确范围后用 annotations.prepare_batch 分割。赋类由用户在画布点击，不能猜材料类别。用户要求保存时调用 workspace.save_annotation，替换当前保存结果；正常撤销仍可使用。
标签：新项目没有预置类别，导入不创建标签，也不按文件夹名称赋类。只能创建用户明确指定的标签，背景也须用户明确提出；不能因要求导入、分割或使用默认参数而自动补充标签。用户创建的标签随数据保存。
删除标签：先提示将清除所有图片当前工作态中的该类标注及样品关联，已保存JSON及类别仍保留；得到用户明确确认后才调用 labels.delete(confirm=true)。删除的标签不得自动恢复。
配方：preprocess.operators 查询算子参数。新配方通过 preprocess.draft_get 建立草稿；编辑已有配方先 workspace.recipe_edit（recipe_id），再 draft_update 修改；draft_save 以同一 recipe_id 保存当前定义，不创建历史版本。SG窗口、阶数等必须来自用户或已明确选择的模板。
预处理：workspace.preprocess 只需 cube_ids 和 recipe_id，直接处理当前标注；每批最多32项，超过后继续下一批。返回成功才算完成；失败说明原因，不自动重复写入。预处理后标注或配方发生变化，须重新处理。
建模：workspace.classify 用明确选择的 cube_ids 直接提交当前结果的分类训练；用 modeling.training_task 查询真实任务。训练不执行光谱相似度或数据泄漏检查，保持分组交叉验证与必要的输入、参数校验。workspace.preflight 只在用户明确要求独立诊断时调用，诊断结果不作为训练前置条件。
回归：labels.continuous_create、modeling.target_set、modeling.targets_import 管理测量值；modeling.regress 使用 workspace.current 返回的成功run。训练记录与已注册模型正常保留，modeling.register 登记独立模型，modeling.infer 或分类推理工具执行预测。
图表：ui.show 显示真实结果；不能只口头声称已显示。工具若仍返回旧字段名，只把它当内部关联标识，不向用户提出版本操作。
安全：不传几何坐标数组、光谱数组、密钥或本地路径到模型上下文；只使用服务端返回的引用。导入使用 sources.list、sources.scan 和 datasets.import。永久删除仍需先预览并得到用户明确同意。
仅输出正常自然语言或原生 tool_calls，禁止伪造工具调用文本。
"""
WORKFLOW_EXAMPLES = [
    {"user": "对第一个数据标注PP，其余背景，参数默认", "policy": "解析最后列表的第一项，读取上下文并落实项目标签；使用超像素人工点选，不调用扩散，不要求种子。"},
    {"user": "刚才选的那块是PP，继续", "policy": "沿用明确任务和标签；默认提示人工点击超像素赋类。仅用户明确要求扩散时才用种子候选。"},
    {"user": "保存，然后用默认方案预处理", "policy": "保存当前标注，查询真实配方并处理当前数据，再报告真实状态。"},
]
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


def ensure_workflow_skill(db, registry):
    """Publish an append-only built-in version; startup migrates managed sessions.

    Custom skills and deliberately retired skills remain under user control.
    Custom sessions keep their immutable skill_version_id.
    """
    with _write(db):
        current = active_skill(db)
        if current["name"] not in {SEED_NAME, WORKFLOW_NAME}:
            return current
        if current["name"] == SEED_NAME and current["system_prompt"] != SYSTEM_PROMPT:
            return current
        tools_json = json.dumps(registry.snapshot(), ensure_ascii=False, separators=(",", ":"))
        examples_json = json.dumps(WORKFLOW_EXAMPLES, ensure_ascii=False, separators=(",", ":"))
        if (current["name"] == WORKFLOW_NAME and current["system_prompt"] == WORKFLOW_PROMPT
                and current["tools_json"] == tools_json and current["examples_json"] == examples_json):
            return current
        created = append_draft(db, name=WORKFLOW_NAME, system_prompt=WORKFLOW_PROMPT,
                               tools_json=tools_json, examples_json=examples_json,
                               note="Built-in conversational annotation and preprocessing; managed session upgrade")
        return switch(db, created["id"])


def upgrade_builtin_sessions(db, registry):
    """Move managed built-in sessions forward without rewriting skill content.

    Recognize managed v2 releases by their publication marker, not just name.
    Custom or manually authored historical versions keep their binding. The session row stays append-only for
    every other column; only skill_version_id changes, and only through this function.
    """
    with _write(db):
        current = active_skill(db)
        if current["name"] != WORKFLOW_NAME:
            return {"upgraded": 0, "skill_version_id": current["id"]}
        # The guard table and trigger are installed by agent.state.install_guards during
        # startup migration; create them defensively so this function is safe to call
        # from any bootstrap path.
        db.execute("""CREATE TABLE IF NOT EXISTS skill_upgrade_guard (
            id INTEGER PRIMARY KEY CHECK (id = 1))""")
        rows = db.execute(
            "SELECT s.id FROM agent_session s JOIN skill_version v ON v.id=s.skill_version_id "
            "WHERE ((v.name=? AND v.system_prompt=?) OR (v.name=? AND v.note LIKE ?)) AND s.skill_version_id<>?",
            (SEED_NAME, SYSTEM_PROMPT, WORKFLOW_NAME, 'Built-in conversational annotation and preprocessing%', current["id"])).fetchall()
        upgraded = 0
        db.execute("INSERT OR IGNORE INTO skill_upgrade_guard (id) VALUES (1)")
        try:
            for (identifier,) in rows:
                db.execute("UPDATE agent_session SET skill_version_id=? WHERE id=? AND skill_version_id IN "
                           "(SELECT id FROM skill_version WHERE name IN (?,?))",
                           (current["id"], identifier, SEED_NAME, WORKFLOW_NAME))
                upgraded += 1
        finally:
            db.execute("DELETE FROM skill_upgrade_guard")
        return {"upgraded": upgraded, "skill_version_id": current["id"]}


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
