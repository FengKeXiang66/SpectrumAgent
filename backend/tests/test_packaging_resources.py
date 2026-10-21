"""Packaging regression: assets are required, byte-checked and never substituted."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("frozen_resources", ROOT/"scripts/verify_frozen_backend.py")
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


def test_catalog_and_all_schema_json_are_required_frozen_resources(tmp_path):
    actual = resources.package_data()
    assert {"annotation/catalog/plastic.json", "api/openapi.json", "data/schema.json", "data/error-schema.json"} <= actual.keys()
    for name, source in actual.items():
        target = tmp_path/"_internal/spectrumagent"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    checks = resources.verify_data(tmp_path)
    assert len(checks) == len(actual)
    assert next(row for row in checks if row["path"].endswith("plastic.json"))["sha256"] == resources.sha(actual["annotation/catalog/plastic.json"])


def test_missing_catalog_blocks_packaging_before_engine_start(tmp_path):
    with pytest.raises(ValueError, match="annotation/catalog/plastic.json"):
        resources.verify_data(tmp_path)


def test_stale_or_corrupt_data_is_rejected_and_future_json_is_checked(tmp_path):
    source = tmp_path/"source"
    frozen = tmp_path/"frozen"
    source.mkdir()
    (source/"future.json").write_text('{"revision":2}', "utf-8")
    target = frozen/"_internal/spectrumagent/future.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"revision":1}', "utf-8")
    with pytest.raises(ValueError, match="differs from source: future.json"):
        resources.verify_data(frozen, source)
