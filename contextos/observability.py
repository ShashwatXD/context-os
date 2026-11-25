"""Traces, cost and the audit log: what ran, how long each step took, what it cost, and who asked.

    run    one briefing, one ask, one MCP call                        (trace_runs)
    span   one step inside it: triage, assemble, model call, apply   (trace_spans)
    audit  every tool call an agent made, with its arguments          (audit_log)

Spans are flat and ordered (start offset + duration), which is enough to draw a waterfall and spot the slow
step. Everything is written to the same SQLite file, so `contextos trace` and `contextos audit` work offline
and nothing leaves the machine.

Cost: model prices change often, so none are hard-coded. Set them once in .env, in USD per million tokens:
    CONTEXTOS_PRICES="gemini-3.8-flash=0.30/2.50, gemini-3.1-flash-lite=0.10/0.40"
Without prices, traces still record tokens and cost shows as unknown.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_runs (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    started_at REAL NOT NULL,
    ms         REAL,
    status     TEXT NOT NULL DEFAULT 'running',   -- running | ok | error
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_usd   REAL,
    meta       TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS trace_spans (
    id       INTEGER PRIMARY KEY,
    run_id   INTEGER NOT NULL,
    name     TEXT NOT NULL,
    start_ms REAL NOT NULL,
    ms       REAL NOT NULL,
    attrs    TEXT NOT NULL DEFAULT '{}',
    error    TEXT,
    detail   TEXT                          -- full request/response for model and tool steps (JSON)
);
CREATE INDEX IF NOT EXISTS idx_spans_run ON trace_spans(run_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY,
    at      REAL NOT NULL,
    actor   TEXT NOT NULL,                 -- mcp | ask | web
    tool    TEXT NOT NULL,
    args    TEXT NOT NULL,
    refs    TEXT NOT NULL DEFAULT '[]',    -- message tags the tool returned
    flagged TEXT NOT NULL DEFAULT '[]',    -- ...of which the guard flagged as untrusted instructions
    ok      INTEGER NOT NULL,
    ms      REAL NOT NULL
);
"""

_PRICE = re.compile(r"\s*([\w.\-]+)\s*=\s*([\d.]+)\s*/\s*([\d.]+)\s*")


def prices_from_env(value: str | None = None) -> dict[str, tuple[float, float]]:
    """'model=in/out, model2=in/out' → {model: (usd per 1M input, usd per 1M output)}."""
    value = os.environ.get("CONTEXTOS_PRICES", "") if value is None else value
    out = {}
    for part in value.split(","):
        m = _PRICE.fullmatch(part)
        if m:
            out[m[1]] = (float(m[2]), float(m[3]))
    return out


def cost(usage: dict, prices: dict[str, tuple[float, float]]) -> float | None:
    """USD for an LLM usage summary ({model: {input, output}}). None if any used model has no price."""
    total = 0.0
    for model, u in usage.items():
        if not (u.get("input") or u.get("output")):
            continue
        if model not in prices:
            return None
        p_in, p_out = prices[model]
        total += u.get("input", 0) * p_in / 1e6 + u.get("output", 0) * p_out / 1e6
    return round(total, 6)


MAX_DETAIL_CHARS = 200_000  # per text field; a busy day's prompt fits, a runaway one doesn't fill the disk


def _clip(value):
    if isinstance(value, str) and len(value) > MAX_DETAIL_CHARS:
        return value[:MAX_DETAIL_CHARS] + f"\n…[{len(value) - MAX_DETAIL_CHARS:,} more characters not stored]"
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


@dataclass
class Span:
    name: str
    start_ms: float
    ms: float = 0.0
    attrs: dict = field(default_factory=dict)
    error: str | None = None
    detail: dict | None = None  # what was sent and what came back, shown under "details" on the Traces page


class Tracer:
    """Records one run. Use `with tracer.span("triage") as s: s.attrs["kept"] = 12`."""

    def __init__(self, store=None, name: str = "run", **meta):
        self.store = store
        self.name = name
        self.meta = meta
        self.spans: list[Span] = []
        self._t0 = time.perf_counter()
        self.started_at = time.time()
        self.run_id: int | None = None
        if store is not None:
            with store.db:
                self.run_id = store.db.execute(
                    "INSERT INTO trace_runs (name, started_at, meta) VALUES (?, ?, ?)",
                    (name, self.started_at, json.dumps(meta, default=str)),
                ).lastrowid

    def _elapsed(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    @contextmanager
    def span(self, name: str, **attrs):
        s = Span(name, self._elapsed(), attrs=dict(attrs))
        try:
            yield s
        except Exception as e:
            s.error = f"{type(e).__name__}: {e}"[:300]
            raise
        finally:
            s.ms = self._elapsed() - s.start_ms
            self.spans.append(s)
            if self.store is not None and self.run_id is not None:
                with self.store.db:
                    self.store.db.execute(
                        "INSERT INTO trace_spans (run_id, name, start_ms, ms, attrs, error, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (self.run_id, s.name, round(s.start_ms, 2), round(s.ms, 2), json.dumps(s.attrs, default=str), s.error,
                         json.dumps(_clip(s.detail), default=str) if s.detail else None),
                    )

    def finish(self, usage: dict | None = None, error: str | None = None, **meta) -> None:
        usage = usage or {}
        tokens_in = sum(u.get("input", 0) for u in usage.values())
        tokens_out = sum(u.get("output", 0) for u in usage.values())
        self.meta.update(meta)
        if self.store is None or self.run_id is None:
            return
        with self.store.db:
            self.store.db.execute(
                "UPDATE trace_runs SET ms = ?, status = ?, tokens_in = ?, tokens_out = ?, cost_usd = ?, meta = ? WHERE id = ?",
                (round(self._elapsed(), 1), "error" if error else "ok", tokens_in, tokens_out,
                 cost(usage, prices_from_env()), json.dumps({**self.meta, **({"error": error} if error else {})}, default=str),
                 self.run_id),
            )


def usage_delta(before: dict, after: dict) -> dict:
    """Per-model tokens used between two LLM usage snapshots ({model: {input, output, calls}})."""
    out = {}
    for model, u in after.items():
        b = before.get(model, {})
        d = {k: u.get(k, 0) - b.get(k, 0) for k in ("input", "output", "calls")}
        if any(d.values()):
            out[model] = d
    return out


def snapshot(llm) -> dict:
    by_model = (llm.usage_summary() or {}).get("by_model", {}) if hasattr(llm, "usage_summary") else {}
    return {m: dict(u) for m, u in by_model.items()}


def runs(store, limit: int = 20) -> list[dict]:
    rows = store.db.execute("SELECT * FROM trace_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "meta": json.loads(r["meta"])} for r in rows]


def spans(store, run_id: int) -> list[dict]:
    rows = store.db.execute("SELECT * FROM trace_spans WHERE run_id = ? ORDER BY start_ms, id", (run_id,)).fetchall()
    return [{**dict(r), "attrs": json.loads(r["attrs"]), "detail": json.loads(r["detail"]) if r["detail"] else None} for r in rows]


def get_run(store, run_id: int) -> dict | None:
    r = store.db.execute("SELECT * FROM trace_runs WHERE id = ?", (run_id,)).fetchone()
    return {**dict(r), "meta": json.loads(r["meta"])} if r else None


def tokens_of(before: dict, after: dict) -> dict:
    """{'tokens_in': n, 'tokens_out': m} used between two snapshots, for a span's attrs."""
    d = usage_delta(before, after)
    return {"tokens_in": sum(u["input"] for u in d.values()), "tokens_out": sum(u["output"] for u in d.values())}


def audit(store, actor: str, tool: str, args: dict, refs: list[str], flagged: list[str], ok: bool, ms: float) -> None:
    with store.db:
        store.db.execute(
            "INSERT INTO audit_log (at, actor, tool, args, refs, flagged, ok, ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), actor, tool, json.dumps(args, default=str), json.dumps(refs), json.dumps(flagged), int(ok), round(ms, 1)),
        )


def audit_rows(store, limit: int = 50) -> list[dict]:
    rows = store.db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "args": json.loads(r["args"]), "refs": json.loads(r["refs"]), "flagged": json.loads(r["flagged"])}
            for r in rows]


__all__ = ["Tracer", "audit", "audit_rows", "cost", "get_run", "prices_from_env", "runs", "snapshot", "spans", "tokens_of",
           "usage_delta"]
