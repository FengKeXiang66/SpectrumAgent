"""Audited local report forms; neither a training command nor a generic proxy."""
import json
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from spectrumagent.data import DataError
from .tools import ToolInput, Reference

PREFIX = '提交实物评价定义 '


class MappingRow(ToolInput):
    source_ref: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    sample_id: Annotated[str, Field(min_length=1, max_length=160)]


class Definition(ToolInput):
    experiment_id: Reference
    expected_revision: Annotated[int, Field(ge=0)]
    mode: Literal['IMAGE', 'MAPPED', 'MIXED']
    minimum_valid: Annotated[int, Field(ge=1, le=1000000)] = 100
    mapping: Annotated[list[MappingRow], Field(max_length=4096)] = []


class Form(Definition):
    form_id: Annotated[str, Field(pattern=r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')]
    mapping_csv: str | None = None


class Read(ToolInput):
    experiment_id: Reference


def summary(service, identifier):
    view = service.view(identifier)
    report = view['report'] or {}
    out = dict(sample_evaluation=True, experiment_id=identifier, archived_experiment_id=identifier,
               status='succeeded', revision=view['revision'],
               evaluation_status=report.get('status', 'unconfigured'), mode=(view['definition'] or {}).get('mode'),
               total_objects=report.get('total_objects'), source_count=len(view['sources']))
    out.update(applicable=view['applicable'], unavailable_reason=view['unavailable_reason'])
    for role, row in report.get('roles', {}).items():
        out.update({role+'_'+key: row[key] for key in ('total', 'included', 'excluded')})
        for key in ('accuracy', 'macro_f1'):
            out[role+'_'+key] = (row['metrics'] or {}).get(key)
        for reason, count in row['exclusion_counts'].items(): out[role+'_'+reason] = count
    out['sources_truncated'] = len(view['sources']) > 20
    for i, source in enumerate(view['sources'][:20], 1): out[f'image_{i}_source_ref'] = source['source_ref']
    return out


def register(registry, dialogue):
    service = dialogue.service.sample_evaluations
    registry.register('experiments.sample_evaluation_get', Read,
        '打开已完成实验的实物评价表单；返回revision及图像source_ref，不猜物理含义，不训练',
        lambda args: summary(service, args.experiment_id))
    def update(args):
        try:
            service.update(args.experiment_id, args.expected_revision, args.mode, args.minimum_valid,
                           [row.model_dump() for row in args.mapping])
        except ValueError as error:
            raise DataError('SAMPLE_EVALUATION_INVALID', '实物定义或完整分组表不合法，请核对表单') from error
        return summary(service, args.experiment_id)
    registry.register('experiments.sample_evaluation_update', Definition,
        '仅按用户明确声明派生实物报告，不训练或改变Study。IMAGE=一图一物；MAPPED须完整source_ref/sample_id表；MIXED=一图多物，不适用。默认有效观测阈值100，所有图像观测合并投票，真值冲突/平票/不足/跨训练测试排除。不把batch或NPZ groups推断为实物编号。', update)


def route(machine, content):
    if not content.startswith(PREFIX): return None
    return generate(machine, content[len(PREFIX):])


def generate(machine, payload):
    store, sid = machine.store, machine.session_id
    row = store.new_round(sid, '在对话中声明实物评价并生成派生报告', [], 'running')
    command = None
    try:
        if len(payload.encode()) > 1024*1024: raise ValueError('表单过大')
        command = Form.model_validate(json.loads(payload))
        machine.tools.resolve('experiments.sample_evaluation_update')
        if getattr(machine, 'control', None): machine.control.begin('tool')
        base = getattr(machine.tools, 'base', machine.tools)
        service = base.experiment_dialogue.service.sample_evaluations
        mapping = [r.model_dump() for r in command.mapping]
        if command.mapping_csv:
            if command.mode != 'MAPPED' or mapping: raise ValueError('CSV分组表仅用于MAPPED，不能同时传两份映射')
            mapping = service.csv_mapping(command.experiment_id, command.mapping_csv)
        service.update(command.experiment_id, command.expected_revision, command.mode,
                       command.minimum_valid, mapping, command.form_id)
        result = summary(service, command.experiment_id)
        result['form_id'] = command.form_id
        answer = '实物评价定义和派生报告已保存。原训练、像素指标与Study排序保留；请核对逐实物结果和未计入列表。'
        status, outcome = 'ok', 'replied'
    except (DataError, ValidationError, ValueError, OSError, KeyError, TypeError) as error:
        detail = error.payload.detail if isinstance(error, DataError) else str(error) if isinstance(error, ValueError) and not isinstance(error, ValidationError) else '请核对声明、分组表及必填项'
        result = dict(sample_evaluation=True, error=error.code if isinstance(error, DataError) else 'INVALID_FORM', detail=detail,
                      form_id=command.form_id if command else None)
        answer, status, outcome = '实物报告未生成：'+detail, 'error', 'needs_input'
    yield machine._step_event(store.add_step(row, 'experiments.sample_evaluation_form', {}, status, result, 0))
    store.save_answer(row['id'], answer); store.round_status(row['id'], 'done')
    yield 'done', dict(content=answer, step_count=1, request_status='finished', reply_status=outcome)
