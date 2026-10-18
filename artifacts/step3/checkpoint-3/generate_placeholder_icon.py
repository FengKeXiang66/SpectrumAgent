"""Minimal Windows resource placeholder required by installed tauri-build (no design asset)."""
import struct
from pathlib import Path

root = Path(__file__).resolve().parents[3]
target = root / "src-tauri/icons/icon.ico"
size = 32
pixels = bytes((96, 96, 96, 255)) * size * size
mask = bytes(((size + 31) // 32) * 4 * size)
dib = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels + mask
icon = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(dib), 22) + dib
target.parent.mkdir(exist_ok=True)
if target.exists():
    assert target.read_bytes() == icon, "Refuse to overwrite unknown icon"
else:
    target.write_bytes(icon)
print(f"{target}: {len(icon)} bytes; 32x32 RGBA resource placeholder")
