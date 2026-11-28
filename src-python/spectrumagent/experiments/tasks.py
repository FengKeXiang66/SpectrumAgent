"""Session-owned numerical tasks with persistent receipts and cooperative cancellation."""
from copy import deepcopy
import json
from threading import Event, RLock, Thread
from time import time
from uuid import uuid4

from backend.database import connect_database
from spectrumagent.projects import worker as project_worker
from spectrumagent.data import DataError
from .conversation import CONFIRM


PHASES = ('checking', 'preparing', 'training', 'testing', 'reporting')
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}


class ExperimentTasks:
    def __init__(self, dialogue):
        self.dialogue = dialogue
        self.lock = RLock()
        self.rows = {}
        with connect_database(dialogue.database) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_task (
                task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_session(id),
                revision INTEGER NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL,
                UNIQUE(session_id, revision))''')

    @staticmethod
    def _save(db, row):
        snapshot = json.dumps({key:value for key,value in row.items() if key != 'cancel'}, ensure_ascii=False)
        db.execute('INSERT INTO experiment_task VALUES (?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE '
                   'SET status=excluded.status,snapshot=excluded.snapshot',
                   (row['task_id'], row['session_id'], row['revision'], row['status'], snapshot))

    def _persist(self, row):
        with connect_database(self.dialogue.database) as db:
            self._save(db, row)

    def recover(self):
        with connect_database(self.dialogue.database) as db:
            db.execute('BEGIN IMMEDIATE')
            for saved, in db.execute("SELECT snapshot FROM experiment_task WHERE status IN ('queued','running')").fetchall():
                row = json.loads(saved)
                row.update(status='interrupted', finished_at=time(), failed_phase=row['phase'],
                           error='EXPERIMENT_INTERRUPTED', subprogress=None)
                self._save(db, row)

    def view(self, owner, task_id):
        with self.lock:
            row = self.rows.get(task_id)
            if row is None:
                with connect_database(self.dialogue.database) as db:
                    saved = db.execute('SELECT snapshot FROM experiment_task WHERE task_id=? AND session_id=?',
                                       (task_id, owner)).fetchone()
                row = json.loads(saved[0]) if saved else None
            if row is None or row['session_id'] != owner:
                error = DataError('EXPERIMENT_TASK_NOT_FOUND', '本会话没有该实验任务记录')
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
        with connect_database(self.dialogue.database) as db:
            row = db.execute('SELECT task_id FROM experiment_task WHERE session_id=? ORDER BY rowid DESC LIMIT 1', (owner,)).fetchone()
        return row[0] if row else None

    def cancel(self, owner, task_id):
        with self.lock:
            self.view(owner, task_id)
            row = self.rows.get(task_id)
            if row and row['status'] not in TERMINAL:
                row['cancel_requested'] = True
                row['cancel'].set()
                self._persist(row)
        return self.view(owner, task_id)

    def submit(self, owner, content, turn, *, confirmation=None):
        from spectrumagent.agent.step_plan import validate_operation
        validate_operation(self.dialogue.database, owner, 'experiment')
        with self.lock:
            record = self.dialogue._read(owner)
            if (not record or not CONFIRM.fullmatch(content.strip())
                    or record['reviewed_revision'] != record['revision'] or record['review_turn'] == turn
                    or not record['review_sources_json']):
                raise DataError('EXPERIMENT_CONFIRMATION_REQUIRED', '请先核对完整实验方案，再单独回复“确认执行”')
            target = ('experiment', record['revision'], record['review_turn'])
            task_id = str(uuid4())
            row = dict(task_id=task_id, session_id=owner, revision=record['revision'],
                       status='queued', phase=None, completed_phases=[], started_at=time(), finished_at=None,
                       cancel_requested=False, cancel=Event(), experiment_id=None, error=None, failed_phase=None,
                       train_accuracy=None, test_accuracy=None, subprogress=None)
            with connect_database(self.dialogue.database) as db:
                db.execute('BEGIN IMMEDIATE')
                existing = db.execute('SELECT task_id FROM experiment_task WHERE session_id=? AND revision=?',
                                      (owner, record['revision'])).fetchone()
                if existing and confirmation is None:
                    return self.view(owner, existing[0])
                if db.execute("SELECT 1 FROM experiment_task WHERE status IN ('queued','running')").fetchone():
                    raise DataError('EXPERIMENT_BUSY', '已有数值实验正在运行，请先完成或取消该任务')
                if (self.dialogue.confirmation(owner, db) != target or
                        confirmation is not None and confirmation != target):
                    raise DataError('EXPERIMENT_CONFIRMATION_REQUIRED', '当前训练方案没有等待确认，请重新审阅。')
                self.dialogue.clear_confirmation(db, owner, 'experiment')
                self._save(db, row)
            self.rows[task_id] = row
            Thread(target=project_worker(self._work), args=(task_id, content, turn, target), daemon=True).start()
            return self.view(owner, task_id)

    def _work(self, task_id, content, turn, accepted_plan):
        row = self.rows[task_id]

        def on_detail(**details):
            with self.lock:
                if row['cancel'].is_set():
                    raise DataError('EXPERIMENT_CANCELLED', '实验已取消，已完成产物保留')
                if 'experiment_id' in details:
                    row['experiment_id'] = details['experiment_id']
                    self._persist(row)
                elif details:
                    row['subprogress'] = details

        def progress(phase):
            with self.lock:
                on_detail()
                if row['phase'] and row['phase'] != phase:
                    row['completed_phases'].append(row['phase'])
                row.update(status='running', phase=phase, subprogress=None)
                self._persist(row)
        try:
            result = self.dialogue.run_confirmed(row['session_id'], content, turn,
                         progress=progress, on_detail=on_detail, expected_revision=row['revision'], accepted_plan=accepted_plan)
            with self.lock:
                row.update(status='succeeded', finished_at=time(), completed_phases=list(PHASES), experiment_id=result['experiment_id'],
                           train_accuracy=result['metrics']['train']['accuracy'], test_accuracy=result['metrics']['test']['accuracy'])
                self._persist(row)
        except Exception as error:
            with self.lock:
                code = error.code if isinstance(error, DataError) else 'EXPERIMENT_FAILED'
                row.update(status='cancelled' if code == 'EXPERIMENT_CANCELLED' else 'failed', finished_at=time(), failed_phase=row['phase'],
                           error=code, experiment_id=error.payload.context.get('experiment_id') if isinstance(error, DataError) else None)
                self._persist(row)
