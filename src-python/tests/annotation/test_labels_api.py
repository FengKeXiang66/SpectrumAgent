from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.database import connect_database
from spectrumagent.annotation.labels import plastic_catalog


def custom(project_id, **extra):
    return dict(project_id=project_id, code="CUSTOM", name="自定义材料", tree_path="材料/塑料/CUSTOM", color_hex="#b23434", **extra)


def test_post_three_shapes_and_tree(label_api):
    client, paths, project_id = label_api
    schema = client.post("/api/v1/labels", json={"project_id": project_id, "schema": {"name": "温度", "tree_path": "温度", "field_type": "continuous", "unit": "℃", "config": {"min": 0, "max": 100}}})
    assert schema.status_code == 201
    assert schema.json()["config"] == {"min": 0, "max": 100}
    # Reverse selection order must not change fixed catalog ordinal.
    catalog = client.post("/api/v1/labels", json={"project_id": project_id, "from_catalog": "plastic", "codes": ["PVC", "PS"]})
    assert catalog.status_code == 201
    assert [(row["code"], row["tree_path"], row["sort_order"]) for row in catalog.json()] == [("PVC", "材料/塑料/PVC", 5), ("PS", "材料/塑料/PS", 4)]
    added = client.post("/api/v1/labels", json=custom(project_id))
    assert added.status_code == 201 and added.json()["sort_order"] == 6
    tree = client.get("/api/v1/labels", params={"project_id": project_id}).json()
    assert len(tree) == 2 and sum(len(row["labels"]) for row in tree) == 7
    with connect_database(paths.database) as db:
        assert db.execute("SELECT count(*) FROM annotation").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM sample_spectrum").fetchone()[0] == 0


@pytest.mark.parametrize("field_type", ["enum", "bool", "continuous", "ordinal"])
def test_schema_types(label_api, field_type):
    client, _, project_id = label_api
    result = client.post("/api/v1/labels", json={"project_id": project_id, "schema": {"name": field_type, "tree_path": field_type, "field_type": field_type}})
    assert result.status_code == 201 and result.json()["field_type"] == field_type


@pytest.mark.parametrize("change", [
    {"from_catalog": "plastic", "codes": ["PS"]}, {"schema": {"name": "X", "tree_path": "X", "field_type": "enum"}},
    {"color_hex": "bad"}, {"shortcut_key": 10}, {"shortcut_key": -1}, {"shortcut_key": 0}, {"shortcut_key": 1},
    {"tree_path": "缺失/塑料/CUSTOM"}, {"tree_path": "材料错/塑料/CUSTOM"}, {"tree_path": ""}, {"tree_path": "   "},
    {"schema_id": "forbidden"}, {"sort_order": 100}, {"shortcut_key": True}, {"code": "PE"},
])
def test_custom_invalid_inputs_are_field_errors(label_api, change):
    client, _, project_id = label_api
    body = custom(project_id)
    body.update(change)
    result = client.post("/api/v1/labels", json=body)
    assert result.status_code == 422
    payload = result.json()
    assert set(payload) == {"error", "detail", "context"}
    assert all(field["field"] and field["message"] for field in payload["context"]["fields"])


@pytest.mark.parametrize("missing", ["project_id", "code", "name", "tree_path", "color_hex"])
def test_custom_missing_fields(label_api, missing):
    client, _, project_id = label_api
    body = custom(project_id)
    del body[missing]
    assert client.post("/api/v1/labels", json=body).status_code == 422


@pytest.mark.parametrize("body", [
    {}, {"from_catalog": "plastic"}, {"from_catalog": "plastic", "codes": []},
    {"from_catalog": "plastic", "codes": ["PS"], "tree_path": "材料/塑料/PS"},
    {"from_catalog": "plastic", "codes": ["PS"], "schema": {"name": "X", "tree_path": "X", "field_type": "enum"}},
    {"schema": {"name": "X", "tree_path": "材料/塑料", "field_type": "enum"}},
    {"schema": {"name": "X", "tree_path": "X", "field_type": "unsupported"}},
])
def test_missing_and_mixed_contracts(label_api, body):
    client, _, project_id = label_api
    assert client.post("/api/v1/labels", json={"project_id": project_id, **body}).status_code == 422


def test_catalog_duplicates_and_unknown_are_atomic(label_api):
    client, _, project_id = label_api
    for codes in (["PS", "PS"], ["PS", "MISSING"], ["PS", "PE"]):
        result = client.post("/api/v1/labels", json={"project_id": project_id, "from_catalog": "plastic", "codes": codes})
        assert result.status_code == 422
        tree = client.get("/api/v1/labels", params={"project_id": project_id}).json()
        assert len(tree[0]["labels"]) == 4


def test_catalog_readonly_and_null_shortcuts_above_nine_classes(label_api):
    client, _, project_id = label_api
    before = client.get("/api/v1/catalog/plastic").json()
    assert before == plastic_catalog() and len(before) == 21
    codes = [row["code"] for row in before[3:]]
    result = client.post("/api/v1/labels", json={"project_id": project_id, "from_catalog": "plastic", "codes": codes})
    assert result.status_code == 201
    assert all(row["shortcut_key"] is None for row in result.json())
    assert [row["sort_order"] for row in result.json()] == list(range(4, 22))
    assert client.get("/api/v1/catalog/plastic").json() == before


def test_unknown_project_and_non_enum_schema_fail(label_api):
    client, _, project_id = label_api
    assert client.post("/api/v1/labels", json=custom("missing")).status_code == 422
    assert client.get("/api/v1/labels", params={"project_id": "missing"}).status_code == 422
    body = {"project_id": project_id, "schema": {"name": "布尔", "tree_path": "布尔", "field_type": "bool"}}
    assert client.post("/api/v1/labels", json=body).status_code == 201
    request = custom(project_id)
    request["tree_path"] = "布尔/塑料/CUSTOM"
    assert client.post("/api/v1/labels", json=request).status_code == 422
    assert client.post("/api/v1/labels", json=body).status_code == 422


def test_concurrent_custom_sort_order(label_api):
    client, _, project_id = label_api
    def add(i):
        request = custom(project_id)
        request.update(code=f"CUSTOM{i}", tree_path=f"材料/塑料/CUSTOM{i}")
        response = client.post("/api/v1/labels", json=request)
        assert response.status_code == 201
        return response.json()["sort_order"]
    with ThreadPoolExecutor(3) as pool:
        assert sorted(pool.map(add, range(3))) == [4, 5, 6]


def test_auth_identity_and_stage_boundary(label_api):
    client, _, _ = label_api
    for path in ("/api/v1/projects", "/api/v1/labels", "/api/v1/catalog/plastic"):
        denied = client.get(path, headers={"Authorization": ""})
        assert denied.status_code == 401 and "X-SpectrumAgent-Pid" not in denied.headers
    result = client.get("/api/v1/catalog/plastic")
    assert result.headers["X-SpectrumAgent-Pid"] and result.headers["X-SpectrumAgent-Boot-Id"]
    assert client.headers["Authorization"][7:] not in result.text
    paths = client.app.openapi()["paths"]
    assert "/api/v1/datasets/{identifier}/superpixels" in paths
    assert not any("/annotations" in path or "/diffuse" in path for path in paths)
