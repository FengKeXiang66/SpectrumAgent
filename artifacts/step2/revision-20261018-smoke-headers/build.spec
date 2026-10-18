# -*- mode: python ; coding: utf-8 -*-
"""Separate approved smoke-header batch; never overwrites the sealed old dist."""
from pathlib import Path
from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

OUTPUT = Path(SPECPATH).resolve()
ROOT = OUTPUT.parents[2]
CONF["distpath"] = str(OUTPUT / "dist")
CONF["workpath"] = str(OUTPUT / "build")
Path(CONF["workpath"]).mkdir(parents=True, exist_ok=True)
# Same collection strategy as the accepted batch. No manual DLL collection or GDAL env.
a = Analysis(
    [str(ROOT / "backend" / "__main__.py")], pathex=[str(ROOT)],
    binaries=[], datas=collect_data_files("rasterio"),
    hiddenimports=collect_submodules("rasterio") + collect_submodules("uvicorn"),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="app", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=True,
    disable_windowed_traceback=False, contents_directory="_internal",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="app")
