"""Cooperative request cancellation; execution results are never rolled back."""
import asyncio
from threading import Event, Lock


NUMERICAL_RUNS = frozenset({
    'workspace.classify','modeling.classify','modeling.regress',
    'modeling.infer','modeling.classification_infer',
})


def numerical_confirmation(call):
    if call['name'] not in NUMERICAL_RUNS:
        return None
    arguments = call['arguments']
    summary = {key:arguments[key] for key in ('model_id','n_components','max_components','cv_folds',
                                             'outer_folds','evaluation_protocol','target_schema_id')
               if arguments.get(key) is not None}
    for key in ('cube_ids','preprocess_run_ids'):
        if isinstance(arguments.get(key),list):
            summary[key+'_count'] = len(arguments[key])
    return summary


class RequestCancelled(BaseException):
    """Must bypass generic model/tool error handlers."""


class RequestControl:
    def __init__(self, request_id):
        self.request_id = request_id
        self.cancelled = Event()
        self.lock = Lock()
        self.phase = 'starting'

    def cancel(self):
        with self.lock:
            self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise RequestCancelled()

    def begin(self, phase):
        # Cancellation and admission to the next operation share one boundary.
        with self.lock:
            self.check()
            self.phase = phase

    async def wait_for(self, operation):
        """Cancel and await the HTTP task so its connection closes before release."""
        task = asyncio.create_task(operation)
        try:
            self.check()
            while not task.done():
                await asyncio.wait({task}, timeout=0.05)
                self.check()
            self.check()
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
