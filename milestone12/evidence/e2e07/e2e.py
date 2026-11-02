"""TASK-07 12.7 / R24 + 12.7.1 / R26-R27: real ASGI routes, mock provider, synthetic DN only.

Run with .venv/Scripts/python.exe from the repository. The evidence copy is
identical and runnable. No source/key/vendor configuration is supplied by users.
All generated cubes and application data stay under E:/AI_Agent/.runtime.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from time import perf_counter
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "src-python/spectrumagent/app.py").is_file())
OUT = ROOT / "milestone07/evidence/12.7"
sys.path[:0] = [str(ROOT), str(ROOT / "src-python")]

import httpx
import numpy as np
from fastapi.testclient import TestClient
from scipy.io import loadmat

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.agent import mat
from spectrumagent.agent.llm import OpenAICompatibleClient, _json, set_api_key
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.raster import rasterize
from spectrumagent.app import create_app
from spectrumagent.preprocess.run import file_sha256


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", "utf-8")


def rect(r0, c0, r1, c1):
    return {"type": "polygon", "points": [[r0, c0], [r0, c1], [r1, c1], [r1, c0]]}


class Evidence:
    def __init__(self):
        self.data = {"source_level": "R24 TestClient / real ASGI stack / synthetic DN / MockTransport",
                     "started_at": datetime.now(timezone.utc).isoformat(), "base_commit": "c9795c8",
                     "assertions": [], "http": [], "measurements": [], "success": False}

    def check(self, condition, label):
        self.data["assertions"].append({"name": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    def call(self, client, method, path, body=None, status=200):
        started = perf_counter()
        response = client.request(method, path, **({"json": body} if body is not None else {}))
        self.data["http"].append({"method": method, "path": path, "status": response.status_code,
                                  "seconds": perf_counter() - started})
        self.check(response.status_code == status, f"HTTP {method} {path} = {status}")
        if status != 401:
            self.check("X-SpectrumAgent-Boot-Id" in response.headers, f"identity header {method} {path}")
        return response

    def stream(self, client, path, body):
        started = perf_counter()
        with client.stream("POST", path, json=body) as response:
            self.check(response.status_code == 200, "SSE HTTP 200")
            self.check(response.headers["content-type"].startswith("text/event-stream"), "SSE MIME")
            events, event = [], None
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    events.append({"event": event, "data": json.loads(line[6:])})
        return events, perf_counter() - started


def synthetic_cube(directory, shape, *, large=False):
    """Rows only, no full source materialization; deterministic fixture rule.

    Small fixture: annotation conftest's RNG seed/range, 40x12, 8 bands as #05.
    Large: R24 fixed shape, float32 DN so source itself is about 118MB. Each
    line is 1000 + (flattened sample/band index + line) modulo 5000. Spectra
    have no physical significance. ENVI BIP / scale 65535, never B01 outputs.
    """
    directory.mkdir(parents=True)
    header = directory / "synthetic.hdr"
    lines, samples, bands = shape
    rng = np.random.default_rng(17)  # Existing annotation test fixture provenance.
    with header.with_suffix(".img").open("wb") as stream:
        for row in range(lines):
            values = ((1000 + (np.arange(samples * bands).reshape(samples, bands) + row) % 5000).astype("<f4")
                      if large else rng.integers(1000, 6000, (samples, bands), dtype=np.uint16))
            stream.write(values.tobytes())
    wavelengths = ",".join(str(450 + i) for i in range(bands))
    header.write_text(f"ENVI\nlines={lines}\nsamples={samples}\nbands={bands}\ndata type={4 if large else 12}\n"
                      f"interleave=bip\nbyte order=0\nreflectance scale factor=65535\nwavelength={{{wavelengths}}}\n", "utf-8")
    return header


def observe_mat(measurements):
    """Instrumentation only: original generate and scipy writer both execute."""
    generate, writer = mat.MatStore.generate, mat.savemat

    def measured_generate(store, cube, version, label_map):
        item = {"cube_id": str(cube), "version_id": str(version), "write": None}
        measurements.append(item)
        started = perf_counter()
        try:
            result = generate(store, cube, version, label_map)
            item.update(status="ok", db_row=result,
                        file_bytes=(store.paths.root / result["relative_path"]).stat().st_size)
            return result
        except Exception as error:
            item.update(status="error", error_type=type(error).__name__)
            raise
        finally:
            item["seconds"] = perf_counter() - started

    def measured_write(path, contents, **kwargs):
        tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        started = perf_counter()
        try:
            return writer(path, contents, **kwargs)
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            measurements[-1]["write"] = {"seconds": perf_counter() - started,
                "tracemalloc_peak_increment_bytes": peak - before,
                "do_compression": kwargs["do_compression"]}
    return patch.object(mat.MatStore, "generate", measured_generate), patch.object(mat, "savemat", measured_write)


def assert_snapshot(e, sessions, version):
    snapshot = sessions.read_version(version)
    with connect_database(sessions.database) as db:
        relative = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=?", (version,)).fetchone()[0]
    folder = sessions.paths.snapshots / relative
    e.check({p.name for p in folder.iterdir()} == {"annotation.json", "label_map.npz", "label_index.json", "spectra.npz"}, "exact four snapshot files")
    e.check(np.array_equal(rasterize(snapshot["document"], snapshot["label_map"].shape), snapshot["label_map"]), "snapshot JSON/map bit-exact")
    return snapshot, folder


def annotation_chain(e, client, app, header):
    imported = e.call(client, "POST", "/api/v1/datasets/import", {"path": str(header), "raw": True}).json()
    cube = imported["datasets"][0]["id"]
    base = f"/api/v1/annotations/{cube}/draft"
    report = e.call(client, "POST", f"/api/v1/datasets/{cube}/superpixels",
                    {"n_segments": 24, "compactness": .5, "pca_components": 5}).json()
    e.check(report["superpixel_count"] > 0, "real superpixel engine executed")
    empty = e.call(client, "GET", base).json()
    e.check(empty["estimated_mat_bytes"] == empty["revision"] == 0 and empty["document"] is None, "empty draft estimated bytes = 0")
    first = e.call(client, "POST", base + "/regions", {"revision": 0, "class_code": "BG", "geometry": rect(0, 0, 4, 4)}).json()
    partial = e.call(client, "GET", base).json()
    e.check(partial["estimated_mat_bytes"] == 16 * 8 * 4, "partial estimated bytes = 512")
    e.call(client, "POST", base + "/regions/" + first["region_id"], {"revision": 1, "geometry": rect(0, 0, 40, 6)})
    e.call(client, "POST", base + "/regions", {"revision": 2, "class_code": "PP", "geometry": rect(0, 6, 40, 12)})
    full = e.call(client, "GET", base).json()
    e.check(full["estimated_mat_bytes"] == 40 * 12 * 8 * 4, "full estimated bytes = 15360")
    before = app.state.annotation_sessions.drafts.get(cube)
    started = perf_counter()
    confirmed = e.call(client, "POST", base + "/confirm", {"revision": 3}).json()
    confirm_seconds = perf_counter() - started
    e.check(confirmed["training_mat_id"] is not None and confirmed["overlap_conflicts"] == 0, "REST confirm produces MAT")
    e.check(app.state.annotation_sessions.drafts.get(cube) == before, "REST confirmation leaves draft unchanged")
    snapshot, _ = assert_snapshot(e, app.state.annotation_sessions, confirmed["version_id"])
    download = e.call(client, "GET", f"/api/v1/annotations/{cube}/versions/{confirmed['version_id']}/training-mat")
    e.check(download.headers["content-type"] == "application/octet-stream", "MAT download MIME")
    e.check(download.headers["content-disposition"] == 'attachment; filename="training_mat.mat"', "MAT attachment name")
    e.check(download.content.startswith(b"MATLAB 5.0 MAT-file"), "MATLAB magic")
    mats = mat.MatStore(app.state.superpixel_engine.registry, app.state.annotation_sessions.paths)
    row = mats.get(cube, confirmed["version_id"])
    content = loadmat(mats.file(row), simplify_cells=True)
    e.check(content["spectra"].dtype == np.float32 and content["spectra"].shape == (480, 8), "MAT float32 full spectra shape")
    e.check(set(content["labels"]) == {0, 3} and row["n_classes"] == 4, "original indices {0,3}, full four-class table")
    e.check(np.array_equal(snapshot["label_map"][content["rows"], content["cols"]], content["labels"]), "MAT rows/cols reverse-map labels")
    raw, _ = app.state.superpixel_engine.registry.readable(cube, raw=True)
    dn = np.concatenate([raw.read_region(r, r + 1, 0, 12).reshape(-1, 8) for r in range(40)])
    e.check(np.array_equal(content["spectra"], dn.astype(np.float32)), "MAT raw DN exact, no B01")
    e.check(json.loads(content["label_index"]) == snapshot["label_index"], "MAT full frozen label_index")
    e.check(file_sha256(mats.file(row)) == row["sha256"], "MAT file SHA256 matches DB")
    exported = app.state.agent_tools.invoke("training_mat.export", {"cube_id": cube, "version_id": confirmed["version_id"]})
    e.check(set(exported) == {"cube_id", "version_id", "training_mat_id", "n_spectra", "n_bands", "n_classes", "sha256", "status"}, "export exact eight keys")
    e.check(all(type(v) in (str, int, bool, float) for v in exported.values()), "export all scalars")
    e.data["annotation"] = {"cube_id": cube, "version": confirmed, "export": exported,
                            "estimated_mat_bytes": [0, 512, 15360], "confirm_http_seconds": confirm_seconds}
    return cube


def settings_chain(e, client):
    # Runtime-only mock fixture, not a vendor default. No credential is written to evidence.
    config = {"base_url": "https://mock.invalid/v1", "model": "task07-replay",
              "temperature": "", "max_tokens": "", "timeout_ms": "", "egress_enabled": True}
    e.call(client, "PUT", "/api/v1/settings/llm", config)
    before = e.call(client, "GET", "/api/v1/settings/llm").json()
    e.check({key: before[key] for key in config} == config, "settings six-key configuration round-trip")
    e.check(before["has_key"] is False, "settings config PUT leaves has_key=false")
    credential = uuid4().hex
    status = e.call(client, "PUT", "/api/v1/settings/llm/key", {"key": credential}).json()
    e.check(status == {"has_key": True}, "settings key PUT returns only has_key=true")
    after = e.call(client, "GET", "/api/v1/settings/llm").json()
    e.check(after["has_key"] is True, "settings GET has_key=true after key PUT")
    e.check(set(after) == set(config) | {"has_key"} and credential not in _json(after), "settings GET excludes key field and credential body")
    e.check({key: after[key] for key in config} == config, "settings key PUT preserves six-key configuration")
    e.data["settings_chain"] = {"sequence": ["PUT config", "GET has_key=false", "PUT key", "GET has_key=true without key body"],
                                "configuration_preserved": True, "credential_echoed": False}


def dialogue_chain(e, client, app, cube):
    # Runtime fixture configuration, never a default or a vendor configuration.
    e.call(client, "PUT", "/api/v1/settings/llm", {"base_url": "https://mock.invalid/v1", "model": "task07-replay"})
    calls, timings = [], []

    def provider(request):
        started = perf_counter()
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            message = {"content": None, "tool_calls": [{"id": "confirm-1", "type": "function", "function": {
                "name": "annotations.draft_confirm", "arguments": _json({"cube_id": cube, "revision": 3})}}]}
        else:
            e.check("tools" not in body, "INTERPRET sends tools=None")
            message = {"content": "标注版本已确认，训练 MAT 已生成。"}
        response = httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
        timings.append({"stage": "PARSE" if len(calls) == 1 else "INTERPRET", "seconds": perf_counter() - started})
        return response

    app.state.agent_llm_factory = lambda session: OpenAICompatibleClient(app.state.annotation_sessions.database,
        session_id=session, transport=httpx.MockTransport(provider))
    session = e.call(client, "POST", "/api/v1/agent/sessions", {}).json()
    path = f"/api/v1/agent/sessions/{session['id']}/messages"
    with connect_database(app.state.annotation_sessions.database) as db:
        old_count = db.execute("SELECT count(*) FROM annotation_version WHERE cube_id=?", (cube,)).fetchone()[0]
    events, message_seconds = e.stream(client, path, {"content": "确认当前标注版本"})
    e.check([v["event"] for v in events] == ["human_check"], "initial SSE suspends at HUMAN_CHECK")
    with connect_database(app.state.annotation_sessions.database) as db:
        e.check(db.execute("SELECT count(*) FROM annotation_version WHERE cube_id=?", (cube,)).fetchone()[0] == old_count, "HUMAN_CHECK executes zero confirmations")
    confirm_spans = []
    original = app.state.annotation_sessions.confirm
    def measured_confirm(*args, **kwargs):
        started = perf_counter()
        result = original(*args, **kwargs)
        confirm_spans.append(perf_counter() - started)
        return result
    with patch.object(app.state.annotation_sessions, "confirm", measured_confirm):
        resumed, approve_seconds = e.stream(client, path, {"check_id": events[0]["data"]["check_id"], "decision": "approve"})
    e.check([v["event"] for v in resumed] == ["step", "done"], "approve SSE sequence step/done")
    summary = resumed[0]["data"]["result_summary"]
    e.check(resumed[0]["data"]["status"] == "ok" and summary["training_mat_id"], "approved step has version and MAT")
    e.check(len(calls) == 2 and len(confirm_spans) == 1, "exact two mock provider calls and one confirm")
    e.check("[[" not in _json(calls[-1]["messages"]), "INTERPRET context excludes coordinate arrays")
    assert_snapshot(e, app.state.annotation_sessions, summary["version_id"])
    with connect_database(app.state.annotation_sessions.database) as db:
        e.check(db.execute("SELECT count(*) FROM training_mat WHERE annotation_version_id=?", (summary["version_id"],)).fetchone()[0] == 1, "dialogue MAT persisted")
        audits = db.execute("SELECT session_id,status,prompt_tokens,completion_tokens,total_tokens FROM llm_call").fetchall()
    e.check(len(audits) == 2 and all(tuple(r) == (session["id"], "ok", None, None, None) for r in audits), "gateway audits session id, usage absent stays NULL")
    step_response = e.call(client, "GET", f"/api/v1/agent/sessions/{session['id']}/steps").json()
    e.check(len(step_response["steps"]) == 1 and len(step_response["steps"][0]["result_digest"]) == 64, "durable step and digest")
    e.data["dialogue"] = {"session_id": session["id"], "initial_events": events, "resumed_events": resumed,
        "provider": "httpx.MockTransport; two callbacks; no real provider network", "provider_calls": len(calls),
        "message_to_human_check_seconds": message_seconds, "approve_to_final_sse_seconds": approve_seconds,
        "total_http_seconds": message_seconds + approve_seconds, "provider_stages": timings,
        "confirm_seconds": confirm_spans[0], "mat_generation_seconds": e.data["measurements"][-1]["seconds"],
        "savemat_seconds": e.data["measurements"][-1]["write"]["seconds"],
        "timing_note": "nested spans, not additive; TestClient buffers finite SSE; human think time excluded"}


def plan_chain(e, client, app):
    """F06: real HTTP + gateway, immutable plans and plan-level invalidation."""
    database = app.state.annotation_sessions.database
    names = ["datasets.list", "settings.llm_get", "datasets.list"]
    results = []
    for action, indices in [("skip", [0]), ("rollback", [1, 2]), ("reject", [])]:
        bodies = []
        def provider(request):
            body = json.loads(request.content)
            bodies.append(body)
            message = {"content": "仅解读已执行步骤，其余步骤未执行。"}
            if "tools" in body:
                message = {"content": None, "tool_calls": [{"id": f"{action}-{i}", "type": "function", "function": {
                    "name": name, "arguments": "{}"}} for i, name in enumerate(names)]}
            return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
        factory = lambda session: OpenAICompatibleClient(database, session_id=session, transport=httpx.MockTransport(provider))
        with patch.object(app.state, "agent_llm_factory", factory), patch.object(app.state.agent_tools, "invoke", wraps=app.state.agent_tools.invoke) as invoke:
            session = e.call(client, "POST", "/api/v1/agent/sessions", {}).json()
            path = f"/api/v1/agent/sessions/{session['id']}/messages"
            initial, _ = e.stream(client, path, {"content": f"计划动作 {action}"})
            e.check([event["event"] for event in initial] == ["plan"], f"{action}: multistep suspends before execution")
            plan = initial[0]["data"]
            e.check(plan == {"plan_id": plan["plan_id"], "reason": "执行计划待确认", "steps": [
                {"seq": i + 1, "tool": name, "summary": {}, "gpu": False, "estimate_ms": None} for i, name in enumerate(names)]},
                f"{action}: exact static plan payload")
            e.check(len(bodies) == 1 and invoke.call_count == 0, f"{action}: one PARSE and no tool execution while pending")
            answer = {"plan_id": plan["plan_id"], "action": action, "reason": f"用户原因 {action}"}
            if action != "reject":
                answer["step_ref"] = 2
            resumed, _ = e.stream(client, path, answer)
            e.check([event["event"] for event in resumed] == ["step"] * len(indices) + ["done"], f"{action}: effective event sequence")
            e.check([call.args[0] for call in invoke.call_args_list] == [names[i] for i in indices], f"{action}: only effective tools execute in order")
        with connect_database(database) as db:
            steps = db.execute("SELECT tool,status FROM agent_step WHERE round_id=? ORDER BY seq", (plan["plan_id"],)).fetchall()
            audits = db.execute("SELECT session_id,action,seq_ref,reason FROM agent_plan_action WHERE round_id=?", (plan["plan_id"],)).fetchall()
            status = db.execute("SELECT status FROM agent_round WHERE id=?", (plan["plan_id"],)).fetchone()[0]
        e.check(steps == [(names[i], "ok") for i in indices], f"{action}: no step rows for unexecuted calls")
        e.check(audits == [(session["id"], action, None if action == "reject" else 2, answer["reason"])], f"{action}: original reason and plan action audited")
        e.check(status == "done", f"{action}: round finishes")
        if action == "reject":
            e.check(len(bodies) == 1 and resumed == [{"event": "done", "data": {"content": "计划已拒绝、未执行", "step_count": 0}}],
                    "reject: zero execution and no INTERPRET")
        else:
            messages = bodies[-1]["messages"]
            actual_calls = [call for message in messages if message["role"] == "assistant" for call in message["tool_calls"]]
            tool_results = [message for message in messages if message["role"] == "tool"]
            e.check(len(bodies) == 2 and "tools" not in bodies[-1], f"{action}: exactly PARSE plus INTERPRET")
            e.check([call["id"] for call in actual_calls] == [f"{action}-{i}" for i in indices]
                    and [message["tool_call_id"] for message in tool_results] == [call["id"] for call in actual_calls],
                    f"{action}: tool_calls and results have matching counts and ids")
            e.check(json.loads(messages[-1]["content"]) == {"skipped": [
                {"seq": i + 1, "tool": name} for i, name in enumerate(names) if i not in indices],
                "rolled_back_from": 2 if action == "rollback" else None}, f"{action}: all unexecuted calls appear in INTERPRET summary")
        results.append({"action": action, "initial_events": initial, "resumed_events": resumed, "provider_calls": len(bodies),
                        "executed_indices": indices, "audit": [list(row) for row in audits]})
    e.data["plan"] = {"provider": "httpx.MockTransport; no real provider network", "cases": results}


def gesture_chain(e, client, app, cube):
    """12.8: stored gestures -> SAM/region -> scalar tool interpretation."""
    base = f"/api/v1/annotations/{cube}"
    sessions = app.state.annotation_sessions
    initial = e.call(client, "GET", base + "/draft").json()
    revision, writes = initial["revision"], []
    refs = {}
    for kind, seed in [("point", {"point": [2, 3]}), ("box", {"box": [0, 4, 0, 4]}),
                       ("doodle", {"doodle": [[2, 3], [3, 3]]})]:
        result = e.call(client, "POST", base + "/gestures", {"seed": seed}).json()
        e.check(set(result) == {"gesture_ref", "kind"} and result["kind"] == kind
                and re.fullmatch(r"g-[0-9a-f]{32}", result["gesture_ref"]), f"gesture: {kind} stored with opaque reference")
        refs[kind] = result["gesture_ref"]
    working = f"/api/v1/datasets/{cube}/annotations/working"
    queue_before = e.call(client, "GET", working).json()["queue"]
    sam_results = []
    for floor, confidence in [(-1, "medium"), (.99, "low")]:
        result = e.call(client, "POST", base + "/draft/candidates", {"revision": revision, "class_code": "PE", "method": "SAM",
            "params": {"gesture_ref": refs["doodle"], "threshold": .5, "queue_min_similarity": floor}}).json()
        e.check(set(result) == {"revision", "region_id", "geometry_type", "preview_statistics"}
                and set(result["preview_statistics"]) == {"n_superpixels", "pixel_count", "min_similarity", "avg_similarity"}, "gesture: exact SAM response shape")
        revision = result["revision"]; writes.append(revision)
        document = e.call(client, "GET", base + "/draft").json()["document"]
        region = document["regions"][-1]
        e.check(region["source"] == "algorithm" and region["confidence"] == confidence
                and region["geometry"]["type"] == "pixel_set", f"gesture: SAM source and {confidence} confidence persisted")
        if confidence == "low":
            e.check(result["preview_statistics"]["min_similarity"] < floor, "gesture: real SAM minimum is below 0.99")
        e.check(len(e.call(client, "GET", working).json()["queue"]) == len(queue_before), "gesture: no ghost candidate remains")
        sam_results.append(result)
    manual = e.call(client, "POST", base + "/draft/regions", {"revision": revision, "class_code": "PP", "geometry": {"gesture_ref": refs["box"]}}).json()
    revision = manual["revision"]; writes.append(revision)
    region = e.call(client, "GET", base + "/draft").json()["document"]["regions"][-1]
    e.check(region["source"] == "manual" and region["confidence"] == "high", "gesture: manual default high confidence")
    bodies = []
    arguments = {"cube_id": cube, "revision": revision, "class_code": "PET", "geometry": {"gesture_ref": refs["doodle"]}}
    def provider(request):
        body = json.loads(request.content); bodies.append(body)
        message = {"content": "手势标注已完成。"}
        if "tools" in body:
            message = {"content": None, "tool_calls": [{"id": "gesture-tool", "type": "function", "function": {
                "name": "annotations.draft_add_region", "arguments": _json(arguments)}}]}
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
    factory = lambda session: OpenAICompatibleClient(sessions.database, session_id=session, transport=httpx.MockTransport(provider))
    with patch.object(app.state, "agent_llm_factory", factory):
        session = e.call(client, "POST", "/api/v1/agent/sessions", {}).json()
        path = f"/api/v1/agent/sessions/{session['id']}/messages"
        events, _ = e.stream(client, path, {"content": "用当前手势标注 PET"})
        e.check([event["event"] for event in events] == ["step", "done"] and events[0]["data"]["status"] == "ok", "gesture: tool replay executes")
        summary = events[0]["data"]["result_summary"]
        e.check(set(summary) == {"cube_id", "revision", "region_id", "op", "n_superpixels", "pixel_count", "class_code"}
                and all(value is None or type(value) in (str, int, float, bool) for value in summary.values()), "gesture: tool summary is exactly seven scalars")
        revision = summary["revision"]; writes.append(revision)
        text = _json(bodies[-1]["messages"])
        e.check("[[" not in text and not re.search(r"\b(points|polygon|sample_pixels|bbox|document)\b", text), "gesture: no geometry in INTERPRET")
        row = e.call(client, "GET", base + "/draft").json()["document"]
        region = row["regions"][-1]
        e.check(region["source"] == "manual" and row["classes"][region["class_index"]]["code"] == "PET", "gesture: tool wrote manual PET")
        stale_events, _ = e.stream(client, path, {"content": "重放旧 revision"})
        e.check([event["event"] for event in stale_events] == ["step", "error"]
                and stale_events[0]["data"]["status"] == "error" and stale_events[-1]["data"]["code"] == "DRAFT_REVISION_CONFLICT", "gesture: stale tool revision is an audited step error")
        e.check(e.call(client, "GET", base + "/draft").json()["document"] == row, "gesture: stale tool leaves document unchanged")
    slic = e.call(client, "POST", base + "/draft/candidates", {"revision": revision, "class_code": "PE", "method": "SLIC",
        "params": {"n_segments": 24, "compactness": .5, "pca_components": 5}}, status=400)
    e.check(slic.json()["error"] == "TOOL_NOT_IMPLEMENTED", "gesture: SLIC remains explicitly unsupported")
    missing = e.call(client, "POST", base + "/draft/regions", {"revision": revision, "class_code": "PP", "geometry": {"gesture_ref": "g-" + "0" * 32}}, status=404)
    e.check(missing.json()["error"] == "GESTURE_NOT_FOUND", "gesture: unknown reference is 404")
    stale = e.call(client, "POST", base + "/draft/regions", {"revision": arguments["revision"], "class_code": "PP", "geometry": {"gesture_ref": refs["box"]}}, status=409)
    e.check(stale.json()["error"] == "DRAFT_REVISION_CONFLICT", "gesture: stale REST revision is HTTP 409")
    # Isolate this chain's intentional cross-class overlaps from later confirm
    # recovery tests. Reuse the same undo service; no document/table manipulation.
    for _ in reversed(writes):
        sessions.undo(cube)
    e.check(sessions.drafts.get(cube)["document"] == initial["document"], "gesture: undo restores fixture for subsequent chains")
    e.data["gesture"] = {"refs": refs, "sam": sam_results, "manual": manual, "tool_events": events,
        "stale_tool_events": stale_events, "provider_calls": len(bodies), "isolated_writes_undone": len(writes)}


def legacy_chain(e, client, app, cube):
    base = f"/api/v1/datasets/{cube}/annotations"
    sessions = app.state.annotation_sessions
    before = sessions.drafts.get(cube)["document"]
    e.call(client, "POST", base + "/regions", {"geometry": {"polygon": rect(0, 0, 4, 4)["points"]}, "action": "uncertain"})
    changed = sessions.drafts.get(cube)["document"]
    e.check(changed["regions"][-1]["op"] == "uncertain", "legacy regions writes draft JSON")
    e.call(client, "POST", base + "/undo")
    e.check(sessions.drafts.get(cube)["document"] == before, "legacy undo restores document")
    before_files = set(sessions.paths.exports.rglob("*.mat"))
    with connect_database(sessions.database) as db:
        before_rows = db.execute("SELECT count(*) FROM training_mat").fetchone()[0]
    saved = e.call(client, "POST", base + "/save", {}).json()
    snapshot, folder = assert_snapshot(e, sessions, saved["id"])
    with connect_database(sessions.database) as db:
        e.check(db.execute("SELECT count(*) FROM training_mat").fetchone()[0] == before_rows, "legacy save creates no MAT row")
    e.check(set(sessions.paths.exports.rglob("*.mat")) == before_files, "legacy save creates no MAT file")
    # Construct the pre-#07 fixture format in the isolated harness app only.
    (folder / "annotation.json").unlink()
    old = sessions.read_version(saved["id"])
    e.check(old["document"] is None, "old three-file snapshot returns document=None")
    e.check(np.array_equal(old["label_map"], snapshot["label_map"]), "old snapshot map replay preserved")
    e.data["legacy"] = {"version_id": saved["id"], "old_snapshot_files": sorted(p.name for p in folder.iterdir()),
                        "document": old["document"], "mat_row_count_unchanged": True}


def recovery_chain(e, client, app, cube):
    """Close the §6 failure→manual rebuild sequence in one integration fixture."""
    sessions = app.state.annotation_sessions
    revision = sessions.drafts.get(cube)["revision"]
    with patch.object(mat, "savemat", side_effect=OSError("synthetic injected writer failure")):
        result = e.call(client, "POST", f"/api/v1/annotations/{cube}/draft/confirm", {"revision": revision}).json()
    e.check(result["training_mat_id"] is None and "synthetic injected writer failure" in result["mat_error"], "MAT failure reports null and reason")
    assert_snapshot(e, sessions, result["version_id"])
    missing = e.call(client, "GET", f"/api/v1/annotations/{cube}/versions/{result['version_id']}/training-mat", status=404)
    e.check(missing.json()["error"] == "MAT_NOT_FOUND", "failed MAT has no downloadable half-artifact")
    with connect_database(sessions.database) as db:
        e.check(db.execute("SELECT count(*) FROM training_mat WHERE annotation_version_id=?", (result["version_id"],)).fetchone()[0] == 0, "failed MAT has no half-registered row")
    e.check(not (sessions.paths.exports / cube / result["version_id"] / ".tmp").exists(), "failed writer temp directory cleaned")
    rebuilt = mat.MatStore(sessions.registry, sessions.paths).rebuild(cube, result["version_id"])
    e.check(rebuilt["n_spectra"] == 480 and rebuilt["annotation_version_id"] == result["version_id"], "service rebuild restores failed export")
    e.call(client, "GET", f"/api/v1/annotations/{cube}/versions/{result['version_id']}/training-mat")
    e.data["recovery"] = {"version_id": result["version_id"], "failed_mat_id": result["training_mat_id"],
                          "rebuild_mat_id": rebuilt["id"], "n_spectra": rebuilt["n_spectra"]}


def large_performance(e, app, runtime):
    shape = (231, 640, 200)  # R24 fixed shape, 147840 labeled pixels.
    header = synthetic_cube(runtime / "large-source", shape, large=True)
    registry = app.state.superpixel_engine.registry
    cube = str(registry.import_path(str(header), raw=True).datasets[0].id)
    sessions = app.state.annotation_sessions
    params = Parameters()
    # Synthetic regular grid is setup, not a claim about SLIC or labeling quality.
    grid_rows = round(math.sqrt(params.n_segments * shape[0] / shape[1]))
    grid_cols = math.ceil(params.n_segments / grid_rows)
    rr, cc = np.indices(shape[:2])
    segments = ((rr * grid_rows // shape[0]) * grid_cols + cc * grid_cols // shape[1]).astype(np.int32)
    sessions.set_segmentation(cube, SimpleNamespace(segments=segments, report={"params": asdict(params)}))
    sessions.drafts.add(cube, 0, class_code="BG", geometry=rect(0, 0, shape[0], shape[1] // 2))
    sessions.drafts.add(cube, 1, class_code="PP", geometry=rect(0, shape[1] // 2, shape[0], shape[1]))
    view = sessions.drafts.view(cube)
    e.check(view["estimated_mat_bytes"] == 147840 * 200 * 4, "large full-label estimate = 118272000")
    started = perf_counter()
    result = sessions.confirm(cube, revision=2)
    total = perf_counter() - started
    e.check(result["training_mat_id"] is not None and result["n_spectra"] == 147840, "large full-label confirm succeeds")
    measurement = e.data["measurements"][-1]
    e.check(measurement["seconds"] <= 30, "large MAT generation <= 30 seconds (R24 synthetic gate)")
    row = measurement["db_row"]
    e.check((row["n_spectra"], row["n_bands"], row["n_classes"]) == (147840, 200, 4), "large DB counts")
    performance = {"source_level": "synthetic fixed-size fixture; no physical spectral meaning; real IO/compute code paths",
        "started_at": e.data["started_at"], "runtime": str(runtime), "shape": list(shape),
        "environment": {"python": sys.version, "platform": platform.platform(), "logical_cpus": os.cpu_count(),
            "thread_environment": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")}},
        "measurement_mode": "standalone e2e process, no concurrent regression/build/flake process during measured run; defaults unchanged",
        "source": {"header": str(header), "raw_bytes": header.with_suffix(".img").stat().st_size, "dtype": "<f4", "formula": "1000 + (flattened sample-band index + row) % 5000"},
        "segmentation_setup": {"kind": "deterministic regular grid, setup excluded; MAT gate does not measure SLIC", "grid": [grid_rows, grid_cols], "params": asdict(params)},
        "large": {**measurement, "confirm_seconds": total, "estimated_spectra_bytes": view["estimated_mat_bytes"],
            "draft_document_bytes": len(_json(view["document"]).encode("utf-8")), "gate_seconds": 30, "gate_passed": measurement["seconds"] <= 30},
        "small": {**e.data["measurements"][0], "confirm_seconds": e.data["annotation"]["confirm_http_seconds"], "shape": [40, 12, 8]},
        "dialogue": e.data["dialogue"], "real_cube_and_real_llm": "owner smoke checklist; not executed here"}
    write_json(OUT / "performance.json", performance)
    e.data["large_performance"] = {"mat_seconds": measurement["seconds"], "confirm_seconds": total,
                                  "file_bytes": measurement["file_bytes"], "gate_passed": True}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / ".runtime" / "task07-12.7" / uuid4().hex
    runtime.mkdir(parents=True)
    e = Evidence()
    e.data["runtime"] = str(runtime)
    # All temporary application locations are explicit and remain on E:.
    os.environ.update(TEMP=str(runtime), TMP=str(runtime))
    set_api_key("")  # R27 starts without a credential to verify config/key separation.
    try:
        header = synthetic_cube(runtime / "small-source", (40, 12, 8))
        identity = EngineIdentity()
        app = create_app(AppPaths(runtime / "app"), identity)
        generate_observer, write_observer = observe_mat(e.data["measurements"])
        with generate_observer, write_observer, TestClient(app) as client:
            client.headers["Authorization"] = "Bearer " + identity.token
            settings_chain(e, client)
            cube = annotation_chain(e, client, app, header)
            dialogue_chain(e, client, app, cube)
            plan_chain(e, client, app)
            gesture_chain(e, client, app, cube)
            legacy_chain(e, client, app, cube)
            recovery_chain(e, client, app, cube)
            large_performance(e, app, runtime)
        e.data["success"] = True
    except Exception as error:
        e.data["error"] = {"type": type(error).__name__, "detail": str(error)}
        raise
    finally:
        set_api_key("")
        e.data["assertion_count"] = len(e.data["assertions"])
        e.data["passed_assertions"] = sum(a["passed"] for a in e.data["assertions"])
        write_json(OUT / "e2e-result.json", e.data)
        if Path(__file__).resolve() != (OUT / "e2e.py").resolve():
            shutil.copyfile(__file__, OUT / "e2e.py")
        print(json.dumps({key: e.data[key] for key in ("success", "assertion_count", "passed_assertions", "runtime")}, ensure_ascii=False), flush=True)
        if "large_performance" in e.data:
            print(json.dumps(e.data["large_performance"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
