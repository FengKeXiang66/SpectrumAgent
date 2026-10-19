"""Populate only the verified official NSIS cache, with hard anchors and safe paths."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(r"E:\AI_Agent")
OUT = ROOT / "artifacts/step3/checkpoint-4/release-custom-protocol-20261018"
INCOMING = ROOT / "src-tauri/target/tauri"
CACHE = ROOT / "src-tauri/target/.tauri"


def hash_file(path, algorithm="sha256"):
    return hashlib.new(algorithm, path.read_bytes()).hexdigest().upper()


def main():
    archive = INCOMING / "nsis-3.13.zip"
    plugin = INCOMING / "nsis_tauri_utils.dll"
    assert archive.stat().st_size == 2363925 and hash_file(archive, "sha1") == "DB14F8AF2EA346B786C6AE19343F61AAF5E09B8E"
    assert plugin.stat().st_size == 34304 and hash_file(plugin, "sha1") == "75197FEE3C6A814FE035788D1C34EAD39349B860"
    destination = CACHE / "NSIS"
    assert not destination.exists(), "Do not overwrite unknown cache contents"
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for member in z.infolist():
            parts = PurePosixPath(member.filename).parts
            assert parts and parts[0] == "nsis-3.13" and ".." not in parts
            assert not any(":" in p or "\\" in p for p in parts)
            target = destination.joinpath(*parts[1:]).resolve()
            assert target.is_relative_to(destination.resolve())
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as f:
                    f.write(z.read(member))
    plugin_destination = destination / "Plugins/x86-unicode/additional/nsis_tauri_utils.dll"
    plugin_destination.parent.mkdir(parents=True, exist_ok=True)
    with plugin_destination.open("xb") as f:
        f.write(plugin.read_bytes())
    required = ["makensis.exe", "Bin/makensis.exe", "Stubs/lzma-x86-unicode", "Stubs/lzma_solid-x86-unicode",
                "Plugins/x86-unicode/additional/nsis_tauri_utils.dll", "Include/MUI2.nsh", "Include/FileFunc.nsh",
                "Include/x64.nsh", "Include/nsDialogs.nsh", "Include/WinMessages.nsh", "Include/Win/COM.nsh",
                "Include/Win/Propkey.nsh", "Include/Win/RestartManager.nsh"]
    assert all((destination / name).is_file() for name in required)
    assert hash_file(destination / "NSIS.exe", "sha1") == "6D45D4E8CCF18FE1FDAC9164058F356102A2ECF2"
    assert hash_file(plugin_destination, "sha1") == "75197FEE3C6A814FE035788D1C34EAD39349B860"
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "incoming_root": str(INCOMING), "actual_cli_tools_root": str(CACHE),
              "nsis_root": str(destination), "plugin_path": str(plugin_destination), "required_file_count": len(required),
              "required_files_all_present": True, "NSIS_exe_sha1": hash_file(destination / "NSIS.exe", "sha1"),
              "plugin_sha1": hash_file(plugin_destination, "sha1"), "note": "CLI validation still required; no assertion that bundling passed"}
    with (OUT / "tools-cache-layout.json").open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
