"""Context assembly: turn stored messages into compact, citable text for the model.

Design choices (each one is a context-engineering decision you can measure):
  * Group by source → channel → thread, in time order. Conversations stay together,
    so the model sees a question next to its answer.
  * Every message gets a short citation tag like [m42]. The model must cite tags, and we
    verify every tag afterwards. That turns "trust me" into "check me".
  * Long emails are truncated; quoted replies were already stripped at ingestion.
  * Low-priority messages are rendered as one-line headlines, not full text.
  * Tokens are estimated (chars / 4). If the whole day doesn't fit the budget, blocks are
    packed into chunks for a summarize-then-combine pass.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import tzinfo

from contextos.models import Message
from contextos.noise import Triage

CHARS_PER_TOKEN = 4
EMAIL_BODY_CHARS = 1500
CHAT_TEXT_CHARS = 800
LOW_LINE_CHARS = 140
MAX_LOW_LINES = 80


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + 1


@dataclass
class Block:
    header: str
    lines: list[str]

    def render(self) -> str:
        return "\n".join([self.header, *self.lines])

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.render())


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …[truncated]"


def _markers(m: Message) -> str:
    tags = []
    if m.is_from_me:
        tags.append("you")
    elif m.is_to_me:
        tags.append("to you")
    if m.is_automated:
        tags.append("automated")
    return f" ({', '.join(tags)})" if tags else ""


def render_message(m: Message, tz: tzinfo, reply: bool = False) -> str:
    when = m.ts.astimezone(tz).strftime("%H:%M")
    if m.source == "gmail":
        body = _clip(m.text, EMAIL_BODY_CHARS).replace("\n", "\n    ")
        return f"[{m.ref}] {when} From: {m.author}{_markers(m)}\n    {body}"
    text = _clip(m.text, CHAT_TEXT_CHARS).replace("\n", "\n    ")
    arrow = "  ↳ " if reply else ""
    return f"{arrow}[{m.ref}] {when} {m.author}{_markers(m)}: {text}"


def build_blocks(t: Triage, tz: tzinfo) -> list[Block]:
    blocks: list[Block] = []

    # Email: one block per thread, headed by its subject.
    threads: dict[str, list[Message]] = defaultdict(list)
    chats: dict[tuple[str, str], list[Message]] = defaultdict(list)
    for m in t.keep:
        if m.source == "gmail":
            threads[m.thread_id or m.id].append(m)
        else:
            chats[(m.source, m.channel)].append(m)

    for msgs in threads.values():
        msgs.sort(key=lambda m: m.ts)
        blocks.append(Block(f'### gmail · "{msgs[0].title}"', [render_message(m, tz) for m in msgs]))

    # Chat: one block per channel; thread replies are nested under their parent.
    for (source, channel), msgs in chats.items():
        msgs.sort(key=lambda m: m.ts)
        roots: dict[str, list[Message]] = defaultdict(list)
        order: list[str] = []
        for m in msgs:
            key = m.thread_id or m.id
            if key not in roots:
                order.append(key)
            roots[key].append(m)
        lines = []
        for key in order:
            for i, m in enumerate(roots[key]):
                lines.append(render_message(m, tz, reply=i > 0))
        blocks.append(Block(f"### {source} · {channel}", lines))

    blocks.sort(key=lambda b: b.header)

    if t.low:
        low = sorted(t.low, key=lambda m: m.ts)
        lines = []
        for m in low[:MAX_LOW_LINES]:
            when = m.ts.astimezone(tz).strftime("%H:%M")
            headline = m.title if m.source == "gmail" else m.text
            lines.append(f"[{m.ref}] {when} {m.source} · {m.author}: {_clip(headline or '', LOW_LINE_CHARS)}")
        if len(low) > MAX_LOW_LINES:
            lines.append(f"(+{len(low) - MAX_LOW_LINES} more automated messages not shown)")
        blocks.append(Block("### Automated / low priority (headlines only)", lines))

    return blocks


def pack(blocks: list[Block], max_tokens: int) -> list[str]:
    """Greedy bin-packing of blocks into chunks under max_tokens. Oversized blocks are split by line."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0

    def flush():
        nonlocal current, size
        if current:
            chunks.append("\n\n".join(current))
        current, size = [], 0

    for block in blocks:
        if block.tokens > max_tokens:
            flush()
            part: list[str] = [block.header]
            for line in block.lines:
                if estimate_tokens("\n".join(part + [line])) > max_tokens and len(part) > 1:
                    chunks.append("\n".join(part))
                    part = [block.header + " (continued)"]
                part.append(line)
            chunks.append("\n".join(part))
            continue
        if size + block.tokens > max_tokens:
            flush()
        current.append(block.render())
        size += block.tokens
    flush()
    return chunks
