from pathlib import Path
import re
import sqlite3

from backend.database import connect_database
from spectrumagent.agent.migrations import DDL, SETTING_KEYS, migrate
from spectrumagent.api.registry import DatasetRegistry


def schema(db, table):
    return db.execute(f"PRAGMA table_info({table})").fetchall()


def test_only_eight_tables_match_card_ddl_and_comments_are_split_safe():
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
        tables = {"llm_settings", "llm_call", "skill_version", "agent_session", "agent_round", "agent_step", "annotation_draft", "training_mat"}
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == tables
        for table in tables:
            assert schema(db, table) == schema(expected, table)
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == dict.fromkeys(SETTING_KEYS, "")


def test_idempotent_migration_preserves_configuration_and_audit(gateway_case):
    c = gateway_case
    with connect_database(c.database) as db:
        db.execute("INSERT INTO llm_call (id,model,prompt_sha256,latency_ms,status,created_at) "
                   "VALUES ('existing','mock','digest',0,'ok','fixture')")
        before = list(db.iterdump())
        migrate(db)
        migrate(db)
        assert list(db.iterdump()) == before
    DatasetRegistry(c.database)
    with connect_database(c.database) as db:
        assert list(db.iterdump()) == before


def test_startup_wires_g1_and_g3_with_empty_llm_values(tmp_path):
    database = tmp_path / "db.sqlite3"
    DatasetRegistry(database)
    with connect_database(database) as db:
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == dict.fromkeys(SETTING_KEYS, "")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "skill_version" in tables
        assert db.execute("SELECT version_no,status FROM skill_version").fetchall() == [(1, "active")]
        assert {"agent_session", "agent_round", "agent_step"} <= tables
        assert "annotation_draft" in tables
        assert "training_mat" in tables
