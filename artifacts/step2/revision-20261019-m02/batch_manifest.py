"""Create-once provenance, seven crosschecks and canonical staging for the approved batch."""
import argparse
import hashlib
import json
import marshal
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

BATCH = Path(__file__).resolve().parent
ROOT = BATCH.parents[2]
PRODUCT = BATCH / "dist/app"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write(name, data):
    with (BATCH / name).open("x", encoding="utf-8", newline="\n") as out:
        json.dump(data, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print(json.dumps({"file": name, "result": data}, ensure_ascii=False), flush=True)


def inventory(root):
    paths = sorted(root.rglob("*"))
    assert all(not p.is_symlink() and not p.is_junction() for p in paths), "Reparse path in product"
    return [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in paths if p.is_file()]


def inputs():
    assert not (BATCH / "dist").exists(), "Inputs must precede first build"
    assert not git("diff", "HEAD", "--", "backend", "src-python/spectrumagent", "requirements-lock.txt", "artifacts/step2/build.spec", str(BATCH.relative_to(ROOT)))
    sources = sorted((ROOT / "backend").rglob("*.py")) + [ROOT / "requirements-lock.txt"]
    sources += sorted((ROOT / "src-python/spectrumagent").rglob("*.py"))
    sources += sorted(BATCH.glob("*.py")) + sorted(BATCH.glob("*.ps1")) + [BATCH / "build.spec"]
    # -z avoids core.quotePath octal quoting for Chinese evidence filenames.
    old = subprocess.check_output(
        ["git", "ls-files", "-z", "artifacts/step2"], cwd=ROOT
    ).decode("utf-8").rstrip("\0").split("\0")
    old = [p for p in old if not p.startswith(BATCH.relative_to(ROOT).as_posix() + "/")]
    write("build-inputs.json", {
        "artifact_source_commit": git("rev-parse", "HEAD"),
        "source_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in sources},
        "sealed_old_evidence_sha256": {p: sha(ROOT / p) for p in old},
    })


def unchanged_inputs():
    before = json.loads((BATCH / "build-inputs.json").read_text(encoding="utf-8"))
    for field in ("source_sha256", "sealed_old_evidence_sha256"):
        for path, digest in before[field].items():
            if ROOT / path == Path(__file__).resolve() and sha(ROOT / path) != digest:
                # The manifest generator may advance independently of artifact sources.
                original = subprocess.check_output(["git", "show", before["artifact_source_commit"] + ":" + path], cwd=ROOT)
                current = subprocess.check_output(["git", "show", "HEAD:" + path], cwd=ROOT)
                assert hashlib.sha256(original).hexdigest() == digest and current == (ROOT / path).read_bytes()
                continue
            assert sha(ROOT / path) == digest, f"Changed {field}: {path}"
    return before


def source():
    before = unchanged_inputs()
    exe = PRODUCT / "app.exe"
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive("PYZ.pyz")
    matches = {}
    for path in sorted((ROOT / "backend").glob("*.py")):
        name = path.stem
        code = marshal.loads(archive.extract("__main__")) if name == "__main__" else pyz.extract(
            "backend" if name == "__init__" else "backend." + name)
        expected = compile(path.read_text(encoding="utf-8"), code.co_filename, "exec", dont_inherit=True, optimize=0)
        matches[path.relative_to(ROOT).as_posix()] = code == expected
    for path in sorted((ROOT / "src-python/spectrumagent").rglob("*.py")):
        parts = path.relative_to(ROOT / "src-python").with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        code = pyz.extract(module)
        expected = compile(path.read_text(encoding="utf-8"), code.co_filename, "exec", dont_inherit=True, optimize=0)
        matches[path.relative_to(ROOT).as_posix()] = code == expected
    assert all(matches.values()), "Embedded Python source mismatch"
    assert not any(name == "matplotlib" or name.startswith("matplotlib.") for name in pyz.toc), "Unexpected matplotlib payload"
    write("source-manifest.json", {
        "artifact_source_commit": before["artifact_source_commit"],
        "source_sha256": before["source_sha256"], "exe_bytes": exe.stat().st_size,
        "exe_sha256": sha(exe), "embedded_code_matches": matches,
        "previous_manifest": "artifacts/step2/revision-20261018-smoke-headers/product-manifest.json",
    })


def seal():
    before = unchanged_inputs()
    source_manifest = json.loads((BATCH / "source-manifest.json").read_text(encoding="utf-8"))
    files = inventory(PRODUCT)
    internal = [r for r in files if r["path"].startswith("_internal/")]
    exe = PRODUCT / "app.exe"
    old_manifest = json.loads((BATCH.parent / "revision-20261018-smoke-headers/product-manifest.json").read_text(encoding="utf-8"))
    old_internal = [r for r in old_manifest["files"] if r["path"].startswith("_internal/")]
    checks = {
        "1_exe_exists_and_new_batch_bytes": exe.is_file() and exe.stat().st_size == source_manifest["exe_bytes"],
        "2_exe_sha_matches_source_manifest": sha(exe) == source_manifest["exe_sha256"],
        "3_internal_543_files_238793334_bytes": len(internal) == 543 and sum(r["bytes"] for r in internal) == 238793334,
        "4_python312_dll_exists": (PRODUCT / "_internal/python312.dll").is_file(),
        "5_rasterio_36_dll": len(list((PRODUCT / "_internal/rasterio.libs").glob("*.dll"))) == 36,
        "6_rasterio_15_pyd": len(list((PRODUCT / "_internal/rasterio").glob("*.pyd"))) == 15,
        "7_no_experimental_residue": {p.name for p in PRODUCT.iterdir()} == {"app.exe", "_internal"}
            and all(not any(s in r["path"].lower() for s in ("test-backup", "manifest", "fault_fixture", ".tmp")) for r in files),
    }
    old_by_path = {r["path"]: r for r in old_internal}
    changed = [r["path"] for r in internal if old_by_path.get(r["path"]) != r]
    assert changed in ([], ["_internal/base_library.zip"]), "Unexpected dependency payload drift"
    zip_order_only = False
    if changed:
        # PyInstaller ZIP ordering differs between builds; every member byte and
        # all member metadata except the order-dependent offset must still match.
        old_zip = ROOT / old_manifest["artifact_root"] / changed[0]
        with zipfile.ZipFile(old_zip) as a, zipfile.ZipFile(PRODUCT / changed[0]) as b:
            assert set(a.namelist()) == set(b.namelist()) and a.comment == b.comment
            metadata = ("date_time", "compress_type", "comment", "extra", "create_system", "create_version",
                        "extract_version", "flag_bits", "volume", "internal_attr", "external_attr", "CRC", "compress_size", "file_size")
            for name in a.namelist():
                assert a.read(name) == b.read(name), "base_library.zip member bytes changed"
                assert all(getattr(a.getinfo(name), key) == getattr(b.getinfo(name), key) for key in metadata)
            zip_order_only = a.namelist() != b.namelist()
            assert zip_order_only
    assert len(files) == 544
    write("seven-crosschecks.json", {"checks": checks, "all_passed": all(checks.values()),
          "old_exe_bytes": next(r["bytes"] for r in old_manifest["files"] if r["path"] == "app.exe"), "new_exe_bytes": exe.stat().st_size,
          "byte_change_basis": "Milestone03 approved composed dataset app; source manifest verifies all backend/spectrumagent embedded code",
          "internal_changed_paths": changed, "zip_order_only_payloads_identical": zip_order_only,
          "old_evidence_unchanged": True})
    assert all(checks.values()), "Do not issue authoritative product manifest on failed check"
    write("product-manifest.json", {
        "schema_version": old_manifest["schema_version"],
        "artifact_source_commit": before["artifact_source_commit"],
        "manifest_generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "manifest_generator_commit": git("rev-parse", "HEAD"),
        "artifact_root": PRODUCT.relative_to(ROOT).as_posix(), "files": files,
    })


def stage():
    unchanged_inputs()
    manifest = json.loads((BATCH / "product-manifest.json").read_text(encoding="utf-8"))
    assert inventory(PRODUCT) == manifest["files"]
    destination = BATCH / "staged/backend"
    assert not destination.exists(), "Never overwrite existing stage"
    shutil.copytree(PRODUCT, destination)
    assert inventory(destination) == manifest["files"]
    write("staging-comparison.json", {"mode": "Canonical", "source": str(PRODUCT),
          "destination": str(destination), "manifest": str(BATCH / "product-manifest.json"),
          "matched_files": len(manifest["files"]), "fault_fixture": False,
          "scope": "new engine batch staging only; not final Tauri resource resolver/release validation"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inputs", "source", "seal", "stage", "verify"])
    action = parser.parse_args().action
    if action == "verify":
        unchanged_inputs()
        manifest = json.loads((BATCH / "product-manifest.json").read_text(encoding="utf-8"))
        assert inventory(PRODUCT) == manifest["files"]
        print('sealed_old_evidence_unchanged=true new_product_manifest_match=true')
    else:
        globals()[action]()
