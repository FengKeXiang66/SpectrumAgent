"""10.1 acceptance against real sqlite3; no database or HTTP stubs."""
import colorsys
from pathlib import Path
import re
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.annotation.labels import CustomRequest, LabelStore, label_sort_order, plastic_catalog
from spectrumagent.annotation.migrations import DDL, default_project_id
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.app import create_app

sys.path.insert(0, str(Path(__file__).parents[1] / "fixtures"))
from cubes import cube


@pytest.fixture
def ledger(tmp_path):
    database = tmp_path / "store.sqlite3"
    DatasetRegistry(database)
    return database


def test_two_startups_backfill_existing_registry_without_replacing_payload(tmp_path):
    paths = AppPaths(tmp_path / "app")
    paths.database.parent.mkdir(parents=True)
    with connect_database(paths.database) as db:
        db.execute("CREATE TABLE dataset_registry (id TEXT PRIMARY KEY, header_key TEXT NOT NULL, raw INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(header_key,raw))")
        db.execute("INSERT INTO dataset_registry VALUES ('legacy','legacy.hdr',0,'{\"untouched\":true}')")
    snapshots = []
    for _ in range(2):
        with TestClient(create_app(paths, EngineIdentity())):
            with connect_database(paths.database) as db:
                assert "project_id" in {row[1] for row in db.execute("PRAGMA table_info(dataset_registry)")}
                snapshots.append({table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                                  for table in ("project", "label_schema", "label", "dataset_registry")})
                assert db.execute("SELECT project_id FROM dataset_registry").fetchone()[0] == default_project_id(db)
                assert db.execute("SELECT payload FROM dataset_registry").fetchone()[0] == '{"untouched":true}'
                assert db.execute("SELECT count(*) FROM annotation").fetchone()[0] == 0
    assert snapshots[0] == snapshots[1]
    assert [len(snapshots[0][table]) for table in ("project", "label_schema", "label")] == [1, 1, 4]


@pytest.mark.parametrize("background,key,allowed", [(1, 0, True)] + [(0, key, True) for key in range(1, 10)] + [(0, 0, False), (0, None, True), (0, 10, False)])
def test_shortcut_table_check(ledger, background, key, allowed):
    with connect_database(ledger) as db:
        row = list(db.execute("SELECT * FROM label LIMIT 1").fetchone())
        db.execute("DELETE FROM label")
        row[7], row[9] = key, background
        if allowed:
            db.execute("INSERT INTO label VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        else:
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                db.execute("INSERT INTO label VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)


def test_shortcut_unique_and_multiple_nulls(ledger):
    with connect_database(ledger) as db:
        row = list(db.execute("SELECT * FROM label WHERE code='PE'").fetchone())
        row[0], row[3] = "second", "SECOND"
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            db.execute("INSERT INTO label VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        row[7] = None
        db.execute("INSERT INTO label VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        row[0], row[3] = "third", "THIRD"
        db.execute("INSERT INTO label VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        assert db.execute("SELECT count(*) FROM label WHERE shortcut_key IS NULL").fetchone()[0] == 2


def test_ddl_matches_card_verbatim():
    card = (Path(__file__).parents[3] / "TASK-04-标注L1.md").read_text("utf-8")
    assert DDL.strip() == card.split("```sql\n", 1)[1].split("\n```", 1)[0].strip()


def test_version_params_and_foreign_keys(ledger):
    with connect_database(ledger) as db:
        for _ in range(2):
            with connect_database(ledger) as other:
                assert other.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute("INSERT INTO annotation (id,cube_id,version_id,granularity,label_id,pixel_count,created_at) VALUES ('a','c','missing','pixel','l',1,'now')")
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,created_at) VALUES ('v','c',1,'snap',1,0,'now')")
        assert ("annotation_version", "version_id", "id") in {(row[2], row[3], row[4]) for row in db.execute("PRAGMA foreign_key_list(annotation)")}
        assert "'scene'" in db.execute("SELECT sql FROM sqlite_master WHERE name='annotation'").fetchone()[0]
        assert db.execute("SELECT count(*) FROM annotation WHERE granularity='scene'").fetchone()[0] == 0


def test_every_application_connection_enables_foreign_keys(tmp_path, monkeypatch):
    import backend.database as connections
    original = connections.open_database
    checks = []
    def checked(*args, **kwargs):
        db = original(*args, **kwargs)
        checks.append(db.execute("PRAGMA foreign_keys").fetchone()[0])
        return db
    monkeypatch.setattr(connections, "open_database", checked)
    monkeypatch.setattr("backend.app.open_database", checked)
    paths = AppPaths(tmp_path / "app")
    identity = EngineIdentity()
    with TestClient(create_app(paths, identity)) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        project_id = client.get("/api/v1/projects").json()[0]["id"]
        client.get("/api/v1/labels", params={"project_id": project_id})
        header = cube(tmp_path / "source")[0]
        response = client.post("/api/v1/datasets/import", json={"path": str(header)})
        assert response.status_code == 200
        identifier = response.json()["datasets"][0]["id"]
        assert client.get(f"/api/v1/datasets/{identifier}").status_code == 200
        with connect_database(paths.database) as db:
            assert db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (identifier,)).fetchone()[0] == project_id
            assert db.execute("SELECT count(*) FROM annotation WHERE granularity='scene'").fetchone()[0] == 0
    assert len(checks) >= 6 and set(checks) == {1}


def test_catalog_colors_and_names_match_card():
    card = (Path(__file__).parents[3] / "TASK-04-标注L1.md").read_text("utf-8")
    section = card.split("### 4.4", 1)[1].split("### 5.1", 1)[0]
    table = section.split("初始色值（均可被项目内覆盖）：", 1)[1].split("\n- 目录色值", 1)[0]
    expected = re.findall(r"\b([A-Z]+) `(#\w{6})`", table)
    catalog = plastic_catalog()
    assert len(catalog) == len({row["code"] for row in catalog}) == 21
    assert [(row["code"], row["color_hex"]) for row in catalog[3:]] == expected
    assert [row["color_hex"] for row in catalog[:3]] == ["#5aa469", "#c98a3c", "#2f7fb0"]
    for j, (_, color) in enumerate(expected):
        rgb = colorsys.hls_to_rgb(j * 20 / 360, 0.45, 0.55)
        assert "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb) == color
    names = {row["code"]: row["name"] for row in catalog}
    assert names["PS"] == "聚苯乙烯" and names["PVC"] == "聚氯乙烯"


def test_custom_empty_project_sort_and_precise_schema_match(ledger):
    with connect_database(ledger) as db:
        db.execute("INSERT INTO project VALUES ('other','测试项目','now',NULL)")
        db.execute("INSERT INTO label_schema VALUES ('other-schema','other','材料','材料','enum',NULL,NULL,'now')")
        assert label_sort_order(db, "other", "X", "custom") == 1
    result = LabelStore(ledger).add(CustomRequest(project_id="other", code="X", name="X", tree_path="材料/塑料/X", color_hex="#b23434"))
    assert result["schema_id"] == "other-schema" and result["sort_order"] == 1


def test_schema_and_seed_identity_survive_restart(label_api):
    client, paths, project_id = label_api
    before = client.get("/api/v1/labels", params={"project_id": project_id}).json()
    schema = before[0]
    assert (schema["tree_path"], schema["name"], schema["field_type"]) == ("材料", "材料", "enum")
    expected = {"BG": (0, "#9aa7b2", 0), "PE": (1, "#5aa469", 1), "PET": (2, "#c98a3c", 2), "PP": (3, "#2f7fb0", 3)}
    for label in schema["labels"]:
        assert (label["sort_order"], label["color_hex"], label["shortcut_key"]) == expected[label["code"]]
        assert label["tree_path"] == f"材料/塑料/{label['code']}" and label["schema_id"] == schema["id"]
    DatasetRegistry(paths.database)
    assert LabelStore(paths.database).tree(project_id) == before
