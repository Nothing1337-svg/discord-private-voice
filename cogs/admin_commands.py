from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import cleanup_guild_rooms, send_interaction_error
from utils.permissions import ensure_manage_guild, require_bot_permissions
from views.voice_panel import send_control_panel


LOGGER = logging.getLogger(__name__)


class VoiceAdminCommands(commands.GroupCog, name="voice-admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if ensure_manage_guild(interaction):
            return True
        await send_interaction_error(interaction, "Эта команда доступна только администраторам с правом Manage Server.")
        return False

    @app_commands.command(name="setup", description="Создать категорию, join-to-create канал, control канал и панель")
    @app_commands.default_permissions(manage_guild=True)
    async def setup_command(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await send_interaction_error(interaction, "Команда доступна только на сервере.")
            return

        try:
            require_bot_permissions(guild, manage_channels=True, send_messages=True, embed_links=True, view_channel=True, connect=True, move_members=True)
            await interaction.response.defer(ephemeral=True, thinking=True)

            settings = await self.bot.db.get_guild_settings(guild.id)
            category = guild.get_channel(settings.category_id) if settings else None
            if not isinstance(category, discord.CategoryChannel):
                category = await guild.create_category("Private Voice", reason="Private voice setup")

            creator = guild.get_channel(settings.creator_channel_id) if settings else None
            if not isinstance(creator, discord.VoiceChannel):
                creator = await category.create_voice_channel("➕ Создать приват", reason="Private voice setup")

            control = guild.get_channel(settings.control_channel_id) if settings else None
            if not isinstance(control, discord.TextChannel):
                control = await guild.create_text_channel("🔊・voice-control", category=category, reason="Private voice setup")

            message = await send_control_panel(control)
            await self.bot.db.upsert_guild_settings(guild.id, category.id, creator.id, control.id, message.id)

            await interaction.followup.send(
                "✅ Setup готов.\n"
                f"Категория: {category.mention}\n"
                f"Join-to-create: {creator.mention}\n"
                f"Панель: {control.mention}",
                ephemeral=True,
            )
            LOGGER.info("Voice setup completed in guild %s", guild.id)
        except (discord.Forbidden, discord.HTTPException, Exception) as exc:
            LOGGER.exception("Voice setup failed")
            message = getattr(exc, "message", "Не удалось выполнить setup. Проверьте права бота и позицию роли.")
            if interaction.response.is_done():
                await interaction.followup.send(f"⚠️ {message}", ephemeral=True)
            else:
                await send_interaction_error(interaction, message)

    @app_commands.command(name="reset", description="Удалить настройки и временные комнаты бота")
    @app_commands.default_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await send_interaction_error(interaction, "Команда доступна только на сервере.")
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.db.get_guild_settings(guild.id)
        deleted_rooms, stale = await cleanup_guild_rooms(self.bot, guild, delete_non_empty=True)

        deleted_setup_channels: list[str] = []
        if settings:
            for channel_id in (settings.creator_channel_id, settings.control_channel_id):
                channel = guild.get_channel(channel_id)
                if channel is not None:
                    try:
                        await channel.delete(reason="Private voice reset")
                        deleted_setup_channels.append(channel.name)
                    except (discord.Forbidden, discord.HTTPException):
                        LOGGER.exception("Failed to delete setup channel %s", channel_id)

            category = guild.get_channel(settings.category_id)
            if isinstance(category, discord.CategoryChannel) and not category.channels:
                try:
                    await category.delete(reason="Private voice reset")
                    deleted_setup_channels.append(category.name)
                except (discord.Forbidden, discord.HTTPException):
                    LOGGER.exception("Failed to delete setup category %s", settings.category_id)

        await self.bot.db.delete_voice_channels_for_guild(guild.id)
        await self.bot.db.delete_guild_settings(guild.id)
        await interaction.followup.send(
            "✅ Reset выполнен.\n"
            f"Удалено временных комнат: {deleted_rooms}\n"
            f"Удалено битых записей: {stale}\n"
            f"Удалены setup-каналы: {', '.join(deleted_setup_channels) if deleted_setup_channels else 'нет'}",
            ephemeral=True,
        )
        LOGGER.info("Voice reset completed in guild %s", guild.id)

    @app_commands.command(name="config", description="Показать текущую конфигурацию приватных комнат")
    @app_commands.default_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await send_interaction_error(interaction, "Команда доступна только на сервере.")
            return

        settings = await self.bot.db.get_guild_settings(guild.id)
        if settings is None:
            await interaction.response.send_message("Настройка ещё не выполнена. Запустите `/voice-admin setup`.", ephemeral=True)
            return

        category = guild.get_channel(settings.category_id)
        creator = guild.get_channel(settings.creator_channel_id)
        control = guild.get_channel(settings.control_channel_id)
        rooms = await self.bot.db.list_voice_channels(guild.id)

        embed = discord.Embed(title="⚙️ Voice Admin Config", color=discord.Color.blurple())
        embed.add_field(name="Категория", value=category.mention if category else f"`{settings.category_id}` missing", inline=False)
        embed.add_field(name="Создать приват", value=creator.mention if creator else f"`{settings.creator_channel_id}` missing", inline=False)
        embed.add_field(name="Панель", value=control.mention if control else f"`{settings.control_channel_id}` missing", inline=False)
        embed.add_field(name="Panel message ID", value=str(settings.panel_message_id or "не сохранён"), inline=True)
        embed.add_field(name="Активные комнаты", value=str(len(rooms)), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="cleanup", description="Удалить заброшенные временные комнаты и битые записи")
    @app_commands.default_permissions(manage_guild=True)
    async def cleanup(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await send_interaction_error(interaction, "Команда доступна только на сервере.")
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            deleted_rooms, stale_records = await cleanup_guild_rooms(self.bot, guild)
            await interaction.followup.send(
                "✅ Cleanup выполнен.\n"
                f"Удалено пустых временных комнат: {deleted_rooms}\n"
                f"Удалено битых записей: {stale_records}",
                ephemeral=True,
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Voice cleanup failed")
            await interaction.followup.send(f"⚠️ {getattr(exc, 'message', 'Discord отклонил cleanup.')}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceAdminCommands(bot))
