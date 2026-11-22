"""Project label registry, following TASK-04 §§4.1, 4.3, 4.4, 5.1 (R13)."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, ValidationError, model_validator

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


class SimpleLabelRequest(Input):
    """Minimal workbench creation: the user supplies only a name and a color.

    The internal code and tree path are generated here so no structured
    registration ever leaks into the annotation UI.
    """
    project_id: Nonempty
    name: Nonempty
    color_hex: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


LabelRequest = CatalogRequest | CustomRequest | SchemaRequest | SimpleLabelRequest


class LabelPatch(Input):
    name: Nonempty | None = None
    color_hex: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    shortcut_key: Annotated[int, Field(strict=True, ge=0, le=9)] | None = None
    tree_path: Nonempty | None = None

    @model_validator(mode="after")
    def supplied_values(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set - {"shortcut_key"}):
            raise ValueError("至少提供一个字段，只有 shortcut_key 可清空")
        return self


class ImportTreeScope(Input):
    project_id: Nonempty
    root: Nonempty
    depth: Annotated[int, Field(strict=True, ge=1, le=10)] = 1


class ImportTreeCandidate(Input):
    directory: Nonempty  # Relative to the guarded root, never a caller-supplied cube list.
    code: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,16}$")]
    name: Nonempty
    color_hex: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
    sample_count: Annotated[int, Field(strict=True, ge=0)]
    reuse: StrictBool
    needs_naming: StrictBool
    confirmed: StrictBool = False


class ImportTreeApply(ImportTreeScope):
    candidates: Annotated[list[ImportTreeCandidate], Field(min_length=1, max_length=1000)]


class AssignSamples(Input):
    project_id: Nonempty
    cube_ids: Annotated[list[Nonempty], Field(min_length=1, max_length=1000)]
    label_id: Nonempty
    source: Literal["manual", "dialog"]


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
        self.lock = RLock()

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
                    "SELECT * FROM label WHERE schema_id=? AND project_id=? AND deleted_at IS NULL ORDER BY sort_order,code", (schema["id"], project_id))]
            return schemas

    def add(self, request: LabelRequest):
        with self.lock, connect_database(self.database, timeout=10) as db:
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
            if isinstance(request, SimpleLabelRequest):
                used = {row[0] for row in db.execute("SELECT code FROM label WHERE project_id=?", (request.project_id,))}
                serial = 1
                while f"L{serial:03d}" in used:
                    serial += 1
                return insert_label(db, CustomRequest(project_id=request.project_id, code=f"L{serial:03d}",
                                                     name=request.name, tree_path="材料",
                                                     color_hex=request.color_hex), origin="custom")
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

    @staticmethod
    def require_label(db, label_id):
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM label WHERE id=? AND deleted_at IS NULL", (str(label_id),)).fetchone()
        if row is None:
            raise invalid("label_id", "标签不存在")
        return {key: row[key] for key in row.keys() if key != 'deleted_at'}

    def update(self, label_id, **changes):
        try:
            patch = LabelPatch.model_validate(changes)
        except ValidationError as error:
            raise invalid("patch", str(error)) from None
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.require_label(db, label_id)
            row.update(patch.model_dump(exclude_unset=True))
            if row["shortcut_key"] == 0 and not row["is_background"]:
                raise invalid("shortcut_key", "0 仅供背景标签使用")
            if row["shortcut_key"] is not None and db.execute(
                "SELECT 1 FROM label WHERE project_id=? AND shortcut_key=? AND id<>?",
                (row["project_id"], row["shortcut_key"], row["id"]),
            ).fetchone():
                raise invalid("shortcut_key", "项目内快捷键已占用")
            row["schema_id"] = resolve_schema_id(db, row["project_id"], row["tree_path"])
            db.execute("UPDATE label SET name=:name,color_hex=:color_hex,shortcut_key=:shortcut_key,"
                       "tree_path=:tree_path,schema_id=:schema_id WHERE id=:id", row)
            return row

    @staticmethod
    def _draft_references(db, code, project_id=None):
        """Only region references use a label; an unused palette entry does not."""
        rows = db.execute("SELECT a.document_json FROM annotation_draft a JOIN dataset_registry d ON d.id=a.cube_id "
                          "WHERE (? IS NULL OR d.project_id=?)", (project_id, project_id))
        count = 0
        for (text,) in rows:
            document = json.loads(text)
            indices = {item['index'] for item in document['classes'] if item['code'] == code}
            count += any(region.get('op', 'add') == 'add' and region.get('class_index') in indices
                         for region in document['regions'])
        return count

    def delete(self, label_id, *, confirm=False):
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            label = self.require_label(db, label_id)
            if confirm is not True:
                error = DataError("LABEL_DELETE_CONFIRM_REQUIRED", "删除标签会清除该标签在所有图片当前工作态中的标注和样品关联；已保存 JSON 及类别信息保留。请确认后删除。")
                error.status_code = 409
                raise error
            # No restore path: only immutable class metadata for saved results survives.
            db.execute("UPDATE label SET deleted_at=?,shortcut_key=NULL WHERE id=?", (now(), str(label_id)))
            db.execute("DELETE FROM label_alias WHERE label_id=?", (str(label_id),))
            db.execute("DELETE FROM sample_label WHERE label_id=?", (str(label_id),))
            # Keep persisted drafts valid when indices after the removed entry shift.
            from .draft import remap_document
            labels = db.execute("SELECT id,code,name,color_hex FROM label WHERE project_id=? AND deleted_at IS NULL ORDER BY sort_order,code",
                                (label['project_id'],)).fetchall()
            drafts = db.execute("SELECT a.cube_id,a.document_json,a.revision,d.payload FROM annotation_draft a JOIN dataset_registry d ON d.id=a.cube_id "
                                "WHERE d.project_id=?", (label['project_id'],)).fetchall()
            from .raster import rasterize, encode_rle
            import numpy as np
            for cube_id, text, revision, payload in drafts:
                document = json.loads(text)
                removed = {item['index'] for item in document['classes'] if item['code'] == label['code']}
                mask = None
                if any(region.get('op', 'add') == 'add' and region.get('class_index') in removed for region in document['regions']):
                    mask = np.isin(rasterize(document, json.loads(payload)['shape']), list(removed))
                document['regions'] = [region for region in document['regions']
                                       if not (region.get('op', 'add') == 'add' and region.get('class_index') in removed)]
                if mask is not None and mask.any():
                    # Deleting a class clears its visible pixels; it must not expose
                    # older overlapping regions of another class underneath them.
                    document['regions'].append({'region_id': f'r-{revision + 1:04d}', 'op': 'erase',
                        'geometry': {'type': 'pixel_set', 'rows': encode_rle(mask), 'segments_fingerprint': None},
                        'source': 'manual', 'created_at': now()})
                normalized = remap_document(document, labels)
                if normalized != json.loads(text):
                    db.execute("UPDATE annotation_draft SET document_json=?,revision=revision+1,updated_at=? WHERE cube_id=?",
                               (json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':')), now(), cube_id))
            return {"deleted": str(label_id)}

    def merge(self, source_id, target_id):
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            source, target = self.require_label(db, source_id), self.require_label(db, target_id)
            if source["id"] == target["id"] or source["project_id"] != target["project_id"]:
                raise invalid("target_id", "必须合并到同项目的另一标签")
            drafts = self._draft_references(db, source["code"])
            if drafts:
                error = DataError("LABEL_IN_USE", "标签仍被草稿引用，不能合并", references={"draft": drafts})
                error.status_code = 409
                raise error
            counts = {}
            for table in ("annotation", "sample_spectrum"):
                counts[table] = db.execute(f"UPDATE {table} SET label_id=? WHERE label_id=?",
                                           (str(target_id), str(source_id))).rowcount
            counts["sample_label"] = db.execute("SELECT count(*) FROM sample_label WHERE label_id=?", (str(source_id),)).fetchone()[0]
            # Preserve an existing target association (including its provenance).
            db.execute("INSERT OR IGNORE INTO sample_label (project_id,cube_id,label_id,source,created_at) "
                       "SELECT project_id,cube_id,?,source,created_at FROM sample_label WHERE label_id=?",
                       (str(target_id), str(source_id)))
            db.execute("DELETE FROM sample_label WHERE label_id=?", (str(source_id),))
            db.execute("DELETE FROM label WHERE id=?", (str(source_id),))
            return {"target": target, "references": counts}

    def _import_root(self, root):
        from spectrumagent.storage import guard as storage
        path = Path(root)
        if not path.is_absolute() or ".." in path.parts:
            raise invalid("root", "根目录必须位于已登记数据根内，不接受相对或遍历路径")
        try:
            path = path.resolve(strict=True)
        except (OSError, ValueError, RuntimeError):
            raise invalid("root", "根目录不存在或不可访问") from None
        if not path.is_dir() or not any(path.is_relative_to(source) for source in storage.for_database(self.database).sources):
            raise invalid("root", "根目录超出已登记数据根")
        return path

    def _tree_directories(self, root, depth):
        folders = [root]
        for _ in range(depth):
            children = []
            for parent in folders:
                for child in parent.iterdir():
                    if child.is_dir():
                        if not child.resolve().is_relative_to(root) or child.is_symlink() or child.is_junction():
                            raise invalid("root", "目录树包含链接，不能用于归类")
                        children.append(child)
            folders = sorted(children, key=lambda p: (p.relative_to(root).as_posix().casefold(), p.relative_to(root).as_posix()))
            if len(folders) > 1000:
                raise invalid("depth", "候选目录超过 1000 个，请缩小范围")
        return folders

    @staticmethod
    def _registered_samples(db, project_id, folder):
        rows = db.execute("SELECT id,payload FROM dataset_registry WHERE project_id=? ORDER BY id", (project_id,))
        return [row[0] for row in rows if Path(json.loads(row[1])["header_path"]).resolve().is_relative_to(folder)]

    def import_tree(self, root, depth=1, *, project_id=None):
        root = self._import_root(root)
        # Reuse the same strict depth validation for direct service consumers.
        if type(depth) is not int or not 1 <= depth <= 10:
            raise invalid("depth", "深度须为 1–10 的整数")
        with connect_database(self.database) as db:
            project_id = project_id or db.execute("SELECT id FROM project ORDER BY created_at,id LIMIT 1").fetchone()[0]
            self.require_project(db, project_id)
            existing = {code.upper(): color for code, color in db.execute("SELECT code,color_hex FROM label WHERE project_id=? AND deleted_at IS NULL", (project_id,))}
            folders = self._tree_directories(root, depth)
            reserved = {folder.name.upper() for folder in folders if re.fullmatch(r"[A-Za-z0-9_]{1,16}", folder.name)}
            used = set(existing) | reserved | {"BG"}
            planned, result, serial = set(), [], 1
            palette = ("#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2")
            for index, folder in enumerate(folders):
                needs_naming = re.fullmatch(r"[A-Za-z0-9_]{1,16}", folder.name) is None
                if needs_naming:
                    while f"L{serial:03d}" in used:
                        serial += 1
                    code = f"L{serial:03d}"
                    used.add(code)
                else:
                    code = folder.name.upper()
                reuse = code in existing or code in planned
                planned.add(code)
                result.append(ImportTreeCandidate(directory=folder.relative_to(root).as_posix(), code=code, name=folder.name,
                    sample_count=len(self._registered_samples(db, project_id, folder)), color_hex=existing.get(code, palette[index % len(palette)]),
                    reuse=reuse, needs_naming=needs_naming).model_dump())
            return result

    def apply_tree(self, candidates, *, project_id, root, depth=1):
        request = ImportTreeApply(project_id=project_id, root=str(root), depth=depth, candidates=candidates)
        root = self._import_root(request.root)
        directories = {folder.relative_to(root).as_posix(): folder for folder in self._tree_directories(root, depth)}
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_project(db, project_id)
            counts = dict(created_labels=0, created_samples=0, skipped=0)
            seen = set()
            for candidate in request.candidates:
                folder = directories.get(candidate.directory)
                if folder is None or candidate.directory in seen:
                    raise invalid("candidates.directory", "目录已变化、重复或超出预览范围，请重新预览")
                seen.add(candidate.directory)
                needs_naming = re.fullmatch(r"[A-Za-z0-9_]{1,16}", folder.name) is None
                if needs_naming and not candidate.confirmed:
                    raise invalid("candidates.confirmed", "占位 code 与名称须经用户确认")
                samples = self._registered_samples(db, project_id, folder)
                if len(samples) != candidate.sample_count:
                    raise invalid("candidates.sample_count", "登记样品数已变化，请重新预览")
                labels = db.execute("SELECT id FROM label WHERE project_id=? AND upper(code)=? AND deleted_at IS NULL ORDER BY code", (project_id, candidate.code)).fetchall()
                if len(labels) > 1:
                    raise invalid("code", "存在大小写冲突的既有 code，请先合并标签")
                if labels:
                    label_id = labels[0][0]
                else:
                    label_id = insert_label(db, CustomRequest(project_id=project_id, code=candidate.code, name=candidate.name,
                        color_hex=candidate.color_hex, tree_path="材料"), origin="custom")["id"]
                    counts["created_labels"] += 1
                for cube_id in samples:
                    inserted = db.execute("INSERT OR IGNORE INTO sample_label (project_id,cube_id,label_id,source,created_at) VALUES (?,?,?,'folder',?)",
                                          (project_id, cube_id, label_id, now())).rowcount
                    counts["created_samples"] += inserted
                    counts["skipped"] += 1 - inserted
            return counts
