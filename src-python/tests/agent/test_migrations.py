from pathlib import Path
import re
import sqlite3
import pytest

from backend.database import connect_database
from spectrumagent.agent.migrations import DDL, migrate
from spectrumagent.api.registry import DatasetRegistry


def schema(db, table):
    return db.execute(f"PRAGMA table_info({table})").fetchall()


def test_only_nine_tables_match_card_ddl_and_comments_are_split_safe():
    card = (Path(__file__).resolve().parents[3] / "TASK-07-对话编排与标注JSON.md").read_text("utf-8")
    sql = card.split("```sql\n", 1)[1].split("\n```", 1)[0]
    card_ddl = sql
    # Comments differ only to comply with the explicit ban on both semicolons.
    without_comments = lambda value: re.sub(r"--[^\n]*", "", value).strip()
    assert without_comments(DDL.split("-- G3：SKILL", 1)[0]) == without_comments(sql.split("-- G2/G3", 1)[0])
    skill_ddl = sql[sql.index("-- G3：SKILL"):].split("-- G5：", 1)[0]
    assert DDL[DDL.index("-- G3：SKILL"):].split("-- G2/G3", 1)[0].strip() == skill_ddl.replace("；", "，").strip()
    agent_ddl = sql[sql.index("-- G2/G3"):].split("-- G3：SKILL", 1)[0]
    assert DDL[DDL.index("-- G2/G3"):].split("-- G5：", 1)[0].strip() == agent_ddl.replace("；", "，").strip()
    assert DDL[DDL.index("-- G5："):].strip() == sql[sql.index("-- G5："):].replace("；", "，").strip()
    for line in DDL.splitlines():
        if "--" in line:
            assert ";" not in line.split("--", 1)[1]
            assert "；" not in line.split("--", 1)[1]
    with sqlite3.connect(":memory:") as db, sqlite3.connect(":memory:") as expected:
        migrate(db)
        expected.executescript(card_ddl)
        tables = {"llm_settings", "llm_call", "skill_version", "agent_session", "agent_round", "agent_step", "annotation_draft", "training_mat", "agent_plan_action", "skill_upgrade_guard"}
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == tables
        for table in tables:
            assert schema(db, table) == schema(expected, table)
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == {"base_url": "", "model": "", "temperature": "",
            "max_tokens": "", "timeout_ms": "", "egress_enabled": "1"}


def test_idempotent_migration_preserves_configuration_and_audit(gateway_case):
    c = gateway_case
    with connect_database(c.database) as db:
        db.execute("INSERT INTO llm_call (id,model,prompt_sha256,latency_ms,status,created_at) "
                   "VALUES ('existing','mock','digest',0,'ok','fixture')")
        before = sorted(db.iterdump())
        migrate(db)
        migrate(db)
        assert sorted(db.iterdump()) == before
    DatasetRegistry(c.database)
    with connect_database(c.database) as db:
        assert sorted(db.iterdump()) == before


def test_startup_wires_g1_and_g3_with_empty_llm_values(tmp_path):
    database = tmp_path / "db.sqlite3"
    DatasetRegistry(database)
    with connect_database(database) as db:
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == {"base_url": "", "model": "", "temperature": "",
            "max_tokens": "", "timeout_ms": "", "egress_enabled": "1"}
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "skill_version" in tables
        assert db.execute("SELECT version_no,status FROM skill_version").fetchall() == [(1, "active")]
        assert {"agent_session", "agent_round", "agent_step"} <= tables
        assert "annotation_draft" in tables
        assert "training_mat" in tables
        assert "agent_plan_action" in tables

def test_upgrade_seeds_enabled_without_overwriting_existing_values():
    with sqlite3.connect(":memory:") as db:
        migrate(db)
        db.execute("DELETE FROM llm_settings WHERE key='egress_enabled'")
        db.execute("UPDATE llm_settings SET value='existing-model' WHERE key='model'")
        migrate(db)
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == {
            "base_url": "", "model": "existing-model", "temperature": "",
            "max_tokens": "", "timeout_ms": "", "egress_enabled": "1"}
        db.execute("UPDATE llm_settings SET value='0' WHERE key='egress_enabled'")
        migrate(db)
        migrate(db)
        assert db.execute("SELECT value FROM llm_settings WHERE key='egress_enabled'").fetchone() == ("0",)
        assert db.execute("SELECT value FROM llm_settings WHERE key='model'").fetchone() == ("existing-model",)


@pytest.mark.parametrize("target", ["running", "done", "error"])
def test_old_round_trigger_and_missing_plan_table_upgrade(gateway_case, target):
    from spectrumagent.agent.state import AgentStore
    store = AgentStore(gateway_case.database)
    session = store.create_session()
    row = store.new_round(session["id"], "升级路径", [], "plan_check")
    with connect_database(gateway_case.database) as db:
        db.execute("DROP TABLE agent_plan_action")
        db.execute("DROP TRIGGER agent_round_transition")
        db.execute("""CREATE TRIGGER agent_round_transition BEFORE UPDATE OF status ON agent_round
            WHEN NOT ((OLD.status='running' AND NEW.status IN ('human_check','done','error'))
                   OR (OLD.status='human_check' AND NEW.status IN ('running','done','error')))
            BEGIN SELECT RAISE(ABORT,'AGENT_TRANSITION_INVALID'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="AGENT_TRANSITION_INVALID"):
            db.execute("UPDATE agent_round SET status=? WHERE id=?", (target, row["id"]))
        migrate(db)
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_plan_action'").fetchone()
        db.execute("UPDATE agent_round SET status=? WHERE id=?", (target, row["id"]))
        assert db.execute("SELECT status FROM agent_round WHERE id=?", (row["id"],)).fetchone() == (target,)


def test_plan_actions_are_immutable_in_every_column_and_cannot_be_deleted(gateway_case):
    from spectrumagent.agent.state import AgentStore
    store = AgentStore(gateway_case.database)
    session = store.create_session()
    row = store.new_round(session["id"], "审计", [], "plan_check")
    store.add_plan_action(row, "reject", None, "原始原因")
    with connect_database(gateway_case.database) as db:
        before = db.execute("SELECT * FROM agent_plan_action").fetchall()
        for column in ["id", "session_id", "round_id", "action", "seq_ref", "reason", "created_at"]:
            with pytest.raises(sqlite3.IntegrityError, match="AGENT_IMMUTABLE"):
                db.execute(f"UPDATE agent_plan_action SET {column}={column}")
        with pytest.raises(sqlite3.IntegrityError, match="AGENT_IMMUTABLE"):
            db.execute("DELETE FROM agent_plan_action")
        assert db.execute("SELECT * FROM agent_plan_action").fetchall() == before
