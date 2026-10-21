"""Reproduce §3 table/FK and seed evidence; fingerprint inputs are explicit fixtures."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT),str(ROOT/"src-python")]

from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.recipes import RecipeStore, input_fingerprint

TABLES = ["preprocess_recipe","preprocess_recipe_version","project_recipe","preprocess_run","preprocess_artifact"]


def main():
    directory = ROOT/".runtime/m05-11.2"/uuid4().hex
    directory.mkdir(parents=True)
    database = directory/"verification.sqlite3"
    DatasetRegistry(database)
    store = RecipeStore(database)
    with connect_database(database) as db:
        db.row_factory = sqlite3.Row
        tables = {table:{"table_info":[dict(row) for row in db.execute(f"PRAGMA table_info({table})")],
                        "foreign_key_list":[dict(row) for row in db.execute(f"PRAGMA foreign_key_list({table})")]}
                  for table in TABLES}
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    (HERE/"table-info.json").write_text(json.dumps(tables,ensure_ascii=False,indent=2)+"\n","utf-8")
    seed = store.list()[0]
    (HERE/"builtin-seed.json").write_text(json.dumps(seed,ensure_ascii=False,indent=2)+"\n","utf-8")
    hashes = {"sample.raw":hashlib.sha256(b"fixture binary").hexdigest(),
              "sample.hdr":hashlib.sha256(b"fixture header").hexdigest()}
    dataset_id = "11111111-1111-4111-8111-111111111111"
    a,b = "22222222-2222-4222-8222-222222222222","33333333-3333-4333-8333-333333333333"
    first = input_fingerprint(dataset_id,hashes,a,6)
    second = input_fingerprint(dataset_id,hashes,b,6)
    restored = input_fingerprint(dataset_id,hashes,a,6)
    assert first != second and first == restored
    fingerprint = {"source_level":"pure function fixture measurement; synthetic IDs and source digests, no source file IO",
                   "dataset_id":dataset_id,"source_hashes":hashes,"n_pixels":6,
                   "annotation_version_a":a,"annotation_version_b":b,
                   "fingerprint_a":first,"fingerprint_b":second,"restored":restored}
    (HERE/"fingerprint.json").write_text(json.dumps(fingerprint,indent=2)+"\n","utf-8")
    for source,target in (("src-python/spectrumagent/preprocess/registry.py","registry.diff"),
                          ("src-python/tests/preprocess/test_registry.py","test-registry.diff")):
        context = ["--unified=0"] if target == "test-registry.diff" else []
        output = subprocess.check_output(["git","diff",*context,"HEAD","--",source],cwd=ROOT)
        if output:
            (HERE/target).write_bytes(output)
        else:
            # After commit, reproduce the change against its parent.
            output = subprocess.check_output(["git","diff",*context,"HEAD^","HEAD","--",source],cwd=ROOT)
            (HERE/target).write_bytes(output)
    print(json.dumps({"fingerprint_a":first,"fingerprint_b":second,"tables":list(tables),"seed_code":seed["code"]},indent=2))


if __name__ == "__main__":
    main()
