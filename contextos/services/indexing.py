"""Build the meaning index: embed messages that don't have a vector yet.

Runs right after each sync, so new messages become searchable by meaning within minutes. Each message is
embedded once; it's only re-embedded if its text changes (the store drops the old vector on edit).
"""

from __future__ import annotations

from collections.abc import Callable

from contextos.config import Config
from contextos.llm import LLM
from contextos.pipeline.search import embed_text, to_blob
from contextos.storage import Store

BATCH = 100          # messages per embedding request
MAX_PER_RUN = 3000   # cap per run so a huge first backlog doesn't block a sync; the rest continues next time


def index_messages(store: Store, llm: LLM, cfg: Config, progress: Callable[[str], None] = lambda _: None) -> int:
    done = 0
    while done < MAX_PER_RUN:
        pending = store.missing_embeddings(cfg.embed_model, limit=BATCH)
        if not pending:
            break
        vectors = llm.embed([embed_text(m) for m in pending], model=cfg.embed_model,
                            task="RETRIEVAL_DOCUMENT", dim=cfg.embed_dim)
        store.save_embeddings(cfg.embed_model, [(m.rid, to_blob(v)) for m, v in zip(pending, vectors, strict=True)])
        done += len(pending)
        progress(f"Indexed {done} message{'s' if done != 1 else ''} for meaning search")
    return done
