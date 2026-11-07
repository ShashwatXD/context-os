"""Keeps ContextOS fresh without you asking: periodic sync and one morning briefing per day."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime

from contextos.config import Config, load_config
from contextos.services import tasks
from contextos.sources import all_sources
from contextos.storage import Store

log = logging.getLogger("contextos")


class Scheduler(threading.Thread):
    """Syncs every N minutes and writes the morning briefing once a day, without you asking."""

    def __init__(
        self,
        llm_factory: tasks.LLMFactory = tasks.default_llm,
        config_loader: Callable[[], Config] = load_config,
        tick_seconds: int = 30,
    ):
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

        tz = tasks.local_tz()
        local_now = datetime.fromtimestamp(now, UTC).astimezone(tz)
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
                tasks.run_refresh(cfg, self.llm_factory, "today", lambda m: log.info("briefing: %s", m))
                return "briefing"

        if now - self.last_sync_attempt >= cfg.auto_sync_minutes * 60:
            self.last_sync_attempt = now
            if tasks.RUN_LOCK.acquire(blocking=False):
                try:
                    tasks.run_sync(cfg, lambda m: log.info("sync: %s", m))
                finally:
                    tasks.RUN_LOCK.release()
                return "sync"
        return None
