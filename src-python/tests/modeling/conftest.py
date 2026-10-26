"""Isolated real databases and confirmed snapshots for modeling tests."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.run import RunEngine


@pytest.fixture
def legacy_case(tmp_path):
    paths = AppPaths(tmp_path / "legacy")
    with patch("spectrumagent.api.registry.migrate_modeling", lambda db: None):
        registry = DatasetRegistry(paths.database)
    runner = RunEngine(registry, paths)
    return SimpleNamespace(paths=paths, registry=registry, runner=runner)


def insert_run(db, identifier="training", status="pending"):
    db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,"
               "task,target,cv_strategy,cv_folds,seed,status,created_at) "
               "VALUES (?,'[]','[]','[]','classification','label','group_kfold',2,17,?,'fixture')",
               (identifier, status))
