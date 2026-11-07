"""Run ContextOS on the benchmark inbox and measure it. Every number printed here is reproducible:
same seed, same data, same scoring. Run with `contextos bench`.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contextos.bench.dataset import Benchmark, build
from contextos.config import Config
from contextos.llm import LLM
from contextos.pipeline.digest import SECTIONS, make_digest
from contextos.pipeline.search import Searcher, SearchRequest, parse_date
from contextos.services.indexing import index_messages
from contextos.storage import Store

TOP_K = 5


def words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def run(cfg: Config, llm: LLM, progress=print) -> dict:
    now = datetime.now(UTC).replace(microsecond=0)
    bench = build(now)
    tz = UTC
    with tempfile.TemporaryDirectory() as tmp:
        bcfg = replace(cfg, home=Path(tmp), mute=[])
        store = Store(bcfg.db_path)
        store.upsert(bench.messages)
        progress(f"Loaded {len(bench.messages)} benchmark messages")

        report = {"messages": len(bench.messages)}
        report["briefing"] = _briefing(store, llm, bcfg, bench, tz, progress)
        progress("Embedding messages for meaning search…")
        index_messages(store, llm, bcfg)
        report["search"] = _search(store, llm, bcfg, bench, tz, progress)
        store.close()
    report["models"] = {"main": cfg.main_model, "embed": cfg.embed_model}
    report["llm_usage"] = llm.usage_summary()
    return report


def _briefing(store: Store, llm: LLM, cfg: Config, bench: Benchmark, tz, progress) -> dict:
    start, end = bench.now - timedelta(hours=24), bench.now + timedelta(seconds=1)
    window = store.between(start, end)

    # Baseline: what you'd send (and read) with no context engineering: every message, in full.
    naive = "\n\n".join(f"{m.source} {m.channel} {m.author} {m.title or ''}\n{m.text}" for m in window)
    progress("Writing the briefing…")
    t0 = time.perf_counter()
    d = make_digest(store, llm, cfg, start, end, tz)
    seconds = time.perf_counter() - t0

    # The context actually sent: rebuild it the same way make_digest does, then count both with Gemini's tokenizer.
    from contextos.pipeline.context import build_blocks
    from contextos.pipeline.noise import triage

    sent = "\n\n".join(b.render() for b in build_blocks(triage(window, cfg.mute), tz))
    naive_tokens = llm.count_tokens(naive, model=cfg.main_model)
    sent_tokens = llm.count_tokens(sent, model=cfg.main_model)

    out = d.output
    brief_text = " ".join([out.get("headline", "")] + [f"{i['title']} {i['detail']}" for s in SECTIONS for i in out.get(s, [])])
    cited = [r for s in SECTIONS for i in out.get(s, []) for r in i.get("refs", [])]
    total_citations = len(cited) + len(d.dropped_refs)

    by_ref = {m.ref: m.id for m in d.messages.values()}
    needs_ids = {by_ref.get(r) for i in out.get("needs_you", []) for r in i.get("refs", [])}
    caught = {label for label, ids in bench.needs_you.items() if needs_ids & set(ids)}
    handled_flagged = bool(needs_ids & set(bench.already_handled))

    return {
        "window_messages": len(window),
        "kept_full": len(d.triage.keep),
        "headlines_only": len(d.triage.low),
        "dropped": dict(d.triage.dropped),
        "naive_tokens": naive_tokens,
        "sent_tokens": sent_tokens,
        "token_reduction_pct": round(100 * (1 - sent_tokens / naive_tokens), 1),
        "raw_words": words(naive),
        "briefing_words": words(brief_text),
        "reading_reduction_x": round(words(naive) / max(1, words(brief_text)), 1),
        "citations_total": total_citations,
        "citations_valid_pct": round(100 * len(cited) / total_citations, 1) if total_citations else None,
        "needs_you_recall_pct": round(100 * len(caught) / len(bench.needs_you), 1),
        "needs_you_missed": sorted(set(bench.needs_you) - caught),
        "already_handled_wrongly_flagged": handled_flagged,
        "items": {s: len(out.get(s, [])) for s in SECTIONS},
        "seconds": round(seconds, 1),
    }


def _search(store: Store, llm: LLM, cfg: Config, bench: Benchmark, tz, progress) -> dict:
    def embed_query(text: str) -> list[float]:
        return llm.embed([text], model=cfg.embed_model, task="RETRIEVAL_QUERY", dim=cfg.embed_dim)[0]

    modes = {
        "plain_keyword": None,                                   # raw FTS on the words, no filters/fuzzy
        "keyword_plus": Searcher(store),                         # + fuzzy names, typo fix, date/person filters
        "hybrid": Searcher(store, embed_query, cfg.embed_model),  # + meaning vectors, fused with RRF
    }
    results: dict[str, dict] = {}
    for name, searcher in modes.items():
        progress(f"Scoring search: {name}…")
        hits, by_kind, per_q, latencies = 0, {}, [], []
        for q in bench.questions:
            if searcher is None:
                text = " ".join(str(v) for k, v in q.args.items() if k in ("query", "person"))
                found = [m.id for m in store.search(text, limit=TOP_K)]
            else:
                req = SearchRequest(
                    query=q.args.get("query", ""), person=q.args.get("person"),
                    after=parse_date(q.args.get("after"), tz), before=parse_date(q.args.get("before"), tz, end_of_day=True),
                    limit=TOP_K,
                )
                t0 = time.perf_counter()
                found = [m.id for m in searcher.search(req).messages]
                latencies.append((time.perf_counter() - t0) * 1000)
            ok = bool(set(found[:TOP_K]) & set(q.expected))
            hits += ok
            k = by_kind.setdefault(q.kind, [0, 0])
            k[0] += ok
            k[1] += 1
            per_q.append({"q": q.text, "kind": q.kind, "hit": ok})
        results[name] = {
            f"recall_at_{TOP_K}_pct": round(100 * hits / len(bench.questions), 1),
            "by_kind": {k: f"{a}/{b}" for k, (a, b) in sorted(by_kind.items())},
            "latency_ms_p50": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else None,
            "latency_ms_p95": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 1) if latencies else None,
            "questions": per_q,
        }
    return results


def save(report: dict, home: Path) -> Path:
    out = home / "bench"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"results-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path
