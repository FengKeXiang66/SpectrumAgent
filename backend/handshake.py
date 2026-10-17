"""Publish only a complete handshake and remove only our own generation."""

import json
import os
from pathlib import Path


def publish(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def remove_if_owned(path: Path, boot_id: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("boot_id") == boot_id:
            path.unlink(missing_ok=True)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
