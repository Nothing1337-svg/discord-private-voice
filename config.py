from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class Config:
    discord_token: str
    database_path: str = "private_voice.sqlite3"
    log_level: str = "INFO"
    sync_commands: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is missing. Create .env from .env.example and add the bot token.")

        return cls(
            discord_token=token,
            database_path=os.getenv("DATABASE_PATH", "private_voice.sqlite3").strip() or "private_voice.sqlite3",
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            sync_commands=_as_bool(os.getenv("SYNC_COMMANDS"), True),
        )
