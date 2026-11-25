"""ContextOS command line. The website is the main way to use it; these are handy for debugging.

contextos web               start the website on http://localhost:8000
contextos auth gmail        one-time Google login
contextos sync              pull new messages from every configured source
contextos today             sync, then print today's briefing
contextos ask "question"    search my messages and answer
contextos people            who is the same person across apps (merge / split by hand)
contextos trace [id]        timings, tokens and cost of recent runs
contextos audit             tool calls agents made, and anything the guard flagged
contextos status            what's configured and stored
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta

from rich.console import Console

from contextos.config import load_config
from contextos.storage import Store

console = Console()


def _local_tz():
    return datetime.now().astimezone().tzinfo


def _require_llm():
    from contextos.llm import LLM, LLMError

    try:
        return LLM()
    except LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


def _llm_failed(e: Exception) -> None:
    console.print(f"[red]{e}[/red]")
    sys.exit(1)


def cmd_auth(args, cfg, store):
    from contextos.sources.gmail import AuthRequired, GmailSource

    if args.source != "gmail":
        console.print(f"{args.source} uses a token from .env; no login step needed.")
        return
    try:
        email = GmailSource(cfg).authorize()
    except AuthRequired as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(f"[green]Gmail connected as {email}.[/green] Token saved to {cfg.gmail_token}")


def cmd_sync(args, cfg, store, cover_from=None):
    from contextos.cli.render import print_sync
    from contextos.services.sync import sync

    with console.status("Syncing…"):
        reports = sync(store, cfg, only=getattr(args, "source", None), cover_from=cover_from)
    print_sync(console, reports)
    if all(r.skipped for r in reports):
        console.print("[yellow]No sources are set up yet. See README → Setup.[/yellow]")


def cmd_today(args, cfg, store):
    from contextos.cli.render import print_digest
    from contextos.llm import LLMError
    from contextos.pipeline.digest import make_digest

    tz = _local_tz()
    end = datetime.now(UTC)
    if args.hours:
        start = end - timedelta(hours=args.hours)
    else:
        start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    if not args.no_sync:
        cmd_sync(args, cfg, store, cover_from=start)

    llm = _require_llm()
    try:
        with console.status(f"Reading your messages with {cfg.main_model}…"):
            d = make_digest(store, llm, cfg, start, end, tz)
    except LLMError as e:
        _llm_failed(e)

    if args.json:
        print(json.dumps(d.output, indent=2))
    else:
        print_digest(console, d, llm, tz)


def cmd_ask(args, cfg, store):
    from contextos.cli.render import print_answer
    from contextos.llm import LLMError
    from contextos.pipeline.ask import ask

    if not args.no_sync:
        cmd_sync(args, cfg, store)
    if not store.counts():
        console.print("No messages stored yet. Set up a source and run `contextos sync` first (see README).")
        return
    tz = _local_tz()
    llm = _require_llm()

    def on_step(name, inp):
        detail = inp.get("query") or inp.get("ref") or ""
        console.print(f"[dim]  → {name} {detail}[/dim]")

    try:
        result = ask(" ".join(args.question), store, llm, cfg, tz, on_step=on_step)
    except LLMError as e:
        _llm_failed(e)
    print_answer(console, result, llm, tz)


def cmd_status(args, cfg, store):
    from contextos.sources import all_sources

    console.print(f"[bold]Data dir[/bold] {cfg.home}")
    console.print(f"[bold]Models[/bold]   main={cfg.main_model} worker={cfg.worker_model}")
    key = "set (from .env)" if cfg.has_api_key else "[yellow]missing: add GEMINI_API_KEY to .env[/yellow]"
    console.print(f"[bold]Gemini key[/bold] {key}")
    counts = store.counts()
    tz = _local_tz()
    for src in all_sources(cfg):
        last = store.last_synced(src.name)
        state = "[green]configured[/green]" if src.is_configured() else f"[dim]not set up: {src.setup_hint()}[/dim]"
        when = f", last sync {last.astimezone(tz):%d %b %H:%M}" if last else ""
        console.print(f"  {src.name:8} {state}  {counts.get(src.name, 0)} stored{when}")


def cmd_people(args, cfg, store):
    """List people seen in more than one app, or merge / split two names by hand."""
    if args.action in ("merge", "split"):
        if len(args.names) != 2:
            console.print(f"Usage: contextos people {args.action} \"Name A\" \"Name B\"")
            sys.exit(1)
        store.add_identity_override(args.names[0], args.names[1], args.action)
        console.print(f"[green]{args.action.title()}d[/green] {args.names[0]} and {args.names[1]}.")
        return
    store.rebuild_identities()
    people = store.identities(min_sources=1 if args.all else 2)
    if not people:
        console.print("No one found in more than one app yet." if not args.all else "No people stored yet.")
        return
    for p in people:
        aliases = ", ".join(f"{a['source']}: {a['author']}" for a in p["aliases"])
        console.print(f"[bold]{p['name']}[/bold]  [dim]{aliases}[/dim]")


def cmd_trace(args, cfg, store):
    """Recent runs, or one run's steps as a waterfall."""
    from contextos import observability as obs

    tz = _local_tz()
    if args.run is None:
        rows = obs.runs(store, args.limit)
        if not rows:
            console.print("No traced runs yet. Write a briefing or ask a question first.")
            return
        for r in rows:
            when = datetime.fromtimestamp(r["started_at"], tz).strftime("%d %b %H:%M")
            cost = f"${r['cost_usd']:.4f}" if r["cost_usd"] is not None else "cost ?"
            ms = f"{r['ms'] / 1000:.1f}s" if r["ms"] else "-"
            color = {"ok": "green", "error": "red"}.get(r["status"], "yellow")
            console.print(f"#{r['id']:<4} {when}  {r['name']:9} [{color}]{r['status']:7}[/{color}] {ms:>7}  "
                          f"{r['tokens_in']:>7,} in {r['tokens_out']:>6,} out  {cost}")
        console.print("[dim]contextos trace <id> shows one run's steps[/dim]")
        return
    spans = obs.spans(store, args.run)
    if not spans:
        console.print(f"No run #{args.run}.")
        return
    total = max(s["start_ms"] + s["ms"] for s in spans) or 1
    width = 30
    for s in spans:
        lead = int(width * s["start_ms"] / total)
        bar = "█" * max(1, int(width * s["ms"] / total))
        attrs = ", ".join(f"{k}={v}" for k, v in s["attrs"].items() if k != "args")
        err = f" [red]{s['error']}[/red]" if s["error"] else ""
        console.print(f"{s['name']:16} {' ' * lead}{bar:<{width - lead}} {s['ms']:>8.1f} ms  [dim]{attrs}[/dim]{err}")


def cmd_audit(args, cfg, store):
    """Every tool call agents made through ContextOS: who, what, how many messages, anything flagged."""
    from contextos import observability as obs

    rows = obs.audit_rows(store, args.limit)
    if not rows:
        console.print("No tool calls recorded yet.")
        return
    tz = _local_tz()
    for r in reversed(rows):
        when = datetime.fromtimestamp(r["at"], tz).strftime("%d %b %H:%M:%S")
        args_s = json.dumps(r["args"], ensure_ascii=False)[:70]
        flag = f"  [red]flagged: {', '.join(r['flagged'])}[/red]" if r["flagged"] else ""
        ok = "" if r["ok"] else "  [red]error[/red]"
        console.print(f"{when}  {r['actor']:4} {r['tool']:16} {args_s:<70} {len(r['refs']):>3} msgs{flag}{ok}")


def cmd_mcp(args, cfg, store):
    """Serve ContextOS over MCP stdio. Nothing may be printed to stdout here: it carries the protocol."""
    from contextos.mcp_server import main as serve

    serve()


def cmd_bench(args, cfg, store):
    """Measure ContextOS on a labeled benchmark inbox (uses Gemini; costs a few cents)."""
    from contextos.bench.run import run, save
    from contextos.llm import LLMError

    llm = _require_llm()
    try:
        report = run(cfg, llm, progress=lambda m: console.print(f"[dim]{m}[/dim]"))
    except LLMError as e:
        _llm_failed(e)
    b, sr = report["briefing"], report["search"]
    console.print("\n[bold]Briefing[/bold]")
    console.print(f"  token reduction        {b['token_reduction_pct']}%  ({b['naive_tokens']:,} → {b['sent_tokens']:,} tokens)")
    console.print(f"  reading reduction      {b['reading_reduction_x']}×  ({b['raw_words']:,} → {b['briefing_words']} words)")
    console.print(f"  needs-you recall       {b['needs_you_recall_pct']}%  missed: {b['needs_you_missed'] or 'none'}")
    console.print(f"  citations valid        {b['citations_valid_pct']}%  of {b['citations_total']}")
    console.print(f"  handled ask flagged    {'yes (bad)' if b['already_handled_wrongly_flagged'] else 'no (good)'}")
    console.print(f"  time                   {b['seconds']}s")
    console.print("\n[bold]Search (recall@5 on 25 questions)[/bold]")
    for name, r in sr.items():
        lat = f"  p50 {r['latency_ms_p50']} ms, p95 {r['latency_ms_p95']} ms" if r.get("latency_ms_p50") else ""
        console.print(f"  {name:15} {r['recall_at_5_pct']:5}%{lat}")
    console.print(f"\n[dim]Saved to {save(report, cfg.home)}[/dim]")


def cmd_web(args, cfg, store):
    import threading
    import webbrowser

    import uvicorn

    from web.app import create_app

    url = f"http://localhost:{args.port}"
    console.print(f"[bold]ContextOS[/bold] running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # 127.0.0.1 only: your messages never become reachable from the network.
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="contextos", description="ContextOS: what happened today, across your inboxes.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("mcp", help="run as an MCP server so AI agents can use your context (stdio)")
    p.set_defaults(fn=cmd_mcp)

    p = sub.add_parser("bench", help="measure quality on a labeled benchmark inbox")
    p.set_defaults(fn=cmd_bench)

    p = sub.add_parser("web", help="start the website")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=cmd_web)

    p = sub.add_parser("auth", help="log in to a source (gmail)")
    p.add_argument("source", choices=["gmail", "slack", "discord"])
    p.set_defaults(fn=cmd_auth)

    p = sub.add_parser("sync", help="fetch new messages")
    p.add_argument("--source", choices=["gmail", "slack", "discord"])
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("today", help="brief me on today")
    p.add_argument("--hours", type=float, help="look back N hours instead of since midnight")
    p.add_argument("--no-sync", action="store_true", help="use stored messages only")
    p.add_argument("--json", action="store_true", help="print raw JSON output")
    p.set_defaults(fn=cmd_today)

    p = sub.add_parser("ask", help="ask a question about your messages")
    p.add_argument("question", nargs="+")
    p.add_argument("--no-sync", action="store_true")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("people", help="people linked across Gmail, Slack and Discord")
    p.add_argument("action", nargs="?", choices=["list", "merge", "split"], default="list")
    p.add_argument("names", nargs="*")
    p.add_argument("--all", action="store_true", help="also show people seen in only one app")
    p.set_defaults(fn=cmd_people)

    p = sub.add_parser("trace", help="timings, tokens and cost of recent briefings and asks")
    p.add_argument("run", nargs="?", type=int, help="run id to show step by step")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(fn=cmd_trace)

    p = sub.add_parser("audit", help="every tool call AI agents made through ContextOS")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser("status", help="show configuration and stored data")
    p.set_defaults(fn=cmd_status)

    args = parser.parse_args(argv)
    cfg = load_config()
    store = Store(cfg.db_path)
    try:
        args.fn(args, cfg, store)
    except KeyboardInterrupt:
        console.print("\n[dim]interrupted[/dim]")
    finally:
        store.close()


if __name__ == "__main__":
    main()
