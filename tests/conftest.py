from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from contextos.config import Config
from contextos.models import Message
from contextos.store import Store

NOW = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)


def msg(n: int, **kw) -> Message:
    base = dict(
        id=f"slack:C1:{n}", source="slack", channel="#eng", author="Alice",
        ts=NOW - timedelta(hours=5) + timedelta(minutes=n), text=f"message number {n}",
    )
    base.update(kw)
    return Message(**base)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(home=tmp_path, user_name="Sam")


@pytest.fixture
def store(cfg: Config) -> Store:
    s = Store(cfg.db_path)
    yield s
    s.close()


class FakeLLM:
    """Stands in for ctx.llm.LLM. Records prompts; returns canned outputs."""

    def __init__(self, json_out=None, text_out="- notes [m1]", turns=None):
        self.json_out = json_out
        self.text_out = text_out
        self.turns = list(turns or [])
        self.calls: list[dict] = []

    def text(self, **kw):
        self.calls.append({"kind": "text", **kw})
        return self.text_out

    def json(self, **kw):
        self.calls.append({"kind": "json", **kw})
        return self.json_out

    def create(self, **kw):
        self.calls.append({"kind": "create", **kw, "messages": list(kw["messages"])})
        return self.turns.pop(0)

    def usage_summary(self):
        return {}

    def cost_usd(self):
        return 0.0


def text_block(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(name, inp, id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


def turn(stop_reason, *content):
    return SimpleNamespace(stop_reason=stop_reason, content=list(content))
