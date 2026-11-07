"""Work the website runs in the background: refresh the briefing, answer questions, keep sources synced.

Each piece of work is a Job running in a thread. It emits events ("Syncing gmail…", "Writing your
briefing…"); the browser streams them live via server-sent events.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Callable

import anthropic

from contextos.config import Config, load_config
from contextos.llm import LLM, LLMError
from contextos.sources import all_sources
from contextos.store import Store

log = logging.getLogger("contextos")

# Only one sync/briefing at a time, whether started by you or by the scheduler.
RUN_LOCK = threading.Lock()

LLMFactory = Callable[[Config], LLM]


def default_llm(cfg: Config) -> LLM:
    return LLM(api_key=cfg.anthropic_api_key or None)


def local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo


def window_for(kind: str, tz: tzinfo, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    if kind == "24h":
        return now - timedelta(hours=24), now
    midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc), now


def friendly_error(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError) or (isinstance(e, TypeError) and "authentication" in str(e)):
        return "No valid Anthropic API key. Add one in Settings."
    if isinstance(e, anthropic.RateLimitError):
        return "Claude rate limit hit. Try again in a minute."
    if isinstance(e, (LLMError, anthropic.APIError)):
        return f"Claude call failed: {e}"
    return f"{type(e).__name__}: {e}"


# ---- jobs -------------------------------------------------------------------


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


# ---- work -------------------------------------------------------------------


def run_sync(cfg: Config, progress: Callable[[str], None], cover_from: datetime | None = None) -> list:
    from contextos.sync import sync

    store = Store(cfg.db_path)
    try:
        return sync(store, cfg, cover_from=cover_from, progress=progress)
    finally:
        store.close()


def run_refresh(cfg: Config, llm_factory: LLMFactory, kind: str, progress: Callable[[str], None]) -> dict:
    from contextos.digest import make_digest

    tz = local_tz()
    start, end = window_for(kind, tz)
    if not RUN_LOCK.acquire(blocking=False):
        progress("Waiting for the background sync to finish…")
        RUN_LOCK.acquire()
    try:
        run_sync(cfg, progress, cover_from=start)
        store = Store(cfg.db_path)
        try:
            llm = llm_factory(cfg)
            d = make_digest(store, llm, cfg, start, end, tz, progress=progress)
        finally:
            store.close()
    finally:
        RUN_LOCK.release()
    if d.empty:
        return {"digest_id": None, "empty": True}
    return {"digest_id": d.digest_id}


def run_ask(cfg: Config, llm_factory: LLMFactory, question: str, job: Job) -> dict:
    from contextos.ask import ask

    store = Store(cfg.db_path)
    try:
        llm = llm_factory(cfg)

        def on_step(name: str, inp: dict) -> None:
            detail = inp.get("query") or inp.get("ref") or ""
            label = {"search_messages": "Searching", "get_thread": "Reading thread",
                     "recent_activity": "Checking recent activity"}.get(name, name)
            job.emit("step", text=f"{label} {detail}".strip())

        result = ask(question, store, llm, cfg, local_tz(), on_step=on_step)
        ask_id = store.save_ask(question, result.answer, list(result.cited), {
            "steps": result.steps, "unknown_refs": result.unknown_refs, "llm": llm.usage_summary(),
        })
        return {"ask_id": ask_id}
    finally:
        store.close()


def connect_gmail(cfg: Config, progress: Callable[[str], None]) -> dict:
    from contextos.sources.gmail import GmailSource

    progress("Opening Google sign-in in a new browser tab…")
    email = GmailSource(cfg).authorize()
    return {"email": email}


# ---- scheduler --------------------------------------------------------------


class Scheduler(threading.Thread):
    """Syncs every N minutes and writes the morning briefing once a day, without you asking."""

    def __init__(self, llm_factory: LLMFactory = default_llm, config_loader: Callable[[], Config] = load_config,
                 tick_seconds: int = 30):
        super().__init__(daemon=True, name="scheduler")
        self.llm_factory = llm_factory
        self.config_loader = config_loader
        self.tick_seconds = tick_seconds
        self.stop = threading.Event()
        self.last_sync_attempt = 0.0
        self.last_brief_attempt = 0.0

    def run(self) -> None:
        while not self.stop.wait(self.tick_seconds):
            try:
                self.tick()
            except Exception:
                log.error("scheduler tick failed: %s", traceback.format_exc())

    def tick(self, now: float | None = None) -> str | None:
        now = now or time.time()
        cfg = self.config_loader()
        if not any(s.is_configured() for s in all_sources(cfg)):
            return None

        tz = local_tz()
        local_now = datetime.fromtimestamp(now, timezone.utc).astimezone(tz)
        midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Morning briefing: once per day after morning_hour, retried at most hourly on failure.
        if cfg.has_api_key and local_now.hour >= cfg.morning_hour and now - self.last_brief_attempt > 3600:
            store = Store(cfg.db_path)
            try:
                have_today = store.latest_digest(created_since=midnight) is not None
            finally:
                store.close()
            if not have_today:
                self.last_brief_attempt = now
                self.last_sync_attempt = now
                run_refresh(cfg, self.llm_factory, "today", lambda m: log.info("briefing: %s", m))
                return "briefing"

        if now - self.last_sync_attempt >= cfg.auto_sync_minutes * 60:
            self.last_sync_attempt = now
            if RUN_LOCK.acquire(blocking=False):
                try:
                    run_sync(cfg, lambda m: log.info("sync: %s", m))
                finally:
                    RUN_LOCK.release()
                return "sync"
        return None
