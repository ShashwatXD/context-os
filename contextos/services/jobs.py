"""Background jobs: run work in a thread and record progress events the browser can stream (SSE)."""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from contextos.services.tasks import friendly_error

log = logging.getLogger("contextos")


@dataclass
class Job:
    id: str
    kind: str
    events: list[dict] = field(default_factory=list)
    finished: bool = False
    result: dict | None = None
    error: str | None = None
    meta: dict = field(default_factory=dict)  # e.g. the question being asked, the briefing window

    def emit(self, type_: str, **data) -> None:
        self.events.append({"type": type_, **data})


class Jobs:
    """Jobs live on the server, so a page you navigate away from can reconnect to them later."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def running(self, kind: str) -> Job | None:
        """The unfinished job of this kind, if any."""
        return next((j for j in reversed(list(self._jobs.values())) if j.kind == kind and not j.finished), None)

    def start(self, kind: str, fn: Callable[[Job], dict | None], meta: dict | None = None) -> Job:
        """Start a job. If one of the same kind is already running, return that one instead of a duplicate."""
        with self._lock:
            existing = self.running(kind)
            if existing:
                return existing
            job = Job(uuid.uuid4().hex[:12], kind, meta=meta or {})
            self._jobs[job.id] = job

        def run():
            try:
                job.result = fn(job) or {}
                job.emit("done", result=job.result)
            except Exception as e:
                log.error("job %s failed: %s", kind, traceback.format_exc())
                job.error = friendly_error(e)
                job.emit("error", text=job.error)
            finally:
                job.finished = True

        threading.Thread(target=run, daemon=True, name=f"job-{kind}").start()
        self._gc()
        return job

    def _gc(self, keep: int = 50) -> None:
        done = [j for j in self._jobs.values() if j.finished]
        for j in done[:-keep]:
            self._jobs.pop(j.id, None)
