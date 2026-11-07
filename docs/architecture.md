# Architecture

This page explains how ContextOS turns scattered messages into a briefing, and why each step exists. File paths are relative to `src/contextos/`.

## The big picture

```
sources/ ──► services/sync.py ──► storage/ (SQLite + full-text index)
                                        │
                     ┌──────────────────┴──────────────────┐
                     ▼                                     ▼
          pipeline/digest.py                      pipeline/ask.py
   (we choose the context: "push")      (the model searches for context: "pull")
                     │                                     │
                     └──────────────► web/ ◄───────────────┘
```

There are two ways to give a model context:

- **Push**: your code decides exactly what the model sees. The daily briefing works this way, because "what happened today" is a time filter, not a search.
- **Pull**: the model is given tools and fetches what it needs. Ask works this way, because questions can be about anything.

## 1. Sources → one shape (`sources/`, `models.py`)

Each connector turns a provider's API into the same `Message` object: source, channel, author, time, text, thread, link, and three flags (`is_to_me`, `is_from_me`, `is_automated`). Everything after this point works the same for every source.

Sync is **incremental**. Each source remembers when it last synced, re-fetches a 15-minute overlap to catch late or edited messages, and saves with an upsert so repeats are harmless (`services/sync.py`).

## 2. Noise filter (`pipeline/noise.py`)

Messages are sorted into three buckets before any model call:

| Bucket | What goes in | What the model sees |
|---|---|---|
| keep | normal conversation | full text |
| low | newsletters, bots, notifications | a one-line headline |
| dropped | promotions, muted channels, empty messages | nothing |

This is the cheapest way to improve quality: every token you don't send costs nothing and can't distract the model.

## 3. Context assembly (`pipeline/context.py`)

The kept messages are grouped by source, then channel, then thread, in time order, so a question sits next to its answer. Every message gets a short tag like `[m42]`. Long emails are truncated and quoted replies are stripped at ingestion.

The size is estimated in tokens. If it's over the budget, the blocks are packed into chunks.

## 4. Writing the briefing (`pipeline/digest.py`)

- **Normal day**: one call to the main model with a JSON schema, so the output always has `needs_you`, `important` and `fyi` sections.
- **Busy day**: a lighter model condenses each chunk in parallel (keeping the tags), then the main model writes the briefing from those notes.

The prompt tells the model who you are (from Settings) and treats message text as **untrusted data**, so an email saying "ignore your instructions" has no effect.

## 5. Verifying citations (`pipeline/digest.py → verify_refs`)

Every tag the model cites is checked against the messages it was actually given. Unknown tags are removed. An item with no valid citation is kept but labelled *unverified*. The model can't cite a message that doesn't exist.

## 6. Ask (`pipeline/ask.py`, `llm/gemini.py`)

A tool-calling loop. The model can call `search_messages` (full-text search), `get_thread` and `recent_activity`. We run each call, return the results, and repeat until it answers (at most 8 steps). Citations in the answer are checked against the messages the tools actually returned.

## 7. The website (`web/`, `services/`)

- Long work (sync, briefing, ask) runs as a **background job** (`services/jobs.py`). The page streams its progress live using server-sent events.
- The **scheduler** (`services/scheduler.py`) syncs on a timer and writes one briefing each morning.
- **Done / Snooze** actions are stored by the item's citations. When a briefing is rewritten with the same messages, your choices still apply. If a new message joins the topic, the item comes back.
- The server only answers requests addressed to `localhost`, and rejects form posts from other websites.

## 8. Measuring quality

Every briefing, 👍 / 👎 vote and "you missed this" note is stored (`digests` and `feedback` tables). After a couple of weeks, this becomes an evaluation set: change one thing (a prompt, a filter rule, the budget), rerun, and compare.
