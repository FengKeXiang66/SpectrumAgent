# -*- mode: python ; coding: utf-8 -*-
"""Current source onedir; build_release.ps1 supplies a new, isolated build root."""
import os
from pathlib import Path
import sys

from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
OUTPUT = Path(os.environ["SPECTRUM_BUILD_ROOT"]).resolve()
if not OUTPUT.is_relative_to(ROOT) or OUTPUT == ROOT:
    raise ValueError("SPECTRUM_BUILD_ROOT must be a dedicated directory inside the workspace")
sys.path.insert(0, str(ROOT / "src-python"))
CONF["distpath"] = str(OUTPUT / "engine-dist")
CONF["workpath"] = str(OUTPUT / "engine-build")
Path(CONF["workpath"]).mkdir(parents=True, exist_ok=True)

slim = os.environ.get("SPECTRUMAGENT_SLIM_BACKEND") == "1"
runtime_module = lambda name: not any(part in {"tests", "testing"} for part in name.split("."))
hiddenimports = (collect_submodules("rasterio", filter=(lambda name: runtime_module(name) and not name.startswith("rasterio.rio")) if slim else lambda name: True)
                 + collect_submodules("uvicorn")
                 + collect_submodules("spectrumagent") + collect_submodules("spectral", filter=runtime_module if slim else lambda name: True)
                 # savefig selects this backend by output suffix at runtime;
                 # the automatic matplotlib hook only sees use("Agg").
                 + ["matplotlib.backends.backend_svg"])
# Python modules and package data are separate collections. In particular the
# catalog is read during database migration, before the readiness handshake.
datas = collect_data_files("rasterio") + collect_data_files("spectrumagent")
a = Analysis(
    [str(ROOT / "backend" / "__main__.py")],
    pathex=[str(ROOT), str(ROOT / "src-python")], binaries=[], datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={"matplotlib":{"backends":["Agg","svg"]}} if slim else {},
    runtime_hooks=[], excludes=["pysptools","pytest","_pytest","IPython","tkinter","PyQt5","PyQt6","PySide2","PySide6"] if slim else [], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="app", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True, disable_windowed_traceback=False,
    contents_directory="_internal",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="app")
