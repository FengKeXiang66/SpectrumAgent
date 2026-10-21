"""Explicit pixel/annotation fixture; no historical sample spectrum is consumed."""
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from backend.database import connect_database
from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.run import RunEngine


@pytest.fixture
def run_case(tmp_path):
    values = np.random.default_rng(84).integers(1000, 40000, (24, 5, 8), dtype=np.uint16)
    header = tmp_path/"pixels.hdr"
    header.with_suffix(".bil").write_bytes(values.transpose(0, 2, 1).tobytes())
    header.write_text("ENVI\nlines=24\nsamples=5\nbands=8\ndata type=12\ninterleave=bil\nreflectance scale factor=65535\n", "utf-8")
    paths = AppPaths(tmp_path/"app")
    registry = DatasetRegistry(paths.database)
    cube = str(registry.import_path(str(header), raw=True).datasets[0].id)
    runner = RunEngine(registry, paths)
    label_map = np.repeat(np.arange(3, dtype=np.int32), 8)[:, None]*np.ones((1, 5), dtype=np.int32)
    label_map[-1] = -2
    label_map[-2] = -1
    version = str(uuid4())
    with connect_database(paths.database) as db:
        label_ids = [row[0] for row in db.execute("SELECT id FROM label ORDER BY sort_order,code LIMIT 3")]
        db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) "
                   "VALUES (?,?,1,?,120,110,'{}','fixture')", (version, cube, f"{cube}/v1"))
    directory = paths.snapshots/cube/"v1"
    directory.mkdir(parents=True)
    np.savez_compressed(directory/"label_map.npz", label_map=label_map)
    (directory/"label_index.json").write_text(json.dumps(dict(enumerate(label_ids))), "utf-8")
    # Deliberately omit spectra.npz: only the pixel snapshot is a run input.
    def recipe(steps):
        row = runner.recipes.create(str(uuid4()), "test", None, {"steps": steps})
        return row["versions"][0]["id"]
    def report(row):
        item = next(item for item in row["artifacts"] if item["kind"] == "report")
        return json.loads((paths.preprocessed/item["relative_path"]).read_text("utf-8"))
    def spectra(row):
        item = next(item for item in row["artifacts"] if item["kind"] == "sample_spectra")
        with np.load(paths.preprocessed/item["relative_path"]) as archive:
            return {key: archive[key].copy() for key in archive.files}
    return SimpleNamespace(runner=runner, paths=paths, registry=registry, cube=cube, version=version,
                           values=values, label_map=label_map, header=header, recipe=recipe, report=report, spectra=spectra)


def step(op, **params):
    return {"op": op, "version": 1, "params": params}
