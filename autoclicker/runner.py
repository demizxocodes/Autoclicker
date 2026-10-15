"""Background thread that walks the click sequence A -> B -> C -> A ..."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Callable

from .model import ClickPoint, RunSettings

# Reasons passed to on_finish.
STOPPED = "stopped"
ROUNDS_DONE = "rounds"
TIME_UP = "time"


class ClickRunner:
    def __init__(
        self,
        points: list[ClickPoint],
        settings: RunSettings,
        click: Callable[[ClickPoint], None],
        on_progress: Callable[[int, int], None] | None = None,
        on_finish: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not points:
            raise ValueError("need at least one click point")
        # Copies, so editing the profile while running doesn't change this run.
        self._points = [replace(p) for p in points]
        self._settings = replace(settings)
        self._click = click
        self._on_progress = on_progress
        self._on_finish = on_finish
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="clicker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _wait(self, seconds: float) -> bool:
        """Sleep, returning False if stop() was called meanwhile."""
        return not self._stop.wait(seconds)

    def _run(self) -> None:
        reason = STOPPED
        try:
            reason = self._loop()
        except Exception as exc:  # report instead of dying silently
            reason = f"error: {exc}"
        finally:
            if self._on_finish:
                self._on_finish(reason)

    def _loop(self) -> str:
        settings = self._settings
        deadline = None
        if settings.mode == "time":
            deadline = self._clock() + settings.duration_seconds
        rnd = 0
        while True:
            rnd += 1
            for index, point in enumerate(self._points):
                if self._on_progress:
                    self._on_progress(rnd, index)
                wait = point.delay
                if deadline is not None:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        return TIME_UP
                    if wait >= remaining:
                        # Time runs out before this click would happen.
                        return TIME_UP if self._wait(remaining) else STOPPED
                if not self._wait(wait):
                    return STOPPED
                self._click(point)
            if settings.mode == "rounds" and rnd >= settings.rounds:
                return ROUNDS_DONE
