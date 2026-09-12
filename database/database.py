from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone

import aiosqlite

from database.models import GuildSettings, UserPreferences, VoiceChannelRecord


LOGGER = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA foreign_keys = ON")
        await self.connection.execute("PRAGMA journal_mode = WAL")
        await self.connection.commit()
        LOGGER.info("Connected to SQLite database at %s", self.path)

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("Database is not connected")
        return self.connection

    async def init_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                creator_channel_id INTEGER NOT NULL,
                control_channel_id INTEGER NOT NULL,
                panel_message_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS voice_channels (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
                hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
                user_limit INTEGER NOT NULL DEFAULT 0 CHECK (user_limit BETWEEN 0 AND 99),
                bitrate INTEGER NOT NULL DEFAULT 64000 CHECK (bitrate > 0)
            );

            CREATE INDEX IF NOT EXISTS idx_voice_channels_guild
                ON voice_channels (guild_id);

            CREATE INDEX IF NOT EXISTS idx_voice_channels_owner
                ON voice_channels (guild_id, owner_id);

            CREATE TABLE IF NOT EXISTS voice_permissions (
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission_type TEXT NOT NULL CHECK (permission_type IN ('allow', 'block')),
                PRIMARY KEY (channel_id, user_id, permission_type),
                FOREIGN KEY (channel_id) REFERENCES voice_channels(channel_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                preferred_name TEXT,
                user_limit INTEGER NOT NULL DEFAULT 0 CHECK (user_limit BETWEEN 0 AND 99),
                bitrate INTEGER,
                privacy_mode TEXT NOT NULL DEFAULT 'open'
                    CHECK (privacy_mode IN ('open', 'locked', 'hidden', 'locked_hidden')),
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS user_preference_permissions (
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                permission_type TEXT NOT NULL CHECK (permission_type IN ('allow', 'block')),
                PRIMARY KEY (guild_id, owner_id, target_user_id, permission_type),
                FOREIGN KEY (guild_id, owner_id)
                    REFERENCES user_preferences(guild_id, user_id) ON DELETE CASCADE
            );
            """
        )
        await self.conn.commit()

    async def get_guild_settings(self, guild_id: int) -> GuildSettings | None:
        async with self.conn.execute(
            """
            SELECT guild_id, category_id, creator_channel_id, control_channel_id, panel_message_id
            FROM guild_settings
            WHERE guild_id = ?
            """,
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._settings_from_row(row) if row else None

    async def upsert_guild_settings(
        self,
        guild_id: int,
        category_id: int,
        creator_channel_id: int,
        control_channel_id: int,
        panel_message_id: int | None,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO guild_settings
                (guild_id, category_id, creator_channel_id, control_channel_id, panel_message_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                category_id = excluded.category_id,
                creator_channel_id = excluded.creator_channel_id,
                control_channel_id = excluded.control_channel_id,
                panel_message_id = excluded.panel_message_id
            """,
            (guild_id, category_id, creator_channel_id, control_channel_id, panel_message_id),
        )
        await self.conn.commit()

    async def delete_guild_settings(self, guild_id: int) -> None:
        await self.conn.execute("DELETE FROM guild_settings WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()

    async def create_voice_channel(
        self,
        guild_id: int,
        channel_id: int,
        owner_id: int,
        locked: bool,
        hidden: bool,
        user_limit: int,
        bitrate: int,
    ) -> VoiceChannelRecord:
        created_at = datetime.now(timezone.utc).isoformat()
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO voice_channels
                (guild_id, channel_id, owner_id, created_at, locked, hidden, user_limit, bitrate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, owner_id, created_at, int(locked), int(hidden), user_limit, bitrate),
        )
        await self.conn.commit()
        return VoiceChannelRecord(guild_id, channel_id, owner_id, created_at, locked, hidden, user_limit, bitrate)

    async def get_voice_channel(self, channel_id: int) -> VoiceChannelRecord | None:
        async with self.conn.execute(
            """
            SELECT guild_id, channel_id, owner_id, created_at, locked, hidden, user_limit, bitrate
            FROM voice_channels
            WHERE channel_id = ?
            """,
            (channel_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._room_from_row(row) if row else None

    async def get_owner_room(self, guild_id: int, owner_id: int) -> VoiceChannelRecord | None:
        async with self.conn.execute(
            """
            SELECT guild_id, channel_id, owner_id, created_at, locked, hidden, user_limit, bitrate
            FROM voice_channels
            WHERE guild_id = ? AND owner_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (guild_id, owner_id),
        ) as cursor:
            row = await cursor.fetchone()
        return self._room_from_row(row) if row else None

    async def list_voice_channels(self, guild_id: int | None = None) -> list[VoiceChannelRecord]:
        if guild_id is None:
            cursor = await self.conn.execute(
                """
                SELECT guild_id, channel_id, owner_id, created_at, locked, hidden, user_limit, bitrate
                FROM voice_channels
                """
            )
        else:
            cursor = await self.conn.execute(
                """
                SELECT guild_id, channel_id, owner_id, created_at, locked, hidden, user_limit, bitrate
                FROM voice_channels
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
        async with cursor:
            rows = await cursor.fetchall()
        return [self._room_from_row(row) for row in rows]

    async def update_room_state(
        self,
        channel_id: int,
        *,
        locked: bool | None = None,
        hidden: bool | None = None,
        user_limit: int | None = None,
        bitrate: int | None = None,
        owner_id: int | None = None,
    ) -> None:
        updates: list[str] = []
        values: list[int] = []

        if locked is not None:
            updates.append("locked = ?")
            values.append(int(locked))
        if hidden is not None:
            updates.append("hidden = ?")
            values.append(int(hidden))
        if user_limit is not None:
            updates.append("user_limit = ?")
            values.append(user_limit)
        if bitrate is not None:
            updates.append("bitrate = ?")
            values.append(bitrate)
        if owner_id is not None:
            updates.append("owner_id = ?")
            values.append(owner_id)

        if not updates:
            return

        values.append(channel_id)
        await self.conn.execute(
            f"UPDATE voice_channels SET {', '.join(updates)} WHERE channel_id = ?",
            tuple(values),
        )
        await self.conn.commit()

    async def delete_voice_channel(self, channel_id: int) -> None:
        await self.conn.execute("DELETE FROM voice_channels WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()

    async def set_channel_permission(self, channel_id: int, user_id: int, permission_type: str) -> None:
        opposite = "block" if permission_type == "allow" else "allow"
        await self.conn.execute(
            "DELETE FROM voice_permissions WHERE channel_id = ? AND user_id = ? AND permission_type = ?",
            (channel_id, user_id, opposite),
        )
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO voice_permissions (channel_id, user_id, permission_type)
            VALUES (?, ?, ?)
            """,
            (channel_id, user_id, permission_type),
        )
        await self.conn.commit()

    async def remove_channel_permission(self, channel_id: int, user_id: int, permission_type: str | None = None) -> None:
        if permission_type is None:
            await self.conn.execute(
                "DELETE FROM voice_permissions WHERE channel_id = ? AND user_id = ?",
                (channel_id, user_id),
            )
        else:
            await self.conn.execute(
                "DELETE FROM voice_permissions WHERE channel_id = ? AND user_id = ? AND permission_type = ?",
                (channel_id, user_id, permission_type),
            )
        await self.conn.commit()

    async def get_channel_permissions(self, channel_id: int, permission_type: str | None = None) -> list[int]:
        if permission_type is None:
            cursor = await self.conn.execute(
                "SELECT user_id FROM voice_permissions WHERE channel_id = ?",
                (channel_id,),
            )
        else:
            cursor = await self.conn.execute(
                "SELECT user_id FROM voice_permissions WHERE channel_id = ? AND permission_type = ?",
                (channel_id, permission_type),
            )
        async with cursor:
            rows = await cursor.fetchall()
        return [int(row["user_id"]) for row in rows]

    async def get_user_preferences(self, guild_id: int, user_id: int) -> UserPreferences:
        async with self.conn.execute(
            """
            SELECT guild_id, user_id, preferred_name, user_limit, bitrate, privacy_mode
            FROM user_preferences
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            return self._preferences_from_row(row)
        return UserPreferences(guild_id, user_id, None, 0, None, "open")

    async def upsert_user_preferences(
        self,
        guild_id: int,
        user_id: int,
        *,
        preferred_name: str | None = None,
        user_limit: int | None = None,
        bitrate: int | None = None,
        privacy_mode: str | None = None,
    ) -> None:
        current = await self.get_user_preferences(guild_id, user_id)
        next_name = preferred_name if preferred_name is not None else current.preferred_name
        next_limit = user_limit if user_limit is not None else current.user_limit
        next_bitrate = bitrate if bitrate is not None else current.bitrate
        next_privacy = privacy_mode if privacy_mode is not None else current.privacy_mode
        await self.conn.execute(
            """
            INSERT INTO user_preferences (guild_id, user_id, preferred_name, user_limit, bitrate, privacy_mode)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                preferred_name = excluded.preferred_name,
                user_limit = excluded.user_limit,
                bitrate = excluded.bitrate,
                privacy_mode = excluded.privacy_mode
            """,
            (guild_id, user_id, next_name, next_limit, next_bitrate, next_privacy),
        )
        await self.conn.commit()

    async def set_preference_permission(
        self,
        guild_id: int,
        owner_id: int,
        target_user_id: int,
        permission_type: str,
    ) -> None:
        prefs = await self.get_user_preferences(guild_id, owner_id)
        await self.upsert_user_preferences(
            guild_id,
            owner_id,
            preferred_name=prefs.preferred_name,
            user_limit=prefs.user_limit,
            bitrate=prefs.bitrate,
            privacy_mode=prefs.privacy_mode,
        )
        opposite = "block" if permission_type == "allow" else "allow"
        await self.conn.execute(
            """
            DELETE FROM user_preference_permissions
            WHERE guild_id = ? AND owner_id = ? AND target_user_id = ? AND permission_type = ?
            """,
            (guild_id, owner_id, target_user_id, opposite),
        )
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO user_preference_permissions
                (guild_id, owner_id, target_user_id, permission_type)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, owner_id, target_user_id, permission_type),
        )
        await self.conn.commit()

    async def get_preference_permissions(self, guild_id: int, owner_id: int, permission_type: str) -> list[int]:
        async with self.conn.execute(
            """
            SELECT target_user_id
            FROM user_preference_permissions
            WHERE guild_id = ? AND owner_id = ? AND permission_type = ?
            """,
            (guild_id, owner_id, permission_type),
        ) as cursor:
            rows = await cursor.fetchall()
        return [int(row["target_user_id"]) for row in rows]

    async def delete_voice_channels_for_guild(self, guild_id: int) -> None:
        await self.conn.execute("DELETE FROM voice_channels WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()

    async def remove_permissions_for_missing_users(self, guild_id: int, valid_user_ids: Iterable[int]) -> None:
        valid = set(valid_user_ids)
        if not valid:
            return
        rooms = await self.list_voice_channels(guild_id)
        for room in rooms:
            user_ids = await self.get_channel_permissions(room.channel_id)
            for user_id in user_ids:
                if user_id not in valid:
                    await self.remove_channel_permission(room.channel_id, user_id)

    @staticmethod
    def _settings_from_row(row: aiosqlite.Row) -> GuildSettings:
        panel_id = row["panel_message_id"]
        return GuildSettings(
            guild_id=int(row["guild_id"]),
            category_id=int(row["category_id"]),
            creator_channel_id=int(row["creator_channel_id"]),
            control_channel_id=int(row["control_channel_id"]),
            panel_message_id=int(panel_id) if panel_id is not None else None,
        )

    @staticmethod
    def _room_from_row(row: aiosqlite.Row) -> VoiceChannelRecord:
        return VoiceChannelRecord(
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            owner_id=int(row["owner_id"]),
            created_at=str(row["created_at"]),
            locked=bool(row["locked"]),
            hidden=bool(row["hidden"]),
            user_limit=int(row["user_limit"]),
            bitrate=int(row["bitrate"]),
        )

    @staticmethod
    def _preferences_from_row(row: aiosqlite.Row) -> UserPreferences:
        bitrate = row["bitrate"]
        return UserPreferences(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            preferred_name=row["preferred_name"],
            user_limit=int(row["user_limit"]),
            bitrate=int(bitrate) if bitrate is not None else None,
            privacy_mode=str(row["privacy_mode"]),
        )
