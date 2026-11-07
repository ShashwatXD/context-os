"""ContextOS command line. The website is the main way to use it; these are handy for debugging.

    contextos web               start the website on http://localhost:8000
    contextos auth gmail        one-time Google login
    contextos sync              pull new messages from every configured source
    contextos today             sync, then print today's briefing
    contextos ask "question"    search my messages and answer
    contextos status            what's configured and stored
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import anthropic
from rich.console import Console

from contextos.config import load_config
from contextos.store import Store

console = Console()


def _local_tz():
    return datetime.now().astimezone().tzinfo


def cfg_key():
    return load_config().anthropic_api_key or None


def _require_llm():
    from contextos.llm import LLM

    try:
        return LLM(api_key=cfg_key())
    except anthropic.AnthropicError as e:
        console.print(f"[red]Can't create the Claude client: {e}[/red]\nSet ANTHROPIC_API_KEY in .env (see README).")
        sys.exit(1)


def _claude_failed(e: Exception) -> None:
    if isinstance(e, TypeError) and "authentication" not in str(e):
        raise e
    if isinstance(e, (TypeError, anthropic.AuthenticationError)):
        console.print("[red]No valid Anthropic credentials.[/red] Put ANTHROPIC_API_KEY=... in .env (see README).")
    else:
        console.print(f"[red]Claude call failed: {e}[/red]")
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
    from contextos.render import print_sync
    from contextos.sync import sync

    with console.status("Syncing…"):
        reports = sync(store, cfg, only=getattr(args, "source", None), cover_from=cover_from)
    print_sync(console, reports)
    if all(r.skipped for r in reports):
        console.print("[yellow]No sources are set up yet. See README → Setup.[/yellow]")


def cmd_today(args, cfg, store):
    from contextos.digest import make_digest
    from contextos.llm import LLMError
    from contextos.render import print_digest

    tz = _local_tz()
    end = datetime.now(timezone.utc)
    if args.hours:
        start = end - timedelta(hours=args.hours)
    else:
        start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    if not args.no_sync:
        cmd_sync(args, cfg, store, cover_from=start)

    llm = _require_llm()
    try:
        with console.status(f"Reading your messages with {cfg.main_model}…"):
            d = make_digest(store, llm, cfg, start, end, tz)
    except (LLMError, anthropic.AnthropicError, TypeError) as e:
        _claude_failed(e)

    if args.json:
        print(json.dumps(d.output, indent=2))
    else:
        print_digest(console, d, llm, tz)


def cmd_ask(args, cfg, store):
    from contextos.ask import ask
    from contextos.llm import LLMError
    from contextos.render import print_answer

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
    except (LLMError, anthropic.AnthropicError, TypeError) as e:
        _claude_failed(e)
    print_answer(console, result, llm, tz)


def cmd_status(args, cfg, store):
    from contextos.sources import all_sources

    console.print(f"[bold]Data dir[/bold] {cfg.home}")
    console.print(f"[bold]Models[/bold]   main={cfg.main_model} worker={cfg.worker_model}")
    key = "set" if os.environ.get("ANTHROPIC_API_KEY") else "[yellow]missing[/yellow]"
    console.print(f"[bold]API key[/bold]  {key}")
    counts = store.counts()
    tz = _local_tz()
    for src in all_sources(cfg):
        last = store.last_synced(src.name)
        state = "[green]configured[/green]" if src.is_configured() else f"[dim]not set up: {src.setup_hint()}[/dim]"
        when = f", last sync {last.astimezone(tz):%d %b %H:%M}" if last else ""
        console.print(f"  {src.name:8} {state}  {counts.get(src.name, 0)} stored{when}")


def cmd_web(args, cfg, store):
    import threading
    import webbrowser

    import uvicorn

    from contextos.web.app import create_app

    url = f"http://localhost:{args.port}"
    console.print(f"[bold]ContextOS[/bold] running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # 127.0.0.1 only: your messages never become reachable from the network.
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="contextos", description="ContextOS: what happened today, across your inboxes.")
    sub = parser.add_subparsers(dest="cmd", required=True)

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
