"""Bounded validation diagnostics; never serialize inputs or exception context."""
import re

from .errors import DataError


PARAMETER_ERRORS = frozenset({'TOOL_ARGS_INVALID', 'INVALID_OPERATOR_PARAMS'})
REGRESSION_PLAN_ERRORS = {
    'REGRESSION_PLAN_CONFLICT': '回归方案已变化或正在执行，请刷新后核对当前修订',
    'REGRESSION_PLAN_INCOMPLETE': '回归方案参数尚未补齐，请填写表单或明确选择参数模板',
    'REGRESSION_INPUT_NOT_CURRENT': '样品的标注或配方已变化，请完成当前预处理后重新审阅',
    'REGRESSION_TARGETS_MISSING': '所选样品尚未全部填写连续量，请补齐测量值；未自动排除样品',
    'REGRESSION_OPERATOR_UNSUPPORTED': '配方含当前严格回归不支持的算子或版本，请调整配方',
    'REGRESSION_INPUT_CHANGED': '数据、标注、配方或测量值已变化，请重新审阅回归方案',
    'REGRESSION_REVIEW_REQUIRED': '请先审阅当前回归方案，再确认训练；不会自动重试',
}
INPUT_ERRORS = PARAMETER_ERRORS | {'RECIPE_DRAFT_REVISION_CONFLICT','RECIPE_CONFIRMATION_STALE','RECIPE_DELETED','SOURCE_CHANGED','QUERY_SNAPSHOT_EXPIRED','QUERY_PAGE_REFERENCE_REQUIRED','QUERY_SCOPE_MISMATCH','PREPROCESS_REFERENCES_REQUIRED','PREPROCESS_RETRY_SCOPE_MISMATCH','RUN_NOT_FOUND'}
INPUT_ERRORS |= REGRESSION_PLAN_ERRORS.keys()
SAMPLE_EVALUATION_ERRORS = {
    'EXPERIMENT_EVALUATION_INVALID': '请核对实物定义、ENVI输入及完整分组表；训练未启动',
    'SAMPLE_EVALUATION_INVALID': '实物定义或完整分组表不合法，请核对表单',
    'SAMPLE_EVALUATION_UNAVAILABLE': '缺少可对应的原图来源、真值或预测；不能从NPZ批次分组猜测实物身份',
    'SAMPLE_EVALUATION_CONFLICT': '实物定义已变化，请刷新后核对当前修订',
    'SAMPLE_EVALUATION_STALE': '保存的预测或来源记录变化，请重新核对',
}
INPUT_ERRORS |= SAMPLE_EVALUATION_ERRORS.keys()
_RULES = {
    'int_type': ('integer', '需要整数；不要传字符串或小数'),
    'float_type': ('number', '需要数值'),
    'bool_type': ('boolean', '需要布尔值'),
    'string_type': ('string', '需要字符串'),
    'string_pattern_mismatch': ('declared string format', '字符串格式不符合字段声明；请使用真实引用，不要传占位文本'),
    'list_type': ('array', '需要列表'),
    'dict_type': ('object', '需要对象'),
    'missing': ('required', '请补充必填字段'),
    'extra_forbidden': ('declared fields', '请移除未声明字段'),
    'greater_than': ('greater than minimum', '数值必须大于声明的下限'),
    'greater_than_equal': ('at least minimum', '数值不得小于声明的下限'),
    'less_than_equal': ('at most maximum', '数值不得大于声明的上限'),
    'literal_error': ('declared enum', '请选择声明的枚举值'),
    'union_tag_invalid': ('declared discriminator', '请使用字段声明的类型或算子'),
    'union_tag_not_found': ('required discriminator', '请补充声明的类型或算子标识'),
    'json_invalid': ('JSON', '请提供合法 JSON'),
}
_MESSAGES = {
    'window 必须为奇数': ('odd_window', 'odd integer', 'window 必须为奇数；请选择正奇数窗口'),
    'polyorder 必须严格小于 window': ('polynomial_window', 'polyorder < window', '请使 polyorder 严格小于 window'),
    'interp 窗口不得超过输入 bands': ('input_bands', 'window <= input bands', 'interp 窗口不得超过该步骤输入的有效波段数；请缩小 window'),
    '边缘亮度上下界或探测波长不合法': ('foreground_bounds', 'ordered bounds and unique bands', '边缘亮度下限须小于上限，探测波长不得重复'),
}
_SEGMENTS = frozenset('''
    pipeline steps params op version window polyorder mode order zero_std method code name description note
    recipe recipe_id recipe_version_id source_recipe_version_id cube_id annotation_version_id annotation_version_no
    retry_of_submission run_id items members source_ref draft_id expected_revision revision action snv sg_smooth
    sg_derivative standardize body response
    axis grid archive saved_native start_nm stop_nm step_nm role kind train test roi_images npz envi
    input input_stage evaluation_unit source_refs spectra_key labels_key wavelengths_key groups_key
    header_ref roi_ref sample_id batch data_ref centers_ref neighborhood sampling_stride max_per_class sampling_seed
    wavelength_unit mapping_window_nm nearest_tolerance_nm
    classes label preprocessing preprocessing_edit index step savgol derivative delta_nm center standard_scale
    l2 epsilon ddof pca model n_components scale max_iter tol model_id reset additional_metrics test_usage
    sample_evaluation minimum_valid mapping evaluation_target study_selection definition_digest scoring
    quality min_mean min_std max_zero_fraction saturation
    foreground brightness_edges none wavelengths_nm threshold left_min right_min edge_search_columns
    edge_bad_fraction edge_low edge_high exclusions exclusions_ref name_fragments prefixes
'''.split())


def location(parts, allowed_fields=()):
    if isinstance(parts, str):
        parts = parts.split('.')
    if not isinstance(parts,(list,tuple)):
        parts=('field',)
    allowed = _SEGMENTS | set(allowed_fields)
    return '.'.join(str(p) if (type(p) is int and 0<=p<1000000)
                    or (isinstance(p,str) and (p in allowed or len(p)<=6 and p.isdecimal())) else 'field'
                    for p in list(parts)[:10]) or 'arguments'


def field_errors(error, allowed_fields=()):
    """Pydantic's msg for value_error can contain arbitrary validator text."""
    result = []
    try:
        items=error.errors(include_input=False, include_context=False, include_url=False)
    except TypeError:
        items=error.errors()  # FastAPI wrapper; only the three fields below are read.
    for item in items[:8]:
        rule = item['type']
        expected, message = _RULES.get(rule, ('declared constraint', '请按字段声明修正参数'))
        raw = item['msg'].removeprefix('Value error, ')
        if raw in _MESSAGES:
            rule, expected, message = _MESSAGES[raw]
        result.append({'field': location(item['loc'], allowed_fields), 'rule': rule if rule in _RULES or rule in {'odd_window', 'polynomial_window'} else 'constraint',
                       'expected': expected, 'message': message})
    return result


def validation_error(code, error, allowed_fields=()):
    return DataError(code, '参数不合法，请按字段说明修正', fields=field_errors(error, allowed_fields))


def safe_error(error):
    """Only curated diagnostics cross the tool boundary, as bounded scalars."""
    result = {'error': error.code}
    if error.code in SAMPLE_EVALUATION_ERRORS:
        return {**result, 'detail': SAMPLE_EVALUATION_ERRORS[error.code]}
    if error.code in REGRESSION_PLAN_ERRORS:
        return {**result, 'detail': REGRESSION_PLAN_ERRORS[error.code]}
    if error.code == 'RECIPE_DRAFT_REVISION_CONFLICT':
        result['detail'] = '草稿已更新，请读取最新修订并合并；后续操作未执行'
        revision = error.payload.context.get('latest_revision')
        if type(revision) is int and revision > 0:
            result['latest_revision'] = revision
        for i,change in enumerate(error.payload.context.get('differences',[])[:8],1):
            if isinstance(change,dict) and change.get('change') in {'added','removed','changed'}:
                result[f'difference_{i}'] = location(change.get('field','pipeline')) + ':' + change['change']
        for i in range(1,9):
            value = error.payload.context.get(f'difference_{i}')
            if isinstance(value,str) and len(value)<=160 and re.fullmatch(r'(?:steps|params|op|version|pipeline|field|\d+)(?:\.(?:steps|params|op|version|field|\d+))*:(?:added|removed|changed)',value):
                result[f'difference_{i}'] = value
        return result
    if error.code in INPUT_ERRORS - PARAMETER_ERRORS:
        result['detail'] = {'RECIPE_CONFIRMATION_STALE':'定义或范围改变，旧执行确认已失效，请重新绑定当前有效内容',
                            'PREPROCESS_REFERENCES_REQUIRED':'候选查询仅发现版本，请明确确认引用，或明确授权使用本轮查询结果',
                            'RECIPE_DELETED':'配方已删除；历史可读，新提交须先明确恢复',
                            'QUERY_SNAPSHOT_EXPIRED':'查询快照失效或不属于当前会话，请从第一页重新查询',
                            'QUERY_PAGE_REFERENCE_REQUIRED':'续页缺少快照引用；请沿用上一页的snapshot_ref和next_offset；首次查询须给完整范围和配方',
                            'QUERY_SCOPE_MISMATCH':'分页范围或配方发生变化；续页只需原snapshot_ref和next_offset，不能将范围缩成剩余样品',
                            'PREPROCESS_RETRY_SCOPE_MISMATCH':'仅能重试当前会话原批次中明确失败的成员；请先用preprocess.runs核对真实回执，成功项保留',
                            'RUN_NOT_FOUND':'该预处理运行不存在；请从preprocess.runs读取真实批次回执，不猜测或使用占位运行引用',
                            'SOURCE_CHANGED':'输入内容已改变，请重新核对确认范围'}[error.code]
        return result
    if error.code not in PARAMETER_ERRORS:
        return result
    result['detail'] = '参数不合法，请按字段说明修正；后续操作未执行'
    identifier = error.payload.context.get('run_id')
    if isinstance(identifier,str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',identifier):
        result['run_id'] = identifier
    completed = error.payload.context.get('completed_count')
    if type(completed) is int and 0 <= completed <= 32:
        result['completed_count'] = completed
    fields = error.payload.context.get('fields', [])
    for i, field in enumerate(fields[:8] if isinstance(fields, list) else [], 1):
        if not isinstance(field, dict):
            continue
        message = field.get('message', '')
        curated = next((v for k, v in _MESSAGES.items() if message == k or message == v[2]), None)
        known = next(((key,value[0],value[1]) for key,value in _RULES.items() if value[1] == message),None)
        rule, expected, message = curated or known or ('constraint', 'declared constraint', '请按字段声明修正参数')
        result.update({f'field_{i}_location': location(field.get('field', 'arguments')),
                       f'field_{i}_rule': rule, f'field_{i}_expected': expected, f'field_{i}_message': message})
    return result


def parameter_answer(error):
    summary = safe_error(error)
    reasons = [f"{summary[k]}：{summary[k.replace('_location', '_message')]}"
               for k in summary if re.fullmatch(r'field_\d+_location', k)]
    if 'latest_revision' in summary:
        reasons.append('最新 revision ' + str(summary['latest_revision']))
        reasons.extend(v for k,v in summary.items() if k.startswith('difference_'))
    return summary.get('detail', '请修正参数') + ('。' + '；'.join(reasons) if reasons else '')


def public_error(error):
    """HTTP diagnostics retain known references/rules, never arbitrary context."""
    if isinstance(error,dict):
        error=DataError(error['error'],error.get('detail',error['error']),**error.get('context',{}))
    summary=safe_error(error)
    context={}
    for key in ('run_id','operation_id','cube_id','recipe_id','recipe_version_id','version_id'):
        value=error.payload.context.get(key)
        if isinstance(value,str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value):context[key]=value
    for key in ('limit','actual','size','latest_revision','completed_count'):
        value=error.payload.context.get(key)
        if type(value) is int and value>=0:context[key]=value
    if error.code in PARAMETER_ERRORS:
        context['fields']=[{'field':summary[f'field_{i}_location'],'rule':summary[f'field_{i}_rule'],
                            'expected':summary[f'field_{i}_expected'],'message':summary[f'field_{i}_message']}
                           for i in range(1,9) if f'field_{i}_location' in summary]
    elif error.code=='INVALID_REQUEST':
        fields=error.payload.context.get('fields')
        if isinstance(fields,list):
            context['fields']=[location(field) if isinstance(field,str) else {
                'field':location(field.get('field','field')),'message':field.get('message') if field.get('message') in {v[1] for v in _RULES.values()} else '请按字段声明修正参数'}
                for field in fields[:8] if isinstance(field,(str,dict))]
        reason=error.payload.context.get('reason')
        if reason in {'batch_too_large','batch_response_too_large'}:context['reason']=reason
    if error.code=='RECIPE_DRAFT_REVISION_CONFLICT':
        context['differences']=[{'field':v.rsplit(':',1)[0],'change':v.rsplit(':',1)[1]} for k,v in summary.items() if k.startswith('difference_')]
    detail=summary.get('detail','业务操作失败，请按错误代码核对输入与原操作状态')
    if context.get('reason') in {'batch_too_large','batch_response_too_large'}:
        detail={'batch_too_large':'批量输入超过上限','batch_response_too_large':'批量响应超过上限'}[context['reason']]
    return {'error':error.code,'detail':detail,'context':context}


def public_result(value):
    """Sanitize nested run errors in HTTP receipts without changing stored facts."""
    if isinstance(value,list):
        return [public_result(item) for item in value]
    if isinstance(value,dict):
        if isinstance(value.get('error'),str) and 'context' in value:
            return public_error(value)
        return {key:public_result(item) for key,item in value.items()}
    return value
