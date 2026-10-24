"""Mutable annotation document authority, validated before atomic CAS writes."""
from copy import deepcopy
from datetime import datetime
import json
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator, model_validator

from backend.database import connect_database
from spectrumagent.data import DataError
from .labels import now
from .raster import rasterize, rasterize_with_conflicts_v1


class Input(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


Nonempty = Annotated[str, Field(min_length=1)]
Index = Annotated[int, Field(ge=0)]
Coordinate = Annotated[int | float, Field(allow_inf_nan=False)]
Vertex = Annotated[list[Coordinate], Field(min_length=2, max_length=2)]


class Polygon(Input):
    type: Literal["polygon"]
    points: Annotated[list[Vertex], Field(min_length=3)]


class PixelSet(Input):
    type: Literal["pixel_set"]
    rows: list[Annotated[list[int], Field(min_length=3, max_length=3)]]
    # Direct legacy mask callers may have no segmentation: explicitly unknown.
    segments_fingerprint: dict[str, JsonValue] | None


class Class(Input):
    index: Index
    code: Nonempty
    name: str
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Region(Input):
    region_id: Annotated[str, Field(pattern=r"^r-[0-9]{4,}$")]
    geometry: Annotated[Polygon | PixelSet, Field(discriminator="type")]
    source: Literal["manual", "algorithm", "library", "migration", "model"]
    created_at: Nonempty

    @field_validator("created_at")
    @classmethod
    def iso_timestamp(cls, value):
        datetime.fromisoformat(value)
        return value


class Add(Region):
    op: Literal["add"] = "add"
    class_index: Index
    confidence: Literal["high", "medium", "low"]


class Uncertain(Region):
    op: Literal["uncertain"]


class Erase(Region):
    op: Literal["erase"]


class Document(Input):
    schema_version: Literal[1]
    cube_id: Nonempty
    classes: list[Class]
    regions: list[Annotated[Add | Uncertain | Erase, Field(discriminator="op")]]
    raster_rule_version: Literal[1]

    @model_validator(mode="before")
    @classmethod
    def default_add(cls, value):
        if isinstance(value, dict) and any(type(value.get(key)) is not int for key in ("schema_version", "raster_rule_version")):
            raise ValueError("version constants must be integers")
        if isinstance(value, dict) and isinstance(value.get("regions"), list):
            value = {**value, "regions": [{"op": "add", **r} if isinstance(r, dict) else r for r in value["regions"]]}
        return value

    @model_validator(mode="after")
    def references(self):
        if [c.index for c in self.classes] != list(range(len(self.classes))):
            raise ValueError("class indices must be contiguous and ordered")
        if len({c.code for c in self.classes}) != len(self.classes):
            raise ValueError("duplicate class code")
        if len({r.region_id for r in self.regions}) != len(self.regions):
            raise ValueError("duplicate region id")
        if any(isinstance(r, Add) and r.class_index >= len(self.classes) for r in self.regions):
            raise ValueError("unknown class index")
        return self


def invalid(detail="草稿参数或文档不合法"):
    return DataError("TOOL_ARGS_INVALID", detail)


def conflict():
    error = DataError("DRAFT_REVISION_CONFLICT", "草稿已变化，请重新读取后提交")
    error.status_code = 409
    return error


def remap_document(document, labels, old_ids=None):
    """Preserve class identity by live session IDs, or persisted class codes."""
    result = deepcopy(document)
    positions = {row[0]: i for i, row in enumerate(labels)}
    by_code = {row[1]: i for i, row in enumerate(labels)}
    mapping = {}
    for old in result["classes"]:
        target = positions.get(old_ids[old["index"]]) if old_ids is not None else by_code.get(old["code"])
        if target is None:
            raise DataError("LABEL_REMOVED", "工作态引用的标签已被删除")
        mapping[old["index"]] = target
    for region in result["regions"]:
        if region.get("op", "add") == "add":
            region["class_index"] = mapping[region["class_index"]]
    result["classes"] = [{"index": i, "code": row[1], "name": row[2], "color": row[3]}
                         for i, row in enumerate(labels)]
    return result


class DraftStore:
    def __init__(self, database, registry):
        self.database, self.registry = database, registry

    def labels(self, cube_id):
        self.registry.get(cube_id)
        with connect_database(self.database) as db:
            return db.execute("SELECT l.id,l.code,l.name,l.color_hex FROM label l JOIN dataset_registry d "
                              "ON d.project_id=l.project_id WHERE d.id=? ORDER BY l.sort_order ASC,l.code ASC",
                              (str(cube_id),)).fetchall()

    def empty(self, cube_id):
        return {"schema_version": 1, "cube_id": str(cube_id), "classes": [
            {"index": i, "code": row[1], "name": row[2], "color": row[3]}
            for i, row in enumerate(self.labels(cube_id))], "regions": [], "raster_rule_version": 1}

    def get(self, cube_id):
        self.registry.get(cube_id)
        with connect_database(self.database) as db:
            row = db.execute("SELECT revision,document_json,updated_at FROM annotation_draft WHERE cube_id=?",
                             (str(cube_id),)).fetchone()
        return None if row is None else {"revision": row[0], "document": json.loads(row[1]), "updated_at": row[2]}

    def view(self, cube_id):
        dataset, _ = self.registry.get(cube_id)
        row = self.get(cube_id)
        labeled = int(np.count_nonzero(rasterize(row["document"], dataset.shape) >= 0)) if row else 0
        return {"cube_id": str(cube_id), "revision": row["revision"] if row else 0,
                "document": row["document"] if row else None, "schema_version": 1, "raster_rule_version": 1,
                "updated_at": row["updated_at"] if row else None,
                "estimated_mat_bytes": labeled * dataset.shape[2] * 4}

    def validate(self, cube_id, document):
        try:
            result = Document.model_validate(document).model_dump()
        except (ValidationError, TypeError, ValueError):
            raise invalid() from None
        if result["cube_id"] != str(cube_id):
            raise invalid("草稿 cube_id 与目标数据集不一致")
        dataset, _ = self.registry.get(cube_id)
        rasterize(result, dataset.shape)  # Bounds are checked before any SQL write.
        return result

    def _change(self, cube_id, revision, change):
        cube_id = str(cube_id)
        self.registry.get(cube_id)
        if type(revision) is not int or revision < 0:
            raise invalid("revision 必须为非负整数")
        with connect_database(self.database) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision,document_json FROM annotation_draft WHERE cube_id=?", (cube_id,)).fetchone()
            if revision != (row[0] if row else 0):
                raise conflict()
            document = json.loads(row[1]) if row else self.empty(cube_id)
            document, result = change(document, revision + 1)
            document = self.validate(cube_id, document)
            text, timestamp = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")), now()
            if row is None:
                db.execute("INSERT INTO annotation_draft (cube_id,revision,document_json,schema_version,raster_rule_version,updated_at) "
                           "VALUES (?,?,?,?,?,?)", (cube_id, 1, text, 1, 1, timestamp))
            elif db.execute("UPDATE annotation_draft SET document_json=?,revision=revision+1,updated_at=? "
                            "WHERE cube_id=? AND revision=?", (text, timestamp, cube_id, revision)).rowcount != 1:
                raise conflict()
        return {"revision": revision + 1, "document": document, "updated_at": timestamp, **result}

    def replace(self, cube_id, document, revision):
        return self._change(cube_id, revision, lambda old, next_revision: (deepcopy(document), {}))

    def add(self, cube_id, revision, *, geometry, op="add", class_code=None, confidence=None):
        if op not in {"add", "uncertain", "erase"}:
            raise invalid()
        if not isinstance(geometry, dict):
            raise invalid()
        if "gesture_ref" in geometry:
            raise invalid("手势引用尚未接入")
        def change(document, next_revision):
            region = {"region_id": f"r-{next_revision:04d}", "op": op, "geometry": deepcopy(geometry),
                      "source": "manual", "created_at": now()}
            if op == "add":
                index = next((c["index"] for c in document["classes"] if c["code"] == class_code), None)
                if index is None:
                    raise DataError("LABEL_NOT_FOUND", "项目中没有该类 code")
                region.update(class_index=index, confidence=confidence if confidence is not None else "high")
            elif class_code is not None or confidence is not None:
                raise invalid("uncertain/erase 禁传 class_code/confidence")
            document["regions"].append(region)
            return document, {"region_id": region["region_id"]}
        return self._change(cube_id, revision, change)

    def patch(self, cube_id, region_id, revision, patch):
        if not patch or set(patch) - {"class_code", "geometry", "confidence", "deleted"}:
            raise invalid("patch 字段不在白名单内")
        if "deleted" in patch and type(patch["deleted"]) is not bool:
            raise invalid()
        if patch.get("deleted") and len(patch) != 1:
            raise invalid("删除操作不能同时修改字段")
        def change(document, next_revision):
            region = next((r for r in document["regions"] if r["region_id"] == region_id), None)
            if region is None:
                error = DataError("REGION_NOT_FOUND", "区域不存在")
                error.status_code = 404
                raise error
            if patch.get("deleted"):
                document["regions"].remove(region)
            else:
                if region["op"] != "add" and {"class_code", "confidence"} & set(patch):
                    raise invalid("uncertain/erase 禁传 class_code/confidence")
                if "class_code" in patch:
                    index = next((c["index"] for c in document["classes"] if c["code"] == patch["class_code"]), None)
                    if index is None:
                        raise DataError("LABEL_NOT_FOUND", "项目中没有该类 code")
                    region["class_index"] = index
                if "geometry" in patch:
                    geometry = patch["geometry"]
                    if isinstance(geometry, dict) and "gesture_ref" in geometry:
                        raise invalid("手势引用尚未接入")
                    if not isinstance(geometry, dict) or geometry.get("type") != "polygon":
                        raise invalid("手工修改仅接受 polygon")
                    region["geometry"] = deepcopy(geometry)
                if "confidence" in patch:
                    region["confidence"] = patch["confidence"]
            return document, {"region_id": region_id}
        return self._change(cube_id, revision, change)

    def statistics(self, cube_id, document):
        dataset, _ = self.registry.get(cube_id)
        label_map, conflict_map = rasterize_with_conflicts_v1(document, dataset.shape)
        return {"n_pixels": int(label_map.size), "labeled_pixels": int(np.count_nonzero(label_map >= 0)),
                "uncertain_pixels": int(np.count_nonzero(label_map == -2)), "blank_pixels": int(np.count_nonzero(label_map == -1)),
                "overlap_conflicts": int(np.count_nonzero(conflict_map))}
