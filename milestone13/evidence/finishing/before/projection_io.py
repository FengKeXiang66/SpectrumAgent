"""Project-scoped configuration and atomic publication under data_root/exports."""
from collections import Counter
import json
import os
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from .labels import now
from .projection import project


_EXPORT_LOCK = RLock()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def project_config_path(paths, project_id):
    return paths.root / "projects" / str(UUID(str(project_id))) / "projection.json"


def configure_project(paths, project_id, mapping, *, filenames=None):
    """Persist explicit code→external-name mappings; no inferred defaults."""
    value = {"mapping": mapping, "filenames": filenames or {}}
    _validate_config(value)
    path = project_config_path(paths, project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(_json(value), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _validate_config(value):
    if not isinstance(value, dict) or not isinstance(value.get("mapping", {}), dict) or not isinstance(value.get("filenames", {}), dict):
        raise ValueError("项目 projection.json 须含 mapping / filenames 对象")
    if any(not isinstance(key, str) or not isinstance(name, str) or not name
           for key, name in value.get("mapping", {}).items()):
        raise ValueError("对外名称映射须为非空字符串，不得推断名称")
    for cube, filename in value.get("filenames", {}).items():
        UUID(cube)
        _filename(filename)
    return value


def _filename(name):
    if not isinstance(name, str) or not name or any(char in name for char in '/\\:\x00') or name.strip() != name:
        raise ValueError("投影文件名须为本地文件名，不得含路径")
    stem = name[:-5] if name.lower().endswith(".json") else name
    if stem in ("", ".", "..") or stem.casefold() == "manifest" or stem.lower().endswith(".meta"):
        raise ValueError("投影文件名与 manifest/sidecar 冲突")
    return stem + ".json"


def write_projection(paths, cube_id, project_id, source_hdr, version_no, label_map, label_index, *, document=None):
    """Return JSON path and metadata; publish all three files only after validation."""
    cube_id = str(UUID(str(cube_id)))
    config_path = project_config_path(paths, project_id)
    config = _validate_config(json.loads(config_path.read_text("utf-8"))) if config_path.exists() else {}
    text, meta = project(label_map, label_index, config.get("mapping", {}), rule_version=1)
    source = Path(source_hdr)
    if not source.is_absolute():
        raise ValueError("source_hdr 必须为绝对路径")
    requested = _filename(config.get("filenames", {}).get(cube_id, source.stem))
    root = paths.exports.resolve()
    folder = root / cube_id
    generated = now()
    meta.update(cube_id=cube_id, version_no=version_no, source_hdr=str(source), generated_at=generated)
    if document is not None:
        regions = document["regions"]
        confidence = [region["confidence"] for region in regions if region.get("confidence") is not None]
        meta["region_statistics"] = {"count": len(regions), "sources": dict(Counter(region["source"] for region in regions)),
                                     "confidence_count": len(confidence),
                                     "confidence_min": min(confidence) if confidence else None,
                                     "confidence_max": max(confidence) if confidence else None}
    with _EXPORT_LOCK:
        root.mkdir(parents=True, exist_ok=True)
        owned = folder / "manifest.json"
        previous = json.loads(owned.read_text("utf-8")) if owned.exists() else {}
        filename = previous["filename"] if previous.get("requested_filename") == requested else requested
        filename = _filename(filename)
        others = [json.loads(path.read_text("utf-8")) for path in sorted(root.glob("*/manifest.json")) if path != owned]
        used = {entry["filename"].casefold() for entry in others}
        if filename.casefold() in used:
            filename = requested[:-5] + "_" + cube_id[:8] + ".json"
        if filename.casefold() in used:
            raise ValueError("投影文件名追加 cube_id 前 8 位后仍冲突")
        manifest = {"cube_id": cube_id, "source_hdr": str(source), "generated_at": generated,
                    "filename": filename, "requested_filename": requested, "version_no": version_no}
        folder.mkdir(parents=True, exist_ok=True)
        values = {folder / filename: text,
                  folder / (filename[:-5] + ".meta.json"): _json(meta),
                  folder / "manifest.json": _json(manifest)}
        obsolete = []
        if previous.get("cube_id") == cube_id and previous.get("filename") != filename:
            old_name = _filename(previous["filename"])
            obsolete = [folder / old_name, folder / (old_name[:-5] + ".meta.json")]
        managed = [*values, *obsolete]
        previous_bytes = {path: path.read_bytes() if path.exists() else None for path in managed}
        temporary = {path: path.with_name(f".{path.name}.{uuid4().hex}.tmp") for path in managed}
        published = []
        try:
            for path, value in values.items():
                temporary[path].write_text(value, encoding="utf-8")
            # Only our JSON files are replaced. Existing training MATs belong to
            # another service even when they share the cube's export directory.
            for path in values:
                os.replace(temporary[path], path)
                published.append(path)
            # A configured rename must still leave one current JSON per cube.
            # Only the old manifest's owned JSON and sidecar are retired.
            for path in obsolete:
                if path.exists():
                    path.unlink()
                    published.append(path)
        except BaseException:
            for path in reversed(published):
                old = previous_bytes[path]
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    temporary[path].write_bytes(old)
                    os.replace(temporary[path], path)
            raise
        finally:
            for path in temporary.values():
                path.unlink(missing_ok=True)
    return str(folder / filename), meta
