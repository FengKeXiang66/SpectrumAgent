from pathlib import Path
import re
import sqlite3

from backend.database import connect_database
from spectrumagent.agent.migrations import DDL, SETTING_KEYS, migrate
from spectrumagent.api.registry import DatasetRegistry


def schema(db, table):
    return db.execute(f"PRAGMA table_info({table})").fetchall()


def test_only_two_tables_match_card_ddl_and_comments_are_split_safe():
    card = (Path(__file__).resolve().parents[3] / "TASK-07-对话编排与标注JSON.md").read_text("utf-8")
    card_ddl = card.split("```sql\n", 1)[1].split("-- G2/G3", 1)[0]
    # Comments differ only to comply with the explicit ban on both semicolons.
    without_comments = lambda value: re.sub(r"--[^\n]*", "", value).strip()
    assert without_comments(DDL) == without_comments(card_ddl)
    for line in DDL.splitlines():
        if "--" in line:
            assert ";" not in line.split("--", 1)[1]
            assert "；" not in line.split("--", 1)[1]
    with sqlite3.connect(":memory:") as db, sqlite3.connect(":memory:") as expected:
        migrate(db)
        expected.executescript(card_ddl)
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"llm_settings", "llm_call"}
        for table in ("llm_settings", "llm_call"):
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


def test_startup_wires_only_g1_with_empty_values(tmp_path):
    database = tmp_path / "db.sqlite3"
    DatasetRegistry(database)
    with connect_database(database) as db:
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == dict.fromkeys(SETTING_KEYS, "")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not tables & {"annotation_draft", "agent_session", "agent_step", "skill_version", "training_mat"}
