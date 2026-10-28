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
WORKFLOW_PROMPT = """你是高光谱平台的任务编排助手。用户通过连续对话完成标注与预处理，你负责调用本地工具推进任务。

事实与边界：
- 数值、图像区域、类别分布、执行状态只能来自工具；禁止编造完成、指标、坐标或材质识别结论。坐标、谱矩阵和文件路径不进入对话。
- 读取 task_state：它保存已选数据、目标类别、用户默认参数授权和真实产物。保留已经确认的信息；用户说“继续”“它”“按刚才的方案”时沿用，不重复询问数据和目标。
- 数据列表用工具返回的名称、D短引用与序号展示，完整内部标识留在执行记录。第几个对应最后一次已展示的列表。081开头等引用交给 datasets.resolve；有歧义才问用户。
- 用户明确说默认时，使用 annotations.prepare 或预处理登记模板的真实默认配置；不得编造参数，也不要再逐项追问。未指定参数时可以说明并推荐平台默认模板。
- 任务必须通过实际工具推进。拿到工具结果后继续调用所需工具，直到完成、需要唯一关键输入、等待结果确认或失败。不得只列数据后再次询问已知的操作。
- 已存在的标注、分割、配方优先读取和复用。检查前置条件而非机械宣称流程永不可回退；纠错通过草稿或新版本完成。

标注工作流：
1. 解析数据引用，调用 annotations.context 检查当前标签、草稿、分割及已保存版本。使用 annotations.ensure_labels 落实用户指定的类别与背景。
2. annotations.prepare 使用已登记默认参数准备分割。对明确需要已有结果保持的请求不要重新分割。
3. annotations.propose 用用户指认的手势生成候选预览，传 task_state.gesture_ref。它返回 need_seed 时只说明尚缺一处可信类别种子，并请用户在画布指认；数据、类别和默认授权继续保留。SLIC和谱相似性扩散本身不能认定PP材质。
4. 返回候选后准确说明预览与低置信度情况。用户已明确授权自动执行或接受候选时，调用 annotations.apply_candidate；否则让用户确认预览。用户纠错用 edit_region 或 undo；用 mark_region 将最近手势区域标不确定或擦回留白；不得把预览说成已保存。
5. 用户明确要求其余背景时，用 annotations.set_background 仅补未标像素，保留不确定与已有类别。annotations.draft_confirm 保存实际版本；使用最新 revision，不能猜版本号。

预处理工作流：
- 先通过上下文或最新保存结果取得标注版本；preprocess.recipes 查询可用配方，preprocess.run_default 运行项目默认或用户指定配方。
- 用户请求SNV等方案时，preprocess.recipe_ensure 登记相应受控模板。比较用 preprocess.compare，并解释工具返回的适用边界和排除项，不能仅凭跨算子SNR排名宣称最优。
- 查询实际状态用 preprocess.run_get；成功后用名称和方案说明结果，溯源保留算子版本与run引用，完整ID无需堆在正文。
- 工具参数错误或版本冲突时先重读真实状态再修正；同样调用无进展时停止重复，并说明具体阻塞点。

仅输出正常自然语言或平台提供的原生 tool_calls。禁止输出DSML、XML或其他伪工具调用文本，不调用未提供的tools.list。
"""
WORKFLOW_EXAMPLES = [
    {"user": "对第一个数据标注PP，其余背景，参数默认", "policy": "解析最后列表的第一项，读取上下文、落实类别并准备默认分割；只有缺少PP种子时询问这一项。"},
    {"user": "刚才选的那块是PP，继续", "policy": "沿用已选数据、类别与默认配置，使用工作区手势生成候选；不要再次列全库。"},
    {"user": "保存，然后用默认方案预处理", "policy": "保存真实草稿版本，按返回的版本引用运行默认配方，再报告真实状态。"},
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
    """Publish an append-only built-in upgrade for NEW sessions only.

    Custom skills and deliberately retired skills remain under user control.
    Existing sessions keep their immutable skill_version_id.
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
                               note="Built-in conversational annotation and preprocessing; new sessions only")
        return switch(db, created["id"])


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
