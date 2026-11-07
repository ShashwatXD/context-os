"""Configuration: environment variables / .env, overridden by settings saved from the website."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Settings the Sources page can edit. Saved to <home>/settings.json (chmod 600).
# The Gemini API key is deliberately NOT here: it only ever comes from .env.
EDITABLE = {
    "user_name",
    "about_me",
    "mute",
    "slack_token",
    "discord_token",
    "discord_user_id",
    "morning_hour",
    "auto_sync_minutes",
}
SECRETS = {"slack_token", "discord_token"}


def _list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    return [v.strip().lower() for v in (value or "").split(",") if v.strip()]


@dataclass
class Config:
    home: Path
    # Who you are. Goes into every prompt so the model knows what matters to you.
    user_name: str = ""
    about_me: str = ""
    # Models: main = final briefing + ask; worker = bulk notes on busy days.
    main_model: str = "gemini-3.8-flash"
    worker_model: str = "gemini-3.1-flash-lite"
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    # Context budget (estimated input tokens). Above this, summarize in chunks first.
    token_budget: int = 50_000
    chunk_tokens: int = 25_000
    backfill_days: int = 2
    mute: list[str] = field(default_factory=list)
    # Background schedule (website only)
    morning_hour: int = 8
    auto_sync_minutes: int = 15
    # Sources
    gmail_max_messages: int = 300
    slack_token: str = ""
    discord_token: str = ""
    discord_user_id: str = ""

    @property
    def db_path(self) -> Path:
        return self.home / "contextos.db"

    @property
    def settings_path(self) -> Path:
        return self.home / "settings.json"

    @property
    def gmail_credentials(self) -> Path:
        return self.home / "gmail_credentials.json"

    @property
    def gmail_token(self) -> Path:
        return self.home / "gmail_token.json"

    @property
    def has_api_key(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def load_config() -> Config:
    home = Path(os.environ.get("CONTEXTOS_HOME", "~/.contextos")).expanduser()
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(home / ".env")
    home.mkdir(parents=True, exist_ok=True)

    env = os.environ.get
    cfg = Config(
        home=home,
        user_name=env("CONTEXTOS_USER_NAME", ""),
        about_me=env("CONTEXTOS_ABOUT_ME", ""),
        main_model=env("CONTEXTOS_MAIN_MODEL", "gemini-3.8-flash"),
        worker_model=env("CONTEXTOS_WORKER_MODEL", "gemini-3.1-flash-lite"),
        embed_model=env("CONTEXTOS_EMBED_MODEL", "gemini-embedding-001"),
        embed_dim=int(env("CONTEXTOS_EMBED_DIM", "768")),
        token_budget=int(env("CONTEXTOS_TOKEN_BUDGET", "50000")),
        chunk_tokens=int(env("CONTEXTOS_CHUNK_TOKENS", "25000")),
        backfill_days=int(env("CONTEXTOS_BACKFILL_DAYS", "2")),
        mute=_list(env("CONTEXTOS_MUTE")),
        gmail_max_messages=int(env("GMAIL_MAX_MESSAGES", "300")),
        slack_token=env("SLACK_USER_TOKEN", ""),
        discord_token=env("DISCORD_BOT_TOKEN", ""),
        discord_user_id=env("DISCORD_USER_ID", ""),
    )
    apply_settings(cfg, read_settings(cfg))
    return cfg


def read_settings(cfg: Config) -> dict:
    try:
        return json.loads(cfg.settings_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_settings(cfg: Config, settings: dict) -> None:
    """Values saved from the website win over .env; empty values don't override."""
    for key, value in settings.items():
        if key not in EDITABLE or value in ("", None, []):
            continue
        if key == "mute":
            value = _list(value)
        elif key in ("morning_hour", "auto_sync_minutes"):
            value = int(value)
        setattr(cfg, key, value)


def save_settings(cfg: Config, updates: dict) -> None:
    current = read_settings(cfg)
    for key, value in updates.items():
        if key not in EDITABLE:
            continue
        if key in SECRETS and not value:
            continue  # blank secret field = "keep what's saved"
        current[key] = value
    cfg.settings_path.write_text(json.dumps(current, indent=2))
    cfg.settings_path.chmod(0o600)
    apply_settings(cfg, current)
