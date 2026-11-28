"""Session-owned regression plans. Review is a digest of actual raw inputs, never a fit."""
import hashlib
import json
import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, ValidationError

from backend.database import connect_database
from spectrumagent.projects import current as project_current
from spectrumagent.data import DataError
from spectrumagent.modeling.dataset import build_sample_training_set
from spectrumagent.modeling.cv import kennard_stone, plan_folds
from spectrumagent.modeling.regression import PROTOCOL
from spectrumagent.preprocess.fitted import TRAINING_OPERATORS
from .tools import ToolInput, Reference, NoArguments
from .tool_context import owner_session

PREFIX = '提交回归训练方案 '
TEMPLATE = dict(split_strategy='ks', test_ratio=1/3, cv_strategy='kfold', cv_folds=5,
                seed=17, n_components=None, max_components=10)
FIELDS = ('preprocess_run_ids', 'target_schema_id', *TEMPLATE)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


class PlanPatch(ToolInput):
    expected_revision: Annotated[int, Field(ge=0)]
    preprocess_run_ids: Annotated[list[Reference], Field(min_length=4, max_length=256)] | None = None
    target_schema_id: Reference | None = None
    template: Literal['ks_5fold_v1'] | None = None
    split_strategy: Literal['ks'] | None = None
    test_ratio: Annotated[float, Field(gt=0, lt=1)] | None = None
    cv_strategy: Literal['kfold', 'loo'] | None = None
    cv_folds: Annotated[int, Field(ge=2, le=256)] | None = None
    seed: Annotated[int, Field(ge=0, le=2**32-1)] | None = None
    n_components: Annotated[int, Field(ge=1)] | None = None
    max_components: Annotated[int, Field(ge=1)] | None = None


class PlanReview(ToolInput):
    expected_revision: Annotated[int, Field(ge=0)]


class PlanExecute(PlanReview):
    review_digest: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class Form(ToolInput):
    action: Literal['save', 'review', 'execute']
    form_id: Annotated[str, Field(pattern=r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')]
    expected_revision: Annotated[int, Field(ge=0)]
    patch: PlanPatch | None = None
    review_digest: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')] | None = None


class RegressionPlans:
    def __init__(self, tools, datasets, runner, sessions, training):
        self.tools, self.datasets, self.runner = tools, datasets, runner
        self.sessions, self.training = sessions, training
        self.database, self.boot_id = training.database, str(uuid4())
        with connect_database(self.database) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS agent_regression_plan (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, document TEXT NOT NULL,
                status TEXT NOT NULL, review TEXT, digest TEXT, run_id TEXT, boot_id TEXT, error TEXT)''')

    def _read(self, sid):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM agent_regression_plan WHERE session_id=?', (sid,)).fetchone()
        if not row:
            return dict(revision=0, document={}, status='draft', review=None, digest=None, run_id=None, error=None)
        row = dict(row)
        row['document'] = json.loads(row['document'])
        row['review'] = json.loads(row['review']) if row['review'] else None
        if row['status'] == 'running':
            with connect_database(self.database) as db:
                result = db.execute('SELECT status FROM training_run WHERE id=?', (row['run_id'],)).fetchone()
                status = result[0] if result and result[0] in ('succeeded', 'failed') else None
                if status is None and row['boot_id'] != self.boot_id:
                    status = 'interrupted'
                if status:
                    db.execute('UPDATE agent_regression_plan SET status=? WHERE session_id=? AND revision=? AND status=\'running\'',
                               (status, sid, row['revision']))
                    row['status'] = status
        return row

    def summary(self, sid):
        row = self._read(sid)
        out = dict(regression_plan=True, revision=row['revision'], plan_status=row['status'],
                   member_count=len(row['document'].get('preprocess_run_ids') or []),
                   training_protocol=PROTOCOL, review_digest=row['digest'], run_id=row['run_id'])
        out.update({key: value for key, value in row['document'].items() if key != 'preprocess_run_ids'})
        for i, identifier in enumerate(row['document'].get('preprocess_run_ids', []), 1):
            out[f'member_{i}_preprocess_run_id'] = identifier
        if row['status'] == 'succeeded':
            out.update(self.tools.modeling.training_summary(row['run_id']))
        return out

    def view(self, sid):
        from spectrumagent.preprocess.current import CurrentWorkspace
        row = self._read(sid)
        with connect_database(self.database) as db:
            schemas = [dict(zip(('id', 'name', 'unit', 'project_id'), r)) for r in db.execute(
                "SELECT id,name,unit,project_id FROM label_schema WHERE field_type='continuous' AND project_id=? ORDER BY name,id", (project_current(db),))]
            targets = [dict(zip(('cube_id', 'schema_id', 'value'), r)) for r in db.execute(
                'SELECT cube_id,schema_id,value FROM sample_target WHERE project_id=?', (project_current(db),))]
            receipt = db.execute("SELECT status,result_summary FROM agent_step WHERE session_id=? AND tool='modeling.regression_form' ORDER BY seq DESC LIMIT 1", (sid,)).fetchone()
        members = CurrentWorkspace(self.sessions, self.runner).state()['members']
        for member in members:
            dataset, _ = self.datasets.get(member['cube_id'])
            member['name'] = dataset.name
        recipes = {r['id']: r for r in self.runner.recipes.list()}
        for member in members:
            recipe = recipes.get(member['recipe_id'])
            member['recipe_name'] = recipe['name'] if recipe else None
        return dict(revision=row['revision'], document=row['document'], status=row['status'], review=row['review'],
                    review_digest=row['digest'], run_id=row['run_id'], error=row['error'],
                    members=members, schemas=schemas, targets=targets, template=TEMPLATE,
                    last_form_id=json.loads(receipt[1]).get('form_id') if receipt else None,
                    last_form_ok=receipt[0] == 'ok' if receipt else None)

    def update(self, sid, args):
        row = self._read(sid)
        if row['revision'] != args.expected_revision or row['status'] == 'running':
            raise DataError('REGRESSION_PLAN_CONFLICT', '方案已变化或正在执行，请刷新后核对')
        patch = args.model_dump(exclude_unset=True)
        patch.pop('expected_revision')
        template = patch.pop('template', None)
        if any(value is None and key != 'n_components' for key, value in patch.items()):
            raise DataError('INVALID_REQUEST', '必填参数不能设为空')
        doc = {**row['document'], **(TEMPLATE if template else {}), **patch}
        runs = doc.get('preprocess_run_ids', [])
        if len(set(runs)) != len(runs):
            raise DataError('INVALID_REQUEST', '预处理引用不能重复')
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT revision,status FROM agent_regression_plan WHERE session_id=?', (sid,)).fetchone()
            if existing and (existing[0] != args.expected_revision or existing[1] == 'running'):
                raise DataError('REGRESSION_PLAN_CONFLICT', '方案已变化，请刷新后核对')
            db.execute('''INSERT INTO agent_regression_plan(session_id,revision,document,status)
                VALUES (?,?,?,'draft') ON CONFLICT(session_id) DO UPDATE SET revision=excluded.revision,
                document=excluded.document,status='draft',review=NULL,digest=NULL,run_id=NULL,error=NULL''',
                (sid, args.expected_revision+1, encode(doc)))
        return self.summary(sid)

    def _prepare(self, document):
        from .tools.interactive import Regression
        missing = [key for key in FIELDS if key not in document and not (key == 'cv_folds' and document.get('cv_strategy') == 'loo')]
        if missing:
            raise DataError('REGRESSION_PLAN_INCOMPLETE', '请填写全部训练参数或明确选择 KS 五折模板', missing='、'.join(missing))
        args = Regression.model_validate(document)
        from spectrumagent.preprocess.current import is_current_run
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            for identifier in args.preprocess_run_ids:
                run = db.execute('SELECT * FROM preprocess_run WHERE id=?', (identifier,)).fetchone()
                if run is None or run['status'] != 'succeeded' or not is_current_run(db, run):
                    raise DataError('REGRESSION_INPUT_NOT_CURRENT', '样品的当前标注或配方已变化，请先完成预处理')
        data = build_sample_training_set(self.datasets, self.training.paths, preprocess_run_ids=args.preprocess_run_ids,
                                        target_schema_id=args.target_schema_id, apply_preprocessing=False)
        if data['meta']['excluded_without_target']:
            raise DataError('REGRESSION_TARGETS_MISSING', '所选样品尚未全部填写该连续量，未自动排除样品')
        pipeline = data['meta']['cubes'][0]['pipeline']
        if any(step['op'] not in TRAINING_OPERATORS or step['version'] != 1 for step in pipeline['steps']):
            raise DataError('REGRESSION_OPERATOR_UNSUPPORTED', '此方案含不支持训练折内拟合的算子，请调整配方')
        split = kennard_stone(data['X_raw'], data['y'], data['groups'].tolist(), test_ratio=args.test_ratio)
        train, test = split['train_idx'], split['test_idx']
        folds = plan_folds(data['y'][train], data['groups'][train], task='regression', strategy=args.cv_strategy,
                           folds=len(train) if args.cv_strategy == 'loo' else args.cv_folds, seed=args.seed)
        maximum = min(data['X_raw'].shape[1], min(len(f['train_idx'])-1 for f in folds), args.max_components or data['X_raw'].shape[1])
        if maximum < 1 or args.n_components is not None and args.n_components > maximum:
            raise DataError('INVALID_LV', 'LV 超出内层训练样品数或原始特征数，请调小上限或固定 LV')
        with connect_database(self.database) as db:
            schema = db.execute('SELECT name,unit,project_id,tree_path,config FROM label_schema WHERE id=?', (args.target_schema_id,)).fetchone()
        evidence = dict(document=document, raw=data['X_raw'].tolist(), y=data['y'].tolist(),
                        wavelengths=data['wavelengths'].tolist(), members=data['meta']['cubes'], pipeline=pipeline, schema=list(schema))
        digest = hashlib.sha256(encode(evidence).encode()).hexdigest()
        review = dict(training_protocol=PROTOCOL, target_name=schema[0], unit=schema[1],
                      input_stage='已标前景均值谱；每张原图计一个样品',
                      pipeline=pipeline, train_cube_ids=data['groups'][train].tolist(), test_cube_ids=data['groups'][test].tolist(),
                      values=[dict(cube_id=c, value=float(y)) for c, y in zip(data['groups'].tolist(), data['y'])],
                      inner_folds=len(folds), lv_upper_bound=maximum, coverage_repaired=split['coverage_repaired'],
                      metrics=['R²C', 'RMSEC', 'R²P', 'RMSEP', 'RPD', 'RER', '偏差'],
                      note='KS 使用原始均值谱；内层按样品分组。配方在训练折内拟合，验证和测试只变换。多图同实物及批次分组尚不支持。')
        return args, data, digest, review

    def review(self, sid, args):
        row = self._read(sid)
        if row['revision'] != args.expected_revision or row['status'] in ('running', 'succeeded'):
            raise DataError('REGRESSION_PLAN_CONFLICT', '方案已变化或正在执行')
        _, _, digest, review = self._prepare(row['document'])
        with connect_database(self.database) as db:
            changed = db.execute("UPDATE agent_regression_plan SET review=?,digest=?,status='reviewed',error=NULL WHERE session_id=? AND revision=? AND status IN ('draft','reviewed','failed','interrupted')",
                                 (encode(review), digest, sid, args.expected_revision)).rowcount
        if not changed:
            raise DataError('REGRESSION_PLAN_CONFLICT', '审阅过程中方案已变化，请刷新')
        return self.summary(sid)

    def execute(self, sid, args):
        row = self._read(sid)
        if row['revision'] != args.expected_revision or row['digest'] != args.review_digest:
            raise DataError('REGRESSION_PLAN_CONFLICT', '确认不属于当前方案，请重新审阅')
        if row['status'] in ('running', 'succeeded'):
            return self.summary(sid)
        if row['status'] != 'reviewed':
            raise DataError('REGRESSION_REVIEW_REQUIRED', '请先重新审阅当前方案，再确认执行')
        try:
            parameters, data, digest, review = self._prepare(row['document'])
        except DataError:
            with connect_database(self.database) as db:
                db.execute("UPDATE agent_regression_plan SET status='draft',review=NULL,digest=NULL WHERE session_id=? AND revision=? AND status='reviewed'", (sid, args.expected_revision))
            raise
        if digest != args.review_digest:
            with connect_database(self.database) as db:
                db.execute("UPDATE agent_regression_plan SET status='draft',review=NULL,digest=NULL WHERE session_id=? AND revision=? AND status='reviewed'", (sid, args.expected_revision))
            raise DataError('REGRESSION_INPUT_CHANGED', '数据、标注、配方或测量值已变化，请重新审阅')
        identifier = str(uuid4())
        with connect_database(self.database) as db:
            changed = db.execute("UPDATE agent_regression_plan SET status='running',run_id=?,boot_id=?,error=NULL WHERE session_id=? AND revision=? AND status='reviewed' AND digest=?",
                                 (identifier, self.boot_id, sid, args.expected_revision, digest)).rowcount
        if not changed:
            # Another submission already claimed this exact revision.
            return self.summary(sid)
        try:
            evidence = dict(session_id=sid, revision=args.expected_revision, review_digest=digest,
                            document=row['document'], review=review)
            self.training.regress(**parameters.model_dump(), _prepared_data=data, _run_id=identifier, _plan_evidence=evidence)
        except BaseException as error:
            detail = error.payload.detail if isinstance(error, DataError) else '训练未完成，请核对运行记录后重新审阅'
            with connect_database(self.database) as db:
                db.execute("UPDATE agent_regression_plan SET status='failed',error=? WHERE session_id=? AND run_id=?", (detail, sid, identifier))
            raise
        return self.summary(sid)


def register(tools, **services):
    plans = RegressionPlans(tools, **services)
    tools.regression_plans = plans
    for name, schema, description, method in (
        ('modeling.regression_plan_get', NoArguments, '打开本会话回归训练表单，读取修订号；不会训练', lambda sid, a: plans.summary(sid)),
        ('modeling.regression_plan_update', PlanPatch, '更新回归方案；显式模板 ks_5fold_v1 为 KS 测试1/3、五折、seed17、自动 LV 上限10；保存不训练', plans.update),
        ('modeling.regression_plan_review', PlanReview, '核对完整方案及实际样品、测量值、配方和划分，不拟合；返回确认摘要的指纹', plans.review),
        ('modeling.regression_plan_execute', PlanExecute, '执行已审阅的当前回归方案；需要用户确认，变化时拒绝，重复提交复用已有运行', plans.execute),
    ):
        def handler(args, method=method):
            sid = owner_session.get()
            if not sid:
                raise DataError('DRAFT_OWNER_REQUIRED', '需要当前会话')
            return method(sid, args)
        tools.register(name, schema, description, handler)


def route(machine, content):
    if not content.startswith(PREFIX):
        return None
    return generate(machine, content[len(PREFIX):])


def generate(machine, payload):
    sid, store = machine.session_id, machine.store
    row = store.new_round(sid, '在对话中配置或确认回归训练方案', [], 'running')
    command = None
    try:
        if len(payload.encode()) > 65536:
            raise DataError('INVALID_REQUEST', '表单内容过大')
        command = Form.model_validate(json.loads(payload))
        if ((command.action != 'save' and command.patch is not None)
                or (command.action != 'execute' and command.review_digest is not None)):
            raise DataError('INVALID_REQUEST', '本次操作含无关参数，请重新提交表单')
        if getattr(machine, 'control', None):
            machine.control.begin('tool')
        base = getattr(machine.tools, 'base', machine.tools)
        # The old modeling.regress boundary is global too; local forms cannot
        # bypass a scoped registry or expose another session's plan.
        machine.tools.resolve('modeling.regression_plan_execute' if command.action == 'execute' else 'modeling.regression_plan_update')
        plans = base.regression_plans
        if command.action == 'save':
            if command.patch is None or command.patch.expected_revision != command.expected_revision:
                raise DataError('INVALID_REQUEST', '缺少当前修订的方案参数')
            result = plans.update(sid, command.patch)
            answer = '回归训练方案已保存，尚未训练。请审阅样品、测量值、划分与参数。'
        elif command.action == 'review':
            result = plans.review(sid, PlanReview(expected_revision=command.expected_revision))
            answer = '回归方案已核对，请在对话方案卡审阅具体样品、连续量、配方、划分与 LV，再确认训练。尚未拟合。'
        else:
            args = PlanExecute(expected_revision=command.expected_revision, review_digest=command.review_digest)
            # This exact command is emitted by the explicit review/confirm button;
            # model-originated executions instead use the ordinary numerical check.
            result = plans.execute(sid, args)
            answer = '回归训练已完成，报告如下。可继续在对话中登记模型并进行推理。' if result['plan_status'] == 'succeeded' else '本方案已受理，请刷新方案卡核对运行状态。'
        result['form_id'] = command.form_id
        event = store.add_step(row, 'modeling.regression_form', {}, 'ok', result, 0)
        outcome = 'replied'
    except (DataError, ValidationError, ValueError, KeyError, TypeError) as error:
        detail = error.payload.detail if isinstance(error, DataError) else '参数格式不合法，请核对必填项'
        event = store.add_step(row, 'modeling.regression_form', {}, 'error', dict(
            regression_plan=True, error=error.code if isinstance(error, DataError) else 'INVALID_FORM', detail=detail,
            form_id=command.form_id if command else None), 0)
        answer, outcome = '回归方案操作未完成：'+detail, 'needs_input'
    yield machine._step_event(event)
    store.save_answer(row['id'], answer)
    store.round_status(row['id'], 'done')
    yield 'done', dict(content=answer, step_count=1, request_status='finished', reply_status=outcome)
