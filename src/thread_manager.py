from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# SCLogger minimal interface we rely on:
# - log_message(msg, category)
# - log_fatal_error(msg, report_stack=False)


@dataclass
class RestartPolicy:
    mode: str = "never"  # "never" | "on_crash" | "always"
    max_restarts: int = 3
    backoff_seconds: float = 2.0


@dataclass
class ManagedThread:
    name: str
    target: Callable[..., Any]
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    stop_event: threading.Event = field(default_factory=threading.Event)
    logger: Any = None
    restart: RestartPolicy = field(default_factory=RestartPolicy)
    on_fatal_crash: Callable[[str], None] | None = None  # NEW: callback for unrecoverable crashes

    _thread: threading.Thread | None = field(init=False, default=None)
    _crash_event: threading.Event = field(init=False, default_factory=threading.Event)
    _start_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def start(self):
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._crash_event.clear()
            self._thread = threading.Thread(target=self._runner, name=self.name, daemon=True)
            self._thread.start()

    def _runner(self):
        restarts = 0
        while not self.stop_event.is_set():
            try:
                self.logger.log_message(f"[{self.name}] thread starting.", "debug")
                self.target(*self.args, **self.kwargs)
                # Normal exit
                self.logger and self.logger.log_message(f"[{self.name}] exited normally.", "debug")  # pyright: ignore[reportUnusedExpression]
                if self.restart.mode == "always" and not self.stop_event.is_set():
                    restarts += 1
                    if restarts > self.restart.max_restarts:
                        self.logger and self.logger.log_fatal_error(
                            f"[{self.name}] exceeded max restarts ({self.restart.max_restarts}).", report_stack=False
                        )  # pyright: ignore[reportUnusedExpression]
                        self._crash_event.set()
                        # NEW: trigger fatal crash handler
                        if self.on_fatal_crash:
                            self.on_fatal_crash(self.name)
                        break
                    time.sleep(self.restart.backoff_seconds * restarts)
                    continue
                break
            except Exception as e:  # noqa: BLE001
                self.logger and self.logger.log_message(f"[{self.name}] crashed with error: {e}", "error")  # pyright: ignore[reportUnusedExpression]
                self._crash_event.set()
                if self.restart.mode in {"on_crash", "always"}:
                    restarts += 1
                    if restarts > self.restart.max_restarts:
                        self.logger and self.logger.log_fatal_error(
                            f"[{self.name}] exceeded max restarts ({self.restart.max_restarts}).", report_stack=False
                        )  # pyright: ignore[reportUnusedExpression]
                        # NEW: trigger fatal crash handler
                        if self.on_fatal_crash:
                            self.on_fatal_crash(self.name)
                        break
                    time.sleep(self.restart.backoff_seconds * restarts)
                    continue
                # NEW: no restart policy, crash is fatal
                if self.on_fatal_crash:
                    self.on_fatal_crash(self.name)
                break

    def stop(self):
        self.stop_event.set()

    def join(self, timeout: float | None = None):
        if self._thread:
            self._thread.join(timeout=timeout)

    def crashed(self) -> bool:
        return self._crash_event.is_set()


class ThreadManager:
    def __init__(self, logger: Any, global_stop: threading.Event | None = None, exit_on_fatal: bool = True):  # NEW: exit_on_fatal parameter  # noqa: FBT001, FBT002
        self.logger = logger
        self.global_stop = global_stop or threading.Event()
        self.exit_on_fatal = exit_on_fatal  # NEW
        self._threads: list[ManagedThread] = []
        self._lock = threading.Lock()

    def add(
        self,
        name: str,
        target: Callable[..., Any],
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        restart: RestartPolicy | None = None,
        stop_event: threading.Event | None = None,
    ) -> ManagedThread:
        mt = ManagedThread(
            name=name,
            target=target,
            args=args,
            kwargs=kwargs or {},
            stop_event=stop_event or self.global_stop,
            logger=self.logger,
            restart=restart or RestartPolicy(mode="never"),
            on_fatal_crash=self._handle_fatal_crash if self.exit_on_fatal else None,  # NEW
        )
        with self._lock:
            self._threads.append(mt)
        return mt

    # NEW: fatal crash handler
    def _handle_fatal_crash(self, thread_name: str):
        """Called when a thread crashes fatally (no restart or max restarts exceeded)."""
        # Signal all threads to stop
        self.stop_all()

        # Give threads a moment to exit gracefully
        time.sleep(2.0)

        # Force exit
        self.logger.log_fatal_error(f"Thread [{thread_name}] crashed fatally. Shutting down application.", report_stack=True)
        os._exit(1)

    def start_all(self):
        """Set the stop_event for each thread."""
        with self._lock:
            for t in self._threads:
                t.start()

    def stop_all(self):
        with self._lock:
            for t in self._threads:
                t.stop()

    def join_all(self, timeout_per_thread: float = 5.0):
        with self._lock:
            for t in self._threads:
                t.join(timeout=timeout_per_thread)

    def any_crashed(self) -> bool:
        with self._lock:
            return any(t.crashed() for t in self._threads)
