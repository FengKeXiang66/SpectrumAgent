"""TASK-10 acceptance: real LLM over HTTP, real tools, multi-turn annotation to preprocessing.

Unlike scripts/e2e_task07.py this script never mocks the provider. It talks to the
configured OpenAI-compatible endpoint with the platform's own tool catalogue and then
checks the business end state in the database. A mocked provider can only prove that
the facilities are wired; this proves the model picks the right next step.

Usage:
    .venv/Scripts/python.exe scripts/e2e_task10.py --data-root <absolute data root>

The API key is read from the environment and injected through the platform's
write-only key endpoint. The key is never written to disk by this script.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src-python"))
sys.path.insert(0, str(ROOT))


def read_handshake(data_root):
    for _ in range(60):
        path = Path(data_root) / "run" / "handshake.json"
        if path.exists():
            try:
                return json.loads(path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        time.sleep(1)
    raise SystemExit("no handshake: start the engine first")


def call_api(base, token, path, payload=None, method="GET", timeout=180):
    url = f"{base}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
        return json.loads(raw) if raw.strip() else None


def send_message(base, token, session_id, content, timeout=240):
    """Send one user message and collect the SSE event stream."""
    url = f"{base}/api/v1/agent/sessions/{session_id}/messages"
    request = urllib.request.Request(url, data=json.dumps({"content": content}).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="ignore").strip()
            if line.startswith("event: "):
                events.append(["event", line[7:]])
            elif line.startswith("data: "):
                if events and events[-1][0] == "event":
                    events[-1].append(line[6:])
                    events[-1] = [events[-1][1], json.loads(line[6:])]
    return events


def steps_of(base, token, session_id):
    return call_api(base, token, f"/api/v1/agent/sessions/{session_id}/steps")["steps"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--key", default=os.environ.get("SPECTRUM_LLM_API_KEY", ""))
    parser.add_argument("--message", default="对第一个数据标注PP，其余背景，参数默认")
    args = parser.parse_args()
    data_root = args.data_root.resolve()

    handshake = read_handshake(data_root)
    base = f"http://127.0.0.1:{handshake['port']}/api/v1"
    token = handshake["token"]

    runtime = call_api(base, token, "/agent/runtime")
    print("RUNTIME:", json.dumps(runtime, ensure_ascii=False))
    if runtime["skill_name"] != "conversation-workflows-v2":
        raise SystemExit(f"not running v2: {runtime['skill_name']}")

    if args.key:
        call_api(base, token, "/settings/llm/key", {"key": args.key}, method="PUT")
    settings = call_api(base, token, "/settings/llm")
    print("HAS_KEY:", settings.get("has_key"))
    if not settings.get("has_key"):
        raise SystemExit("no API key: pass --key or set SPECTRUM_LLM_API_KEY")

    session = call_api(base, token, "/agent/sessions", {}, method="POST")
    print("SESSION:", session["id"], session.get("skill_name"))
    before = len(steps_of(base, token, session["id"]))

    events = send_message(base, token, session["id"], args.message)
    print("EVENTS:")
    for name, data in events:
        print("  ", name, json.dumps(data, ensure_ascii=False)[:300])

    after = steps_of(base, token, session["id"])
    print("STEPS:")
    for row in after[before:]:
        print(f"   {row['seq']}. {row['tool']} · {row['status']} · {row['result_summary'][:160]}")

    tools_used = [row["tool"] for row in after[before:]]
    report = {
        "runtime": runtime,
        "session_id": session["id"],
        "message": args.message,
        "event_kinds": [name for name, _ in events],
        "tools_used": tools_used,
        "step_count": len(after) - before,
        "v2_tools_used": [t for t in tools_used if t in {
            "datasets.resolve", "annotations.context", "annotations.prepare",
            "annotations.ensure_labels", "annotations.propose", "annotations.apply_candidate",
            "annotations.set_background", "preprocess.recipes", "preprocess.run_default"}],
    }
    out = ROOT / ".runtime" / "e2e_task10_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
