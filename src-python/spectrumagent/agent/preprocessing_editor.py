"""Local, audited preprocessing form commands; never arbitrary tool dispatch."""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.preprocess import submissions

PREFIX = '提交预处理表单 '


def parameter_summary(kind, steps):
    lines = []
    for index, step in enumerate(steps, 1):
        params = step.get('params', {}) if kind == 'recipe' else {key: value for key, value in step.items() if key != 'op'}
        fields = '，'.join(f'{key}={len(value)} 项' if isinstance(value, list) else f'{key}={value}'
                          for key, value in params.items())
        lines.append(f"{index}. {step['op']}" + (f'（{fields}）' if fields else ''))
    return '\n当前参数：\n'+'\n'.join(lines) if lines else '\n当前参数：无附加预处理步骤。'


class FormCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['classification', 'recipe']
    action: Literal['open', 'update', 'save']
    form_id: Annotated[str, Field(pattern=r'^[0-9a-f-]{36}$')]
    draft_id: str | None = None
    expected_revision: Annotated[int, Field(ge=0)] | None = None
    recipe_id: str | None = None
    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    steps: Annotated[list[dict], Field(max_length=30)] | None = None
    axis_cube_id: str | None = None


def editor_view(tools, sid, kind, cube_id=None):
    """Read only metadata needed by a form. No sources, spectra or file paths."""
    intake = tools.data_intake
    runner = intake.runner
    result = {'kind': kind, 'draft_id': None, 'revision': None, 'steps': [],
              'recipe_id': None, 'name': '', 'recipes': [], 'axis': [], 'bands': 0, 'axis_cube_id': cube_id}
    with connect_database(runner.database) as db:
        receipt = db.execute("SELECT status,result_summary FROM agent_step WHERE session_id=? AND tool='preprocess.form_update' ORDER BY seq DESC LIMIT 1", (sid,)).fetchone()
    if receipt:
        result.update(last_form_ok=receipt[0] == 'ok', last_form_id=json.loads(receipt[1]).get('form_id'))
    if kind == 'classification':
        record = tools.experiment_dialogue._read(sid)
        if record and record['document']:
            result.update(draft_id=sid, revision=record['revision'],
                          steps=record['document'].get('preprocessing', []),
                          busy=record['run_status'] == 'running')
    else:
        draft = runner.drafts.get(sid)
        if draft:
            result.update(draft_id=draft['draft_id'], revision=draft['revision'],
                          steps=draft['pipeline']['steps'], name=draft['metadata'].get('name', ''))
            with connect_database(runner.database) as db:
                row = db.execute('SELECT recipe_id FROM preprocess_recipe_version WHERE id=?',
                                 (draft['source_recipe_version_id'],)).fetchone()
            result['recipe_id'] = row[0] if row else None
            if row:
                result['name'] = runner.recipes.get(row[0])['name']
        result['recipes'] = [{'id': r['id'], 'name': r['name']} for r in runner.recipes.list() if not r.get('deleted')]
        from spectrumagent.preprocess.current import CurrentWorkspace
        result['members'] = [{'cube_id': r['cube_id'], 'status': r['status'], 'recipe_id': r['recipe_id']}
                             for r in CurrentWorkspace(intake.sessions, runner).state()['members']]
        if cube_id:
            dataset, _ = intake.registry.get(cube_id)
            result.update(axis=list(dataset.wavelengths) if dataset.wavelengths is not None else [], bands=dataset.shape[2])
    return result


def route(machine, content):
    if not content.startswith(PREFIX):
        return None
    return generate(machine, content[len(PREFIX):])


def generate(machine, payload):
    sid, store = machine.session_id, machine.store
    row = store.new_round(sid, '在对话表单中修改预处理参数', [], 'running')
    steps = 0
    command = None
    try:
        if len(payload.encode('utf-8')) > 65536:
            raise DataError('INVALID_REQUEST', '表单内容过大')
        command = FormCommand.model_validate(json.loads(payload))
        if getattr(machine, 'control', None):
            machine.control.check()
        base = getattr(machine.tools, 'base', machine.tools)
        runner = base.data_intake.runner
        summary = {'kind': command.kind, 'action': command.action, 'form_id': command.form_id}
        if command.kind == 'classification':
            if command.action != 'update' or command.draft_id != sid or command.expected_revision is None or command.steps is None:
                raise DataError('INVALID_REQUEST', '请先打开当前分类方案再提交参数')
            from .tools.experiments import DraftUpdate
            view = base.experiment_dialogue.update(sid, DraftUpdate.model_validate({
                'expected_revision': command.expected_revision, 'preprocessing': command.steps}))
            summary['revision'] = view['revision']
            answer = '分类预处理参数已写入当前训练方案。尚未执行训练；请审阅方案，再单独确认训练或发起 Study。'
        elif command.action == 'open':
            source = None
            if command.recipe_id:
                source = runner.recipes.get(command.recipe_id)['versions'][-1]['id']
            draft = runner.drafts.create(sid, source, new_plan=True)
            summary.update(draft_id=draft['draft_id'], revision=draft['revision'])
            answer = '已打开高级配方草稿，请在对话中的参数表单编辑。尚未保存配方或执行处理。'
        else:
            current = runner.drafts.get(sid)
            if not current or command.draft_id != current['draft_id'] or command.expected_revision != current['revision']:
                raise DataError('RECIPE_DRAFT_CONFLICT', '配方草稿已更新，请刷新最新草稿后核对并重新提交')
            if command.action == 'update':
                if command.steps is None:
                    raise DataError('INVALID_REQUEST', '缺少配方步骤')
                # Reuse the same typed compiler/axis binding as natural-language edits.
                from .tools.recipe_drafts import UpdateDraft
                flattened = [{'op': s['op'], 'version': s['version'], **s['params']} for s in command.steps
                             if set(s) == {'op', 'version', 'params'} and isinstance(s['params'], dict)]
                if len(flattened) != len(command.steps):
                    raise DataError('INVALID_REQUEST', '配方步骤格式不合法')
                args = UpdateDraft.model_validate(dict(draft_id=command.draft_id, expected_revision=command.expected_revision,
                    steps=flattened, **({'axis_cube_id': command.axis_cube_id} if command.axis_cube_id else {}),
                    **({'name': command.name} if command.name else {})))
                from .tool_context import owner_session
                token = owner_session.set(sid)
                try:
                    result = base.invoke('preprocess.draft_update', args.model_dump(exclude_unset=True))
                finally:
                    owner_session.reset(token)
                summary.update(draft_id=command.draft_id, revision=result['revision'])
                answer = '高级配方参数已写入共享草稿。请保存配方后，单独指定样品范围执行预处理。'
            else:
                with connect_database(runner.database) as db:
                    source = db.execute('SELECT recipe_id FROM preprocess_recipe_version WHERE id=?',
                                        (current['source_recipe_version_id'],)).fetchone()
                recipe_id = source[0] if source else None
                if command.recipe_id != recipe_id:
                    raise DataError('RECIPE_DRAFT_CONFLICT', '目标配方与当前草稿不一致，请刷新后重试')
                with submissions.execution_context(submissions.explicit_submission(owner=sid, source='chat_form')):
                    result = runner.drafts.save(sid, command.draft_id, command.expected_revision,
                        recipe_id=recipe_id, name=command.name or current['metadata'].get('name'),
                        code=None if recipe_id else 'recipe-'+command.draft_id.replace('-', '')[:12])
                summary.update(recipe_id=result['recipe_id'])
                answer = '当前配方已保存。尚未执行预处理；请在对话中指定样品范围和该配方进行处理。'
        context = store.context(sid)
        if command.kind == 'recipe':
            context['recipe_editing'] = True
        else:
            context.pop('recipe_editing', None)
        store.save_context(sid, context)
        current_steps = (base.experiment_dialogue._read(sid)['document'].get('preprocessing', [])
                         if command.kind == 'classification' else runner.drafts.get(sid)['pipeline']['steps'])
        answer += parameter_summary(command.kind, current_steps)
        step = store.add_step(row, 'preprocess.form_update', {}, 'ok', summary, 0)
        steps += 1
        yield machine._step_event(step)
        # Show current training review without accepting execution consent.
        if command.kind == 'classification':
            dialogue = base.experiment_dialogue
            try:
                view = dialogue.view(sid)
                card = dialogue.draft_presentation(sid, view)
            except (DataError, ValueError, KeyError, TypeError):
                answer += '参数已保存，但方案摘要暂时无法展示，请查看当前实验方案后继续。'
            else:
                yield machine._step_event(store.add_step(row, 'experiments.draft_presentation', {}, 'ok', card, 0))
                steps += 1
        outcome = 'replied'
    except (DataError, ValidationError, ValueError, KeyError, TypeError) as error:
        code = error.code if isinstance(error, DataError) else 'INVALID_FORM'
        detail = error.payload.detail if isinstance(error, DataError) else '参数格式不合法，请检查步骤和必填项'
        answer = '预处理表单未提交：'+detail
        yield machine._step_event(store.add_step(row, 'preprocess.form_update', {}, 'error',
            {'error': code, 'detail': detail, 'form_id': command.form_id if command else None}, 0))
        steps += 1
        outcome = 'needs_input'
    store.save_answer(row['id'], answer)
    store.round_status(row['id'], 'done')
    yield 'done', {'content': answer, 'step_count': steps, 'request_status': 'finished', 'reply_status': outcome}
