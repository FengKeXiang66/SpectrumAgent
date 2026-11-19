"""Cooperative request cancellation; execution results are never rolled back."""
import asyncio
from threading import Event, Lock


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
