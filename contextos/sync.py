"""Incremental sync: for each configured source, fetch everything since the last sync and upsert it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from contextos.config import Config
from contextos.sources import all_sources
from contextos.store import Store

# Re-fetch a little before the last sync so edits and late-arriving messages aren't missed.
# Upserts are idempotent, so overlap costs only a few API calls.
OVERLAP = timedelta(minutes=15)


@dataclass
class SyncReport:
    source: str
    fetched: int = 0
    new: int = 0
    error: str | None = None
    skipped: str | None = None
    warnings: list[str] = field(default_factory=list)


def sync(
    store: Store, cfg: Config, only: str | None = None, cover_from: datetime | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> list[SyncReport]:
    """Sync all configured sources. `cover_from` guarantees the window starting there is fetched."""
    reports = []
    for src in all_sources(cfg):
        if only and src.name != only:
            continue
        report = SyncReport(src.name)
        reports.append(report)
        if not src.is_configured():
            report.skipped = src.setup_hint()
            continue

        progress(f"Syncing {src.name}…")
        started = datetime.now(timezone.utc)
        last = store.last_synced(src.name)
        since = (last - OVERLAP) if last else started - timedelta(days=cfg.backfill_days)
        if cover_from and cover_from < since:
            since = cover_from

        try:
            batch = []
            for msg in src.fetch(since):
                batch.append(msg)
                if len(batch) >= 200:
                    report.new += store.upsert(batch)
                    report.fetched += len(batch)
                    batch = []
            report.new += store.upsert(batch)
            report.fetched += len(batch)
            store.set_last_synced(src.name, started)  # only advance the cursor on success
            progress(f"{src.name}: {report.new} new")
        except Exception as e:  # one broken source must not block the others
            report.error = f"{type(e).__name__}: {e}"
            progress(f"{src.name} failed: {report.error}")
        report.warnings += getattr(src, "warnings", [])
        store.log_sync(src.name, report.fetched, report.new, report.error)
    return reports
