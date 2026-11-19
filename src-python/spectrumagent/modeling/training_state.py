"""Session-owned training context and versioned metadata; no transport or model defaults."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

from . import ModelingError

DDL = """
CREATE TABLE IF NOT EXISTS training_job (
 id TEXT PRIMARY KEY, boot_id TEXT NOT NULL, owner TEXT NOT NULL, request_key TEXT NOT NULL,
 body TEXT NOT NULL, binding TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_job_event (
 job_id TEXT NOT NULL REFERENCES training_job(id), seq INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(job_id,seq));
CREATE TABLE IF NOT EXISTS training_checkpoint (
 job_id TEXT NOT NULL REFERENCES training_job(id), unit TEXT NOT NULL, manifest TEXT NOT NULL,
 PRIMARY KEY(job_id,unit));
"""

CURRENT = ContextVar("classification_training", default=None)


class TrainingCancelled(ModelingError):
    def __init__(self):
        super().__init__("TRAINING_CANCELLED", "用户取消，指标不完整")


class TrainingControl:
    def __init__(self, service, identifier, binding, cancel, parent=None):
        self.service, self.identifier, self.binding = service, identifier, binding
        self.cancel, self.parent = cancel, parent
        self.started = monotonic()
        self.scope = {}
        self.publishing = False
        self.data = None

    def prepare(self, data, folds, protocol, threshold, support):
        from .training_checkpoints import prepare
        prepare(self, data, folds, protocol, threshold, support)
        from .training_eta import history
        try:
            history(self.service,self.identifier,self.signature)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            self.service.log.warning('training_eta_history_unavailable', job_id=self.identifier)
        self.emit('prepared', input_signature=self.signature)

    def save(self, unit, model, indices=None, probabilities=None):
        from .training_checkpoints import save
        return save(self, unit, model, indices, probabilities)

    def reuse(self, unit):
        from .training_checkpoints import reuse
        return reuse(self, unit)

    def check(self):
        if self.cancel.is_set() and not self.publishing:
            raise TrainingCancelled()

    def emit(self, phase, **values):
        self.check()
        self.service.event(self.identifier, phase, {**self.scope, **values})

    @contextmanager
    def stage(self, **scope):
        previous = self.scope
        self.scope = {**previous, **scope}
        try:
            self.check()
            yield
        finally:
            self.scope = previous

    @contextmanager
    def publish(self):
        with self.service.lock:
            self.check()
            self.publishing = True
            receipt = self.service.jobs[self.identifier]["receipt"]
            receipt['cancelable'] = False
            receipt['snapshot_version'] += 1
            self.service._persist(receipt)
        try:
            yield
        finally:
            self.publishing = False


def checkpoint():
    control = CURRENT.get()
    if control:
        control.check()


def emit(phase, **values):
    control = CURRENT.get()
    if control:
        control.emit(phase, **values)


@contextmanager
def stage(**values):
    control = CURRENT.get()
    if control:
        with control.stage(**values):
            yield
    else:
        yield
