"""Byte-level PE comparison. Only documented timestamp/CodeView metadata is normalized."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pefile

OUT = Path(__file__).resolve().parent
ROOT = Path(r"E:\AI_Agent")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(path):
    raw = Path(path).read_bytes()
    pe = pefile.PE(data=raw)
    fields = [{"kind": "COFF.TimeDateStamp", "offset": pe.FILE_HEADER.get_field_absolute_offset("TimeDateStamp"), "size": 4,
               "value": pe.FILE_HEADER.TimeDateStamp}]
    debug = []
    for entry in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []):
        field = entry.struct
        fields.append({"kind": "DEBUG.TimeDateStamp", "offset": field.get_field_absolute_offset("TimeDateStamp"),
                       "size": 4, "value": field.TimeDateStamp})
        if field.Type == 2:
            start, size = field.PointerToRawData, field.SizeOfData
            data = raw[start:start + size]
            assert data.startswith(b"RSDS"), "Unexpected CodeView format; do not silently normalize"
            fields.append({"kind": "CodeView.RSDS.GUID_age_path", "offset": start + 4, "size": size - 4,
                           "pdb_path": data[24:].split(b"\0", 1)[0].decode("utf-8"), "guid_bytes": data[4:20].hex()})
            # RSDS path length can differ with independent target directories.
            fields.append({"kind": "DEBUG.SizeOfData", "offset": field.get_field_absolute_offset("SizeOfData"),
                           "size": 4, "value": size})
        debug.append({"type": field.Type, "raw_offset": field.PointerToRawData, "size": field.SizeOfData})
    normalized = bytearray(raw)
    for row in fields:
        normalized[row["offset"]:row["offset"] + row["size"]] = b"\0" * row["size"]
    return raw, pe, normalized, fields, debug


def compare(left, right):
    a, p, norm_a, meta_a, dbg_a = inspect(left)
    b, q, norm_b, meta_b, dbg_b = inspect(right)
    sections = []
    assert [s.Name for s in p.sections] == [s.Name for s in q.sections]
    for s, t in zip(p.sections, q.sections):
        sections.append({"name": s.Name.rstrip(b"\0").decode(),
                         "left_offset": s.PointerToRawData, "right_offset": t.PointerToRawData,
                         "left_bytes": s.SizeOfRawData, "right_bytes": t.SizeOfRawData,
                         "left_sha256": digest(s.get_data()), "right_sha256": digest(t.get_data()),
                         "raw_equal": s.get_data() == t.get_data(),
                         "metadata_normalized_equal": norm_a[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
                         == norm_b[t.PointerToRawData:t.PointerToRawData+t.SizeOfRawData]})
    differences = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    unexplained = [i for i, (x, y) in enumerate(zip(norm_a, norm_b)) if x != y]
    return {"left": str(left), "right": str(right), "left_bytes": len(a), "right_bytes": len(b),
            "left_sha256": digest(a), "right_sha256": digest(b), "byte_identical": a == b,
            "different_byte_count": len(differences) + abs(len(a)-len(b)),
            "metadata_normalized_equal": norm_a == norm_b,
            "unexplained_different_byte_count": len(unexplained) + abs(len(a)-len(b)),
            "unexplained_first_offsets": unexplained[:64], "sections": sections,
            "left_metadata": meta_a, "right_metadata": meta_b, "left_debug": dbg_a, "right_debug": dbg_b,
            "IMAGE_DEBUG_TYPE_REPRO_present": any(d["type"] == 16 for d in dbg_a + dbg_b)}


def main():
    cba = OUT.parent / "temp/canonical-cba991aa47d8/spectrum-agent.exe"
    final = OUT / "temp/canonical-22a13e6a4d2e/spectrum-agent.exe"
    fresh = ROOT / "src-tauri/target/repro-check/release/spectrum-agent.exe"
    result = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
              "historical_cba_vs_22a": compare(cba, final), "true_recompile_vs_22a": compare(final, fresh)}
    result["verdict"] = "可复现" if result["true_recompile_vs_22a"]["byte_identical"] else "不可复现（不可字节复现）"
    target = OUT / "repro-pe-comparison.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
