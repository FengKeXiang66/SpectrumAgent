"""12.2: immutable versions, exact R8 seed, atomic activation and restart."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from threading import Barrier

import pytest

from backend.database import connect_database
from spectrumagent.agent import skill
from spectrumagent.agent.tools import build_registry
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError


def draft(db):
    seed = skill.ensure_seeded(db)
    return skill.append_draft(db, name="explicit-test-version", system_prompt=seed["system_prompt"],
                              tools_json=seed["tools_json"], examples_json="[]", note="explicit fixture")


def rows(db):
    return db.execute("SELECT * FROM skill_version ORDER BY version_no").fetchall()


def test_seed_prompt_is_verbatim_card_and_all_required_values_have_sources(gateway_case):
    card = (Path(__file__).resolve().parents[3] / "TASK-07-对话编排与标注JSON.md").read_text("utf-8")
    expected = "\n".join(re.findall(r"^  > ?(.*)$", card, re.M))
    assert expected == skill.SYSTEM_PROMPT
    for phrase in ("只编排不产数", "坐标与谱值禁传", "不确定就反问", "结论带溯源", "只说标识不说路径",
                   "标注 → 预处理 → 建模", "超像素分割 → 扩散 → 逐类确认 → 聚合 → 保存", "preprocess.compare"):
        assert phrase in expected
    with connect_database(gateway_case.database) as db:
        seeded = skill.active_skill(db)
        assert seeded == skill.ensure_seeded(db)
        assert seeded["system_prompt"] == expected
        assert seeded["examples_json"] == "[]"
        assert seeded["version_no"] == 1 and seeded["status"] == "active"
        assert seeded["name"] == "initial-orchestrator" and seeded["note"] is None
        assert len(seeded["id"]) > 0 and datetime.fromisoformat(seeded["created_at"]).tzinfo is not None
        assert json.loads(seeded["tools_json"]) == build_registry().snapshot()
        assert all(seeded[name] is not None for name in (
            "id", "version_no", "name", "system_prompt", "tools_json", "examples_json", "status", "created_at"))


def test_restart_idempotent_and_never_reactivates_retired_seed(gateway_case):
    database = gateway_case.database
    with connect_database(database) as db:
        seed = skill.active_skill(db)
        second = draft(db)
        skill.switch(db, second["id"])
        before = rows(db)
    for _ in range(2):
        DatasetRegistry(database)
        with connect_database(database) as db:
            assert skill.ensure_seeded(db)["status"] == "retired"
            assert rows(db) == before
            assert skill.active_skill(db)["id"] == second["id"]
            assert db.execute("SELECT COUNT(*) FROM skill_version WHERE version_no=1").fetchone()[0] == 1
            assert seed["system_prompt"] == second["system_prompt"]


def test_no_active_parser_gate_and_startup_does_not_invent_replacement(gateway_case):
    database = gateway_case.database
    with connect_database(database) as db:
        skill.transition(db, skill.active_skill(db)["id"], "retired")
        before = rows(db)
        with pytest.raises(DataError) as caught:
            skill.active_skill(db)
        assert caught.value.code == "SKILL_NOT_ACTIVE"
    DatasetRegistry(database)
    with connect_database(database) as db:
        with pytest.raises(DataError, match="拒绝创建会话"):
            skill.active_skill(db)
        assert rows(db) == before


@pytest.mark.parametrize("column,new_value", [
    ("id", "replacement-id"), ("version_no", 99), ("name", "replacement-name"),
    ("system_prompt", "replacement-prompt"), ("tools_json", "[]"), ("examples_json", "[{}]"),
    ("note", "replacement-note"), ("created_at", "replacement-time"),
])
def test_content_update_rejected_by_database_not_just_service(gateway_case, column, new_value):
    with connect_database(gateway_case.database) as db:
        seeded = skill.active_skill(db)
        before = rows(db)
        with pytest.raises(sqlite3.IntegrityError, match="SKILL_IMMUTABLE"):
            db.execute(f"UPDATE skill_version SET {column}=? WHERE id=?", (new_value, seeded["id"]))
        assert rows(db) == before


def test_content_update_combined_with_legal_transition_and_delete_are_rejected(gateway_case):
    with connect_database(gateway_case.database) as db:
        seeded = skill.active_skill(db)
        with pytest.raises(sqlite3.IntegrityError, match="SKILL_IMMUTABLE"):
            db.execute("UPDATE skill_version SET status='retired',name='changed' WHERE id=?", (seeded["id"],))
        with pytest.raises(sqlite3.IntegrityError, match="SKILL_IMMUTABLE"):
            db.execute("DELETE FROM skill_version WHERE id=?", (seeded["id"],))
        assert skill.active_skill(db) == seeded


def test_noop_content_update_is_also_forbidden(gateway_case):
    with connect_database(gateway_case.database) as db:
        before = rows(db)
        with pytest.raises(sqlite3.IntegrityError, match="SKILL_IMMUTABLE"):
            db.execute("UPDATE skill_version SET name=name")
        assert rows(db) == before


def test_append_only_content_explicit_monotonic_versions(gateway_case):
    with connect_database(gateway_case.database) as db:
        initial = skill.active_skill(db)
        second, third = draft(db), draft(db)
        assert [initial["version_no"], second["version_no"], third["version_no"]] == [1, 2, 3]
        assert len({initial["id"], second["id"], third["id"]}) == 3
        assert second["status"] == third["status"] == "draft"
        assert second["name"] == "explicit-test-version" and second["note"] == "explicit fixture"
        assert second["system_prompt"] == initial["system_prompt"]
        assert skill.active_skill(db) == initial


@pytest.mark.parametrize("target", ["active", "retired"])
def test_legal_draft_transitions(gateway_case, target):
    with connect_database(gateway_case.database) as db:
        skill.transition(db, skill.active_skill(db)["id"], "retired")
        version = draft(db)
        updated = skill.transition(db, version["id"], target)
        assert updated == {**version, "status": target}


@pytest.mark.parametrize("target", ["draft", "active", "retired", "unknown"])
def test_retired_terminal_service_and_sql(gateway_case, target):
    with connect_database(gateway_case.database) as db:
        identifier = skill.active_skill(db)["id"]
        skill.transition(db, identifier, "retired")
        before = rows(db)
        with pytest.raises(DataError) as caught:
            skill.transition(db, identifier, target)
        assert caught.value.code == "SKILL_TRANSITION_INVALID"
        with pytest.raises(sqlite3.IntegrityError, match="SKILL_TRANSITION_INVALID"):
            db.execute("UPDATE skill_version SET status=? WHERE id=?", (target, identifier))
        assert rows(db) == before


def test_activate_does_not_switch_existing_active(gateway_case):
    with connect_database(gateway_case.database) as db:
        original = skill.active_skill(db)
        second = draft(db)
        with pytest.raises(DataError) as caught:
            skill.activate(db, second["id"])
        assert caught.value.code == "SKILL_ACTIVE_EXISTS"
        assert skill.active_skill(db) == original
        assert db.execute("SELECT status FROM skill_version WHERE id=?", (second["id"],)).fetchone()[0] == "draft"


def test_parallel_activation_exactly_one_wins_second_fails(gateway_case):
    database = gateway_case.database
    with connect_database(database) as db:
        skill.transition(db, skill.active_skill(db)["id"], "retired")
        versions = [draft(db)["id"], draft(db)["id"]]
    barrier = Barrier(2)
    def activate_one(identifier):
        with connect_database(database) as db:
            barrier.wait()
            try:
                skill.activate(db, identifier)
                return identifier, "active"
            except DataError as error:
                return identifier, error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate_one, versions))
    assert sorted(status for _, status in results) == ["SKILL_ACTIVE_EXISTS", "active"]
    with connect_database(database) as db:
        winner = skill.active_skill(db)["id"]
        assert dict(results)[winner] == "active"
        assert db.execute("SELECT COUNT(*) FROM skill_version WHERE status='active'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM skill_version WHERE status='draft'").fetchone()[0] == 1


def test_unique_index_catches_raw_sql_second_active(gateway_case):
    with connect_database(gateway_case.database) as db:
        second = draft(db)
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            db.execute("UPDATE skill_version SET status='active' WHERE id=?", (second["id"],))
        assert skill.active_skill(db)["version_no"] == 1


def test_switch_atomic_external_observers_never_see_zero_or_two_active(gateway_case):
    database = gateway_case.database
    observed = []
    with connect_database(database) as db:
        original = skill.active_skill(db)
        second = draft(db)
        def observe():
            with connect_database(database) as observer:
                observed.append(observer.execute("SELECT id FROM skill_version WHERE status='active'").fetchall())
            return 1
        db.create_function("observe_active", 0, observe)
        db.execute("""CREATE TRIGGER test_observe_switch AFTER UPDATE OF status ON skill_version
                      BEGIN SELECT observe_active(); END""")
        updated = skill.switch(db, second["id"])
        assert observed == [[(original["id"],)], [(original["id"],)]]
        assert updated == {**second, "status": "active"}
        assert skill.active_skill(db) == updated
        assert db.execute("SELECT status FROM skill_version WHERE id=?", (original["id"],)).fetchone()[0] == "retired"


def test_switch_failure_rolls_back_old_retirement(gateway_case):
    with connect_database(gateway_case.database) as db:
        original = skill.active_skill(db)
        second = draft(db)
        db.execute("""CREATE TRIGGER test_fail_new_active BEFORE UPDATE OF status ON skill_version
                      WHEN NEW.status='active' BEGIN SELECT RAISE(ABORT,'injected'); END""")
        before = rows(db)
        with pytest.raises(DataError, match="数据库约束拒绝"):
            skill.switch(db, second["id"])
        assert rows(db) == before and skill.active_skill(db) == original


def test_switch_preserves_outer_transaction_and_invalid_target_is_unchanged(gateway_case):
    with connect_database(gateway_case.database) as db:
        original = skill.active_skill(db)
        second = draft(db)
        before = rows(db)
        with pytest.raises(DataError):
            skill.switch(db, original["id"])
        assert rows(db) == before
        db.execute("BEGIN IMMEDIATE")
        skill.switch(db, second["id"])
        assert db.in_transaction and skill.active_skill(db)["id"] == second["id"]
        db.rollback()
        assert rows(db) == before and skill.active_skill(db) == original


def test_unknown_version_and_malformed_content_fail_before_writes(gateway_case):
    with connect_database(gateway_case.database) as db:
        before = rows(db)
        with pytest.raises(DataError) as caught:
            skill.activate(db, "missing")
        assert caught.value.code == "SKILL_NOT_FOUND"
        with pytest.raises(DataError) as caught:
            skill.append_draft(db, name="valid", system_prompt="explicit", tools_json='[{}]', examples_json="[]")
        assert caught.value.code == "SKILL_CONTENT_INVALID"
        assert rows(db) == before
