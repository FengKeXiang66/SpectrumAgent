"""Audit this chat's executed tool inputs; never copy the sensitive session transcript."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

SOURCE = Path(r"C:\Users\Administrator\.codex\sessions\2026\10\18\rollout-2026-10-18T07-08-26-01a14c1f-ac00-75d2-afb8-bf4fe20cc166.jsonl")
OUT = Path(__file__).resolve().parent
raw = SOURCE.read_bytes()
patterns = {
    "powershell_property_mutation": r"\b(?:Set|New|Remove)-ItemProperty\b",
    "reg_mutation": r"\breg(?:\.exe)?\s+(?:add|delete|import|restore|load|unload)\b",
    "registry_provider_mutation": r"\b(?:Set|New|Remove)-Item\b[^\n;]{0,160}HK(?:CU|LM|U):",
    "dotnet_value_mutation": r"\.SetValue\s*\(",
    "dotnet_key_mutation": r"\.(?:DeleteSubKey|DeleteValue|CreateSubKey)\s*\(",
}
calls = 0
candidates = []
for line, item in enumerate(raw.splitlines(), 1):
    row = json.loads(item)
    payload = row.get("payload", {})
    if row.get("type") != "response_item" or payload.get("type") not in ("function_call", "custom_tool_call"):
        continue
    calls += 1
    value = payload.get("input", payload.get("arguments", ""))
    if not isinstance(value, str):
        continue
    matches = [name for name, pattern in patterns.items() if re.search(pattern, value, re.I)]
    if matches:
        # A search/audit command mentioning forbidden command names is not execution.
        candidates.append({"line": line, "tool": payload.get("name"), "call_id": payload.get("call_id"),
                           "input_sha256": hashlib.sha256(value.encode()).hexdigest(), "patterns": matches,
                           "review_required": True})
result = {"recorded_utc": datetime.now(timezone.utc).isoformat(), "thread_id": "01a14c1f-ac00-75d2-afb8-bf4fe20cc166",
          "source": str(SOURCE), "source_prefix_bytes": len(raw), "source_prefix_sha256": hashlib.sha256(raw).hexdigest(),
          "executed_tool_inputs_checked": calls, "patterns": patterns, "candidates": candidates,
          "scope": "this chat's tool inputs through the recorded prefix; external host sessions are outside this audit",
          "manual_registry_mutations_found": 0 if not candidates else None,
          "installer_internal_registry_writes": "NSIS template WriteRegStr/DeleteRegKey are installer behavior; not manual reg commands"}
target = OUT / "registry-history-audit.json"
with target.open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"tool_inputs": calls, "candidate_count": len(candidates), "candidates": candidates}, ensure_ascii=True, indent=2))
