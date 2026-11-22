"""One session-owned classification worker shared by desktop and Agent callers."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import RLock, Lock, Thread, Event
from time import monotonic
from uuid import UUID, uuid4

import structlog
from backend.database import connect_database
from spectrumagent.data import DataError
from . import ModelingError
from .dataset import _inputs
from .evaluation import digest, encode, stamp
from .training_state import CURRENT, TrainingControl, TrainingCancelled


def jobs_for(registry, paths, boot_id=None):
    with registry.lock:
        service = getattr(registry, '_training_jobs', None)
        if service is None:
            from .run import TrainingRuns
            service = TrainingJobs(TrainingRuns(registry, paths), boot_id)
            registry._training_jobs = service
        return service


def code_identity():
    import importlib
    import inspect
    import marshal
    import sys
    package = Path(__file__).resolve().parents[1]
    hashes = [(str(p.relative_to(package)), hashlib.sha256(p.read_bytes()).hexdigest())
              for folder in ('modeling', 'preprocess') for p in sorted((package / folder).rglob('*.py'))]
    # Include loaded code rather than relying on Git HEAD or source files that
    # may have changed since Python imported them. Frozen PYZ has no .py files.
    for name in ('classification', 'cv', 'metrics', 'evaluation', 'inference'):
        module = importlib.import_module('spectrumagent.modeling.'+name)
        for key, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ == module.__name__:
                hashes.append((name+'.'+key, hashlib.sha256(marshal.dumps(value.__code__)).hexdigest()))
    if getattr(sys, 'frozen', False):
        value = hashlib.sha256()
        with Path(sys.executable).open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''): value.update(chunk)
        hashes.append(('loaded_engine_build', value.hexdigest()))
    return digest(hashes)


class TrainingJobs:
    def __init__(self, runs, boot_id=None):
        self.runs, self.database = runs, runs.database
        self.boot_id = boot_id or str(uuid4())
        self._code_identity = None
        self.lock, self.submission_lock = RLock(), Lock()
        self.jobs = {}
        self.log = structlog.get_logger('engine.training')

    @property
    def code_identity(self):
        # Listing historical results needs no classifier imports or source scan.
        # Freeze still computes the exact same identity before admitting training.
        with self.lock:
            if self._code_identity is None:self._code_identity=code_identity()
            return self._code_identity

    @staticmethod
    def validate_id(identifier):
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ModelingError('INVALID_TRAINING_JOB', '训练任务编号无效') from None

    def freeze(self, body, *, fixed=False):
        bound = deepcopy(body)
        bound['evaluation_protocol'] = body.get('evaluation_protocol') or 'nested_group_cv'
        rows = _inputs(self.runs.registry, cube_ids=bound['cube_ids'], annotation_version_ids=bound['annotation_version_ids'],
                       preprocess_run_ids=bound['preprocess_run_ids'], target=body.get('target', 'label'),
                       recipe_version_id=body.get('recipe_version_id'), dataset_version_ref=body.get('dataset_version_ref'))
        with connect_database(self.database) as db:
            catalog = [list(r) for r in db.execute('SELECT id,code,name,color_hex,is_background,sort_order FROM label ORDER BY sort_order,code,id')]
        binding = {'body': bound, 'code_identity': self.code_identity, 'catalog': catalog,
                   'references': [{'cube_id': r['cube_id'], 'annotation': {k:v for k,v in r['annotation'].items() if k not in {'note','created_at'}},
                                   'run_id': r['run']['id'], 'input_fingerprint': r['run']['input_fingerprint'],
                                   'pipeline': r['pipeline']} for r in rows]}
        return bound, binding

    def _saved(self, identifier, owner=None):
        with connect_database(self.database) as db:
            row = db.execute('SELECT boot_id,owner,request_key,body,binding,snapshot FROM training_job WHERE id=?', (identifier,)).fetchone()
        if not row:
            return None
        if owner is not None and row[1] != owner:
            raise ModelingError('TRAINING_SCOPE_MISMATCH', '训练任务不属于当前工作会话')
        return {'key': row[2], 'body': json.loads(row[3]), 'binding': json.loads(row[4]),
                'receipt': json.loads(row[5]), 'owner': row[1]}

    def _persist(self, snapshot):
        with connect_database(self.database) as db:
            db.execute("UPDATE training_job SET snapshot=? WHERE id=? AND json_extract(snapshot,'$.snapshot_version')<=?",
                       (encode(snapshot), snapshot['job_id'], snapshot['snapshot_version']))

    def submit(self, identifier, body, *, owner='desktop', parent=None):
        self.validate_id(identifier)
        key = digest({'body': body, 'parent': parent})
        with self.submission_lock:
            existing = self._saved(identifier, owner)
            if existing:
                if existing['key'] != key:
                    raise ModelingError('TRAINING_JOB_CONFLICT', '该任务编号已绑定其他训练参数')
                return self.status(identifier, owner=owner)
            with self.lock:
                if any(j['receipt']['status'] in ('queued', 'running') for j in self.jobs.values()):
                    raise ModelingError('TRAINING_BUSY', '已有分类训练正在运行，请等待完成')
            lease = self.runs.registry.recycle.coordinator.job()
            lease.__enter__()
            try:
                if parent:
                    prior = self._saved(parent, owner)
                    bound, binding = self.freeze(prior['binding']['body'], fixed=True)
                    if binding != prior['binding']:
                        raise ModelingError('CHECKPOINT_IDENTITY_MISMATCH', '原任务引用或算法已变化，不能继续')
                else:
                    bound, binding = self.freeze(body)
                created = monotonic()
                receipt = {'job_id': identifier, 'engine_boot_id': self.boot_id, 'status': 'queued', 'phase': 'queued',
                           'run_id': None, 'evaluation_id': None, 'error': None, 'created_at': stamp(),
                           'snapshot_version': 1, 'cancel_requested': False, 'cancelable': True,
                           'result_status': 'none', 'completed_folds': [], 'reused_folds': [],
                           'total_folds': body.get('cv_folds', 5), 'event_cursor': 0, 'eta_seconds': None,
                           'band_selection': body.get('band_selection'),
                           'cube_ids': bound['cube_ids'], 'retry_of': parent}
                with connect_database(self.database) as db:
                    db.execute('INSERT INTO training_job VALUES (?,?,?,?,?,?,?,?)',
                               (identifier, self.boot_id, owner, key, encode(body), encode(binding), encode(receipt), stamp()))
                job = {'key': key, 'owner': owner, 'body': deepcopy(body), 'binding': binding, 'receipt': receipt,
                       'cancel': Event(), 'created': created, 'started': None, 'phase_started': created,
                       'lease': lease, 'parent': parent}
                with self.lock:
                    terminal = [i for i, j in self.jobs.items() if j['receipt']['status'] not in ('queued', 'running')]
                    while len(self.jobs) >= 64 and terminal:
                        self.jobs.pop(terminal.pop(0))
                    self.jobs[identifier] = job
                Thread(target=self._work, args=(identifier, bound), name='classification-training', daemon=True).start()
            except BaseException:
                lease.__exit__(None, None, None)
                with self.lock:
                    if identifier in self.jobs:
                        receipt = self.jobs[identifier]['receipt']
                        receipt.update(status='failed', cancelable=False, finished_at=stamp(),
                                       error={'error': 'TRAINING_START_FAILED', 'detail': '未能启动训练任务', 'context': {}})
                        receipt['snapshot_version'] += 1
                        self._persist(deepcopy(receipt))
                raise
            self.log.info('training_accepted', job_id=identifier, boot_id=self.boot_id)
            return self.status(identifier, owner=owner)

    def status(self, identifier, *, owner=None):
        self.validate_id(identifier)
        with self.lock:
            job = self.jobs.get(identifier)
            if job:
                if owner is not None and job['owner'] != owner:
                    raise ModelingError('TRAINING_SCOPE_MISMATCH', '训练任务不属于当前工作会话')
                result = deepcopy(job['receipt'])
                now = monotonic()
                if result['status'] in ('queued', 'running'):
                    result['elapsed_s'] = round(now-job['created'], 3)
                    result['run_elapsed_s'] = round(now-job['started'], 3) if job['started'] else 0
                    result['phase_elapsed_s'] = round(now-job['phase_started'], 3)
                    from .training_eta import expire
                    expire(job, result)
                return result
        saved = self._saved(identifier, owner)
        if not saved:
            error = ModelingError('TRAINING_JOB_NOT_FOUND', '训练任务回执不存在，请检查结果列表')
            error.status_code = 404
            raise error
        return saved['receipt']

    def list(self, *, owner=None, limit=20):
        with connect_database(self.database) as db:
            sql = 'SELECT id FROM training_job WHERE 1=1'
            args = []
            if owner is not None:
                sql += ' AND owner=?'; args.append(owner)
            ids = [r[0] for r in db.execute(sql+' ORDER BY created_at DESC LIMIT ?', (*args, limit))]
        return {'items': [self.status(i, owner=owner) for i in ids], 'engine_boot_id': self.boot_id}

    def event(self, identifier, phase, values):
        with self.lock:
            job = self.jobs[identifier]
            receipt = job['receipt']
            if receipt['phase'] != phase:
                job['phase_started'] = monotonic()
            receipt['phase'] = phase
            receipt['snapshot_version'] += 1
            receipt['event_cursor'] += 1
            receipt['current'] = deepcopy(values)
            if phase == 'prepared': receipt['input_signature'] = values['input_signature']
            from .training_eta import observe
            try:
                observe(job, phase, values)
            except (ValueError, KeyError, TypeError, ArithmeticError):
                # ETA is advisory. An invalid timing observation cannot change a
                # scientific result or prevent cancellation/checkpoint commits.
                job.pop('eta_history', None)
                receipt.update(eta_seconds=None, stage_eta_seconds=None,
                               eta={'state':'unknown','method':'unavailable','samples':0,'scope':'whole_task'})
                self.log.warning('training_eta_unavailable', job_id=identifier)
            if phase == 'run':
                receipt['run_id'] = values['run_id']
                receipt['total_pixels'] = values['total_pixels']
            if phase == 'fold_complete':
                receipt['completed_folds'] = sorted(set(receipt['completed_folds']) | {values['outer_fold']})
                receipt['result_status'] = 'partial'
            if phase == 'baseline_complete':
                receipt['baseline_folds'] = sorted(set(receipt.get('baseline_folds', [])) | {values['outer_fold']})
            if phase in ('checkpoint', 'reused'):
                unit = values['unit']
                if unit == 'final':
                    receipt['final_ready'] = True
                elif unit.startswith('fold-'):
                    index = int(unit.split('-')[1])
                    field = 'completed_folds' if unit.endswith('-selected') else 'baseline_folds'
                    receipt[field] = sorted(set(receipt.get(field, [])) | {index})
                    receipt['result_status'] = 'partial'
                    if phase == 'reused' and unit.endswith('-selected'):
                        receipt['reused_folds'] = sorted(set(receipt['reused_folds']) | {index})
            event = {'seq': receipt['event_cursor'], 'at': stamp(), 'elapsed_s': round(monotonic()-job['created'], 3),
                     'phase': phase, **deepcopy(values)}
            snapshot = deepcopy(receipt)
            # Keep cursor and the corresponding event durable in one transaction,
            # while readers/cancellation observe the same version under this lock.
            with connect_database(self.database) as db:
                db.execute('INSERT INTO training_job_event VALUES (?,?,?)', (identifier, event['seq'], encode(event)))
                db.execute('UPDATE training_job SET snapshot=? WHERE id=?', (encode(snapshot), identifier))

    def events(self, identifier, after=0, limit=50, *, owner=None):
        if type(after) is not int or type(limit) is not int or after < 0 or not 1 <= limit <= 50:
            raise ModelingError('INVALID_PAGE', '事件分页参数非法')
        with self.lock:
            status = self.status(identifier, owner=owner)
            with connect_database(self.database) as db:
                rows = db.execute('SELECT payload FROM training_job_event WHERE job_id=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?',
                                  (identifier, after, status['event_cursor'], limit)).fetchall()
        return {'job_id': identifier, 'snapshot_version': status['snapshot_version'], 'events': [json.loads(r[0]) for r in rows],
                'cursor': json.loads(rows[-1][0])['seq'] if rows else after}

    @staticmethod
    def file_hash(path):
        from .evaluation import Evaluations
        return Evaluations.file_hash(path)

    def cancel(self, identifier, *, owner=None):
        self.status(identifier, owner=owner)
        with self.lock:
            job = self.jobs.get(identifier)
            if not job or job['receipt']['status'] not in ('queued', 'running') or not job['receipt']['cancelable']:
                return self.status(identifier, owner=owner)
            job['cancel'].set()
            job['receipt']['cancel_requested'] = True
            job['receipt']['snapshot_version'] += 1
            snapshot = deepcopy(job['receipt'])
        self._persist(snapshot)
        return self.status(identifier, owner=owner)

    def partial(self, identifier, *, owner=None):
        from .training_checkpoints import partial
        return partial(self, identifier, owner)

    def resume(self, parent, identifier, *, owner=None):
        saved = self._saved(parent, owner)
        if not saved:
            raise ModelingError('TRAINING_JOB_NOT_FOUND', '原训练任务不存在')
        if saved['receipt']['status'] not in ('failed', 'cancelled'):
            raise ModelingError('TRAINING_NOT_RESUMABLE', '仅已终止的未完成任务可继续')
        with connect_database(self.database) as db:
            count = db.execute('SELECT COUNT(*) FROM training_checkpoint WHERE job_id=?', (parent,)).fetchone()[0]
        if not count:
            raise ModelingError('NO_CHECKPOINT', '尚无可复用的完成单元，请发起新训练')
        return self.submit(identifier, saved['body'], owner=saved['owner'], parent=parent)

    def _work(self, identifier, body):
        with self.lock:
            job = self.jobs[identifier]
            job['started'] = monotonic()
            job['receipt'].update(status='running')
            job['receipt']['snapshot_version'] += 1
        control = TrainingControl(self, identifier, job['binding'], job['cancel'], job['parent'])
        token = CURRENT.set(control)
        self.log.info('training_worker_enter', job_id=identifier, boot_id=self.boot_id)
        try:
            control.emit('validation')
            _, actual = self.freeze(body, fixed=True)
            if actual != job['binding']:
                raise ModelingError('TRAINING_REFERENCE_CHANGED', '受理后的训练引用发生变化，请重新发起训练')
            result = self.runs.classify(**body)
            if result['status'] not in ('succeeded', 'failed'):
                raise ModelingError('TRAINING_INCOMPLETE', '训练返回了未完成状态')
            update = {'status': result['status'], 'run_id': result['run_id'], 'error': result.get('error'),
                      'evaluation_id': result.get('evaluation', {}).get('evaluation_id'),
                      'result_status': 'complete' if result['status'] == 'succeeded' else 'none'}
        except TrainingCancelled as error:
            update = {'status': 'cancelled', 'error': error.as_dict()}
        except ModelingError as error:
            update = {'status': 'failed', 'error': error.as_dict()}
        except DataError as error:
            update = {'status': 'failed', 'error': {'error': error.code, 'detail': '模型输入不可用', 'context': {}}}
        except Exception:
            update = {'status': 'failed', 'error': {'error': 'TRAINING_FAILED', 'detail': '后台分类训练失败，请检查输入和引擎日志', 'context': {}}}
        finally:
            CURRENT.reset(token)
        try:
            with self.lock:
                job['receipt'].update(**update, cancelable=False, eta_seconds=None, stage_eta_seconds=None, finished_at=stamp(), elapsed_s=round(monotonic()-job['created'], 3))
                job['receipt']['snapshot_version'] += 1
                snapshot = deepcopy(job['receipt'])
                self._persist(snapshot)
        finally:
            job['lease'].__exit__(None, None, None)
        self.log.info('training_worker_exit', job_id=identifier, status=update['status'], run_id=snapshot.get('run_id'))
