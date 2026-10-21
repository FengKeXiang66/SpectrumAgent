"""B07 append-only recipe library and R3 pure input fingerprint, no run execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from backend.database import connect_database
from . import builtin_registry
from .migrations import migrate


def input_fingerprint(dataset_id, source_hashes, annotation_version_id, n_pixels):
    """R3: caller supplies persisted relative-path -> SHA256; never read source IO.

    UTF-8 encoding of dataset_id | digests sorted by relative path |
    annotation_version_id | decimal pixel count. Source hashes, not file contents,
    enter the function. Recipe/run persistence and fingerprint comparisons are later.
    """
    if type(n_pixels) is not int or n_pixels < 0:
        raise ValueError("n_pixels 必须为非负整数")
    if not isinstance(dataset_id, str) or not isinstance(annotation_version_id, str):
        raise ValueError("dataset_id/annotation_version_id 必须为字符串")
    if not isinstance(source_hashes, dict) or not all(isinstance(path, str) for path in source_hashes):
        raise ValueError("source_hashes 必须为相对路径到 SHA256 的映射")
    hashes = []
    for path in sorted(source_hashes):
        digest = source_hashes[path]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
            raise ValueError("源摘要须为 SHA256 十六进制字符串")
        hashes.append(digest.lower())
    payload = "|".join([dataset_id, *hashes, annotation_version_id, str(n_pixels)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _version(row):
    result = dict(row)
    result["pipeline"] = json.loads(result["pipeline"])
    return result


class RecipeStore:
    def __init__(self, database, registry=None):
        self.database = Path(database)
        self.registry = registry if registry is not None else builtin_registry()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with connect_database(self.database) as db:
            migrate(db)

    def _pipeline(self, pipeline):
        parsed = self.registry.parse_pipeline(pipeline)
        return json.dumps(parsed.model_dump(), ensure_ascii=False, allow_nan=False)

    def create(self, code, name, description, pipeline, note=None):
        if not isinstance(code, str) or not code.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("code/name 须为非空字符串")
        if description is not None and not isinstance(description, str) or note is not None and not isinstance(note, str):
            raise ValueError("description/note 须为字符串或 None")
        encoded = self._pipeline(pipeline)
        identifier, timestamp = str(uuid4()), _timestamp()
        with connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO preprocess_recipe (id,code,name,description,builtin,created_at) VALUES (?,?,?,?,?,?)",
                       (identifier, code, name, description, 0, timestamp))
            db.execute("INSERT INTO preprocess_recipe_version (id,recipe_id,version_no,pipeline,note,created_at) VALUES (?,?,?,?,?,?)",
                       (str(uuid4()), identifier, 1, encoded, note, timestamp))
        return self.get(identifier)

    def add_version(self, recipe_id, pipeline, note=None):
        if note is not None and not isinstance(note, str):
            raise ValueError("note 须为字符串或 None")
        encoded = self._pipeline(pipeline)
        row = {"id": str(uuid4()), "recipe_id": str(recipe_id), "pipeline": encoded,
               "note": note, "created_at": _timestamp()}
        with connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM preprocess_recipe WHERE id=?", (str(recipe_id),)).fetchone():
                raise KeyError(recipe_id)
            row["version_no"] = db.execute("SELECT coalesce(max(version_no),0)+1 FROM preprocess_recipe_version WHERE recipe_id=?",
                                           (str(recipe_id),)).fetchone()[0]
            db.execute("INSERT INTO preprocess_recipe_version (id,recipe_id,version_no,pipeline,note,created_at) "
                       "VALUES (:id,:recipe_id,:version_no,:pipeline,:note,:created_at)", row)
        return _version(row)

    def get(self, recipe_id):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM preprocess_recipe WHERE id=?", (str(recipe_id),)).fetchone()
            if row is None:
                raise KeyError(recipe_id)
            result = dict(row)
            result["versions"] = [_version(row) for row in db.execute(
                "SELECT * FROM preprocess_recipe_version WHERE recipe_id=? ORDER BY version_no", (str(recipe_id),))]
        return result

    def list(self):
        with connect_database(self.database) as db:
            identifiers = [row[0] for row in db.execute("SELECT id FROM preprocess_recipe ORDER BY code")]
        return [self.get(identifier) for identifier in identifiers]

    def select_project(self, project_id, recipe_id):
        with connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO project_recipe (project_id,recipe_id,selected_at) VALUES (?,?,?) "
                       "ON CONFLICT(project_id,recipe_id) DO NOTHING", (str(project_id), str(recipe_id), _timestamp()))
            db.row_factory = sqlite3.Row
            return dict(db.execute("SELECT * FROM project_recipe WHERE project_id=? AND recipe_id=?",
                                   (str(project_id), str(recipe_id))).fetchone())

    def project_recipes(self, project_id):
        with connect_database(self.database) as db:
            identifiers = [row[0] for row in db.execute(
                "SELECT r.id FROM preprocess_recipe r JOIN project_recipe p ON p.recipe_id=r.id WHERE p.project_id=? ORDER BY r.code",
                (str(project_id),))]
        return [self.get(identifier) for identifier in identifiers]
