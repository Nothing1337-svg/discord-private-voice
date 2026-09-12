from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from config import Config
from database.database import Database
from utils.logging import setup_logging
from views.voice_panel import VoicePanelView


LOGGER = logging.getLogger(__name__)


class PrivateVoiceBot(commands.Bot):
    db: Database

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.room_locks: dict[int, asyncio.Lock] = {}
        self.member_create_locks: dict[tuple[int, int], asyncio.Lock] = {}
        self.action_cooldowns: dict[tuple[int, str], float] = {}

    async def setup_hook(self) -> None:
        self.db = Database(self.config.database_path)
        await self.db.connect()
        await self.db.init_schema()

        self.add_view(VoicePanelView())

        for extension in ("cogs.voice_events", "cogs.voice_commands", "cogs.admin_commands"):
            await self.load_extension(extension)
            LOGGER.info("Loaded extension %s", extension)

        if self.config.sync_commands:
            synced = await self.tree.sync()
            LOGGER.info("Synced %s slash commands globally", len(synced))

    async def close(self) -> None:
        if hasattr(self, "db"):
            await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")


async def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)
    bot = PrivateVoiceBot(config)
    async with bot:
        await bot.start(config.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
