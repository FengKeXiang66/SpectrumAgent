"""Reference-only SQLite ledger, with atomic batches and persisted default raw."""
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

from spectrumagent.data import DataError, SpectrumDataSet
from spectrumagent.data.readers import BinaryReader, FallbackEnviReader, open_envi
from spectrumagent.data.readers.header import EXTENSIONS, classic, key_name, read_text
from spectrumagent.data.readers.binary import json_object
from .schemas import DatasetRecord, ImportResponse, ImportSummary


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
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE IF NOT EXISTS dataset_registry (id TEXT PRIMARY KEY, header_key TEXT NOT NULL, raw INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(header_key,raw))")

    def import_path(self, value: str, *, raw=False, data_path=None):
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
        records = []
        with self.lock, sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            for key, dataset in prepared:
                row = db.execute("SELECT id,payload FROM dataset_registry WHERE header_key=? AND raw=?", (key, int(raw))).fetchone()
                if row:
                    stored = TypeAdapter(SpectrumDataSet).validate_json(row[1])
                    if stored.name != dataset.name:
                        stored = replace(stored, name=dataset.name)
                        db.execute("UPDATE dataset_registry SET payload=? WHERE id=?", (json.dumps(stored.as_dict(), ensure_ascii=False), row[0]))
                    records.append(DatasetRecord(id=row[0], dataset=stored, existing=True))
                else:
                    identifier = str(uuid4())
                    db.execute("INSERT INTO dataset_registry VALUES (?,?,?,?)", (identifier, key, int(raw), json.dumps(dataset.as_dict(), ensure_ascii=False)))
                    records.append(DatasetRecord(id=identifier, dataset=dataset, existing=False))
        existing = sum(r.existing for r in records)
        return ImportResponse(datasets=records, summary=ImportSummary(total=len(records), imported=len(records)-existing, existing=existing))

    def get(self, identifier):
        with sqlite3.connect(self.database) as db:
            row = db.execute("SELECT payload,raw FROM dataset_registry WHERE id=?", (str(identifier),)).fetchone()
        if row is None:
            raise DataError("DATASET_NOT_FOUND", "数据集不存在", id=str(identifier))
        return TypeAdapter(SpectrumDataSet).validate_json(row[0]), bool(row[1])

    def readable(self, identifier, raw=None):
        stored, default = self.get(identifier)
        mode = default if raw is None else raw
        current = read_header(Path(stored.header_path), Path(stored.data_path), raw=mode)
        for field in ("shape", "dtype", "interleave", "wavelengths", "fwhm"):
            if getattr(current, field) != getattr(stored, field):
                raise DataError("SOURCE_CHANGED", "源元数据与登记记录不一致", field=field)
        return current, mode
