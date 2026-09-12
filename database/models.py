from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuildSettings:
    guild_id: int
    category_id: int
    creator_channel_id: int
    control_channel_id: int
    panel_message_id: int | None = None


@dataclass(frozen=True, slots=True)
class VoiceChannelRecord:
    guild_id: int
    channel_id: int
    owner_id: int
    created_at: str
    locked: bool
    hidden: bool
    user_limit: int
    bitrate: int


@dataclass(frozen=True, slots=True)
class UserPreferences:
    guild_id: int
    user_id: int
    preferred_name: str | None
    user_limit: int
    bitrate: int | None
    privacy_mode: str
