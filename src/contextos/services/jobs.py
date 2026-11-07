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

    def emit(self, type_: str, **data) -> None:
        self.events.append({"type": type_, **data})


class Jobs:
    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def start(self, kind: str, fn: Callable[[Job], dict | None]) -> Job:
        job = Job(uuid.uuid4().hex[:12], kind)
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
