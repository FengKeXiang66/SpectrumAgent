"""Bind port zero, probe the bound HTTP server, then atomically announce it."""

import httpx
import structlog
import uvicorn

from backend.handshake import HandshakeError, publish, remove_if_owned, sweep_stale
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from backend.startup_mutex import StartupMutex

log = structlog.get_logger("engine")


class HandshakeServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, paths: AppPaths, identity: EngineIdentity):
        super().__init__(config)
        self.paths = paths
        self.identity = identity

    async def startup(self, sockets=None) -> None:
        # Ownership is acquired/released on the startup thread, never in main().
        with StartupMutex():
            sweep_stale(self.paths.handshake)
            await super().startup(sockets=sockets)
            if not self.started or self.should_exit:
                return
            # Read the kernel-assigned port from the bound asyncio.Server socket.
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
    # Both source/dev and frozen/release boot the same composed application.
    from spectrumagent.app import create_app

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
        try:
            remove_if_owned(paths.handshake, identity.boot_id, phase="finally")
        except HandshakeError as exc:
            log.error("engine_final_cleanup_failed", error=exc.code)
