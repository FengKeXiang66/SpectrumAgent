"""Compare embedded code objects to current sources, after normalizing filename."""
import hashlib
import json
import marshal
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[2]
exe = root / "artifacts/step2/dist/app/app.exe"
archive = CArchiveReader(str(exe))
pyz = archive.open_embedded_archive("PYZ.pyz")
results = {}
for source in sorted((root / "backend").glob("*.py")):
    name = source.stem
    if name == "__main__":
        actual = marshal.loads(archive.extract("__main__"))
    else:
        module = "backend" if name == "__init__" else "backend." + name
        actual = pyz.extract(module)
    expected = compile(
        source.read_text(encoding="utf-8"), actual.co_filename,
        "exec", dont_inherit=True, optimize=0,
    )
    results[str(source.relative_to(root))] = actual == expected
output = {"exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "code_matches": results}
target = root / "artifacts/step2/revision-01/frozen-source-comparison.json"
target.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps(output))
assert all(results.values()), "Embedded engine source does not match working tree"
