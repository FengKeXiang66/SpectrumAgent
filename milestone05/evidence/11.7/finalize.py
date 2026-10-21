"""Recheck evidence, generate the exact card checklist mapping and receipt summary.

No product files are written. TASK-05 R16 is appended separately after these checks.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def read(name):
    return (OUT/name).read_text('utf-8-sig')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8')


def ref(module, *names):
    path = ROOT/f'src-python/tests/preprocess/{module}.py'
    found = {node.name for node in ast.parse(path.read_text('utf-8')).body if isinstance(node, ast.FunctionDef)}
    assert set(names) <= found, (module, set(names)-found)
    return '<br>'.join(f'`{path.relative_to(ROOT).as_posix()}::{name}`' for name in names)


def main():
    e2e = json.loads(read('e2e-result.json'))
    perf = json.loads(read('performance.json'))
    hardware = json.loads(read('environment.json'))
    assert e2e['passed'] and e2e['sidecar_stopped'] and e2e['token_absent_from_logs'] and e2e['source_and_seed_unchanged']
    py = re.search(r'(\d+) passed', read('pytest-full.txt'))
    assert py and int(py[1]) == 621
    suites = [list(map(int, values)) for values in re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', read('cargo-test.txt'))]
    assert sum(row[0] for row in suites) == 56 and all(row[1:] == [0, 0] for row in suites)
    assert '# pass 59' in read('node-test.txt') and '# fail 0' in read('node-test.txt') and '# skipped 0' in read('node-test.txt')
    assert 'exit_code=0' in read('tsc.txt') and 'warning:' not in read('clippy.txt') and 'error:' not in read('clippy.txt')
    assert 'Finished' in read('clippy.txt')
    audit_output = read('audit-output.txt')
    audit = json.loads(audit_output[audit_output.index('{'):])
    assert audit['release_handler_count'] == 7 and audit['dev_handler_matches_release']
    assert not git('diff', '5f5f2be869a6e5cfc5936f2cefaf0fcb6c324aa2', '--', 'src-tauri/', 'src-python/', 'src/', 'backend/', 'package.json', 'package-lock.json', 'requirements-lock.txt', 'docs/release_manifest.md')
    assert not git('diff', '5f5f2be869a6e5cfc5936f2cefaf0fcb6c324aa2', '--', 'milestone05/evidence/11.5/boundary.json')
    seed_sha = hashlib.sha256((ROOT/'milestone04/evidence/seeds_20.json').read_bytes()).hexdigest().upper()
    assert seed_sha == '388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2'
    (OUT/'boundary.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', 'utf-8')

    coverage = [
        (ref('test_reflectance', 'test_three_hdr_branches_formulas_and_records', 'test_requested_branch_cannot_override_hdr', 'test_negative_guards_and_counts'), '算子三分支通过；真实run验证scale；reference文件解析按R11缓建'),
        (ref('test_savgol', 'test_even_window_and_polyorder_ge_window_structured_before_scipy', 'test_smoothing_modes_and_configurable_window_order'), '通过；按11.1开工令R7严格<，不采用卡旧≤笔误'),
        (ref('test_savgol', 'test_derivative_polynomial_per_band_index_and_unchanged_nonuniform_axis'), '通过，一/二阶各参数化'),
        (ref('test_scatter', 'test_snv_population_formula_and_metadata', 'test_explicit_reference_lstsq_formula_coefficient_fingerprints', 'test_reference_is_required_never_current_input_mean'), '三算子及显式参考/指纹通过；训练集/样品来源选择流程依R15 D2留阶段二，不冒称已交付'),
        (ref('test_standardize', 'test_four_methods_formula_fit_metadata_and_determinism')+'<br>'+ref('test_run', 'test_standard_fitted_matches_global_pixel_formula_and_not_block_fit', 'test_annotation_version_fingerprint_and_fitted_recomputed'), '通过，fitted随run落值；换指纹真重算'),
        (ref('test_resample', 'test_crop_closed_range_preserves_endpoints_single_hit_and_explicit_source', 'test_fwhm_is_median_not_mean_and_proxy_marked', 'test_fwhm_strictly_greater_than_five_percent'), '通过，明确间隔代理非实测分辨率'),
        (ref('test_recipes', 'test_create_append_versions_history_immutable_and_params_not_fitted', 'test_api_has_no_update_delete_or_overwrite_methods', 'test_project_selection_is_same_shared_recipe_not_copy_and_idempotent', 'test_builtin_exact_code_chain_versions_and_default_provenance')+'<br>`e2e-result.json`: project_selection_preserves_recipe_and_versions', '通过；按开工裁定复用内置v1，另建e2e-snv-sg1覆盖POST'),
        (ref('test_decomposition', 'test_b08_scores_axis_loadings_sign_variance_and_repeat', 'test_ica_random_state_is_param_and_reserved_run_argument_is_unused'), '通过：得分为算子返回值、载荷/累积方差为meta；run只落授权两类artifact'),
        (ref('test_continuum', 'test_b09_fixed_endpoints_same_axis_and_reproducible', 'test_continuum_zero_denominator_nan_and_count'), '通过；UI像素去背景/ROI仍不适用，不能与谱级linear混同'),
        (ref('test_compare', 'test_metrics_pixel_snr_quantiles_pooled_pairwise_fisher_and_three_boundaries', 'test_compare_reuses_run_and_sql_authorizer_explodes_aggregate_reads', 'test_unlabeled_real_run_only_snr_no_sample_spectrum')+'<br>`e2e-result.json`: compare / artifact_audits', '通过；SQL authorizer实际炸聚合表访问，非仅grep；真实N=3'),
        (ref('test_run', 'test_actual_content_hash_and_annotation_version_change_fingerprint')+'<br>`e2e-result.json`: reproduction（max diff=0.0）', '通过；相同输入、两次实际HTTP run；指纹变化另由测试真换输入'),
        (ref('test_run', 'test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success', 'test_failed_after_running_records_error_and_no_half_artifact', 'test_running_state_is_committed_and_failure_error_is_as_dict'), '通过，四态/失败清理/真实as_dict'),
        ('`performance.json` / `performance.md` / `environment.json`', '通过，双计时明确、实际产物字节/进程峰值、两触发线分别判；不构成跨机承诺'),
        (ref('test_run', 'test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success')+'<br>`e2e-result.json`: lineage（7条run，真实快照存在）', '通过；DB关联含#04版本与样本行，未读聚合谱替代输入'),
        (ref('test_registry', 'test_registered_schema_parse_execute_and_invalid_params_full_chain'), '通过'),
        (ref('test_registry', 'test_operator_level_determinism_1e12_without_mutating_inputs')+'<br>'+ref('test_standardize', 'test_four_methods_formula_fit_metadata_and_determinism'), '通过；ICA按B08单独验'),
        (ref('test_registry', 'test_same_name_multiversion_retained_and_stale_only_when_absent')+'<br>'+ref('test_run', 'test_stale_really_triggered_before_pending_and_other_version_works'), '通过，真实run预检STALE且不建pending'),
        (ref('test_registry', 'test_new_operator_demo_is_local_registration_without_framework_changes'), '接口可插拔自证通过；≤0.5人日未做人力计时，不以测试运行秒数冒充工时'),
        (ref('test_reflectance', 'test_ambiguous_and_unknown_never_guess', 'test_negative_guards_and_counts', 'test_zero_denominator_guards', 'test_nonfinite_denominator_and_input_nan_propagation')+'<br>'+ref('test_compare', 'test_zero_variance_nan_and_unlabeled_explicit_limits'), '通过'),
        (ref('test_savgol', 'test_even_window_and_polyorder_ge_window_structured_before_scipy', 'test_smoothing_modes_and_configurable_window_order'), '通过；11.1开工令R7严格<优先，polyorder==window拒绝'),
        (ref('test_savgol', 'test_derivative_polynomial_per_band_index_and_unchanged_nonuniform_axis', 'test_no_delta_or_bad_types_orders_modes'), '通过；delta固定、不暴露'),
        (ref('test_scatter', 'test_snv_zero_variance_policies', 'test_explicit_reference_lstsq_formula_coefficient_fingerprints', 'test_real_zero_target_and_default_emsc_order', 'test_nan_rows_detected_without_passing_nan_to_lapack'), '数值/退化/系数指纹通过；reference来源选择仍授权缓建'),
        (ref('test_registry', 'test_two_return_forms_json_safe_meta_and_no_input_mutation'), '通过，两个返回形态和strict JSON-safe'),
        (ref('test_standardize', 'test_four_methods_formula_fit_metadata_and_determinism', 'test_zero_denominators_three_policies_and_error_context', 'test_signed_area_uses_band_index_not_wavelength_and_does_not_abs'), '通过'),
        (ref('test_resample', 'test_axis_and_range_fail_at_schema_level', 'test_interpolation_formula_and_no_clamp_or_extrapolation', 'test_fwhm_is_median_not_mean_and_proxy_marked', 'test_runtime_wavelengths_do_not_supply_missing_source'), '通过'),
        (ref('test_recipes', 'test_builtin_exact_code_chain_versions_and_default_provenance')+'<br>'+ref('test_migrations', 'test_twice_same_connection_schema_and_seed_rows_identical'), '通过；snv/sg_derivative为注册名，B01不入配方'),
        (ref('test_axis_contract', 'test_crop_then_resample_final_axis_and_summary_only', 'test_changed_bands_without_axis_always_rejected', 'test_rows_rank_empty_or_nonreal_output_rejected', 'test_declared_axis_validated_before_records'), '通过；axis不进records，只有len/hash'),
        (ref('test_decomposition', 'test_r10_axis_minimum_schema_guard_and_old_reference_unchanged'), '通过，AxisVector≥2而FiniteVector原语义不变'),
        (ref('test_run', 'test_run_raw_scale_artifacts_hashes_lineage_and_four_state_success', 'test_publication_failure_rolls_back_both_artifacts')+'<br>'+ref('test_decomposition', 'test_mnf_r12_noise_reconstruction_and_singular_pinv')+'<br>`e2e-result.json`: single_runs/negative_paths/artifact_audits', '通过：真实raw/scale、artifact仅双类型、失败无半份、无轴显式null'),
        (ref('test_run', 'test_preflight_failures_leave_no_run', 'test_global_fit_independent_of_disk_block_size', 'test_b08_run_nan_fit_exclusion_and_input_provenance_count', 'test_ica_temp_bytes_peak_rss_and_finally_cleanup')+'<br>'+ref('test_decomposition', 'test_mnf_independent_full_r12_formula_eigenvalues_and_scores')+'<br>'+ref('test_continuum', 'test_continuum_zero_denominator_nan_and_count'), '通过，真实数值边界与分块不变'),
    ]
    frontend = [
        ('pipeline.test.ts: operator directory / move-delete-repeat / empty pipeline；PipelineEditor接线', '通过'),
        ('pipeline.test.ts: schema-direction validation / all exposed methods；panel.test.ts接线', '通过，逐名10项；不扩reference方法'),
        ('pipeline.test.ts: axisAfter / crop→resample→crop / no wavelengths / target creation', '通过'),
        ('test_curves.py四项；pipeline.test.ts curve gaps；panel.test.ts legend；e2e-result.json artifact_audits', '通过逻辑/真实HTTP曲线；完整画布/视觉由科祥冒烟'),
        ('panel.test.ts S06 component wiring；test_compare.py numerical metrics；e2e-result.json compare', '通过逻辑；不以节点测试冒充实机操作'),
        ('panel.test.ts S06 component wiring（ICA variance_definition）；test_decomposition.py', '通过逻辑与后端数值'),
        ('api.test.ts create/get/add_version；test_recipes.py历史不可变；test_routes.py duplicate；e2e.py POST创建', '通过逻辑/HTTP，版本UI待人工清单'),
        ('api.test.ts select/deselect/list_project_recipes；e2e-result.json project_selection_preserves_recipe_and_versions', '通过'),
        ('api.test.ts run only two IDs；panel.test.ts no-version gating / errors；test_run.py四态；e2e-result.json', '通过'),
        ('panel.test.ts recovery / submit TRANSPORT automatically restores；api.ts已发货helper', '通过已有逻辑测试；本阶段不伪造真实超时，人工故障场景见smoke-checklist.md'),
        ('api.test.ts compare；panel.test.ts backend ranking wiring；e2e-result.json compare', '通过'),
        ('api.test.ts 12 exact IPC projections；panel.test.ts no invoke/fetch outside API；ipc_probe.rs/e2e-result.json真实forward', '通过；probe不冒充WebView invoke'),
        ('pytest-full.txt / cargo-test.txt / node-test.txt / tsc.txt / clippy.txt / audit-output.txt', '621 / 56 / 59 passed，tsc0/clippy0/audit0'),
    ]
    text = (ROOT/'TASK-05-预处理.md').read_text('utf-8')
    section = text.split('## 5. 验收标准', 1)[1].split('## 6.', 1)[0]
    main_text, front_text = section.split('### 5.1', 1)
    main_items = [line[6:].strip() for line in main_text.splitlines() if line.startswith('- [ ] ')]
    front_items = [line[6:].strip() for line in front_text.splitlines() if line.startswith('- [ ] ')]
    assert len(main_items) == len(coverage) == 30 and len(front_items) == len(frontend) == 13
    lines = ['# TASK-05 §5 全量验收映射 · 11.7', '',
             '本表从当前任务卡逐条提取，主清单30条 + S06十三条，共43条，无遗漏。测试名由AST核验存在；不改既有断言。', '',
             '执行模式：Python仓库根 `python -m pytest backend/tests src-python/tests -q` 默认参数、同命令设E盘PYTEST_DEBUG_TEMPROOT；Rust `cargo test`默认并行/default features；node托管22.22.2内置runner三目录；tsc `npx --no-install tsc --noEmit`；clippy `--all-targets -- -D warnings`；均exit0。', '',
             '授权缓建不伪装为完整业务通过：reference文件解析、MSC/EMSC来源选择UI依R11/R15；新增算子演示是接口自证，不是≤0.5人日的人力测量。实机UI/签名/干净机等留科祥，见smoke-checklist.md。', '',
             '| 序号 | 卡原文（不改写） | 测试/证据 | 结论与范围 |', '|---|---|---|---|']
    for i, (item, (tests, conclusion)) in enumerate(zip(main_items, coverage), 1):
        lines.append(f'| §5-{i} | {item.replace("|", "&#124;")} | {tests} | {conclusion} |')
    for i, (item, (tests, conclusion)) in enumerate(zip(front_items, frontend), 1):
        lines.append(f'| §5.1-{i} | {item.replace("|", "&#124;")} | {tests} | {conclusion} |')
    lines.extend(['', '新增集成断言另见 e2e.py：真实首个pe、三类人工确认的脚本夹具、默认参数run与同指纹重跑、N=3/Fisher、只读选用解除、7条run血缘与产物哈希/下载长度、负向反射率配方400和跨cube版本404、真实Rust forward report JSON。',
                  '每份性能数字附实现层/环境/时钟范围；两条触发线按HTTP全程分别判定，均未触发。源文件内容及seeds哈希不变。所有失败尝试保留，未将其算作成功。', ''])
    (OUT/'acceptance-map.md').write_text('\n'.join(lines), 'utf-8')
    summary = {'stage': '11.7', 'baseline_commit': '5f5f2be869a6e5cfc5936f2cefaf0fcb6c324aa2',
               'python': {'passed': 621, 'failed': 0, 'skipped': 0, 'exit_code': 0, 'mode': 'repository-root .venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q; default parameters; PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp in same command'},
               'rust': {'passed': 56, 'failed': 0, 'ignored': 0, 'exit_code': 0, 'mode': 'src-tauri cwd; cargo test default parallel/default features; unit/integration/doc; CARGO_NET_OFFLINE=true; TEMP/TMP on E', 'suites': suites},
               'node': {'passed': 59, 'failed': 0, 'skipped': 0, 'exit_code': 0, 'mode': 'managed 22.22.2 --test src/components/preprocess/*.test.ts src/components/datasets/*.test.ts src/components/annotation/*.test.ts; built-in default runner'},
               'typescript': {'exit_code': 0, 'mode': 'managed Node22.22.2 first on PATH; npx --no-install tsc --noEmit'},
               'clippy': {'exit_code': 0, 'warnings': 0, 'mode': 'src-tauri cwd cargo clippy --all-targets -- -D warnings'},
               'e2e': {'passed': True, 'failed': False, 'exit_code': 0, 'mode': 'real source sidecar --data-root isolated E runtime, bearer/identity checked loopback HTTP; real Rust parse_request/forward evidence probe, no WebView claim',
                       'http_calls': len(e2e['events']), 'shape': e2e['shape'], 'labeled_pixels': e2e['labeled_pixels'], 'reproduction_max_absolute_difference': e2e['reproduction']['max_absolute_difference'], 'ipc_probe': e2e['ipc_probe']},
               'audit': {'exit_code': 0, 'mode': 'repository-root python milestone03/audit_boundary.py; original assertions unmodified', 'commands': 7},
               'performance': {'file': 'performance.json', 'triggers': perf['thresholds'], 'single_http_seconds': [r['http_seconds'] for r in perf['single_runs']], 'compare_http_seconds': perf['compare']['http_seconds'], 'compare_cost_per_recipe_mean': perf['compare']['http_seconds_per_recipe_mean']},
               'environment_supplement': hardware, 'acceptance_items': {'main': 30, 's06': 13, 'mapped': 43, 'file': 'acceptance-map.md'},
               'boundaries': {'product_code_and_existing_tests_unchanged': True, 'manifest_unchanged': True, 'seed_sha256': seed_sha, 'T1_T2_implementation': 'unchanged, pending decision',
                              'manual_ui_smoke': '科祥，未执行；smoke-checklist.md'},
               'attempts': [{'attempt': 1, 'exit_code': 1, 'reason': 'new probe dependency search directory omitted deps; fixed evidence harness only', 'result': 'attempt-01-build-result.json'},
                            {'attempt': 2, 'exit_code': 1, 'reason': 'new exact JSON float assertion exceeded requested JSON-object contract; measured roundtrip difference, now structurally exact + TASK-05 §5 1e-12 extra check', 'result': 'attempt-02-json-result.json'},
                            {'attempt': 3, 'exit_code': 0, 'result': 'e2e-result.json'}]}
    card = (ROOT/'TASK-05-预处理.md').read_bytes()
    if b'| R16 |' in card:
        prefix = card.rsplit(b'| R16 |', 1)[0]
        before_hash = (ROOT/'.runtime/m05-11.7/card-before-r16.sha256').read_text('ascii')
        assert hashlib.sha256(prefix).hexdigest() == before_hash
        summary['card'] = {'lines': len(card.decode('utf-8').splitlines()), 'self_edit': 'append R16 only; preceding working-tree 313 lines byte-identical',
                           'preceding_313_lines_sha256': before_hash,
                           'preexisting_human_edits': '§5.1 operator count 11→10 plus §12 R15 correction were already present when 11.7 started'}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps({'python': 621, 'rust': 56, 'node': 59, 'tsc': 0, 'clippy': 0, 'e2e': 0, 'audit': 0, 'checklist_items': 43}))


if __name__ == '__main__':
    main()
