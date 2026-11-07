"""Terminal output with rich: clickable source links, sections, and a cost/coverage footer."""

from __future__ import annotations

from datetime import tzinfo

from rich.console import Console
from rich.markup import escape

from contextos.ask import REF_PATTERN, AskResult
from contextos.digest import DigestResult
from contextos.llm import LLM
from contextos.models import Message
from contextos.sync import SyncReport

SECTION_TITLES = {
    "needs_you": "📌 Needs you",
    "important": "⚡ Important",
    "fyi": "📰 FYI",
}


def _source_label(m: Message, tz: tzinfo) -> str:
    label = f"{m.source} {m.channel} {m.ts.astimezone(tz):%H:%M}"
    return f"[link={m.url}]{escape(label)}[/link]" if m.url else escape(label)


def print_sync(console: Console, reports: list[SyncReport]) -> None:
    for r in reports:
        if r.skipped:
            console.print(f"[dim]· {r.source}: not set up ({r.skipped})[/dim]")
        elif r.error:
            console.print(f"[red]✗ {r.source}: {escape(r.error)}[/red]")
        else:
            console.print(f"[dim]✓ {r.source}: {r.fetched} fetched, {r.new} new[/dim]")
        for w in r.warnings:
            console.print(f"[yellow]  ! {escape(w)}[/yellow]")


def print_digest(console: Console, d: DigestResult, llm: LLM, tz: tzinfo) -> None:
    start, end = d.window
    console.rule(f"[bold]{start.astimezone(tz):%A %d %b}[/bold]  {start.astimezone(tz):%H:%M}–{end.astimezone(tz):%H:%M}")
    if d.empty:
        console.print("Nothing in this window. Run `contextos sync` or widen it with `--hours 24`.")
        return

    if d.output.get("headline"):
        console.print(f"\n[bold]{escape(d.output['headline'])}[/bold]")

    for key, title in SECTION_TITLES.items():
        items = d.output.get(key, [])
        if not items:
            continue
        console.print(f"\n[bold]{title}[/bold]")
        for item in items:
            flag = " [yellow](unverified)[/yellow]" if item.get("unverified") else ""
            console.print(f"  • [bold]{escape(item['title'])}[/bold]{flag}")
            console.print(f"    {escape(item['detail'])}", highlight=False)
            links = [_source_label(d.messages[r], tz) for r in item.get("refs", []) if r in d.messages]
            if links:
                console.print("    [dim]↳ " + " · ".join(links[:4]) + (" …" if len(links) > 4 else "") + "[/dim]")

    t = d.triage
    by_source: dict[str, int] = {}
    for m in t.keep:
        by_source[m.source] = by_source.get(m.source, 0) + 1
    read = ", ".join(f"{n} {s}" for s, n in sorted(by_source.items())) or "0"
    skipped = ", ".join(f"{n} {why}" for why, n in t.dropped.most_common())
    footer = [f"read {read}", f"{len(t.low)} automated as headlines"]
    if skipped:
        footer.append(f"skipped {skipped}")
    footer.append(f"~{d.context_tokens:,} tokens" + (f" in {d.chunks} chunks" if d.chunks > 1 else ""))
    cost = llm.cost_usd()
    if cost is not None:
        footer.append(f"${cost:.3f}")
    if d.dropped_refs:
        footer.append(f"[yellow]{len(d.dropped_refs)} invalid citations removed[/yellow]")
    console.print("\n[dim]" + " · ".join(footer) + "[/dim]")


def print_answer(console: Console, r: AskResult, llm: LLM, tz: tzinfo) -> None:
    def link(match) -> str:
        ref = f"m{match.group(1)}"
        m = r.cited.get(ref)
        return f"[link={m.url}]{ref}[/link]" if m and m.url else ref

    console.print()
    console.print(REF_PATTERN.sub(link, escape(r.answer)), highlight=False)
    if r.cited:
        console.print("\n[dim]Sources:[/dim]")
        for ref, m in r.cited.items():
            console.print(f"[dim]  {ref}: {_source_label(m, tz)} · {escape(m.author)}[/dim]")
    cost = llm.cost_usd()
    extra = f" · ${cost:.3f}" if cost is not None else ""
    warn = f" · [yellow]{len(r.unknown_refs)} citations to unseen messages[/yellow]" if r.unknown_refs else ""
    console.print(f"[dim]{r.steps} steps{extra}[/dim]{warn}")
