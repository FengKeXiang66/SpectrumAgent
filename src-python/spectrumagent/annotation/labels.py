"""Project label registry, following TASK-04 §§4.1, 4.3, 4.4, 5.1 (R13)."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from backend.database import connect_database
from spectrumagent.data import DataError


Nonempty = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchemaField(Input):
    name: Nonempty
    tree_path: Annotated[str, Field(min_length=1, pattern=r"^[^/\s]+(?:[^/]*[^/\s])?$")]
    field_type: Literal["enum", "bool", "continuous", "ordinal"]
    unit: str | None = None
    config: JsonValue = None


class SchemaRequest(Input):
    project_id: Nonempty
    schema_field: SchemaField = Field(alias="schema")


class CatalogRequest(Input):
    project_id: Nonempty
    from_catalog: Literal["plastic"]
    codes: Annotated[list[Nonempty], Field(min_length=1)]


class CustomRequest(Input):
    project_id: Nonempty
    code: Nonempty
    name: Nonempty
    tree_path: Nonempty
    color_hex: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
    # TASK-04 §§4.1/4.3: NULL or 0..9; 0 is background-only.
    shortcut_key: Annotated[int, Field(strict=True, ge=0, le=9)] | None = None
    is_background: StrictBool = False


LabelRequest = CatalogRequest | CustomRequest | SchemaRequest


def invalid(field, message):
    return DataError("INVALID_LABEL", "标签登记参数不合法", fields=[{"field": field, "message": message}])


def plastic_catalog():
    return json.loads((Path(__file__).parent / "catalog" / "plastic.json").read_text("utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def resolve_schema_id(db, project_id, tree_path):
    """R13: exact first-segment match, never a fallback/default schema."""
    row = db.execute(
        "SELECT id FROM label_schema WHERE project_id=? AND field_type='enum' AND tree_path=?",
        (project_id, tree_path.split("/", 1)[0]),
    ).fetchone()
    if row is None:
        raise invalid("tree_path", "第一段无匹配的 enum schema；请先建对应 schema 或从目录添加")
    return row[0]


def label_sort_order(db, project_id, code, origin):
    """All three write paths use the R13 ordering rules here."""
    if origin == "seed":
        return {"BG": 0, "PE": 1, "PET": 2, "PP": 3}[code]  # §4.3 seed values.
    if origin == "catalog":
        return next(i for i, item in enumerate(plastic_catalog(), 1) if item["code"] == code)
    row = db.execute("SELECT max(sort_order) FROM label WHERE project_id=?", (project_id,)).fetchone()
    return 1 if row[0] is None else row[0] + 1  # R13, custom append.


def insert_label(db, request: CustomRequest, *, origin):
    schema_id = resolve_schema_id(db, request.project_id, request.tree_path)
    if request.shortcut_key == 0 and not request.is_background:
        raise invalid("shortcut_key", "0 仅供背景标签使用")
    if db.execute("SELECT 1 FROM label WHERE project_id=? AND code=?", (request.project_id, request.code)).fetchone():
        raise invalid("code", "项目内 code 已登记")
    if request.shortcut_key is not None and db.execute(
        "SELECT 1 FROM label WHERE project_id=? AND shortcut_key=?", (request.project_id, request.shortcut_key)
    ).fetchone():
        raise invalid("shortcut_key", "项目内快捷键已占用")
    row = dict(id=str(uuid4()), project_id=request.project_id, schema_id=schema_id,
               code=request.code, name=request.name, tree_path=request.tree_path,
               color_hex=request.color_hex, shortcut_key=request.shortcut_key,
               sort_order=label_sort_order(db, request.project_id, request.code, origin),
               is_background=int(request.is_background), created_at=now())
    db.execute("INSERT INTO label (id,project_id,schema_id,code,name,tree_path,color_hex,shortcut_key,sort_order,is_background,created_at) "
               "VALUES (:id,:project_id,:schema_id,:code,:name,:tree_path,:color_hex,:shortcut_key,:sort_order,:is_background,:created_at)", row)
    return row


class LabelStore:
    def __init__(self, database):
        self.database = database

    def projects(self):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM project ORDER BY created_at,id")]

    @staticmethod
    def require_project(db, project_id):
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise invalid("project_id", "项目不存在")

    def tree(self, project_id):
        with connect_database(self.database) as db:
            self.require_project(db, project_id)
            db.row_factory = sqlite3.Row
            schemas = [dict(row) for row in db.execute("SELECT * FROM label_schema WHERE project_id=? ORDER BY tree_path", (project_id,))]
            for schema in schemas:
                schema["config"] = json.loads(schema["config"]) if schema["config"] is not None else None
                schema["labels"] = [dict(row) for row in db.execute(
                    "SELECT * FROM label WHERE schema_id=? AND project_id=? ORDER BY sort_order,code", (schema["id"], project_id))]
            return schemas

    def add(self, request: LabelRequest):
        with connect_database(self.database) as db:
            # Serialize max+1 and uniqueness checks with writes, including batches.
            db.execute("BEGIN IMMEDIATE")
            self.require_project(db, request.project_id)
            if isinstance(request, SchemaRequest):
                if db.execute("SELECT 1 FROM label_schema WHERE project_id=? AND tree_path=?",
                              (request.project_id, request.schema_field.tree_path)).fetchone():
                    raise invalid("schema.tree_path", "项目内 schema 路径已登记")
                row = dict(id=str(uuid4()), project_id=request.project_id, **request.schema_field.model_dump(), created_at=now())
                stored = dict(row, config=json.dumps(row["config"], ensure_ascii=False) if row["config"] is not None else None)
                db.execute("INSERT INTO label_schema (id,project_id,name,tree_path,field_type,unit,config,created_at) "
                           "VALUES (:id,:project_id,:name,:tree_path,:field_type,:unit,:config,:created_at)", stored)
                return row
            if isinstance(request, CustomRequest):
                return insert_label(db, request, origin="custom")
            catalog = {item["code"]: item for item in plastic_catalog()}
            rows = []
            for code in request.codes:
                if code not in catalog:
                    raise invalid("codes", f"塑料目录中不存在 {code}")
                item = catalog[code]
                # §4.3 permits NULL (mouse selection); never guess a shortcut.
                label = CustomRequest(project_id=request.project_id, **item, tree_path=f"材料/塑料/{code}")
                rows.append(insert_label(db, label, origin="catalog"))
            return rows
