"""Read-only browser for everything ContextOS stores: what each table is, its rows, and how rows connect.

Table and column names come only from SQLite's own schema (never from the request), and every value is a
bound parameter, so the filters can't be turned into arbitrary SQL. Nothing here writes to the database.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, tzinfo

import numpy as np

from contextos.storage import Store

# What each table is for, in the order of the pipeline. Tables not listed here (SQLite internals, the FTS
# index's shadow tables) are not shown.
TABLES: dict[str, dict] = {
    "messages": {"group": "Messages", "what": "One email or chat message, normalized from any source, with its tags.",
                 "written": "1 Collect, 2 Prepare", "time": "ts", "quick": ["source", "intent", "channel"]},
    "embeddings": {"group": "Messages",
                   "what": "The meaning vector of one message (768 float32 numbers, ~3 KB). Keyed by the message's rid.",
                   "written": "2 Prepare", "quick": ["model"]},
    "identities": {"group": "People", "what": "One person, under the display name ContextOS picked for them.",
                   "written": "2 Prepare"},
    "identity_aliases": {"group": "People", "what": "One name or account a person uses in one app, linked to their identity.",
                         "written": "2 Prepare", "quick": ["source"]},
    "identity_overrides": {"group": "People", "what": "A merge or split you made by hand. Always wins over the rules.",
                           "written": "you", "quick": ["action"]},
    "loops": {"group": "Memory", "what": "One open loop: something you owe, or something you're waiting on, with its evidence.",
              "written": "5 Check & serve", "time": "opened_at", "quick": ["status", "kind"]},
    "digests": {"group": "Memory", "what": "One briefing as JSON, with the messages it covered and its stats.",
                "written": "5 Check & serve", "time": "created_at"},
    "item_actions": {"group": "Memory", "what": "Done, Snooze or Reopen you pressed on a briefing item.",
                     "written": "you", "time": "created_at", "quick": ["action"]},
    "feedback": {"group": "Memory", "what": "A 👍 / 👎 vote or a 'you missed this' note. Raw material for evals.",
                 "written": "you", "time": "created_at"},
    "asks": {"group": "Memory", "what": "One question from the Ask page, its answer and citations.",
             "written": "5 Check & serve", "time": "created_at"},
    "trace_runs": {"group": "Observability", "what": "One briefing or question run: total time, tokens, cost, status.",
                   "written": "4 Think, 5 Check & serve", "time": "started_at", "quick": ["name", "status"]},
    "trace_spans": {"group": "Observability",
                    "what": "One step inside a run: timing, facts, and the exact prompt and output for model steps.",
                    "written": "4 Think, 5 Check & serve", "quick": ["name"]},
    "audit_log": {"group": "Observability",
                  "what": "One tool call an AI agent made, the messages it got back, and which were flagged.",
                  "written": "5 Check & serve", "time": "at", "quick": ["actor", "tool"]},
    "sync_state": {"group": "Sync", "what": "When each source was last synced successfully.", "written": "1 Collect"},
    "sync_log": {"group": "Sync", "what": "One sync attempt per source: fetched, new, error.", "written": "1 Collect",
                 "time": "at", "quick": ["source"]},
}
GROUPS = ["Messages", "People", "Memory", "Observability", "Sync"]

TIME_COLUMNS = {"ts", "at", "created_at", "opened_at", "updated_at", "closed_at", "started_at", "last_synced_at",
                "window_start", "window_end", "until", "promised_at"}
JSON_COLUMNS = {"labels", "refs", "threads", "output", "meta", "message_rids", "args", "flagged", "attrs", "detail", "item"}
PAGE = 50
CELL_CHARS = 90


def _check_table(name: str) -> str:
    if name not in TABLES:
        raise KeyError(name)
    return name


def columns(store: Store, table: str) -> list[dict]:
    """[{name, type}] straight from SQLite's schema for this table."""
    rows = store.db.execute(f"PRAGMA table_info({_check_table(table)})")
    return [{"name": r["name"], "type": (r["type"] or "").upper()} for r in rows]


def overview(store: Store) -> list[dict]:
    out = []
    for group in GROUPS:
        tables = []
        for name, info in TABLES.items():
            if info["group"] != group:
                continue
            count = store.db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            tables.append({"name": name, "count": count, "columns": [c["name"] for c in columns(store, name)], **info})
        out.append({"group": group, "tables": tables})
    return out


def db_size(store: Store) -> int:
    pages = store.db.execute("PRAGMA page_count").fetchone()[0]
    size = store.db.execute("PRAGMA page_size").fetchone()[0]
    return pages * size


# ---- formatting -------------------------------------------------------------


def fmt_time(value, tz: tzinfo) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz).strftime("%d %b %Y %H:%M")
    except (TypeError, ValueError, OSError):
        return str(value)


def vector_info(blob: bytes) -> dict:
    v = np.frombuffer(blob, dtype=np.float32)
    head = v[:48]
    peak = float(np.abs(head).max()) or 1.0
    return {
        "dims": int(v.size),
        "bytes": len(blob),
        "norm": round(float(np.linalg.norm(v)), 4),
        "first": [round(float(x), 4) for x in v[:8]],
        "bars": [round(float(x) / peak * 100, 1) for x in head],
    }


def cell(col: str, value, tz: tzinfo) -> dict:
    """How one value shows in the table: text, a kind for styling, and the full value for a tooltip."""
    if value is None:
        return {"text": "", "kind": "null"}
    if isinstance(value, bytes):
        try:
            info = vector_info(value)
            return {"text": f"vector · {info['dims']} dims · {info['bytes']:,} B", "kind": "blob"}
        except ValueError:
            return {"text": f"blob · {len(value):,} B", "kind": "blob"}
    if col in TIME_COLUMNS and isinstance(value, int | float):
        return {"text": fmt_time(value, tz), "kind": "time", "full": str(value)}
    text = str(value)
    is_json = False
    if col in JSON_COLUMNS:
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False)
            is_json = True
        except (TypeError, ValueError):
            pass
    short = text if len(text) <= CELL_CHARS else text[:CELL_CHARS] + "…"
    kind = "num" if isinstance(value, int | float) else ("json" if is_json else "text")
    return {"text": short, "kind": kind, "full": text if short != text else None}


def full_value(col: str, value, tz: tzinfo) -> dict:
    if value is None:
        return {"kind": "null", "text": "NULL"}
    if isinstance(value, bytes):
        try:
            return {"kind": "vector", **vector_info(value)}
        except ValueError:
            return {"kind": "text", "text": f"<{len(value):,} bytes>"}
    if col in TIME_COLUMNS and isinstance(value, int | float):
        return {"kind": "time", "text": fmt_time(value, tz), "raw": value}
    if col in JSON_COLUMNS:
        try:
            return {"kind": "json", "text": json.dumps(json.loads(value), indent=2, ensure_ascii=False)}
        except (TypeError, ValueError):
            pass
    return {"kind": "text", "text": str(value)}


# ---- browsing ---------------------------------------------------------------


def parse_date(value: str | None, tz: tzinfo, end: bool = False) -> float | None:
    if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    day = datetime.fromisoformat(value).replace(tzinfo=tz)
    return day.timestamp() + (86400 if end else 0)


def browse(store: Store, table: str, params: dict, tz: tzinfo) -> dict:
    """One page of rows with filters applied. `params` is the raw query string."""
    info = TABLES[_check_table(table)]
    cols = columns(store, table)
    names = [c["name"] for c in cols]
    text_cols = [c["name"] for c in cols if c["type"] in ("TEXT", "") and c["name"] in names]
    where, args = [], []

    q = (params.get("q") or "").strip()
    if q:
        where.append("(" + " OR ".join(f"CAST({c} AS TEXT) LIKE ?" for c in text_cols) + ")")
        args += [f"%{q}%"] * len(text_cols)

    quick_values = {}
    for col in info.get("quick", []):
        if col not in names:
            continue
        rows = store.db.execute(f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 40").fetchall()
        quick_values[col] = [(r[0], r[1]) for r in rows if r[0] is not None]
        value = params.get(f"qf_{col}")
        if value:
            where.append(f"{col} = ?")
            args.append(value)

    col, op, val = params.get("f_col"), params.get("f_op", "contains"), params.get("f_val", "")
    if col in names and val != "":
        if op == "eq":
            where.append(f"CAST({col} AS TEXT) = ?")
            args.append(val)
        else:
            where.append(f"CAST({col} AS TEXT) LIKE ?")
            args.append(f"%{val}%")

    if table == "messages" and params.get("flagged"):
        where.append("COALESCE(risk, '') != ''")

    time_col = info.get("time")
    after, before = parse_date(params.get("after"), tz), parse_date(params.get("before"), tz, end=True)
    if time_col and after is not None:
        where.append(f"{time_col} >= ?")
        args.append(after)
    if time_col and before is not None:
        where.append(f"{time_col} < ?")
        args.append(before)

    sort = params.get("sort") if params.get("sort") in names else (time_col or "rowid")
    direction = "ASC" if params.get("dir") == "asc" else "DESC"
    page = max(1, int(params.get("page") or 1)) if str(params.get("page") or "1").isdigit() else 1
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = store.db.execute(f"SELECT COUNT(*) FROM {table}{clause}", args).fetchone()[0]
    rows = store.db.execute(
        f"SELECT rowid AS _rowid_, * FROM {table}{clause} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
        [*args, PAGE, (page - 1) * PAGE],
    ).fetchall()
    return {
        "table": table,
        "info": info,
        "columns": cols,
        "rows": [{"rowid": r["_rowid_"], "cells": [cell(n, r[n], tz) for n in names]} for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PAGE)),
        "sort": sort,
        "dir": direction.lower(),
        "quick": quick_values,
        "time_col": time_col,
        "params": params,
    }


# ---- one row and what it links to ---------------------------------------------


def _rows(store: Store, table: str, sql_where: str, args: list, limit: int = 20) -> dict:
    rows = store.db.execute(f"SELECT rowid AS _rowid_, * FROM {table} WHERE {sql_where} LIMIT ?", [*args, limit]).fetchall()
    return {"table": table, "rows": rows}


def _refs(value) -> list[int]:
    try:
        return [int(r[1:]) for r in json.loads(value or "[]") if re.fullmatch(r"m\d+", str(r))]
    except (TypeError, ValueError):
        return []


def related(store: Store, table: str, row) -> list[dict]:
    """Rows in other tables that point at this one, or that this one points at."""
    out: list[tuple[str, dict]] = []

    def add(label: str, t: str, where: str, args: list) -> None:
        found = _rows(store, t, where, args)
        if found["rows"]:
            out.append((label, found))

    def messages_by_rid(label: str, rids: list[int]) -> None:
        if rids:
            add(label, "messages", f"rid IN ({','.join('?' * len(rids))})", rids)

    if table == "messages":
        add("Its embedding", "embeddings", "rid = ?", [row["rid"]])
        add("Loops that cite it", "loops", "refs LIKE ?", [f'%"m{row["rid"]}"%'])
        add("Its author's identity link", "identity_aliases", "source = ? AND author = ?", [row["source"], row["author"]])
        if row["thread_id"]:
            add("Same thread", "messages", "thread_id = ? AND rid != ?", [row["thread_id"], row["rid"]])
    elif table == "embeddings":
        messages_by_rid("The message", [row["rid"]])
    elif table in ("loops", "asks", "audit_log"):
        messages_by_rid("Evidence messages" if table == "loops" else "Messages it returned or cited", _refs(row["refs"]))
    elif table == "identities":
        add("Names and accounts", "identity_aliases", "identity_id = ?", [row["id"]])
    elif table == "identity_aliases":
        add("Identity", "identities", "id = ?", [row["identity_id"]])
        add("Other names of this person", "identity_aliases", "identity_id = ? AND NOT (source = ? AND author = ?)",
            [row["identity_id"], row["source"], row["author"]])
        add("Messages", "messages", "source = ? AND author = ?", [row["source"], row["author"]])
    elif table == "trace_runs":
        add("Steps", "trace_spans", "run_id = ?", [row["id"]])
    elif table == "trace_spans":
        add("Run", "trace_runs", "id = ?", [row["run_id"]])
    elif table == "digests":
        messages_by_rid("Messages it covered", json.loads(row["message_rids"] or "[]")[:20])
        add("Actions on its items", "item_actions", "digest_id = ?", [row["id"]])
    return [{"label": label, **found} for label, found in out]


def row_detail(store: Store, table: str, rowid: int, tz: tzinfo) -> dict | None:
    _check_table(table)
    row = store.db.execute(f"SELECT rowid AS _rowid_, * FROM {table} WHERE rowid = ?", (rowid,)).fetchone()
    if row is None:
        return None
    names = [c["name"] for c in columns(store, table)]
    links = []
    if table == "trace_runs":
        links.append(("Open on the Traces page", f"/traces/{row['id']}"))
    if table == "digests":
        links.append(("Open this briefing", f"/digest/{row['id']}"))
    if table == "messages" and row["url"]:
        links.append(("Open the original message", row["url"]))
    groups = []
    for g in related(store, table, row):
        g_names = [c["name"] for c in columns(store, g["table"])][:6]
        groups.append({
            "label": g["label"],
            "table": g["table"],
            "columns": g_names,
            "rows": [{"rowid": r["_rowid_"], "cells": [cell(n, r[n], tz) for n in g_names]} for r in g["rows"]],
        })
    return {
        "table": table,
        "rowid": rowid,
        "info": TABLES[table],
        "fields": [{"name": n, **full_value(n, row[n], tz)} for n in names],
        "links": links,
        "related": groups,
    }
