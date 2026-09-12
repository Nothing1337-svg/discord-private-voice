from __future__ import annotations

import logging

import discord
from discord.ext import commands

from utils.helpers import cleanup_guild_rooms, create_private_room, delete_room_by_channel, enforce_blocked_member
from utils.permissions import VoiceControlError


LOGGER = logging.getLogger(__name__)


class VoiceEvents(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._reconciled = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._reconciled:
            return
        self._reconciled = True
        for guild in self.bot.guilds:
            try:
                removed_channels, removed_records = await cleanup_guild_rooms(self.bot, guild)
                LOGGER.info(
                    "Startup cleanup for guild %s: deleted %s empty rooms, removed %s stale records",
                    guild.id,
                    removed_channels,
                    removed_records,
                )
            except (discord.Forbidden, discord.HTTPException, VoiceControlError):
                LOGGER.exception("Startup cleanup failed in guild %s", guild.id)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        if after.channel and isinstance(after.channel, discord.VoiceChannel):
            try:
                await enforce_blocked_member(self.bot, member, after.channel)
            except (discord.Forbidden, discord.HTTPException, VoiceControlError):
                LOGGER.exception("Failed to enforce block list for %s", member.id)

        if after.channel and before.channel != after.channel:
            try:
                await create_private_room(self.bot, member)
            except (discord.Forbidden, discord.HTTPException, VoiceControlError):
                LOGGER.exception("Failed to create private room for %s", member.id)

        if before.channel and isinstance(before.channel, discord.VoiceChannel):
            room = await self.bot.db.get_voice_channel(before.channel.id)
            if room is None:
                return
            if before.channel.members:
                return
            try:
                await delete_room_by_channel(self.bot, before.channel, "Private voice room became empty")
            except (discord.Forbidden, discord.HTTPException):
                LOGGER.exception("Failed to delete empty private room %s", before.channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceEvents(bot))
