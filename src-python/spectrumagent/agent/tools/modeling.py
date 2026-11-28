"""Reference-only adapters for existing modeling services; no scientific defaults change.

Write provenance is supplied by the request-local controller, never tool arguments.
Missing consent/references return need_version before any service side effect.
"""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
from typing import Annotated, Literal
from uuid import uuid5, NAMESPACE_URL

from pydantic import Field

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.modeling.dataset import _inputs
from . import ToolInput, Reference
from ..open_access import OPEN_ACCESS, MAX_MEMBERS


class ModelingMember(ToolInput):
    cube_id: Reference
    annotation_version_id: Reference | None = None
    preprocess_run_id: Reference | None = None


class ModelingBindingArguments(ToolInput):
    training_set_version_id: Reference | None = None
    dataset_version_id: Reference | None = None
    recipe_version_id: Reference | None = None
    items: Annotated[list[ModelingMember], Field(max_length=MAX_MEMBERS)] = Field(default_factory=list)
    preprocess_source: Literal['explicit', 'current_turn'] = 'explicit'
    cv_folds: Annotated[int,Field(ge=2)] = 5
    seed: int = 17
    confidence_threshold: Annotated[float,Field(ge=0,lt=1)] = 0
    n_components: Annotated[int,Field(ge=1,le=20)] | None = None
    max_components: Annotated[int,Field(ge=1,le=20)] | None = None
    band_selection: Literal['ipls'] | None = None
    evaluation_protocol: Literal['nested_group_cv', 'exploratory_group_cv'] = 'nested_group_cv'


class ModelingRunArguments(ToolInput):
    run_id: Reference


class TrainingTaskArguments(ToolInput):
    job_id: Reference
    action: Literal['get', 'events', 'cancel', 'continue'] = 'get'
    after: Annotated[int, Field(ge=0)] = 0


class ModelingListArguments(ToolInput):
    limit: Annotated[int, Field(ge=1, le=50)] = 20
    offset: Annotated[int, Field(ge=0)] = 0


class ModelingModelArguments(ToolInput):
    model_id: Reference


class ModelingMetricsArguments(ModelingRunArguments):
    comparison_run_id: Reference | None = None


class ClassificationInferArguments(ToolInput):
    model_id: Reference
    cube_ids: Annotated[list[Reference], Field(min_length=1, max_length=1000)]
    threshold: Annotated[float, Field(ge=0, lt=1)] | None = None


class ClassificationTaskArguments(ToolInput):
    evaluation_id: Reference
    task_id: Reference
    action: Literal['get', 'cancel', 'retry'] = 'get'


class ClassificationEvidenceArguments(ToolInput):
    evaluation_id: Reference
    action: Literal['summary', 'compare', 'interpret'] = 'summary'
    comparison_id: Reference | None = None


WRITE_TOOLS = frozenset({'modeling.preflight', 'modeling.classify'})
READ_TOOLS = frozenset({'modeling.runs', 'modeling.run', 'modeling.registry',
                        'modeling.coefficients', 'modeling.inference', 'modeling.metrics'})
CLASSIFICATION_TOOLS = frozenset({'modeling.classification_infer', 'modeling.classification_task', 'modeling.classification_result'})
MODELING_TOOLS = WRITE_TOOLS | READ_TOOLS | CLASSIFICATION_TOOLS | {'modeling.training_task'}


class NeedVersion(Exception):
    pass


def need_version():
    return {'status': 'need_version', 'detail': '请明确冻结版本、各标注版本、配方及成功预处理引用；不采用最新、默认或记忆补入。'}


def scalar_summary(value):
    """Only adapter-owned keys and checked values cross the tool boundary."""
    from ..llm import _egress_blocked
    if _egress_blocked(value) or any(isinstance(v, str) and any(c in v for c in '[]{}') for v in value.values()):
        raise DataError('TOOL_RESULT_INVALID', '建模摘要含不安全文本')
    if any(v is not None and (type(v) not in (str, int, float, bool)
                             or type(v) is float and not math.isfinite(v)) for v in value.values()):
        raise DataError('TOOL_RESULT_INVALID', '建模摘要含非法标量')
    if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 128 * 1024:
        raise DataError('TOOL_RESULT_INVALID', '建模摘要过大，请缩小查询范围')
    return value


def metric_scalar(value):
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise DataError('TOOL_RESULT_INVALID', '科学指标必须为有限数值或明确空值')
    return value


def identifiers(database, table):
    # table is selected only by server-owned code, never by a tool argument.
    with connect_database(database) as db:
        return {row[0] for row in db.execute(f'SELECT id FROM {table}')}


def explicitly_named(identifier, text, universe):
    tokens = re.findall(r'(?<![a-zA-Z0-9-])[0-9a-fA-F][0-9a-fA-F-]{7,35}(?![a-zA-Z0-9-])', text)
    return any(identifier.startswith(token.lower()) and
               sum(value.startswith(token.lower()) for value in universe) == 1 for token in tokens)


@dataclass(frozen=True)
class ModelingProvenance:
    user_message: str
    turn_id: str
    request_id: str | None
    steps: tuple
    bound_version: str | None = None
    shown_steps: tuple = ()


@dataclass(frozen=True)
class BoundModelingInputs:
    body: dict
    source: str
    turn_id: str
    request_id: str | None


def resolve_modeling_selection(*, arguments, versions, database, engine, provenance):
    if not arguments.dataset_version_id or not arguments.recipe_version_id or not arguments.items:
        raise NeedVersion()
    if OPEN_ACCESS:
        frozen = versions.get_frozen(arguments.dataset_version_id)
        members = frozen['members']
        items = {item.cube_id: item for item in arguments.items}
        if len(items) != len(arguments.items) or set(items) != {m['cube_id'] for m in members}:
            raise DataError('SESSION_SCOPE_MISMATCH', '建模引用不属于当前工作会话')
        for member in members:
            item = items[member['cube_id']]
            annotation = item.annotation_version_id
            if not annotation:
                raise NeedVersion()
            with connect_database(database) as db:
                actual = db.execute('SELECT cube_id FROM annotation_version WHERE id=?', (annotation,)).fetchone()
            if actual is None or actual[0] != item.cube_id:
                raise DataError('SESSION_SCOPE_MISMATCH', '标注版本与成员不一致')
            if engine is None or engine.source_identity(item.cube_id)[0] != member['content_hash']:
                raise DataError('SESSION_SOURCE_MISMATCH', '源内容与冻结版本不一致')
        return '', members, items
    if provenance is None:
        raise NeedVersion()
    # A reference mentioned in a rejected/negative clause grants no write consent.
    text = '，'.join(clause for clause in re.split(r'[,，;；。\n]', provenance.user_message)
                    if not re.search(r'不要|不用|不得|禁止|别|暂不|先不|不使用|不采用', clause))
    if not re.search(r'预检|训练|建模', text):
        raise NeedVersion()
    version, recipe = arguments.dataset_version_id, arguments.recipe_version_id
    version_named = explicitly_named(version, text, identifiers(database, 'dataset_version'))
    if not version_named and not (version == provenance.bound_version and
                                 re.search(r'本(?:工作)?会话(?:绑定的)?冻结版本', text)):
        raise NeedVersion()
    recipe_named = explicitly_named(recipe, text, identifiers(database, 'preprocess_recipe_version'))
    catalogs = [s for s in provenance.shown_steps if s['tool'] == 'preprocess.recipes' and s['status'] == 'ok']
    if catalogs:
        catalog = json.loads(catalogs[-1]['result_summary'])
        for token in re.findall(r'(?<!\w)[Pp](\d+)(?!\w)', text):
            recipe_named |= catalog.get(f'recipe_{int(token)}_version_id') == recipe
    for step in provenance.steps:
        if step['tool'] == 'preprocess.recipe_ensure' and step['status'] == 'ok':
            original = json.loads(step['arguments_json'])
            profile = original.get('profile')
            if profile in {'raw', 'snv', 'snv_sg1'} and re.search(r'配方\s*' + profile + r'(?![a-zA-Z0-9_])', text, re.I):
                recipe_named |= json.loads(step['result_summary']).get('recipe_version_id') == recipe
    if not recipe_named:
        raise NeedVersion()
    frozen = versions.get_frozen(version)
    members = frozen['members']
    items = {item.cube_id: item for item in arguments.items}
    if len(items) != len(arguments.items) or set(items) != {m['cube_id'] for m in members}:
        raise NeedVersion()
    if not 0 < len(members) <= MAX_MEMBERS:
        raise NeedVersion()
    annotation_ids = identifiers(database, 'annotation_version')
    for member in members:
        item = items[member['cube_id']]
        annotation = item.annotation_version_id
        if not annotation:
            raise NeedVersion()
        if not explicitly_named(annotation, text, annotation_ids):
            numbered = re.findall(r'标注(?:版本)?\s*[vV](\d+)(?!\d)', text)
            with connect_database(database) as db:
                matched = [row[0] for row in db.execute('SELECT id FROM annotation_version WHERE cube_id=? AND version_no=?',
                    (item.cube_id, int(numbered[0])))] if len(set(numbered)) == 1 else []
            if matched != [annotation]:
                raise NeedVersion()
        with connect_database(database) as db:
            actual = db.execute('SELECT cube_id FROM annotation_version WHERE id=?', (annotation,)).fetchone()
        if actual is None or actual[0] != item.cube_id:
            raise DataError('SESSION_SCOPE_MISMATCH', '标注版本与成员不一致')
        if engine is None or engine.source_identity(item.cube_id)[0] != member['content_hash']:
            raise DataError('SESSION_SOURCE_MISMATCH', '源内容与冻结版本不一致')
    return text, members, items


def resolve_modeling_binding(*, arguments, versions, database, registry, engine, provenance):
    text, members, items = resolve_modeling_selection(arguments=arguments, versions=versions,
        database=database, engine=engine, provenance=provenance)
    recipe, version = arguments.recipe_version_id, arguments.dataset_version_id
    run_ids = identifiers(database, 'preprocess_run')
    current = None
    if arguments.preprocess_source == 'current_turn':
        if not OPEN_ACCESS and not re.search(r'(?:本次|本轮)(?:整批)?预处理(?:产生的|生成的)?(?:整套)?(?:结果|运行|run)', text, re.I):
            raise NeedVersion()
        batches = [s for s in provenance.steps if s['tool'] == 'preprocess.run_batch']
        if len(batches) != 1 or batches[0]['status'] != 'ok':
            raise NeedVersion()
        summary = json.loads(batches[0]['result_summary'])
        if summary.get('truncated') is not False or summary.get('failed') != 0 or summary.get('succeeded') != len(members):
            raise NeedVersion()
        current = {}
        for i in range(1, len(members) + 1):
            cube = summary.get(f'item_{i}_cube_id')
            if cube in current or summary.get(f'item_{i}_status') != 'succeeded':
                raise NeedVersion()
            current[cube] = summary.get(f'item_{i}_run_id')
        if set(current) != set(items):
            raise NeedVersion()
    cubes, annotations, runs = [], [], []
    for member in members:
        item = items[member['cube_id']]
        annotation = item.annotation_version_id
        run = current.get(item.cube_id) if current is not None else item.preprocess_run_id
        if not annotation or not run or (current is not None and item.preprocess_run_id not in (None, run)):
            raise NeedVersion()
        if not OPEN_ACCESS and current is None and not explicitly_named(run, text, run_ids):
            raise NeedVersion()
        cubes.append(item.cube_id); annotations.append(annotation); runs.append(run)
    # Existing domain checker validates all annotation/run/recipe ownership before writes.
    rows = _inputs(registry, cube_ids=cubes, annotation_version_ids=annotations, preprocess_run_ids=runs,
            task='classification', target='label', recipe_version_id=recipe, dataset_version_ref=version)
    from spectrumagent.preprocess.recipes import input_fingerprint
    from spectrumagent.preprocess.run import file_sha256
    for row in rows:
        dataset, _ = registry.readable(row['cube_id'], raw=False)
        files = {Path(dataset.header_path), Path(dataset.data_path)}
        root = Path(os.path.commonpath([str(p.parent) for p in files]))
        hashes = {p.relative_to(root).as_posix(): file_sha256(p) for p in sorted(files)}
        fingerprint = input_fingerprint(row['cube_id'], hashes, row['annotation']['id'], row['annotation']['labeled_pixels'])
        if fingerprint != row['run']['input_fingerprint']:
            raise DataError('SESSION_SOURCE_MISMATCH', '预处理输入身份与当前明确引用不一致')
    body = {'task': 'classification', 'cube_ids': cubes, 'annotation_version_ids': annotations,
            'preprocess_run_ids': runs, 'target': 'label', 'cv_strategy': 'group_kfold', 'cv_folds': arguments.cv_folds,
            'split_strategy': 'none', 'seed': arguments.seed, 'confidence_threshold': arguments.confidence_threshold,
            'dataset_version_ref': version, 'recipe_version_id': recipe}
    for key in ('n_components','max_components','band_selection','evaluation_protocol'):
        if getattr(arguments,key) is not None:body[key]=getattr(arguments,key)
    return BoundModelingInputs(body, 'current_turn' if current is not None else 'explicit',
                               provenance.turn_id if provenance else 'direct', provenance.request_id if provenance else None)


def summarize_training_run(row):
    result = {k: row.get(k) for k in ('run_id', 'status', 'task', 'cv_strategy', 'cv_folds',
                                     'n_samples', 'n_pixels_used', 'selected_lv', 'best_lv', 'by_elbow', 'training_protocol')}
    document = row.get('confusion') if isinstance(row.get('confusion'), dict) else {}
    scores = document.get('scores') or {}
    for scope in ('pixel', 'sample'):
        metrics = row.get('metrics') or {}
        values = metrics.get(scope, {}) if isinstance(metrics, dict) else {}
        if scope == 'sample' and row.get('task') == 'regression' and isinstance(metrics, dict):
            for key in ('rmse', 'r2', 'rmsep', 'r2p', 'rpd', 'rer', 'bias'):
                if key in metrics:
                    result['sample_' + key] = metric_scalar(metrics[key])
        detailed = scores.get(scope, {})
        for key in ('oa', 'kappa', 'aa', 'macro_f1'):
            if key in values:
                result[f'{scope}_{key}'] = metric_scalar(values[key])
            elif key in detailed:
                result[f'{scope}_{key}'] = metric_scalar(detailed[key])
            if row.get('evaluation'):
                identity = json.dumps({'population':'accepted','scope':scope,'name':key,'class_id':None,'fold_id':None,
                    'aggregation':'pooled'}, sort_keys=True, separators=(',',':'))
                ref = detailed.get('metric_refs',{}).get(identity)
                if ref:
                    result[f'{scope}_{key}_metric_id'] = ref
        for i, item in enumerate(detailed.get('per_class', []), 1):
            for key in ('label', 'precision', 'recall', 'f1'):
                if key in item:
                    result[f'{scope}_class_{i}_{key}'] = item[key] if key == 'label' else metric_scalar(item[key])
    if row.get('evaluation'):
        result['evaluation_id'] = row['evaluation']['evaluation_id']
        result['evaluation_protocol'] = row['evaluation']['protocol']
        result['group_kind'] = row['evaluation']['group_kind']
        for scope in ('pixel','sample'):
            result[f'{scope}_coverage'] = row['evaluation']['populations']['accepted']['scores'][scope]['coverage']
    leak = row.get('leak_report') or {}
    for key, value in [('leak_passed', leak.get('passed')),
                       ('leak_group_violations', (leak.get('group_cross_fold') or {}).get('violation_count')),
                       ('leak_duplicate_count', (leak.get('duplicate_content') or {}).get('duplicate_count'))]:
        if value is not None:
            result[key] = value
    return scalar_summary(result)


class ModelingTools:
    def __init__(self, *, training, models, inferences, versions, database, datasets, engine):
        self.training, self.models, self.inferences = training, models, inferences
        self.paths = getattr(training, 'paths', None)
        self.versions, self.database, self.datasets, self.engine = versions, database, datasets, engine

    def run_members(self, identifier):
        with connect_database(self.database) as db:
            row = db.execute('SELECT cube_ids,annotation_version_ids,preprocess_run_ids FROM training_run WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise DataError('SESSION_REFERENCE_INVALID', '训练引用不存在')
            cubes, annotations, runs = (json.loads(value) for value in row)
            if (not cubes or any(not isinstance(values, list) or any(not isinstance(c, str) for c in values)
                                 for values in (cubes, annotations, runs))):
                raise DataError('SESSION_REFERENCE_INVALID', '训练成员引用不完整')
            members = set(cubes)
            for refs, table in ((annotations, 'annotation_version'), (runs, 'preprocess_run')):
                for i, ref in enumerate(refs):
                    actual = db.execute(f'SELECT cube_id FROM {table} WHERE id=?', (ref,)).fetchone()
                    if actual is None or len(refs) == len(cubes) and actual[0] != cubes[i]:
                        raise DataError('SESSION_REFERENCE_INVALID', '训练关联引用不一致')
                    members.add(actual[0])
            if len(cubes) == len(annotations) == len(runs):
                for annotation, run in zip(annotations, runs):
                    actual = db.execute('SELECT annotation_version_id FROM preprocess_run WHERE id=?', (run,)).fetchone()
                    if actual is None or actual[0] != annotation:
                        raise DataError('SESSION_REFERENCE_INVALID', '训练关联标注与预处理不一致')
        return members

    def jobs(self):
        from spectrumagent.modeling.training_jobs import jobs_for
        return jobs_for(self.datasets, self.paths)

    @staticmethod
    def owner():
        from ..tool_context import owner_session
        return owner_session.get() or 'application'

    def submission_id(self, provenance=None, suffix='classify'):
        from spectrumagent.preprocess.submissions import current_submission
        from uuid import uuid4
        submission = current_submission.get()
        # One asynchronous classification operation per user turn. A provider
        # regeneration may change its call position, but cannot mint a second
        # operation; a new explicit user request gets a new submission_ref.
        request = (submission.submission_ref if submission else
                   (provenance.request_id or provenance.turn_id) if provenance else str(uuid4()))
        return str(uuid5(NAMESPACE_URL, ':'.join((self.jobs().boot_id, self.owner(), request, suffix))))

    def submit_training(self, body, provenance):
        receipt = self.jobs().submit(self.submission_id(provenance), body, owner=self.owner())
        return scalar_summary({'status': 'accepted', 'job_id': receipt['job_id'], 'task_status': receipt['status'],
                               'complete': False, 'engine_boot_id': receipt['engine_boot_id'],
                               'detail': '后台训练已受理；尚未形成完整评价，请通过任务查询真实进度及结果。'})

    def reference_members(self, name, args, *, owner=None):
        if name == 'modeling.training_task':
            return set(self.jobs().status(args['job_id'], owner=owner or self.owner())['cube_ids'])
        if name in CLASSIFICATION_TOOLS:
            from spectrumagent.modeling.classification_operations import operations_for
            ops = operations_for(self.training.registry, self.training.paths)
            if name == 'modeling.classification_infer':
                model = ops.models.get(args['model_id'])
                return self.run_members(model['run_id']) | set(args['cube_ids'])
            ev = ops.store.get(args['evaluation_id'])
            cubes = {c['cube_id'] for c in ev['cubes']}
            if args.get('comparison_id'):
                cubes |= {c['cube_id'] for c in ops.store.get(args['comparison_id'])['cubes']}
            if name == 'modeling.classification_task':
                row = ops.tasks.status(args['task_id'], 0, 50)
                if row['evaluation_id'] != args['evaluation_id']:
                    raise DataError('SESSION_SCOPE_MISMATCH', '分类任务与评价身份不一致')
                with ops.tasks.lock:
                    cubes |= {t['cube_id'] for t in ops.tasks.jobs[args['task_id']].get('targets', [])}
            return cubes
        if name in WRITE_TOOLS:
            if args.get('training_set_version_id'):
                return {m['cube_id'] for m in self.training_sets.resolve_members(args['training_set_version_id'])['members']}
            cubes = {item['cube_id'] for item in args.get('items', [])}
            version = args.get('dataset_version_id')
            if version:
                cubes |= {m['cube_id'] for m in self.versions.get_frozen(version)['members']}
            return cubes
        if name == 'modeling.run':
            return self.run_members(args['run_id'])
        if name == 'modeling.metrics':
            cubes = self.run_members(args['run_id'])
            if args.get('comparison_run_id'):
                cubes |= self.run_members(args['comparison_run_id'])
            return cubes
        if name == 'modeling.coefficients':
            return self.run_members(self.models.get(args['model_id'])['run_id'])
        if name == 'modeling.inference':
            row = self.inferences.get(args['run_id'])
            model = self.models.get(row['model_id'], calibration=True)
            self.inferences.references(model, row['cube_id'], row['preprocess_run_id'], row['annotation_version_id'])
            return {row['cube_id']} | self.run_members(self.models.get(row['model_id'])['run_id'])
        return set()

    def training_summary(self, identifier, row=None):
        row = self.training.get(identifier) if row is None else row
        if row.get('run_id') != identifier:
            raise DataError('SESSION_RESULT_SCOPE_MISMATCH', '训练返回身份不一致')
        result = summarize_training_run(row)
        with connect_database(self.database) as db:
            raw = db.execute('SELECT cube_ids,annotation_version_ids,preprocess_run_ids,status,task FROM training_run WHERE id=?', (identifier,)).fetchone()
            artifact = db.execute("SELECT id FROM model_artifact WHERE run_id=? AND kind='model'", (identifier,)).fetchone()
            if raw is None:
                raise DataError('SESSION_REFERENCE_INVALID', '训练引用不存在')
            if row.get('status') != raw[3] or row.get('task', raw[4]) != raw[4]:
                raise DataError('SESSION_RESULT_SCOPE_MISMATCH', '训练返回状态与账本不一致')
            cubes, annotations, runs = (json.loads(value) for value in raw[:3])
            result.update(member_count=len(cubes), binding_complete=bool(cubes) and len(cubes) == len(annotations) == len(runs))
            for i, cube in enumerate(cubes, 1):
                result[f'member_{i}_cube_id'] = cube
                if not result['binding_complete']:
                    continue
                result[f'member_{i}_annotation_version_id'] = annotations[i-1]
                result[f'member_{i}_preprocess_run_id'] = runs[i-1]
                recipe = db.execute('SELECT recipe_version_id FROM preprocess_run WHERE id=?', (runs[i-1],)).fetchone()
                if recipe:
                    result[f'member_{i}_recipe_version_id'] = recipe[0]
                else:
                    result['binding_complete'] = False
        if artifact:
            result['model_artifact_id'] = artifact[0]
        document = row.get('confusion') if isinstance(row.get('confusion'), dict) else {}
        manifest = document.get('manifest') or {}
        if manifest.get('dataset_version_ref'):
            result['dataset_version_id'] = manifest['dataset_version_ref']
        return scalar_summary(result)

    def invoke(self, name, arguments, *, provenance=None, allowed_cubes=None):
        args = arguments.model_dump(mode='json')
        if name == 'modeling.training_task':
            cubes = self.reference_members(name, args)
            if allowed_cubes is not None and not cubes <= allowed_cubes:
                raise DataError('SESSION_SCOPE_MISMATCH', '训练任务不属于当前工作会话')
            jobs, owner = self.jobs(), self.owner()
            if arguments.action == 'cancel':
                row = jobs.cancel(arguments.job_id, owner=owner)
            elif arguments.action == 'continue':
                row = jobs.resume(arguments.job_id, self.submission_id(provenance, 'continue:'+arguments.job_id), owner=owner)
            else:
                row = jobs.status(arguments.job_id, owner=owner)
            result = {k: row.get(k) for k in ('job_id', 'status', 'run_id', 'evaluation_id', 'phase', 'elapsed_s',
                       'cancel_requested', 'cancelable', 'result_status', 'total_folds', 'retry_of', 'engine_boot_id')}
            result.update(completed_folds=len(row.get('completed_folds', [])), reused_folds=len(row.get('reused_folds', [])),
                          complete=row['status'] == 'succeeded')
            if row.get('error'):
                result['error_code'] = row['error']['error']
            if arguments.action == 'events':
                page = jobs.events(arguments.job_id, arguments.after, 50, owner=owner)
                result.update(cursor=page['cursor'], event_count=len(page['events']))
                for index, event in enumerate(page['events'], 1):
                    for key in ('seq', 'phase', 'elapsed_s', 'branch', 'outer_fold', 'completed', 'total', 'rmsecv'):
                        if key in event: result[f'event_{index}_{key}'] = event[key]
            if row['status'] == 'succeeded':
                result.update(self.training_summary(row['run_id']))
            return scalar_summary(result)
        if name in CLASSIFICATION_TOOLS:
            cubes = self.reference_members(name, args)
            if allowed_cubes is not None and not cubes <= allowed_cubes:
                raise DataError('SESSION_SCOPE_MISMATCH', '分类结果或推理目标不属于当前工作会话')
            from spectrumagent.modeling.classification_operations import operations_for
            ops = operations_for(self.training.registry, self.training.paths)
            if name == 'modeling.classification_result':
                ev = ops.store.get(arguments.evaluation_id)
                result = {k: ev[k] for k in ('evaluation_id', 'run_id', 'protocol', 'definition', 'threshold')}
                for scope in ('pixel', 'sample'):
                    score = ev['populations']['accepted']['scores'][scope]
                    for metric in ('oa', 'aa', 'kappa', 'macro_f1', 'coverage'):
                        result[scope+'_'+metric] = score[metric]
                    for key, ref in score['metric_refs'].items():
                        dims = json.loads(key)
                        if dims['aggregation'] == 'pooled' and dims['class_id'] is None:
                            result[scope+'_'+dims['name']+'_metric_id'] = ref
                if arguments.action != 'summary':
                    from spectrumagent.api.models import ClassificationOperation
                    body = ClassificationOperation(comparison_id=arguments.comparison_id)
                    document = ops.perform(arguments.evaluation_id, arguments.action, body)
                    compared = document if arguments.action == 'compare' else document.get('comparison')
                    if compared is not None:
                        result.update(comparison_id=compared['comparison_id'], comparable=compared['comparable'],
                                      comparison_differences=','.join(compared['differences']))
                        for row in compared['rows']:
                            if row['population'] == 'accepted':
                                key = row['scope']+'_'+row['name']
                                result[key+'_difference'] = row['difference']
                                result[key+'_difference_metric_id'] = row['metric_id']
                    if arguments.action == 'interpret':
                        result.update(generator=document['generator'], cloud_called=False)
                        for index, claim in enumerate(document['claims']):
                            result['fact_'+str(index+1)] = claim['text']
                            result['fact_'+str(index+1)+'_metric_id'] = claim['metric_id']
                return scalar_summary(result)
            if name == 'modeling.classification_infer':
                row = ops.tasks.submit(arguments.model_id, arguments.cube_ids, arguments.threshold)
            else:
                row = (ops.tasks.status if arguments.action == 'get' else ops.tasks.cancel if arguments.action == 'cancel' else ops.tasks.retry)(arguments.task_id)
            result = {k: row[k] for k in ('task_id', 'evaluation_id', 'status', 'kind', 'total')}
            result.update({'count_'+k: v for k, v in row['counts'].items()})
            for key in ('total_pixels', 'valid_pixels', 'accepted', 'rejected', 'out_of_domain'):
                result[key] = row['summary'][key]
            return scalar_summary(result)
        if name in WRITE_TOOLS and arguments.training_set_version_id:
            members=self.training_sets.resolve_members(arguments.training_set_version_id)['members']
            cubes={m['cube_id'] for m in members}
            if allowed_cubes is not None and not cubes<=allowed_cubes:
                raise DataError('SESSION_SCOPE_MISMATCH','训练集成员不属于当前工作会话')
            if arguments.items or arguments.dataset_version_id or arguments.recipe_version_id:
                raise DataError('INVALID_REQUEST','训练集版本与旧的显式成员绑定不能同时提供')
            if name=='modeling.preflight':
                row=self.training.preflight(cube_ids=[m['cube_id'] for m in members],
                    annotation_version_ids=[m['annotation_version_id'] for m in members],
                    preprocess_run_ids=[m['preprocess_run_id'] for m in members],task='classification',target='label',
                    cv_strategy='group_kfold',cv_folds=arguments.cv_folds,seed=arguments.seed,split_strategy='none',
                    evaluation_protocol=arguments.evaluation_protocol)
            else:
                receipt = self.submit_training(dict(cube_ids=[],annotation_version_ids=[],preprocess_run_ids=[],
                    training_set_version_id=arguments.training_set_version_id,
                    cv_folds=arguments.cv_folds,seed=arguments.seed,confidence_threshold=arguments.confidence_threshold,
                    n_components=arguments.n_components,max_components=arguments.max_components,band_selection=arguments.band_selection,
                    evaluation_protocol=arguments.evaluation_protocol), provenance)
                return {**receipt, 'training_set_version_id': arguments.training_set_version_id}
            result=self.training_summary(row['run_id'],row)
            result['training_set_version_id']=arguments.training_set_version_id
            return result
        if name in WRITE_TOOLS and (not arguments.items
                or not arguments.dataset_version_id or not arguments.recipe_version_id):
            return need_version()
        def allowed(cubes):
            return allowed_cubes is None or bool(cubes) and cubes <= allowed_cubes
        if not allowed(self.reference_members(name, args)) and name not in {'modeling.runs', 'modeling.registry'}:
            raise DataError('SESSION_SCOPE_MISMATCH', '建模引用不属于当前工作会话')
        if name in WRITE_TOOLS:
            try:
                bound = resolve_modeling_binding(arguments=arguments, versions=self.versions, database=self.database,
                    registry=self.datasets, engine=self.engine, provenance=provenance)
            except NeedVersion:
                return need_version()
            body = bound.body
            if name == 'modeling.preflight':
                row = self.training.preflight(**{k: v for k, v in body.items()
                    if k not in {'dataset_version_ref', 'recipe_version_id', 'confidence_threshold',
                                 'n_components','max_components','band_selection'}})
            else:
                result = self.submit_training(body, provenance)
                result.update(modeling_binding_source=bound.source, modeling_turn_id=bound.turn_id,
                              modeling_request_id=bound.request_id, dataset_version_id=body['dataset_version_ref'],
                              recipe_version_id=body['recipe_version_id'], member_count=len(body['cube_ids']))
                return scalar_summary(result)
            result = self.training_summary(row['run_id'], row)
            if self.run_members(result['run_id']) != set(body['cube_ids']):
                raise DataError('SESSION_RESULT_SCOPE_MISMATCH', '训练返回引用不匹配；既有副作用未回滚')
            result.update(modeling_binding_source=bound.source, modeling_turn_id=bound.turn_id,
                          modeling_request_id=bound.request_id, dataset_version_id=body['dataset_version_ref'],
                          recipe_version_id=body['recipe_version_id'], member_count=len(body['cube_ids']))
            for i, (cube, annotation, run) in enumerate(zip(body['cube_ids'], body['annotation_version_ids'], body['preprocess_run_ids']), 1):
                result.update({f'member_{i}_cube_id': cube, f'member_{i}_annotation_version_id': annotation,
                               f'member_{i}_preprocess_run_id': run})
            return scalar_summary(result)
        if name == 'modeling.run':
            return self.training_summary(arguments.run_id)
        if name == 'modeling.metrics':
            left = self.training_summary(arguments.run_id)
            if not arguments.comparison_run_id:
                return left
            right = self.training_summary(arguments.comparison_run_id)
            result = {**{f'left_{k}': v for k, v in left.items()}, **{f'right_{k}': v for k, v in right.items()},
                      'comparison_kind': 'observed_metrics_only',
                      'same_training_protocol': left.get('training_protocol', left.get('evaluation_protocol')) == right.get('training_protocol', right.get('evaluation_protocol')),
                      'same_task': left.get('task') == right.get('task'),
                      'same_members': self.run_members(arguments.run_id) == self.run_members(arguments.comparison_run_id)}
            result['comparable'] = result['same_training_protocol'] and result['same_task'] and result['same_members']
            if not result['same_training_protocol']:
                result['comparison_limitation'] = '训练协议不同，仅分别展示指标，不能直接排名或认定改进。'
            return scalar_summary(result)
        if name in {'modeling.runs', 'modeling.registry'}:
            rows = self.training.list() if name == 'modeling.runs' else self.models.list()
            rows = [row for row in rows if allowed(self.run_members(row['id'] if name == 'modeling.runs' else row['run_id']))]
            page = rows[arguments.offset:arguments.offset + arguments.limit]
            result = {'count': len(page), 'total_count': len(rows), 'offset': arguments.offset,
                      'truncated': arguments.offset + len(page) < len(rows)}
            for i, row in enumerate(page, 1):
                # Untrusted display names do not bypass the path/serialized-object guard.
                for key in ('id', 'status', 'task', 'run_id', 'version', 'stage', 'oa', 'kappa', 'lv', 'training_protocol'):
                    if key in row:
                        result[f'item_{i}_{key}'] = row[key]
                if name == 'modeling.registry':
                    from ..llm import _egress_blocked
                    label = row.get('name')
                    safe = isinstance(label, str) and len(label) <= 160 and not _egress_blocked(label) and not any(c in label for c in '[]{}')
                    result[f'item_{i}_name_available'] = safe
                    if safe:
                        result[f'item_{i}_name'] = label
            return scalar_summary(result)
        if name == 'modeling.coefficients':
            row = self.models.coefficients(arguments.model_id)
            if row.get('model_id') != arguments.model_id:
                raise DataError('SESSION_RESULT_SCOPE_MISMATCH', '模型返回身份不一致')
            result = {k: row.get(k) for k in ('model_id', 'version', 'stage', 'selected_lv',
                'n_features', 'n_wavelengths', 'comparable')}
            result['limitation'] = '只报告真实维度与可比性；系数不构成重要性排序，非波长特征不能按波长解释。'
            return scalar_summary(result)
        if name == 'modeling.inference':
            row = self.inferences.get(arguments.run_id)
            if row.get('id') != arguments.run_id:
                raise DataError('SESSION_RESULT_SCOPE_MISMATCH', '推理返回身份不一致')
            result = {k: row.get(k) for k in ('id', 'status', 'model_id', 'cube_id',
                'annotation_version_id', 'preprocess_run_id')}
            stats = row.get('stats') or {}
            result['statistics_scope'] = stats.get('statistics_scope')
            result['calibration_origin'] = stats.get('calibration_origin')
            result['input_warning'] = stats.get('warning')
            for key in ('n_pixels', 'n_foreground', 'mean', 'std', 'min', 'max', 'pixel_mean',
                        'sample_prediction', 'out_of_domain_count', 'out_of_domain_fraction',
                        'out_of_range_count', 'below_range_count', 'above_range_count', 'low', 'high'):
                if key in stats:
                    result['stats_' + key] = metric_scalar(stats[key])
            for key in ('p05', 'p25', 'p50', 'p75', 'p95'):
                if key in (stats.get('quantiles') or {}):
                    result['quantile_' + key] = metric_scalar(stats['quantiles'][key])
            return scalar_summary(result)
        raise DataError('TOOL_NOT_FOUND', '建模工具未注册')


def register_modeling_tools(registry, *, training=None, models=None, inferences=None, versions=None,
                            database=None, datasets=None, engine=None):
    service = ModelingTools(training=training, models=models, inferences=inferences, versions=versions,
                           database=database, datasets=datasets, engine=engine)
    registry.modeling = service
    specs = [('modeling.preflight', ModelingBindingArguments, '显式引用预检；会写训练记录'),
             ('modeling.classify', ModelingBindingArguments, '异步受理分类训练，立即返回job_id；accepted不表示评价完成，随后查询任务'),
             ('modeling.training_task', TrainingTaskArguments, '查询本会话训练任务、分页日志、取消或继续未完成；完成后返回真实指标'),
             ('modeling.runs', ModelingListArguments, '分页查询历史训练摘要，不选最新触发写入'),
             ('modeling.run', ModelingRunArguments, '查询明确训练 run 的安全摘要'),
             ('modeling.registry', ModelingListArguments, '只读分页查询现有分类或回归注册模型'),
             ('modeling.coefficients', ModelingModelArguments, '只读系数维度与可比性，不返回系数数组'),
             ('modeling.inference', ModelingRunArguments, '只读已有推理结果，不发起推理')]
    specs.append(('modeling.metrics', ModelingMetricsArguments, '只读一个或两个明确训练 run 的标量指标与每类指标；不返回矩阵'))
    specs += [('modeling.classification_infer', ClassificationInferArguments, '对明确模型和图像集合提交冻结分类推理，返回后台task_id；不要求真值'),
              ('modeling.classification_task', ClassificationTaskArguments, '查询、取消或重试明确分类后台任务，重试固定失败子集'),
              ('modeling.classification_result', ClassificationEvidenceArguments, '只读分类评价的真实指标、引用解读或双评价比较，返回metric_id，不返回大数组')]
    ready = all(value is not None for value in (training, models, inferences, versions, database, datasets, engine))
    for name, schema, description in specs:
        registry.register(name, schema, description,
                          (lambda a, n=name: service.invoke(n, a)) if ready else None)
