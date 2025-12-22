"""Web application module for the PowerController project.

This module hosts the web UI and WebSocket API.

- HTTP: serves the Jinja2-rendered index page and static assets
- WS: pushes full state snapshots to all connected clients
- WS: accepts commands (e.g. set_mode) from clients
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from org_enums import AppMode
from starlette.templating import Jinja2Templates

from local_enumerations import Command

if TYPE_CHECKING:
    from threading import Event

    from sc_utility import SCConfigManager, SCLogger

    from controller import PowerController


def _get_repo_root() -> Path:
    # src/webapp.py -> repo_root
    return Path(__file__).resolve().parent.parent


def _validate_access_key(config: SCConfigManager, logger: SCLogger, key_from_request: str | None) -> bool:
    expected_key = os.environ.get("WEBAPP_ACCESS_KEY")
    if not expected_key:
        expected_key = config.get("Website", "AccessKey")
    if expected_key is None:
        return True
    if isinstance(expected_key, str) and not expected_key.strip():
        # Current behavior: empty AccessKey means open access.
        return True

    if key_from_request is None:
        logger.log_message("Missing access key.", "warning")
        return False
    key = key_from_request.strip()
    if not key:
        logger.log_message("Blank access key used.", "warning")
        return False
    if key != expected_key:
        logger.log_message("Invalid access key used.", "warning")
        return False
    return True


def _sanitize_mode(mode: Any) -> str | None:
    if not isinstance(mode, str):
        return None
    mode_s = mode.strip().lower()
    valid_modes = {m.value for m in AppMode}
    return mode_s if mode_s in valid_modes else None


@dataclass
class WebAppNotifier:
    """Thread-safe notifier used by PowerController to trigger WS broadcasts."""

    loop: asyncio.AbstractEventLoop | None = None
    queue: asyncio.Queue[None] | None = None

    def bind(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[None]) -> None:
        self.loop = loop
        self.queue = queue

    def notify(self) -> None:
        loop = self.loop
        queue = self.queue
        if loop is None or queue is None:
            return

        def _enqueue() -> None:
            # If we're already backed up, a later snapshot will catch up.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

        loop.call_soon_threadsafe(_enqueue)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast_json(self, message: dict[str, Any]) -> None:
        text = json.dumps(message)
        async with self._lock:
            targets = list(self._connections)

        for ws in targets:
            try:
                await ws.send_text(text)
            except (RuntimeError, WebSocketDisconnect):
                await self.disconnect(ws)


def _configure_app_state(
    app: FastAPI,
    controller: PowerController,
    config: SCConfigManager,
    logger: SCLogger,
    templates: Jinja2Templates,
    notifier: WebAppNotifier,
    manager: ConnectionManager,
) -> None:
    app.state.notifier = notifier
    app.state.manager = manager
    app.state.controller = controller
    app.state.config = config
    app.state.logger = logger
    app.state.templates = templates
    app.state.update_queue = asyncio.Queue(maxsize=100)
    app.state.broadcast_task = None


def _register_routes(app: FastAPI, controller: PowerController, config: SCConfigManager, logger: SCLogger, templates: Jinja2Templates, manager: ConnectionManager, notifier: WebAppNotifier) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        key = request.query_params.get("key")
        if not _validate_access_key(config, logger, key):
            return HTMLResponse("Access forbidden.", status_code=403)

        snapshot = await asyncio.to_thread(controller.get_webapp_data)
        if not snapshot:
            logger.log_message("No web output data available yet", "warning")
            return HTMLResponse("no output data available yet", status_code=503)

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "global_data": snapshot.get("global", {}),
                "outputs": snapshot.get("outputs", {}),
            },
        )

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        key = ws.query_params.get("key")
        if not _validate_access_key(config, logger, key):
            await ws.close(code=1008)
            return

        await manager.connect(ws)
        try:
            # Send initial snapshot
            snapshot = await asyncio.to_thread(controller.get_webapp_data)
            await ws.send_text(json.dumps({"type": "state_update", "state": snapshot}))

            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if msg.get("type") != "command":
                    continue

                action = msg.get("action")
                if action == "set_mode":
                    output_id = msg.get("output_id")
                    mode = _sanitize_mode(msg.get("mode"))
                    revert_time_mins = msg.get("revert_time_mins")
                    if not isinstance(output_id, str) or not controller.is_valid_output_id(output_id) or not mode:
                        # Ignore invalid commands; client will self-correct on next snapshot
                        continue
                    controller.post_command(Command("set_mode", {"output_id": output_id, "mode": mode, "revert_time_mins": revert_time_mins}))
                    notifier.notify()
        except WebSocketDisconnect:
            await manager.disconnect(ws)
        except RuntimeError:
            await manager.disconnect(ws)


def create_asgi_app(controller: PowerController, config: SCConfigManager, logger: SCLogger) -> tuple[FastAPI, WebAppNotifier]:
    repo_root = _get_repo_root()
    templates = Jinja2Templates(directory=str(repo_root / "templates"))
    notifier = WebAppNotifier()
    manager = ConnectionManager()

    app = FastAPI()

    # Serve static assets at /static
    app.mount("/static", StaticFiles(directory=str(repo_root / "static")), name="static")

    _configure_app_state(app, controller, config, logger, templates, notifier, manager)
    _register_routes(app, controller, config, logger, templates, manager, notifier)

    @app.on_event("startup")
    def _startup() -> None:
        loop = asyncio.get_running_loop()
        notifier.bind(loop, app.state.update_queue)

        async def _broadcast_worker() -> None:
            try:
                while True:
                    await app.state.update_queue.get()
                    # Coalesce bursts into a single snapshot
                    while True:
                        try:
                            app.state.update_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                    snapshot = await asyncio.to_thread(controller.get_webapp_data)
                    await manager.broadcast_json({"type": "state_update", "state": snapshot})
            except asyncio.CancelledError:
                # Expected during shutdown.
                return

        app.state.broadcast_task = loop.create_task(_broadcast_worker())

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = app.state.broadcast_task
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return app, notifier


def serve_asgi_blocking(app: FastAPI, config: SCConfigManager, logger: SCLogger, stop_event: Event):
    """Run an ASGI server in the current thread with cooperative shutdown using stop_event."""
    host_raw = config.get("Website", "HostingIP", default="127.0.0.1")
    host = host_raw if isinstance(host_raw, str) and host_raw else "127.0.0.1"
    port = int(config.get("Website", "Port", default=8080) or 8080)  # pyright: ignore[reportArgumentType]

    # Uvicorn log config can be noisy; keep our SCLogger as the source of truth.
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="warning", reload=False)
    server = uvicorn.Server(uv_config)
    # Running under ThreadManager in a non-main thread: avoid installing signal handlers.
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    async def _run() -> None:
        async def _stop_watcher() -> None:
            # Block in a worker thread until the threading.Event is set.
            await asyncio.to_thread(stop_event.wait)
            server.should_exit = True

        watcher = asyncio.create_task(_stop_watcher())
        try:
            logger.log_message(f"Web server listening on http://{host}:{port}", "summary")
            await server.serve()
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            logger.log_message("Web server shutdown complete.", "detailed")

    try:
        asyncio.run(_run())
    except asyncio.CancelledError:
        # Can occur if background tasks are cancelled during interpreter shutdown.
        logger.log_message("Web server cancelled during shutdown.", "debug")
