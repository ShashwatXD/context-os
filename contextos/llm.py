"""Thin wrapper around the Anthropic SDK: streaming calls, JSON output, usage + cost tracking."""

from __future__ import annotations

import json
from collections import defaultdict

import anthropic

# Server-side fallback: if a model declines a request on policy grounds, the API retries it on
# a suitable fallback model inside the same call. On models without fallback support it's a no-op.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens (input, output). Unknown models just show token counts.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, client: anthropic.Anthropic | None = None, api_key: str | None = None):
        # api_key=None lets the SDK resolve ANTHROPIC_API_KEY (or an `ant auth login` profile) itself.
        self.client = client or anthropic.Anthropic(api_key=api_key or None, max_retries=3)
        self.usage: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})

    # ---- public helpers -----------------------------------------------------

    def text(self, *, model: str, system: str, prompt: str, effort: str = "medium", max_tokens: int = 16000) -> str:
        msg = self._stream(
            model=model, system=system, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
        )
        return _text_of(msg)

    def json(
        self, *, model: str, system: str, prompt: str, schema: dict, effort: str = "medium", max_tokens: int = 16000
    ) -> dict:
        """Structured output: the API constrains the response to `schema`, so json.loads is safe."""
        msg = self._stream(
            model=model, system=system, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        try:
            return json.loads(_text_of(msg))
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {e}") from e

    def create(self, **kwargs):
        """One raw (non-streaming) turn, used by the tool-use loop in `ask`."""
        msg = self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        self._record(msg)
        return msg

    def cost_usd(self) -> float | None:
        total = 0.0
        for model, u in self.usage.items():
            if model not in PRICES:
                return None
            p_in, p_out = PRICES[model]
            # Cache reads bill at ~0.1x input, cache writes at ~1.25x (5-minute TTL).
            billed_in = u["input"] + 0.1 * u.get("cache_read", 0) + 1.25 * u.get("cache_write", 0)
            total += billed_in * p_in / 1e6 + u["output"] * p_out / 1e6
        return total

    def usage_summary(self) -> dict:
        return {"by_model": dict(self.usage), "cost_usd": self.cost_usd()}

    # ---- internals ----------------------------------------------------------

    def _stream(self, **kwargs):
        # Streaming avoids HTTP timeouts on long inputs/outputs; we only need the final message.
        with self.client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **kwargs) as stream:
            msg = stream.get_final_message()
        self._record(msg)
        if msg.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        if msg.stop_reason == "max_tokens":
            raise LLMError("The response hit max_tokens and was cut off.")
        return msg

    def _record(self, msg) -> None:
        u = msg.usage
        # Bill against the model that actually served the request (may differ after a fallback).
        bucket = self.usage[msg.model]
        bucket["input"] += u.input_tokens or 0
        bucket["cache_read"] = bucket.get("cache_read", 0) + (u.cache_read_input_tokens or 0)
        bucket["cache_write"] = bucket.get("cache_write", 0) + (u.cache_creation_input_tokens or 0)
        bucket["output"] += u.output_tokens or 0
        bucket["calls"] += 1


def _text_of(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text").strip()
