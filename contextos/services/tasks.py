"""The units of work ContextOS runs: sync, write a briefing, answer a question, connect Gmail.

Used by the website (as background jobs) and by the scheduler.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING

from contextos.config import Config
from contextos.llm import LLM, LLMError
from contextos.storage import Store

if TYPE_CHECKING:
    from contextos.services.jobs import Job

# Only one sync/briefing at a time, whether started by you or by the scheduler.
RUN_LOCK = threading.Lock()

LLMFactory = Callable[[Config], LLM]


def default_llm(cfg: Config) -> LLM:
    return LLM()  # reads GEMINI_API_KEY from the environment / .env


def local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo


def window_for(kind: str, tz: tzinfo, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    if kind == "24h":
        return now - timedelta(hours=24), now
    midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC), now


def friendly_error(e: Exception) -> str:
    if isinstance(e, LLMError):
        return str(e)
    return f"{type(e).__name__}: {e}"


def run_sync(cfg: Config, progress: Callable[[str], None], cover_from: datetime | None = None) -> list:
    from contextos.services.sync import sync

    store = Store(cfg.db_path)
    try:
        return sync(store, cfg, cover_from=cover_from, progress=progress)
    finally:
        store.close()


def run_refresh(cfg: Config, llm_factory: LLMFactory, kind: str, progress: Callable[[str], None]) -> dict:
    from contextos.pipeline.digest import make_digest

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
    from contextos.pipeline.ask import ask

    store = Store(cfg.db_path)
    try:
        llm = llm_factory(cfg)

        def on_step(name: str, inp: dict) -> None:
            detail = inp.get("query") or inp.get("ref") or ""
            label = {
                "search_messages": "Searching",
                "get_thread": "Reading thread",
                "recent_activity": "Checking recent activity",
            }.get(name, name)
            job.emit("step", text=f"{label} {detail}".strip())

        result = ask(question, store, llm, cfg, local_tz(), on_step=on_step)
        ask_id = store.save_ask(
            question,
            result.answer,
            list(result.cited),
            {
                "steps": result.steps,
                "unknown_refs": result.unknown_refs,
                "llm": llm.usage_summary(),
            },
        )
        return {"ask_id": ask_id}
    finally:
        store.close()


def connect_gmail(cfg: Config, progress: Callable[[str], None]) -> dict:
    from contextos.sources.gmail import GmailSource

    progress("Opening Google sign-in in a new browser tab…")
    email = GmailSource(cfg).authorize()
    return {"email": email}
