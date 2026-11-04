"""Isolated real databases and confirmed snapshots for modeling tests."""
from storage_paths import runtime_path
from types import SimpleNamespace
from unittest.mock import patch
import json
from uuid import uuid4

import numpy as np

import pytest

from backend.paths import AppPaths
from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.run import RunEngine


@pytest.fixture
def legacy_case(tmp_path):
    paths = AppPaths(runtime_path(tmp_path, tmp_path / "legacy"))
    with patch("spectrumagent.api.registry.migrate_modeling", lambda db: None):
        registry = DatasetRegistry(paths.database)
    runner = RunEngine(registry, paths)
    return SimpleNamespace(paths=paths, registry=registry, runner=runner)


@pytest.fixture
def insert_run():
    def insert(db, identifier="training", status="pending"):
        db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,"
                   "task,target,cv_strategy,cv_folds,seed,status,created_at) "
                   "VALUES (?,'[]','[]','[]','classification','label','group_kfold',2,17,?,'fixture')",
                   (identifier, status))
    return insert


@pytest.fixture(params=["scale", "passthrough"])
def reflectance_cube(tmp_path, request):
    registry = DatasetRegistry(runtime_path(tmp_path, tmp_path / "equivalence.sqlite3"))
    branch = request.param
    values = np.arange(1, 97).reshape(3, 4, 8)
    values = values.astype(np.uint16) if branch == "scale" else values.astype(np.float32) / 128
    header = tmp_path / f"{branch}.hdr"
    header.with_suffix(".img").write_bytes(values.tobytes())
    header.write_text("ENVI\nlines=3\nsamples=4\nbands=8\ninterleave=bip\nbyte order=0\n"
                      + ("data type=12\nreflectance scale factor=100\n" if branch == "scale" else "data type=4\n"),
                      "utf-8")
    cube = str(registry.import_path(str(header), raw=True).datasets[0].id)
    return SimpleNamespace(registry=registry, cube=cube, header=header, branch=branch, values=values)


@pytest.fixture
def model_case(tmp_path):
    paths = AppPaths(runtime_path(tmp_path, tmp_path / "model-app"))
    registry = DatasetRegistry(paths.database)
    runner = RunEngine(registry, paths)
    pipeline = {"steps": [{"op": "standardize", "version": 1, "params": {"method": "standard"}}]}
    recipe = runner.recipes.create("training-fixture", "training", None, pipeline)["versions"][0]["id"]
    cubes, versions, runs, values, maps = [], [], [], [], []
    for index in range(4):
        x = np.random.default_rng(131 + index).integers(1000, 30000, (12, 4, 8), dtype=np.uint16)
        header = tmp_path / f"cube-{index}.hdr"
        header.with_suffix(".img").write_bytes(x.tobytes())
        header.write_text("ENVI\nlines=12\nsamples=4\nbands=8\ndata type=12\ninterleave=bip\n"
                          "byte order=0\nreflectance scale factor=65535\n", "utf-8")
        cube = str(registry.import_path(str(header), raw=True).datasets[0].id)
        label_map = np.tile(np.array([-2, -1, 0, 1], np.int32), (12, 1))
        version = str(uuid4())
        relative = f"{cube}/v1"
        folder = paths.snapshots / relative
        folder.mkdir(parents=True)
        np.savez_compressed(folder / "label_map.npz", label_map=label_map)
        with np.load(folder / "label_map.npz", allow_pickle=False) as archive:
            assert archive.files == ["label_map"]  # R2 actual snapshot key.
        with connect_database(paths.database) as db:
            labels = [r[0] for r in db.execute("SELECT id FROM label ORDER BY sort_order,code")]
            db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) "
                       "VALUES (?,?,1,?,48,24,'{}','fixture')", (version, cube, relative))
        (folder / "label_index.json").write_text(json.dumps(dict(enumerate(labels))), "utf-8")
        run = runner.run(cube, version, recipe, block_size=4)
        assert run["status"] == "succeeded", run["error"]
        cubes.append(cube); versions.append(version); runs.append(run["id"])
        values.append(x.astype(float)/65535); maps.append(label_map)
    return SimpleNamespace(paths=paths, registry=registry, runner=runner, cubes=cubes, versions=versions,
                           runs=runs, values=values, maps=maps, pipeline=pipeline,
                           arguments={"cube_ids": cubes, "annotation_version_ids": versions,
                                      "preprocess_run_ids": runs, "target": "label"})


@pytest.fixture
def regression_factory(tmp_path):
    """Real source/snapshot/DB fixtures; ready preprocess rows are explicit test inputs."""
    def make(n=12):
        from spectrumagent.modeling.dataset import SampleTargets
        from spectrumagent.annotation.labels import LabelStore, SchemaRequest
        paths = AppPaths(runtime_path(tmp_path, tmp_path / str(uuid4())))
        registry = DatasetRegistry(paths.database)
        runner = RunEngine(registry, paths)
        project = LabelStore(paths.database).projects()[0]["id"]
        schema = LabelStore(paths.database).add(SchemaRequest.model_validate({"project_id":project,
            "schema":{"name":"含量","tree_path":"含量","field_type":"continuous","unit":"%"}}))["id"]
        recipe = runner.recipes.create("regression-fixture", "regression", None,
            {"steps":[{"op":"standardize","version":1,"params":{"method":"standard"}}]})["versions"][0]["id"]
        with connect_database(paths.database) as db:
            label_ids = dict(db.execute("SELECT code,id FROM label"))
        cubes, versions, runs, values, maps = [], [], [], [], []
        for i in range(n):
            x = np.tile(np.random.default_rng(132+i).integers(500,8500,8,dtype=np.uint16),(2,3,1))
            x[0,0] = np.arange(8)*1000
            x[0,1] += 100
            header = tmp_path / f"{paths.root.name}-sample-{i}.hdr"
            header.with_suffix(".img").write_bytes(x.tobytes())
            header.write_text("ENVI\nlines=2\nsamples=3\nbands=8\ndata type=12\ninterleave=bip\nbyte order=0\nreflectance scale factor=10000\n","utf-8")
            cube = str(registry.import_path(str(header),raw=True).datasets[0].id)
            version, run = str(uuid4()), str(uuid4())
            folder = paths.snapshots/cube/"v1"; folder.mkdir(parents=True)
            labels = np.array([[0,1,1],[1,1,-1]],np.int32)
            np.savez_compressed(folder/"label_map.npz",label_map=labels)
            (folder/"label_index.json").write_text(json.dumps({"0":label_ids["BG"],"1":label_ids["PE"]}),"utf-8")
            with connect_database(paths.database) as db:
                db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) VALUES (?,?,1,?,6,5,'{}','fixture')",(version,cube,f"{cube}/v1"))
                db.execute("INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,created_at) VALUES (?,?,?,?,'scale',?,'succeeded','fixture')",(run,cube,version,recipe,str(uuid4())))
            cubes.append(cube); versions.append(version);runs.append(run); values.append(x.astype(float)/10000);maps.append(labels)
        targets = SampleTargets(paths.database)
        names = [registry.get(cube)[0].name for cube in cubes]
        csv_text = "cube_name,schema,value\n" + "".join(f"{name},含量,{i*.2+values[i][0,1,0]}\n" for i,name in enumerate(names))
        return SimpleNamespace(paths=paths,registry=registry,runner=runner,project=project,schema=schema,
            cubes=cubes,versions=versions,runs=runs,values=values,maps=maps,targets=targets,csv_text=csv_text,
            label_ids=label_ids,arguments={"preprocess_run_ids":runs,"target_schema_id":schema,"cv_folds":3,"max_components":3})
    return make
