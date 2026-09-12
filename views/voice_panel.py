from __future__ import annotations

import logging

import discord

from utils.helpers import (
    build_panel_embed,
    check_action_cooldown,
    claim_room,
    delete_room,
    send_interaction_error,
    send_interaction_success,
    set_hidden,
    set_locked,
)
from utils.permissions import VoiceControlError
from views.modals import BitrateRoomModal, LimitRoomModal, RenameRoomModal
from views.selects import deafen_view, kick_view, mute_view, permit_view, reject_view, transfer_view, undeafen_view, unmute_view


LOGGER = logging.getLogger(__name__)


class ConfirmDeleteView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.button(label="Удалить", style=discord.ButtonStyle.danger, custom_id="pv:confirm_delete")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not isinstance(interaction.user, discord.Member):
            await send_interaction_error(interaction, "Эта функция доступна только на сервере.")
            return
        try:
            await send_interaction_success(interaction, await delete_room(interaction.client, interaction.user))
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Delete confirmation failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил удаление комнаты."))

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary, custom_id="pv:cancel_delete")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await send_interaction_success(interaction, "Удаление отменено.")


class VoicePanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _run_owner_action(
        self,
        interaction: discord.Interaction,
        action_name: str,
        callback,
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            await send_interaction_error(interaction, "Эта функция доступна только на сервере.")
            return
        try:
            check_action_cooldown(interaction.client, interaction.user.id, action_name)
            await send_interaction_success(interaction, await callback(interaction.client, interaction.user))
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Panel action %s failed", action_name)
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил действие."))

    async def _send_select(self, interaction: discord.Interaction, content: str, view: discord.ui.View) -> None:
        if not isinstance(interaction.user, discord.Member):
            await send_interaction_error(interaction, "Эта функция доступна только на сервере.")
            return
        try:
            check_action_cooldown(interaction.client, interaction.user.id, "select")
            await interaction.response.send_message(content, view=view, ephemeral=True)
        except VoiceControlError as exc:
            await send_interaction_error(interaction, exc.message)

    @discord.ui.button(label="Закрыть", emoji="🔒", style=discord.ButtonStyle.secondary, row=0, custom_id="pv:lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._run_owner_action(interaction, "lock", lambda bot, member: set_locked(bot, member, True))

    @discord.ui.button(label="Открыть", emoji="🔓", style=discord.ButtonStyle.secondary, row=0, custom_id="pv:unlock")
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._run_owner_action(interaction, "unlock", lambda bot, member: set_locked(bot, member, False))

    @discord.ui.button(label="Скрыть", emoji="👁", style=discord.ButtonStyle.secondary, row=0, custom_id="pv:hide")
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._run_owner_action(interaction, "hide", lambda bot, member: set_hidden(bot, member, True))

    @discord.ui.button(label="Показать", emoji="👁‍🗨", style=discord.ButtonStyle.secondary, row=0, custom_id="pv:show")
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._run_owner_action(interaction, "show", lambda bot, member: set_hidden(bot, member, False))

    @discord.ui.button(label="Название", emoji="✏️", style=discord.ButtonStyle.primary, row=1, custom_id="pv:rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(RenameRoomModal())

    @discord.ui.button(label="Лимит", emoji="👥", style=discord.ButtonStyle.primary, row=1, custom_id="pv:limit")
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(LimitRoomModal())

    @discord.ui.button(label="Bitrate", emoji="📶", style=discord.ButtonStyle.primary, row=1, custom_id="pv:bitrate")
    async def bitrate(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(BitrateRoomModal())

    @discord.ui.button(label="Владелец", emoji="👑", style=discord.ButtonStyle.primary, row=1, custom_id="pv:transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кому передать комнату?", transfer_view())

    @discord.ui.button(label="Разрешить", emoji="✅", style=discord.ButtonStyle.success, row=2, custom_id="pv:permit")
    async def permit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кому разрешить вход?", permit_view())

    @discord.ui.button(label="Запретить", emoji="🚫", style=discord.ButtonStyle.danger, row=2, custom_id="pv:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кому запретить вход?", reject_view())

    @discord.ui.button(label="Выгнать", emoji="👢", style=discord.ButtonStyle.danger, row=2, custom_id="pv:kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кого отключить от комнаты?", kick_view())

    @discord.ui.button(label="Claim", emoji="🏳", style=discord.ButtonStyle.secondary, row=2, custom_id="pv:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._run_owner_action(interaction, "claim", claim_room)

    @discord.ui.button(label="Mute", emoji="🔇", style=discord.ButtonStyle.secondary, row=3, custom_id="pv:mute")
    async def mute(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кого заглушить?", mute_view())

    @discord.ui.button(label="Unmute", emoji="🔊", style=discord.ButtonStyle.secondary, row=3, custom_id="pv:unmute")
    async def unmute(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "С кого снять mute?", unmute_view())

    @discord.ui.button(label="Deafen", emoji="🎧", style=discord.ButtonStyle.secondary, row=3, custom_id="pv:deafen")
    async def deafen(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кому отключить звук комнаты?", deafen_view())

    @discord.ui.button(label="Undeafen", emoji="🎧", style=discord.ButtonStyle.secondary, row=3, custom_id="pv:undeafen")
    async def undeafen(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._send_select(interaction, "Кому вернуть звук комнаты?", undeafen_view())

    @discord.ui.button(label="Удалить", emoji="🗑", style=discord.ButtonStyle.danger, row=4, custom_id="pv:delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "Вы уверены, что хотите удалить комнату?",
            view=ConfirmDeleteView(),
            ephemeral=True,
        )


async def send_control_panel(channel: discord.TextChannel) -> discord.Message:
    return await channel.send(embed=build_panel_embed(), view=VoicePanelView())
