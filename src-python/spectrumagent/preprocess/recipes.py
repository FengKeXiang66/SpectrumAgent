"""Current recipe library and input content identity; legacy SQL names support existing workspaces."""
from spectrumagent.storage import guard as storage
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from backend.database import connect_database
from . import builtin_registry
from .migrations import migrate
from .registry import PreprocessError, effective_pipeline
from . import submissions


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


def annotation_identity(label_map, label_index):
    return hashlib.sha256(label_map.tobytes() + json.dumps(label_index, sort_keys=True).encode()).hexdigest()


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _version(row):
    result = dict(row)
    result["pipeline"] = json.loads(result["pipeline"])
    return result


RECIPE_HASH_ALGORITHM = "sha256/effective-pipeline-v2"


def pipeline_identity(pipeline, registry=None):
    """One canonical representation for new versions and immutable-row backfill."""
    registry = registry if registry is not None else builtin_registry()
    parsed = effective_pipeline(pipeline, registry)
    encoded = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class RecipeStore:
    def __init__(self, database, registry=None):
        self.database = Path(database)
        self.lock = RLock()
        self.registry = registry if registry is not None else builtin_registry()
        storage.for_database(self.database)
        storage.mkdir(self.database.parent, parents=True, exist_ok=True)
        with connect_database(self.database) as db:
            migrate(db)

    def _pipeline(self, pipeline):
        return pipeline_identity(pipeline, self.registry)

    def create(self, code, name, description, pipeline, note=None):
        if not isinstance(code, str) or not code.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("code/name 须为非空字符串")
        if description is not None and not isinstance(description, str) or note is not None and not isinstance(note, str):
            raise ValueError("description/note 须为字符串或 None")
        encoded, digest = self._pipeline(pipeline)
        identifier, version_id, timestamp = str(uuid4()), str(uuid4()), _timestamp()
        submission = submissions.context()
        payload = dict(code=code, name=name, description=description, pipeline=json.loads(encoded), note=note)
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            operation, fresh = submissions.begin(db, submission, 'preprocess.recipe_create', payload)
            if not fresh:
                return submissions.receipt(operation)
            self._create(db, identifier, version_id, timestamp, code, name, description, encoded, note, digest)
            result = self._get(db, identifier)
            submissions.finish(db, operation['operation_id'], 'succeeded', result)
        return result

    @staticmethod
    def _create(db, identifier, version_id, timestamp, code, name, description, encoded, note, digest):
        db.execute("INSERT INTO preprocess_recipe (id,code,name,description,builtin,created_at) VALUES (?,?,?,?,?,?)",
                       (identifier, code, name, description, 0, timestamp))
        db.execute("INSERT INTO preprocess_recipe_version (id,recipe_id,version_no,pipeline,note,created_at) VALUES (?,?,?,?,?,?)",
                       (version_id, identifier, 1, encoded, note, timestamp))
        db.execute("INSERT INTO recipe_pipeline_hash (recipe_version_id,algorithm,sha256) VALUES (?,?,?)",
                       (version_id, RECIPE_HASH_ALGORITHM, digest))

    def update_current(self, recipe_id, pipeline, note=None):
        if note is not None and not isinstance(note, str):
            raise ValueError("note 须为字符串或 None")
        encoded, digest = self._pipeline(pipeline)
        row = {"id": str(uuid4()), "recipe_id": str(recipe_id), "pipeline": encoded,
               "note": note, "created_at": _timestamp()}
        submission = submissions.context()
        payload = dict(recipe_id=str(recipe_id), pipeline=json.loads(encoded), note=note)
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            operation, fresh = submissions.begin(db, submission, 'preprocess.recipe_update', payload)
            if not fresh:
                return submissions.receipt(operation)
            result = self._update_current(db, row, digest)
            submissions.finish(db, operation['operation_id'], 'succeeded', result)
        return result

    def _update_current(self, db, row, digest):
        from .drafts import assert_available
        recipe_id = row['recipe_id']
        encoded = row['pipeline']
        if not db.execute("SELECT 1 FROM preprocess_recipe WHERE id=?", (str(recipe_id),)).fetchone():
            raise KeyError(recipe_id)
        assert_available(db,recipe_id=recipe_id)
        latest = db.execute("SELECT id,version_no,created_at FROM preprocess_recipe_version WHERE recipe_id=? ORDER BY version_no DESC LIMIT 1", (str(recipe_id),)).fetchone()
        if latest is None:
            raise KeyError(recipe_id)
        row.update(id=latest[0], version_no=latest[1], created_at=latest[2])
        db.execute("UPDATE preprocess_recipe_version SET pipeline=?,note=? WHERE id=?", (encoded,row['note'],row['id']))
        db.execute("UPDATE recipe_pipeline_hash SET algorithm=?,sha256=? WHERE recipe_version_id=?", (RECIPE_HASH_ALGORITHM,digest,row['id']))
        row.update(recipe_hash_alg=RECIPE_HASH_ALGORITHM, recipe_pipeline_sha256=digest)
        return _version(row)

    def get(self, recipe_id):
        with connect_database(self.database) as db:
            return self._get(db, recipe_id)

    @staticmethod
    def _get(db, recipe_id):
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM preprocess_recipe WHERE id=?", (str(recipe_id),)).fetchone()
        if row is None:
            raise KeyError(recipe_id)
        result = dict(row)
        result['deleted'] = bool(db.execute('SELECT 1 FROM recipe_runtime_state WHERE recipe_id=? AND deleted=1',(str(recipe_id),)).fetchone())
        result["versions"] = [_version(row) for row in db.execute(
            "SELECT v.*,h.algorithm AS recipe_hash_alg,h.sha256 AS recipe_pipeline_sha256 "
            "FROM preprocess_recipe_version v JOIN recipe_pipeline_hash h ON h.recipe_version_id=v.id "
            "WHERE v.recipe_id=? ORDER BY v.version_no DESC LIMIT 1", (str(recipe_id),))]
        return result

    def list(self):
        with connect_database(self.database) as db:
            db.execute('BEGIN')
            identifiers = [row[0] for row in db.execute("SELECT r.id FROM preprocess_recipe r LEFT JOIN recipe_runtime_state s ON s.recipe_id=r.id WHERE COALESCE(s.deleted,0)=0 ORDER BY r.code")]
            return [self._get(db,identifier) for identifier in identifiers]

    def by_code(self, code):
        with connect_database(self.database) as db:
            row = db.execute('SELECT id FROM preprocess_recipe WHERE code=?',(code,)).fetchone()
            return self._get(db,row[0]) if row else None

    def set_deleted(self, recipe_id, deleted):
        with self.lock, connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            self._get(db,recipe_id)
            db.execute('INSERT INTO recipe_runtime_state VALUES (?,?,?) ON CONFLICT(recipe_id) DO UPDATE SET deleted=excluded.deleted,updated_at=excluded.updated_at',
                       (str(recipe_id),int(deleted),_timestamp()))
            if deleted and db.execute("SELECT 1 FROM sqlite_master WHERE name='agent_session'").fetchone():
                versions = {row[0] for row in db.execute('SELECT id FROM preprocess_recipe_version WHERE recipe_id=?',(str(recipe_id),))}
                for session_id,raw in db.execute('SELECT id,context_json FROM agent_session').fetchall():
                    state = json.loads(raw)
                    if state.get('recipe_version_id') in versions:
                        state.pop('recipe_version_id',None)
                    if isinstance(state.get('catalogs'),dict):
                        state['catalogs'].pop('recipe',None)
                    db.execute('UPDATE agent_session SET context_json=? WHERE id=?',(submissions.encode(state),session_id))
            return self._get(db,recipe_id)

    def select_project(self, project_id, recipe_id):
        with self.lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            from .drafts import assert_available
            assert_available(db,recipe_id=recipe_id)
            db.execute("INSERT INTO project_recipe (project_id,recipe_id,selected_at) VALUES (?,?,?) "
                       "ON CONFLICT(project_id,recipe_id) DO NOTHING", (str(project_id), str(recipe_id), _timestamp()))
            db.row_factory = sqlite3.Row
            return dict(db.execute("SELECT * FROM project_recipe WHERE project_id=? AND recipe_id=?",
                                   (str(project_id), str(recipe_id))).fetchone())

    def project_recipes(self, project_id):
        with connect_database(self.database) as db:
            identifiers = [row[0] for row in db.execute(
                "SELECT r.id FROM preprocess_recipe r JOIN project_recipe p ON p.recipe_id=r.id LEFT JOIN recipe_runtime_state s ON s.recipe_id=r.id WHERE p.project_id=? AND COALESCE(s.deleted,0)=0 ORDER BY r.code",
                (str(project_id),))]
        return [self.get(identifier) for identifier in identifiers]

    # 取消选用只删除项目关联行，不删除配方本体。“只读关联”指配方历史
    # 不被复制/修改（TASK-05 §2.3）；取消关联不违背配方只增不改。
    def deselect_project(self, project_id, recipe_id):
        with connect_database(self.database, timeout=10) as db:
            db.execute("DELETE FROM project_recipe WHERE project_id=? AND recipe_id=?",
                       (str(project_id), str(recipe_id)))
