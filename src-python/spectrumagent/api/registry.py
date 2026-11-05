"""Reference-only SQLite ledger, with atomic batches and persisted default raw."""
from spectrumagent.storage import guard as storage
from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from uuid import uuid4

from pydantic import TypeAdapter

from backend.database import connect_database
from spectrumagent.annotation.migrations import default_project_id, migrate
from spectrumagent.agent.migrations import migrate as migrate_agent
from spectrumagent.modeling.migrations import migrate as migrate_modeling

from spectrumagent.data import DataError, SpectrumDataSet
from spectrumagent.data.readers import BinaryReader, FallbackEnviReader, open_envi
from spectrumagent.data.readers.header import EXTENSIONS, classic, key_name, read_text
from spectrumagent.data.readers.binary import json_object
from .schemas import DatasetRecord, ImportResponse, ImportSummary


def safe_name(value):
    """A display label may contain a relative filename; never expose directories."""
    value = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    value = re.sub(r"[\x00-\x1f\x7f:]", " ", value).strip()
    value = re.sub(r"\.(?:hdr|img|mat)\b", "", value, flags=re.I)
    return value[:160] or "未命名数据集"


def display_names(rows):
    """Resolve labels in ledger order without changing persisted dataset names."""
    rows = [(identifier, safe_name(name), raw) for identifier, name, raw in rows]
    counts = Counter(name for _, name, _ in rows)
    # Reserve unique base names so a generated suffix cannot steal one.
    used = {name for _, name, _ in rows if counts[name] == 1}
    result = {}
    for identifier, name, raw in rows:
        if counts[name] == 1:
            result[identifier] = name
            continue
        mode = "原始 DN" if raw else "反射率"
        label = f"{name}（{mode}）"
        index = 2
        while label in used:
            label = f"{name}（{mode} #{index}）"
            index += 1
        result[identifier] = label
        used.add(label)
    return result


def absolute(value: str) -> Path:
    try:
        path = Path(value)
        if not path.is_absolute() or "\0" in value:
            raise ValueError("absolute path required")
        return path.resolve()
    except (ValueError, OSError) as exc:
        raise DataError("INVALID_PATH", "必须提供有效绝对路径", path=value) from exc


def read_header(path: Path, data_path=None, *, raw=False):
    if path.suffix.lower() == ".hdr":
        return open_envi(path, data_path, raw=raw)
    try:
        return BinaryReader().open(data_path, path, raw=raw)
    except DataError as error:
        if path.suffix.lower() == ".json" and error.code == "HEADER_INVALID":
            return FallbackEnviReader().open(path, data_path, raw=raw)
        raise


def candidates(root: Path):
    if root.is_file():
        if root.suffix.lower() in (".hdr", ".json", ".txt"):
            return [root]
        for ext in (".hdr", ".json", ".txt"):
            sibling = root.with_suffix(ext)
            if sibling.is_file():
                return [sibling]
        raise DataError("FILE_NOT_FOUND", "数据文件没有伴随头", path=str(root))
    if not root.is_dir():
        raise DataError("FILE_NOT_FOUND", "文件或目录不存在", path=str(root))
    paths = []
    # os.walk's onerror is mandatory: inaccessible branches must not disappear.
    def failed(error):
        raise DataError("DIRECTORY_UNREADABLE", "无法遍历目录", path=str(error.filename)) from error
    for directory, _, names in os.walk(root, onerror=failed, followlinks=False):
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix.lower() == ".hdr":
                paths.append(path)
            elif path.suffix.lower() in (".json", ".txt"):
                # Ignore unrelated README/config text; broken associated headers
                # are still candidates and contribute to the batch error list.
                sibling = any(Path(str(path.with_suffix("")) + ext).is_file() for ext in EXTENSIONS)
                try:
                    text = read_text(path)
                except DataError:
                    if sibling:
                        paths.append(path)
                    continue
                marked = re.search(r"(?i)(samples|lines|bands|data[ _]*type|data[ _]*file)\s*[\"']?\s*[:=]", text)
                if sibling or marked:
                    paths.append(path)
    return sorted({p.resolve() for p in paths})


class DatasetRegistry:
    def __init__(self, database: Path):
        self.database = database
        self.lock = RLock()
        self.storage_guard = storage.for_database(database)
        storage.mkdir(database.parent, parents=True, exist_ok=True)
        with connect_database(database) as db:
            db.execute("CREATE TABLE IF NOT EXISTS dataset_registry (id TEXT PRIMARY KEY, header_key TEXT NOT NULL, raw INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(header_key,raw))")
            migrate(db)
            migrate_agent(db)
            migrate_modeling(db)
        from backend.paths import AppPaths
        from spectrumagent.storage.recycle import RecycleStore
        self.recycle = RecycleStore(self, AppPaths(self.storage_guard.root))

    def import_path(self, value: str, *, raw=False, data_path=None, confirm_new=False):
        self.recycle.coordinator.check()
        root = absolute(value)
        if data_path is not None:
            data_path = absolute(data_path)
            if root.is_dir():
                raise DataError("INVALID_IMPORT", "目录导入不接受单个data_path覆盖")
        headers = candidates(root)
        if not headers:
            raise DataError("EMPTY_DIRECTORY", "目录中没有可关联的数据头", path=str(root))
        prepared, errors = [], []
        names = Counter(path.stem for path in headers)
        for path in headers:
            try:
                explicit = data_path or (root if root.is_file() and root != path else None)
                ds = read_header(path, explicit, raw=raw)
                if names[path.stem] > 1:
                    name = path.relative_to(root).as_posix() if root.is_dir() else f"{path.parent.name}/{path.name}"
                    ds = replace(ds, name=name)
                prepared.append((os.path.normcase(str(path.resolve())), ds))
            except DataError as error:
                errors.append({"path": str(path), **error.as_dict()})
        if errors:
            raise DataError("IMPORT_BATCH_INVALID", "整批导入未登记；请修复所有无效项", items=errors)
        source_directories = ({root} if root.is_dir() else set())
        for _, dataset in prepared:
            source_directories.update((Path(dataset.header_path).parent, Path(dataset.data_path).parent))
        self.storage_guard.add_sources(source_directories)
        with self.lock:
            planned = self._import_preflight(prepared, raw, confirm_new)
            return self._import_batch(prepared, raw, confirm_new, planned)

    @staticmethod
    def _import_conflict(code, detail):
        error = DataError(code, detail)
        error.status_code = 409
        return error

    def _import_preflight(self, prepared, raw, confirm_new):
        """Plan every key from one read snapshot before any batch mutation."""
        with connect_database(self.database) as db:
            db.execute('BEGIN')
            return self._import_decisions(db, prepared, raw, confirm_new)

    def _import_decisions(self, db, prepared, raw, confirm_new, planned=None):
        decisions = {}
        for key, _ in prepared:
            self.recycle.coordinator.check(key=(key, int(raw)))
            active = db.execute('SELECT id,payload FROM dataset_registry WHERE header_key=? AND raw=?',
                                (key, int(raw))).fetchone()
            # Permanent deletion leaves no recycle-bin key behind, so an absent
            # active row is always a first import. Only the confirmed-race case
            # still needs a structured 409.
            if active and confirm_new is True and planned is not None and planned[key] is None:
                raise self._import_conflict('REIMPORT_ACTIVE_EXISTS',
                    '确认后该路径已出现活跃数据集，请重新查看已有数据集并决策')
            decisions[key] = active
        return decisions

    def _insert_dataset(self, db, key, dataset, raw):
        # Recheck immediately before INSERT, including confirmed imports. A unique
        # conflict must remain a decision error rather than silently reusing an id.
        if db.execute('SELECT 1 FROM dataset_registry WHERE header_key=? AND raw=?', (key, int(raw))).fetchone():
            raise self._import_conflict('REIMPORT_ACTIVE_EXISTS', '该路径已有活跃记录，请重新查看并决策')
        identifier = str(uuid4())
        try:
            db.execute('INSERT INTO dataset_registry (id,header_key,raw,payload,project_id) VALUES (?,?,?,?,?)',
                       (identifier, key, int(raw), json.dumps(dataset.as_dict(), ensure_ascii=False), default_project_id(db)))
        except sqlite3.IntegrityError as error:
            code = ('REIMPORT_ACTIVE_EXISTS' if 'UNIQUE constraint failed' in str(error)
                    or getattr(error, 'sqlite_errorname', '') in ('SQLITE_CONSTRAINT_UNIQUE', 'SQLITE_CONSTRAINT_PRIMARYKEY')
                    else 'IMPORT_CONFLICT')
            raise self._import_conflict(code, '导入约束冲突，整批未登记；请重新查看活跃数据集并决策') from error
        return identifier

    def _import_batch(self, prepared, raw, confirm_new, planned):
        records = []
        with connect_database(self.database, timeout=10) as db:
            db.execute('BEGIN IMMEDIATE')
            decisions = self._import_decisions(db, prepared, raw, confirm_new, planned)
            for key, dataset in prepared:
                row = decisions[key]
                if row:
                    stored = TypeAdapter(SpectrumDataSet).validate_json(row[1])
                    if stored.name != dataset.name:
                        stored = replace(stored, name=dataset.name)
                        db.execute("UPDATE dataset_registry SET payload=? WHERE id=?", (json.dumps(stored.as_dict(), ensure_ascii=False), row[0]))
                    records.append((row[0], stored, True))
                else:
                    identifier = self._insert_dataset(db, key, dataset, raw)
                    records.append((identifier, dataset, False))
            rows = db.execute("SELECT id,payload,raw FROM dataset_registry ORDER BY rowid").fetchall()
            names = display_names((identifier, json.loads(payload).get("name"), mode)
                                  for identifier, payload, mode in rows)
            records = [DatasetRecord(id=identifier, dataset=dataset, existing=existing,
                                     display_name=names[identifier])
                       for identifier, dataset, existing in records]
            batch_records = {str(record.id): record for record in records}
            all_records = [batch_records.get(identifier) or DatasetRecord(id=identifier,
                                         dataset=TypeAdapter(SpectrumDataSet).validate_json(payload),
                                         existing=True, display_name=names[identifier])
                           for identifier, payload, _ in rows]
        existing = sum(r.existing for r in records)
        return ImportResponse(datasets=records, all_datasets=all_records,
                              summary=ImportSummary(total=len(records), imported=len(records)-existing, existing=existing))

    def get(self, identifier):
        self.recycle.coordinator.check(str(identifier))
        with connect_database(self.database) as db:
            row = db.execute("SELECT payload,raw FROM dataset_registry WHERE id=?", (str(identifier),)).fetchone()
        if row is None:
            raise DataError("DATASET_NOT_FOUND", "数据集不存在", id=str(identifier))
        return TypeAdapter(SpectrumDataSet).validate_json(row[0]), bool(row[1])

    def display_names(self):
        with connect_database(self.database) as db:
            rows = db.execute("SELECT id,payload,raw FROM dataset_registry ORDER BY rowid").fetchall()
        return display_names((identifier, json.loads(payload).get("name"), raw)
                             for identifier, payload, raw in rows)

    def record(self, identifier):
        dataset, _ = self.get(identifier)
        return DatasetRecord(id=identifier, dataset=dataset, existing=True,
                             display_name=self.display_names()[str(identifier)])

    def readable(self, identifier, raw=None):
        stored, default = self.get(identifier)
        mode = default if raw is None else raw
        try:
            current = read_header(Path(stored.header_path), Path(stored.data_path), raw=mode)
        except DataError as error:
            context = dict(error.payload.context)
            context.pop("source_error", None)
            context.pop("source_detail", None)
            raise DataError("SOURCE_CHANGED", "已登记数据集的源文件不可用",
                            source_error=error.code, source_detail=error.payload.detail,
                            **context) from error
        for field in ("shape", "dtype", "interleave", "wavelengths", "fwhm"):
            if getattr(current, field) != getattr(stored, field):
                raise DataError("SOURCE_CHANGED", "源元数据与登记记录不一致", field=field)
        return current, mode

    def catalog(self, *, limit=100, offset=0):
        self.recycle.coordinator.check()
        with connect_database(self.database) as db:
            db.execute('BEGIN')  # Names, count and page share one WAL read snapshot.
            labels = db.execute("SELECT id,json_extract(payload,'$.name'),raw FROM dataset_registry ORDER BY rowid").fetchall()
            rows = db.execute('SELECT id,payload,raw FROM dataset_registry ORDER BY rowid LIMIT ? OFFSET ?',
                              (limit, offset)).fetchall()
        names = display_names(labels)
        records = []
        for identifier, payload, raw in rows:
            dataset = TypeAdapter(SpectrumDataSet).validate_json(payload)
            try:
                self.readable(identifier)
                available = True
            except DataError:
                available = False
            records.append({'id': identifier, 'display_name': names[identifier], 'shape': dataset.shape,
                            'wavelength_range': [min(dataset.wavelengths), max(dataset.wavelengths)]
                            if dataset.wavelengths else None, 'raw': bool(raw),
                            'source_path': dataset.header_path, 'available': available})
        return {'datasets': records, 'total': len(labels), 'limit': limit, 'offset': offset}
