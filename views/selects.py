from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import discord

from utils.helpers import (
    kick_user,
    permit_user,
    reject_user,
    send_interaction_error,
    send_interaction_success,
    set_member_deafen,
    set_member_mute,
    transfer_ownership,
)
from utils.permissions import VoiceControlError


LOGGER = logging.getLogger(__name__)
ActionCallback = Callable[[discord.Client, discord.Member, discord.Member], Awaitable[str]]


class UserActionSelect(discord.ui.UserSelect):
    def __init__(self, placeholder: str, action: ActionCallback) -> None:
        super().__init__(placeholder=placeholder, min_values=1, max_values=1)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await send_interaction_error(interaction, "Эта функция доступна только на сервере.")
            return
        selected = self.values[0]
        if not isinstance(selected, discord.Member):
            await send_interaction_error(interaction, "Выберите участника этого сервера.")
            return
        try:
            await send_interaction_success(interaction, await self.action(interaction.client, interaction.user, selected))
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("User action select failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил действие."))


class UserActionView(discord.ui.View):
    def __init__(self, placeholder: str, action: ActionCallback) -> None:
        super().__init__(timeout=120)
        self.add_item(UserActionSelect(placeholder, action))


def permit_view() -> UserActionView:
    return UserActionView("Выберите пользователя, которому разрешить вход", permit_user)


def reject_view() -> UserActionView:
    return UserActionView("Выберите пользователя, которому запретить вход", reject_user)


def transfer_view() -> UserActionView:
    return UserActionView("Выберите участника комнаты для передачи владельца", transfer_ownership)


def kick_view() -> UserActionView:
    return UserActionView("Выберите участника комнаты, которого нужно выгнать", kick_user)


async def mute_action(bot: discord.Client, owner: discord.Member, target: discord.Member) -> str:
    return await set_member_mute(bot, owner, target, True)


async def unmute_action(bot: discord.Client, owner: discord.Member, target: discord.Member) -> str:
    return await set_member_mute(bot, owner, target, False)


async def deafen_action(bot: discord.Client, owner: discord.Member, target: discord.Member) -> str:
    return await set_member_deafen(bot, owner, target, True)


async def undeafen_action(bot: discord.Client, owner: discord.Member, target: discord.Member) -> str:
    return await set_member_deafen(bot, owner, target, False)


def mute_view() -> UserActionView:
    return UserActionView("Выберите участника для mute", mute_action)


def unmute_view() -> UserActionView:
    return UserActionView("Выберите участника для unmute", unmute_action)


def deafen_view() -> UserActionView:
    return UserActionView("Выберите участника для deafen", deafen_action)


def undeafen_view() -> UserActionView:
    return UserActionView("Выберите участника для undeafen", undeafen_action)
