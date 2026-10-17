"""Bind port zero, probe the bound HTTP server, then atomically announce it."""

import httpx
import structlog
import uvicorn

from backend.app import create_app
from backend.handshake import publish, remove_if_owned
from backend.identity import EngineIdentity
from backend.paths import AppPaths

log = structlog.get_logger("engine")


class HandshakeServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, paths: AppPaths, identity: EngineIdentity):
        super().__init__(config)
        self.paths = paths
        self.identity = identity

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets=sockets)
        if not self.started or self.should_exit:
            return
        # uvicorn 0.54 exposes asyncio.Server objects in self.servers.
        # The actual kernel-assigned port comes from server.sockets, never a port probe.
        server = self.servers[0]
        port = int(server.sockets[0].getsockname()[1])
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            response = await client.get(f"http://127.0.0.1:{port}/health")
            response.raise_for_status()
            if response.json()["boot_id"] != self.identity.boot_id:
                raise RuntimeError("Startup health identity mismatch")
        publish(self.paths.handshake, self.identity.handshake(port))
        log.info("engine_ready", boot_id=self.identity.boot_id, pid=self.identity.pid, port=port)


def main(paths: AppPaths) -> None:
    identity = EngineIdentity()
    structlog.contextvars.bind_contextvars(boot_id=identity.boot_id, pid=identity.pid)
    app = create_app(paths, identity)
    server = HandshakeServer(
        uvicorn.Config(
            app, host="127.0.0.1", port=0, workers=1,
            log_config=None, access_log=True, timeout_graceful_shutdown=5,
        ),
        paths, identity,
    )
    try:
        server.run()
    finally:
        remove_if_owned(paths.handshake, identity.boot_id)
        log.info("engine_stopped")
