"""Engine-lifetime, session-owned numerical tasks with cooperative cancellation."""
from copy import deepcopy
from threading import Event, RLock, Thread
from time import time
from uuid import uuid4

from spectrumagent.data import DataError
from .conversation import CONFIRM


PHASES = ('checking', 'preparing', 'training', 'testing', 'reporting')
TERMINAL = {'succeeded', 'failed', 'cancelled'}


class ExperimentTasks:
    def __init__(self, dialogue):
        self.dialogue = dialogue
        self.lock = RLock()
        self.rows = {}
        self.submissions = {}

    def view(self, owner, task_id):
        with self.lock:
            row = self.rows.get(task_id)
            if row is None or row['session_id'] != owner:
                error = DataError('EXPERIMENT_TASK_NOT_FOUND', '本会话没有该实验任务；应用重启后旧任务不可继续操作')
                error.status_code = 404
                raise error
            result = deepcopy({key: value for key, value in row.items() if key != 'cancel'})
        result['elapsed_seconds'] = max(0, (result['finished_at'] or time()) - result['started_at'])
        return result

    def active(self, owner):
        with self.lock:
            return next((row['task_id'] for row in self.rows.values()
                         if row['session_id'] == owner and row['status'] not in TERMINAL), None)

    def latest(self, owner):
        with self.lock:
            return next((row['task_id'] for row in reversed(list(self.rows.values())) if row['session_id'] == owner), None)

    def cancel(self, owner, task_id):
        with self.lock:
            self.view(owner, task_id)
            row = self.rows[task_id]
            if row['status'] not in TERMINAL:
                row['cancel_requested'] = True
                row['cancel'].set()
        return self.view(owner, task_id)

    def submit(self, owner, content, turn):
        with self.lock:
            record = self.dialogue._read(owner)
            if (not record or not CONFIRM.fullmatch(content.strip())
                    or record['reviewed_revision'] != record['revision'] or record['review_turn'] == turn
                    or not record['review_sources_json']):
                raise DataError('EXPERIMENT_CONFIRMATION_REQUIRED', '请先核对完整实验方案，再单独回复“确认执行”')
            key = (owner, record['revision'])
            if key in self.submissions:
                return self.view(owner, self.submissions[key])
            if any(row['status'] not in TERMINAL for row in self.rows.values()):
                raise DataError('EXPERIMENT_BUSY', '已有数值实验正在运行，请先完成或取消该任务')
            task_id = str(uuid4())
            self.rows[task_id] = dict(task_id=task_id, session_id=owner, revision=record['revision'],
                status='queued', phase=None, completed_phases=[], started_at=time(), finished_at=None,
                cancel_requested=False, cancel=Event(), experiment_id=None, error=None, failed_phase=None,
                train_accuracy=None, test_accuracy=None)
            self.submissions[key] = task_id
            Thread(target=self._work, args=(task_id, content, turn), daemon=True).start()
            return self.view(owner, task_id)

    def _work(self, task_id, content, turn):
        row = self.rows[task_id]

        def progress(phase):
            with self.lock:
                if row['cancel'].is_set():
                    raise DataError('EXPERIMENT_CANCELLED', '实验已在安全阶段边界取消，已完成产物保留')
                if row['phase'] and row['phase'] != phase:
                    row['completed_phases'].append(row['phase'])
                row.update(status='running', phase=phase)
        try:
            result = self.dialogue.run_confirmed(row['session_id'], content, turn,
                         progress=progress, expected_revision=row['revision'])
            with self.lock:
                row.update(status='succeeded', completed_phases=list(PHASES), experiment_id=result['experiment_id'],
                           train_accuracy=result['metrics']['train']['accuracy'], test_accuracy=result['metrics']['test']['accuracy'])
        except Exception as error:
            with self.lock:
                code = error.code if isinstance(error, DataError) else 'EXPERIMENT_FAILED'
                row.update(status='cancelled' if code == 'EXPERIMENT_CANCELLED' else 'failed', failed_phase=row['phase'],
                           error=code, experiment_id=error.payload.context.get('experiment_id') if isinstance(error, DataError) else None)
        finally:
            with self.lock:
                row['finished_at'] = time()
