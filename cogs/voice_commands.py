from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.helpers import (
    build_room_info_embed,
    claim_room,
    delete_room,
    get_member_room,
    kick_user,
    permit_user,
    reject_user,
    rename_room,
    send_interaction_error,
    send_interaction_success,
    set_bitrate,
    set_hidden,
    set_locked,
    set_user_limit,
    transfer_ownership,
)
from utils.permissions import VoiceControlError
from views.voice_panel import ConfirmDeleteView


LOGGER = logging.getLogger(__name__)


class VoiceCommands(commands.GroupCog, name="voice"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        LOGGER.exception("Voice command failed", exc_info=error)
        await send_interaction_error(interaction, "Команда завершилась ошибкой.")

    @app_commands.command(name="lock", description="Закрыть вашу приватную комнату")
    async def lock(self, interaction: discord.Interaction) -> None:
        await self._member_action(interaction, lambda member: set_locked(self.bot, member, True))

    @app_commands.command(name="unlock", description="Открыть вашу приватную комнату")
    async def unlock(self, interaction: discord.Interaction) -> None:
        await self._member_action(interaction, lambda member: set_locked(self.bot, member, False))

    @app_commands.command(name="hide", description="Скрыть вашу приватную комнату")
    async def hide(self, interaction: discord.Interaction) -> None:
        await self._member_action(interaction, lambda member: set_hidden(self.bot, member, True))

    @app_commands.command(name="show", description="Показать вашу приватную комнату")
    async def show(self, interaction: discord.Interaction) -> None:
        await self._member_action(interaction, lambda member: set_hidden(self.bot, member, False))

    @app_commands.command(name="rename", description="Переименовать вашу приватную комнату")
    @app_commands.describe(name="Новое название комнаты")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        await self._member_action(interaction, lambda member: rename_room(self.bot, member, name))

    @app_commands.command(name="limit", description="Установить лимит участников")
    @app_commands.describe(limit="0 — без лимита, 1–99 — конкретный лимит")
    async def limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        await self._member_action(interaction, lambda member: set_user_limit(self.bot, member, int(limit)))

    @app_commands.command(name="permit", description="Разрешить пользователю вход в комнату")
    async def permit(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self._member_action(interaction, lambda owner: permit_user(self.bot, owner, member))

    @app_commands.command(name="reject", description="Запретить пользователю вход в комнату")
    async def reject(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self._member_action(interaction, lambda owner: reject_user(self.bot, owner, member))

    @app_commands.command(name="kick", description="Отключить пользователя от вашей комнаты")
    async def kick(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self._member_action(interaction, lambda owner: kick_user(self.bot, owner, member))

    @app_commands.command(name="transfer", description="Передать владельца комнаты участнику")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self._member_action(interaction, lambda owner: transfer_ownership(self.bot, owner, member))

    @app_commands.command(name="claim", description="Забрать комнату, если владелец вышел")
    async def claim(self, interaction: discord.Interaction) -> None:
        await self._member_action(interaction, lambda member: claim_room(self.bot, member))

    @app_commands.command(name="bitrate", description="Изменить bitrate комнаты")
    @app_commands.describe(kbps="Bitrate в kbps, не выше лимита сервера")
    async def bitrate(self, interaction: discord.Interaction, kbps: app_commands.Range[int, 8, 384]) -> None:
        await self._member_action(interaction, lambda member: set_bitrate(self.bot, member, int(kbps)))

    @app_commands.command(name="delete", description="Удалить вашу приватную комнату")
    async def delete(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Вы уверены, что хотите удалить комнату?",
            view=ConfirmDeleteView(),
            ephemeral=True,
        )

    @app_commands.command(name="info", description="Показать информацию о текущей приватной комнате")
    async def info(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await send_interaction_error(interaction, "Эта команда доступна только на сервере.")
            return
        try:
            room, channel = await get_member_room(self.bot, interaction.user)
            await interaction.response.send_message(embed=build_room_info_embed(interaction.guild, room, channel), ephemeral=True)
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Voice info failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Не удалось показать информацию."))

    async def _member_action(self, interaction: discord.Interaction, callback) -> None:
        if not isinstance(interaction.user, discord.Member):
            await send_interaction_error(interaction, "Эта команда доступна только на сервере.")
            return
        try:
            await send_interaction_success(interaction, await callback(interaction.user))
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Voice command action failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил действие."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCommands(bot))
