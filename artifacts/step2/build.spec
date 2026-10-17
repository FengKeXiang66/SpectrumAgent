# -*- mode: python ; coding: utf-8 -*-
"""Canonical onedir build. Invoke with the project's explicit Python 3.12."""
from pathlib import Path

from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

OUTPUT = Path(SPECPATH).resolve()
ROOT = OUTPUT.parents[1]
# Output locations are part of the spec, not ad-hoc command-line build options.
CONF["distpath"] = str(OUTPUT / "dist")
CONF["workpath"] = str(OUTPUT / "build")
Path(CONF["workpath"]).mkdir(parents=True, exist_ok=True)

hiddenimports = collect_submodules("rasterio") + collect_submodules("uvicorn")
datas = collect_data_files("rasterio")
# Do not collect DLLs manually or set GDAL_DATA / PROJ_DATA / PROJ_LIB.
# Analysis resolves rasterio's extension dependencies into rasterio.libs.
# __main__.py calls freeze_support() before any engine import/initialization.
a = Analysis(
    [str(ROOT / "backend" / "__main__.py")],
    pathex=[str(ROOT)], binaries=[], datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="app", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
    disable_windowed_traceback=False,
    contents_directory="_internal",
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=False, name="app",
)
