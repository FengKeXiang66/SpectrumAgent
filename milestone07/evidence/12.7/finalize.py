"""Rebuild 12.7 acceptance/performance/receipt docs from the recorded evidence."""
import ast
import hashlib
import json
from pathlib import Path
import re
from contextlib import redirect_stdout
import runpy
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def scope():
    protected = ["backend", "src-python", "src", "src-tauri", "requirements-lock.txt", "package-lock.json",
                 "TASK-07-对话编排与标注JSON.md", "docs/release_manifest.md", "milestone03", "milestone04", "milestone05",
                 "milestone07/evidence/12.4", "milestone07/evidence/12.6"]
    changes = subprocess.check_output(["git", "diff", "21e4f84", "--name-only", "--", *protected], cwd=ROOT).decode().splitlines()
    assert changes == [], changes
    source_bytes = (ROOT / "scripts/e2e_task07.py").read_bytes()
    assert source_bytes == (OUT / "e2e.py").read_bytes(), "e2e evidence copy drift"
    files = {"scripts/e2e_task07.py", "docs/release-notes-v0.3.0.md", "milestone07/evidence/12.7/scope-check.json"}
    files.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    result = {"base_commit": "21e4f84", "protected_paths": protected, "protected_diff": changes,
        "e2e_copy_identical": True, "e2e_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "artifact_files": sorted(files), "artifact_count": len(files), "synthetic_data_tracked": False,
        "card_manifest_version_locks_implementation_tests_unchanged": True}
    (OUT / "scope-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")


def boundary():
    """Run the original audit; redirect only its output file, not assertions."""
    namespace = runpy.run_path(str(ROOT / "milestone03/audit_boundary.py"))
    previous = ROOT / "milestone07/evidence/12.6/boundary.json"
    write = Path.write_text
    def capture(path, data, *args, **kwargs):
        assert path.resolve() == previous.resolve(), path
        return write(OUT / "boundary.json", data, *args, **kwargs)
    with (OUT / "boundary-output.txt").open("w", encoding="utf-8") as output:
        with patch.object(Path, "write_text", capture), redirect_stdout(output):
            namespace["main"]()


def read_json(name):
    return json.loads((OUT / name).read_text("utf-8"))


def source(path, *names):
    tree = ast.parse((ROOT / path).read_text("utf-8"))
    functions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert set(names) <= functions, (path, set(names) - functions)
    return "<br>".join(f"[{name}](E:/AI_Agent/{path})" for name in names)


def agent(file, *names):
    return source("src-python/tests/agent/" + file + ".py", *names)


def annotation(file, *names):
    return source("src-python/tests/annotation/" + file + ".py", *names)


def mat(*names):
    return source("src-python/tests/mat/test_mat.py", *names)


def acceptance():
    a, n, m = agent, annotation, mat
    mappings = {
        "G1": [
            (a("test_probes", "test_probe_1_gateway_tool_interpret_and_two_audited_calls"), "e2e-result.json、pytest-full.txt", "已覆盖 mock；真实云端归冒烟 S07"),
            (a("test_llm", "test_egress_blocked_before_any_transport_and_audited"), "pytest-full.txt", "已覆盖"),
            (a("test_settings", "test_key_never_persisted_full_flow_errors_logs_artifacts_exports_and_process_restart"), "pytest-full.txt", "已覆盖合成内存 key；真实 key 归冒烟 S07"),
            (a("test_llm", "test_usage_missing_fields_are_null_and_provider_zero_is_preserved"), "pytest-full.txt、e2e-result.json", "已覆盖"),
            (a("test_llm", "test_reconfigure_same_client_without_code_changes_and_optional_settings_empty"), "pytest-full.txt", "已覆盖 mock；真实换模型归冒烟 S08"),
            (a("test_settings", "test_key_write_only_clear_and_validation_never_echoes_input", "test_key_never_persisted_full_flow_errors_logs_artifacts_exports_and_process_restart"), "pytest-full.txt", "已覆盖真实子进程重启；安装态归冒烟 S13"),
            (a("test_llm", "test_transport_failures_distinguishable_no_silent_retry") + "<br>" + a("test_state", "test_error_transport_branch_resets_idle_no_retry_and_persists_round"), "pytest-full.txt", "已覆盖，零静默重试"),
        ],
        "G2": [
            (a("test_state", "test_clarify_without_calls_never_executes_and_title_is_first_40_characters"), "pytest-full.txt", "已覆盖"),
            (a("test_annotation_tools", "test_confirm_real_human_gate_and_export_eight_scalars"), "pytest-full.txt、e2e-result.json", "已覆盖注册范围内确认/覆写；删除数据工具不在本卡范围"),
            (a("test_state", "test_sequence_limit_first_eight_execute_rest_are_all_rejected"), "pytest-full.txt", "已覆盖，保持 R12 rejected 先落库顺序"),
            (a("test_state", "test_schema_rejection_audit_is_bounded_and_raw_arguments_never_reach_interpret", "test_normal_steps_digest_interpret_tools_none_and_second_turn_has_no_history"), "pytest-full.txt、e2e-result.json", "已覆盖"),
            (a("test_state", "test_human_check_recovers_original_message_and_remaining_calls_after_restart", "test_human_reject_executes_nothing_and_closes_round_without_llm") + "<br>" + a("test_agent_api", "test_sse_human_check_original_stream_closes_answer_uses_new_stream"), "pytest-full.txt、e2e-result.json", "已覆盖解析器重建/跨请求；安装态 reboot 归 S13"),
            (a("test_state", "test_schema_validation_precedes_human_gate") + "<br>" + a("test_tools", "test_invalid_geometry_extra_or_coerced_types_reject_before_handler"), "pytest-full.txt", "已覆盖"),
        ],
        "G3": [
            (a("test_skill", "test_content_update_rejected_by_database_not_just_service", "test_retired_terminal_service_and_sql", "test_parallel_activation_exactly_one_wins_second_fails", "test_switch_atomic_external_observers_never_see_zero_or_two_active", "test_switch_failure_rolls_back_old_retirement"), "pytest-full.txt", "已覆盖"),
            (a("test_state", "test_session_skill_snapshot_and_metadata_immutability"), "pytest-full.txt", "已覆盖"),
            (a("test_tools", "test_v1_catalogue_snapshot_and_live_schemas_independent_static_scan"), "pytest-full.txt", "已覆盖"),
            (a("test_annotation_tools", "test_coordinates_still_rejected_before_handler_and_recorded"), "pytest-full.txt", "已覆盖"),
            ("[test_probes.py 七探针，参数化共九项](E:/AI_Agent/src-python/tests/agent/test_probes.py)", "pytest-full.txt、e2e-result.json", "已覆盖 MockTransport/FakeLLM，零真实 provider 网络"),
            (a("test_skill", "test_seed_prompt_is_verbatim_card_and_all_required_values_have_sources"), "pytest-full.txt", "已覆盖逐字对读断言；人工复读归 S14"),
        ],
        "G5/G6": [
            (n("test_draft", "test_create_read_update_delete_and_id_never_reused", "test_invalid_schema_or_bounds_roll_back_without_disk_change") + "<br>" + n("test_session", "test_draft_undo_restores_document_map_and_never_reuses_region_id"), "pytest-full.txt", "已覆盖"),
            (n("test_draft", "test_ten_concurrent_connections_have_one_winner_and_monotonic_revision"), "pytest-full.txt、flake-summary.json", "已覆盖，额外十轮"),
            (n("test_draft_routes", "test_cas_missing_revision_replay_and_stale_patch") + "<br>" + n("test_draft", "test_same_revision_replay_second_write_fails"), "pytest-full.txt", "已覆盖"),
            (n("test_draft_routes", "test_patch_rejects_lineage_fields") + "<br>" + n("test_draft", "test_patch_provenance_and_identity_are_immutable"), "pytest-full.txt", "已覆盖"),
            (n("test_draft_routes", "test_illegal_fields_are_rejected_without_creating_document", "test_legacy_geometry_and_action_mapping_are_preserved"), "pytest-full.txt", "manual 已覆盖；algorithm 半边按 R14 延期，不计自动化完成"),
            (n("test_raster", "test_polygon_branch_is_exactly_frozen_polygon_mask", "test_cross_row_rle_and_polygon_mix_same_class_overlap"), "pytest-full.txt", "已覆盖凹形/孔洞/RLE/混合"),
            (n("test_raster", "test_polygon_branch_is_exactly_frozen_polygon_mask"), "pytest-full.txt", "已覆盖中心/边界参数化"),
            (n("test_confirm_routes", "test_overlap_locations_and_four_arbitrations"), "pytest-full.txt", "已覆盖位置载荷与四种解锁"),
            (n("test_raster", "test_idempotent_and_input_is_unchanged", "test_add_then_uncertain_is_minus_two_never_blank", "test_polygon_branch_is_exactly_frozen_polygon_mask", "test_region_order_is_sensitive_not_commutative"), "pytest-full.txt；12.5 A0 见历史交付记录", "已覆盖；本段不伪造历史跑红证据"),
            (n("test_session", "test_document_snapshot_interlock_normalized_copy_and_readonly_draft"), "pytest-full.txt、e2e-result.json", "已覆盖 save/confirm 快照互锁"),
            (n("test_raster", "test_polygon_branch_is_exactly_frozen_polygon_mask") + "<br>" + n("test_session", "test_document_snapshot_interlock_normalized_copy_and_readonly_draft"), "pytest-full.txt、scope-check.json", "已覆盖现有 v1 保留与重放；未来升级继续保留回归"),
            (n("test_session", "test_working_state_restored_from_draft_and_empty_snapshot_three_states"), "pytest-full.txt", "已覆盖新 SessionStore 恢复；实际 UI 打开归 S05/S13"),
            (n("test_session", "test_draft_undo_restores_document_map_and_never_reuses_region_id") + "<br>" + n("test_draft_routes", "test_rest_edits_and_legacy_undo_share_one_document"), "pytest-full.txt、e2e-result.json", "已覆盖"),
            (n("test_session", "test_relative_snapshot_path_three_files_and_no_source_writes", "test_save_reads_before_write_transaction_and_publishes_tmp"), "pytest-full.txt、e2e-result.json", "已覆盖，旧函数名保留而断言为四件套"),
            (n("test_draft_routes", "test_legacy_geometry_and_action_mapping_are_preserved") + "<br>" + n("test_session", "test_working_state_restored_from_draft_and_empty_snapshot_three_states"), "pytest-full.txt、e2e-result.json", "HTTP 已覆盖；完整 WebView/IPC 操作归 S05"),
            (a("test_annotation_tools", "test_real_draft_get_replays_only_scalar_summary_with_size", "test_frozen_schema_and_pending_handlers_remain_unchanged", "test_coordinates_still_rejected_before_handler_and_recorded"), "pytest-full.txt", "已覆盖；该项 confirm 占位为12.5时点，按12.6/R19已绑定；add/select仍延期"),
            (n("test_session", "test_read_pre07_three_file_snapshot_document_is_none"), "pytest-full.txt、e2e-result.json legacy", "已覆盖无 MAT 的 legacy save 及旧版回放"),
            (n("test_draft_routes", "test_uncertain_erase_and_deletion_preserve_document_semantics", "test_illegal_fields_are_rejected_without_creating_document") + "<br>" + n("test_session", "test_snapshot_replay_spectra_counts_params_and_lineage"), "pytest-full.txt", "已覆盖三态及 DB add 指针边界"),
            (n("test_confirm_routes", "test_overlap_locations_and_four_arbitrations") + "<br>" + n("test_draft", "test_conflict_is_sticky_until_erase_or_uncertain_and_recomputed"), "pytest-full.txt", "已覆盖，夹具36像素替代示例100，验最终状态而非累加"),
            (n("test_raster", "test_add_then_uncertain_is_minus_two_never_blank", "test_erase_and_uncovered_are_blank_but_have_distinct_document_history"), "pytest-full.txt", "已覆盖"),
            (n("test_confirm_routes", "test_strong_classes_check_precedes_auto_remap") + "<br>" + n("test_session", "test_document_snapshot_interlock_normalized_copy_and_readonly_draft"), "pytest-full.txt、e2e-result.json", "已覆盖 R20 index→code 强校验及 name/color 刷新"),
            (n("test_draft_routes", "test_three_size_states_are_zero_16_pixels_and_full_480_pixels") + "<br>[confirm.test.ts 阈值/渲染/取体积](E:/AI_Agent/src/components/annotation/confirm.test.ts)", "pytest-full.txt、node-test.txt、e2e-result.json", "逻辑已覆盖；两卡实际 WebView 交互归 S06/S07"),
        ],
        "G7": [
            (n("test_confirm_routes", "test_segmentation_required_and_mat_download_errors") + "<br>" + m("test_raw_dn_axes_dtype_wavelengths_and_nine_metadata_values"), "pytest-full.txt、e2e-result.json", "已覆盖"),
            (m("test_raw_dn_axes_dtype_wavelengths_and_nine_metadata_values"), "pytest-full.txt、e2e-result.json", "已覆盖有/无波长及原始 DN"),
            ("[annotation_chain: original indices {0,3}, full four-class table](E:/AI_Agent/scripts/e2e_task07.py)", "e2e-result.json 中同名断言", "已覆盖字面 {0,3} 夹具；单测 {3} 另保留"),
            (m("test_raw_dn_axes_dtype_wavelengths_and_nine_metadata_values"), "pytest-full.txt、e2e-result.json", "已覆盖 reverse-map labels"),
            (m("test_raw_dn_axes_dtype_wavelengths_and_nine_metadata_values"), "pytest-full.txt、e2e-result.json", "已覆盖 >u2 字节序与无损 uint16→float32"),
            (n("test_confirm_routes", "test_mat_failure_keeps_confirmed_version", "test_failed_confirm_overwrite_invalidates_old_mat_without_rolling_back_version") + "<br>[recovery_chain](E:/AI_Agent/scripts/e2e_task07.py)", "pytest-full.txt、e2e-result.json recovery", "已覆盖失败保版→无行/无半份→service rebuild"),
            (m("test_exports_are_never_preprocess_inputs"), "pytest-full.txt", "已覆盖 exports 路径守卫、指纹/结果不变"),
            (m("test_unique_rebuild_and_bounded_raw_reads_with_write_peak") + "<br>" + n("test_confirm_routes", "test_legacy_overwrite_invalidates_mat_even_if_file_cleanup_fails_and_rebuild_inserts"), "pytest-full.txt、e2e-result.json recovery", "已覆盖 UPDATE/INSERT、UNIQUE、成功/失败临时清理，按R22删行失效"),
            (m("test_unique_rebuild_and_bounded_raw_reads_with_write_peak"), "pytest-full.txt、performance.json", "已覆盖 R20 修订口径：读侧有界、写侧接受 O(n×B) 副本，不声称整体 O(B)"),
            ("[large_performance](E:/AI_Agent/scripts/e2e_task07.py)", "performance.md、performance.json", "已覆盖 R24 合成门；真实 NAS cube 归 S09"),
        ],
        "全局": [
            ("Python/Rust/Node 全量命令及 npm run build", "pytest-full.txt、cargo-test.txt、node-test.txt、clippy.txt、build.txt", "已覆盖，951/75/95，默认参数并发"),
            (a("test_llm", "test_egress_blocked_before_any_transport_and_audited", "test_tool_schema_scanned_and_multiline_unicode_text_allowed"), "pytest-full.txt", "已覆盖全部 messages 与 tools"),
            (a("test_annotation_tools", "test_probe7_real_overlap_interpret_is_count_and_prose_only", "test_real_draft_get_replays_only_scalar_summary_with_size"), "pytest-full.txt、e2e-result.json", "已覆盖真实 handler 回灌"),
            ("[audit_boundary.py](E:/AI_Agent/milestone03/audit_boundary.py) + Rust 受限 forward 测试", "boundary-output.txt、boundary.json、scope-check.json", "已覆盖，十命令/历史证据/冻结配置保持"),
        ],
    }
    text = (ROOT / "TASK-07-对话编排与标注JSON.md").read_text("utf-8")
    section = text.split("## 6. 验收标准", 1)[1].split("\n## 7.", 1)[0]
    original, group = {}, None
    for line in section.splitlines():
        if line.startswith("**"):
            heading = line.strip("*")
            group = next(key for key in mappings if heading.startswith(key))
            original[group] = []
        elif line.startswith("- [ ] "):
            original[group].append(line[6:])
    counts = {key: len(value) for key, value in original.items()}
    assert all(counts[key] == len(mappings[key]) for key in mappings), counts
    output = ["# TASK-07 12.7 验收映射", "",
        "事实源为 R24 任务卡 §6，原文逐项保留，共 55 条（G1 7 / G2 6 / G3 6 / G5-G6 22 / G7 10 / 全局 4）。测试证据不替代真实云端、NAS 数据和安装态 UI 冒烟。",
        "", "模式 P：仓库根 python -m pytest，默认参数并发，无串行限制，PYTEST_DEBUG_TEMPROOT 与命令同条。模式 N：node --test 默认发现/默认并发。模式 R：cargo test 默认并发及 Clippy。模式 E：独立 TestClient 真实 ASGI + MockTransport；不代表独立 sidecar/WebView。flake 按轮串行启动新进程，每次 pytest 默认参数。",
        "", "R14 延期的算法/手势半边明确挂账，不以冒烟或自动化通过替代。§6 中 12.5 时点的 confirm 占位、旧 O(B) 表述按已落卡 R19/R20/R22 解释，不重新裁定或改任务卡。", ""]
    for group, rows in original.items():
        output.extend([f"## {group}", "", "| 编号 | §6 原文（完整） | 测试/入口 | 证据与执行模式 | 状态/边界 |", "|---|---|---|---|---|"])
        for index, (requirement, (tests, evidence, state)) in enumerate(zip(rows, mappings[group]), 1):
            ident = group.replace("/", "-") + f"-{index:02d}"
            requirement = requirement.replace("|", "\\|")
            mode = "P" + (" / N" if "node-test" in evidence else "") + (" / E" if "e2e" in evidence or "performance" in evidence else "")
            if group == "全局" and index in (1, 4):
                mode += " / R / N"
            output.append(f"| {ident} | {requirement} | {tests} | {evidence}；{mode} | {state} |")
        output.append("")
    output.extend(["## 科祥本机项目", "", "[smoke-checklist.md](smoke-checklist.md) 的每项保留未勾选状态与记录位：安装、签名/SmartScreen、干净机、真实 NAS cube/真实 key、完整 S05/S01 UI、长路径、reboot、真实性能及人工 prompt 对读均未计入本次自动化通过。", ""])
    (OUT / "acceptance-map.md").write_text("\n".join(output), "utf-8")
    return counts


def performance():
    p = read_json("performance.json")
    big, small, dialog = p["large"], p["small"], p["dialogue"]
    lines = ["# TASK-07 12.7 性能记录", "",
        "R24 数据口径：合成固定尺寸 cube，谱值无物理意义；实际 registry/readable(raw=True)/row_blocks/memmap/savemat/DB 路径运行，没有模拟计时。真实 NAS PE 数据与真实 LLM 延迟仍归科祥冒烟。本机单次测量不是跨机性能承诺。",
        "", "大夹具 231×640×200，147,840 像素全标，源 float32 原始 DN 共 118,272,000 字节；公式 `1000 + (sample-band flatten index + row) % 5000`。大图分割为 17×48 确定性网格，按既有 Parameters.n_segments=800 推导，仅作为 confirm 前置夹具，未把它宣称为 SLIC 性能。小图 40×12×8 实际调用 superpixels 端点（24/.5/5 来自既有路由测试），DN RNG=17/range1000..5999 来自 annotation fixture。", "",
        "| 记录 | 小图（480全标） | 大图（147840全标） |", "|---|---:|---:|"]
    for label, values in [
        ("MatStore.generate 全程秒（含源hash/IO/写盘/落库）", (small["seconds"], big["seconds"])),
        ("confirm 全程秒（小图含ASGI HTTP，大图service）", (small["confirm_seconds"], big["confirm_seconds"])),
        ("savemat 写入秒", (small["write"]["seconds"], big["write"]["seconds"])),
        ("MAT 文件字节", (small["file_bytes"], big["file_bytes"])),
        ("写侧 tracemalloc 峰值增量字节", (small["write"]["tracemalloc_peak_increment_bytes"], big["write"]["tracemalloc_peak_increment_bytes"]))]:
        lines.append(f"| {label} | {values[0]} | {values[1]} |")
    lines.extend(["", f"30s 门：**{'通过，维持同步，无需重议异步' if big['gate_passed'] else '未通过，必须即停重议'}**。判据用独立 MatStore.generate span={big['seconds']:.6f}s；confirm 全程={big['confirm_seconds']:.6f}s 另列，不将嵌套耗时相加。",
        "", "内存口径按 R20：读侧一行有界，写侧 savemat 固有 O(n×B) 序列化副本接受。tracemalloc 只在原 scipy writer 调用周围启停，记录 Python 分配增量，不是进程 RSS、不含已存在 memmap 的物理驻留页，也不声称整体 O(B)。do_compression=False。",
        "", f"大图 DB 行：n_spectra={big['db_row']['n_spectra']}、n_bands={big['db_row']['n_bands']}、n_classes={big['db_row']['n_classes']}；完整 id/fingerprint/sha256/relative_path/created_at 逐项见 performance.json。预计纯 spectra={big['estimated_spectra_bytes']} 字节，实际 MAT 增量含 labels/rows/cols/类表/元数据。",
        "", f"大图 polygon draft document={big['draft_document_bytes']} UTF-8 字节。此为两个矩形的记录，不代表高碎片 RLE 最坏体积；GET draft 8MiB 限额风险保持挂账，未据此发明截断或采样。", "",
        "## 对话延迟（mock transport）", "", "| 阶段 | 秒 |", "|---|---:|",
        f"| 用户消息→PARSE→human_check SSE 返回 | {dialog['message_to_human_check_seconds']} |",
        f"| PARSE provider callback | {dialog['provider_stages'][0]['seconds']} |",
        f"| approve→confirm→MAT→INTERPRET→step/done SSE | {dialog['approve_to_final_sse_seconds']} |",
        f"| confirm service（嵌套） | {dialog['confirm_seconds']} |",
        f"| MAT generate（嵌套） | {dialog['mat_generation_seconds']} |",
        f"| savemat（嵌套） | {dialog['savemat_seconds']} |",
        f"| INTERPRET provider callback | {dialog['provider_stages'][1]['seconds']} |",
        f"| 两个 HTTP 请求耗时之和（排除人类思考） | {dialog['total_http_seconds']} |", "",
        "TestClient 会缓冲有限 SSE，计时是请求到事件集合返回及内部观测 span，不冒充真实网络逐事件到达延迟。provider 两次均为 MockTransport，真实云端请求=0；usage 未上报，调用留痕三 token 列均为 NULL，不估算 token。",
        "", "机器/线程环境和原精度值在 performance.json；测量时无并发回归、构建或flake进程，未设 BLAS 线程限制，未调整生产参数。生成数据与运行应用均留在 E 盘 .runtime，不进 Git。", ""])
    (OUT / "performance.md").write_text("\n".join(lines), "utf-8")


def receipt(counts):
    e, p, f = (read_json(name) for name in ("e2e-result.json", "performance.json", "flake-summary.json"))
    py = (OUT / "pytest-full.txt").read_text("utf-8")
    cargo = (OUT / "cargo-test.txt").read_text("utf-8")
    node = (OUT / "node-test.txt").read_text("utf-8")
    assert "951 passed" in py
    rust_count = sum(int(value) for value in re.findall(r"test result: ok\. (\d+) passed", cargo))
    assert rust_count == 75 and "pass 95" in node and "fail 0" in node
    assert e["success"] and e["assertion_count"] == e["passed_assertions"]
    assert f["exposure_passed"] == 30 and f["exposure_failed"] == 0 and p["large"]["gate_passed"]
    result = {"base_commit": "21e4f84", "python": 951, "rust": 75, "node": 95,
        "e2e_assertions": e["assertion_count"], "flake_exposures": 30, "flake_failed": 0,
        "mat_seconds": p["large"]["seconds"], "mat_gate_seconds": 30, "acceptance_items": sum(counts.values()),
        "implementation_changed": False, "release_actions": "none; owner only"}
    (OUT / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    lines = ["# TASK-07 12.7 交付凭据", "",
        "基线 commit=21e4f84（R24）。本文件与集成脚本/全部证据同一个提交；交付 commit 的精确 SHA 用 `git log -1 --format=%H -- milestone07/evidence/12.7/receipt.md` 解析，并在交付回复中给出，避免文件自引用自身 commit 哈希。", "",
        "| 出口 | 结果 | 执行模式 |", "|---|---|---|",
        "| Python | 951 passed / 0 failed，基线951+0 | 默认参数并发，无串行限制；环境变量与 python -m pytest 同条 |",
        "| Rust | 75 passed / 0 failed（含doctest1），基线75+0；Clippy零警告 | cargo test 默认并发；clippy --all-targets -- -D warnings |",
        "| 前端 | 95 passed / 0 failed，基线95+0；npm run build通过，含tsc --noEmit | node --test 默认发现/默认并发，含artifacts既有两项 |",
        f"| 集成 | exit0，{e['passed_assertions']}/{e['assertion_count']}断言通过 | TestClient真实ASGI+MockTransport，真实provider网络0 |",
        "| flake | 3目标各10轮，30通过/0失败，无复跑 | 暴露按轮顺序编排；各pytest新进程/默认参数 |",
        f"| MAT门 | {p['large']['seconds']:.6f}s < 30s，通过 | R24合成231×640×200全标，独立计时，无并发构建/回归 |", "",
        "本轮不向 pytest/Rust/Node 单测套件加项，新增为独立集成断言与验收脚本；没有改既有实现或测试凑数。", "",
        "## A0 / R23 销账", "", "| 文件 | 12.5 collected | 12.6/当前 collected | 增量 |", "|---|---:|---:|---:|",
        "| agent/test_annotation_tools.py | 4 | 8 | 4 |", "| annotation/test_confirm_routes.py | 0 | 11 | 11 |",
        "| annotation/test_session.py | 25 | 29 | 4 |", "| mat/test_mat.py | 0 | 6 | 6 |",
        "| 其他文件 | 897 | 897 | 0 |", "| 合计 | 926 | 951 | 25 |", "",
        "MAT 三个函数被 mat_case fixture 的 params=[False,True] 展开为六个 collected，静态22少算的三项全部定位；没有其他收集源，也没有改测试。原始 collect-only.txt 与 collection-reconciliation.json 已保留。", "",
        "## e2e 与边界", "",
        "导入→真实小图分割→draft 三态体积→confirm→四件套互锁→MAT下载→export八标量；MockTransport真实网关→human_check→approve→版本/MAT/step落库→INTERPRET→SSE step/done；legacy regions/undo/save与旧三件套 document=None；另补失败保版→无半份MAT→service rebuild连续恢复路径。原始事件、断言和DB行见e2e-result.json。",
        "", "标签集合{0,3}未重映射，label_index完整四类；两次网关调用真实session_id留痕，未上报usage均NULL。没有真实key或provider请求。真实S05/UI、NAS性能与云端延迟只列冒烟，不计自动化通过。", "",
        "## 文档与证据清单", "",
        "acceptance-map.md（卡§6完整55项）/ performance.md+json / scripts/e2e_task07.py与本目录e2e.py等字节副本+output+result / flake_smoke.py+30条per-test日志+flake-summary.json / smoke-checklist.md / technical-debt.md / 本receipt / collection-reconciliation.json+collect-only.txt / pytest/cargo/clippy/node/build原始日志 / boundary-output.txt / scope-check.json / summary.json / finalize.py。release草稿位于docs/release-notes-v0.3.0.md。", "",
        "## 自定项与理由", "",
        "1. 小图使用40×12×8，形状/种子17/范围来源既有annotation与#05夹具；真实分割参数24/.5/5来自现有HTTP测试。大图用float32 DN以使原始源文件约118MB，逐行公式生成，完整记录dtype与公式。",
        "2. 大图性能用由默认n_segments=800推导的17×48规则网格作前置状态；不把SLIC准备计入MAT门，不声称测过大图SLIC质量。小图链路实际走superpixels端点。",
        "3. 观测器只包装原MatStore.generate和原scipy.savemat，原函数全部执行；MAT门取generate完整span，confirm/写入单列，tracemalloc为writer周围Python分配峰值而非RSS。",
        "4. e2e补连续失败→重建路径及字面{0,3}原index夹具，闭合§6组合要求，没有改生产实现。",
        "5. 对话两个HTTP span相加排除人工思考，内部span嵌套不相加；TestClient缓冲SSE不能冒充真实WebView/网络到达延迟。",
        "6. flake脚本逐个启动新pytest进程，每目标十轮；只有失败时才单独复跑并留痕、不推断根因。本次零失败，未触发复跑。",
        "7. acceptance-map保留§6逐项原文，按R14/R19/R20/R22注明延期和历史时点，不把算法手势半边或人工冒烟标绿。",
        "8. receipt通过本文件Git历史定位交付SHA，父提交明确列出；完整SHA在交付回复，避免同一commit内自引用哈希。所有证据生成脚本留存以便复算。", "",
        "9. 原审计脚本全套断言实际重跑，harness仅将固定的12.6输出文件重定向为12.7/boundary.json，保留旧证据字节；没有改审计代码或豁免新语义。", "",
        "## 即停与剩余事项", "",
        "本轮没有新增即停点或实现修复。e2e首次启动的自动审批超时后按工具许可重试成功，没有失败运行被覆盖为通过。三出口、MAT门与flake均通过；真实NAS/DeepSeek/UI、签名/SmartScreen、干净机、长路径与reboot仍归科祥。未打tag、未push、未建Release、未改manifest或tauri.conf.json；五个公司文档与任务卡不动。", ""]
    (OUT / "receipt.md").write_text("\n".join(lines), "utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    scope()
    boundary()
    counts = acceptance()
    performance()
    receipt(counts)
