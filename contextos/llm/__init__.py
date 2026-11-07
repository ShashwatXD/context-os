"""Language-model access. Everything goes through `LLM`; today it is backed by Gemini."""

from contextos.llm.gemini import LLM, LLMError, ToolCall, ToolTurn, api_key_from_env

__all__ = ["LLM", "LLMError", "ToolCall", "ToolTurn", "api_key_from_env"]
