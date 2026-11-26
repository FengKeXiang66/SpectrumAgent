"""Cross-restart storage for non-sensitive LLM configuration.

Model settings configured in the settings panel are restored on the next
launch. Only the LLMSettings fields are written, as
one JSON file beside the DPAPI key in the permanent root. The API key itself,
dataset paths and every processing artifact are never part of this file.

The runtime database remains the source of truth; this file is a
snapshot taken whenever settings are written and restored once at engine
startup (see ``llm.restore_settings`` and ``api.settings.make_router``).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DIRECTORY = "config"
FILENAME = "llm_settings.json"
FIELDS = frozenset({"base_url", "model", "router_model", "router_base_url", "temperature", "max_tokens",
                    "timeout_ms", "egress_enabled"})
OPTIONAL_ROUTER_FIELDS = {"router_model", "router_base_url"}
PERMANENT_ROOT_ENV = "SPECTRUMAGENT_PERMANENT_ROOT"


def root_from_database(database) -> Path:
    """Mirror AppPaths.credential_root without constructing AppPaths.

    The shell points the environment at the permanent root; legacy launches
    and tests without the variable keep configuration beside the data root.
    """
    override = os.environ.get(PERMANENT_ROOT_ENV)
    if override:
        return Path(override)
    database = Path(database).resolve()
    return database.parent.parent if database.parent.name == "db" else database.parent


def config_path(root: Path) -> Path:
    return Path(root) / DIRECTORY / FILENAME


def save(root: Path, values: dict) -> None:
    """Atomically persist a validated settings dict. No secret is ever passed here."""
    payload = {key: values[key] for key in FIELDS}
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def load(root: Path) -> dict | None:
    """Return the last saved settings, or None when absent or unusable.

    A corrupt or foreign file is a legitimate "not configured" state, never a
    startup crash. Business validation (URL shape, numeric fields) happens in
    LLMSettings.model_validate after this structural check.
    """
    try:
        values = json.loads(config_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(values, dict) or not FIELDS - OPTIONAL_ROUTER_FIELDS <= values.keys() <= FIELDS:
        return None
    for key in OPTIONAL_ROUTER_FIELDS:
        values.setdefault(key, "")
    if any(not isinstance(values[key], str) for key in FIELDS - {"egress_enabled"}):
        return None
    if not isinstance(values["egress_enabled"], bool):
        return None
    return values
