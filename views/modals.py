from __future__ import annotations

import logging

import discord

from utils.helpers import rename_room, send_interaction_error, send_interaction_success, set_bitrate, set_user_limit
from utils.permissions import VoiceControlError


LOGGER = logging.getLogger(__name__)


class RenameRoomModal(discord.ui.Modal, title="Переименовать комнату"):
    name = discord.ui.TextInput(
        label="Новое название",
        placeholder="Например: Комната • Fedor",
        min_length=1,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await send_interaction_success(
                interaction,
                await rename_room(interaction.client, interaction.user, str(self.name), from_button=True),
            )
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Rename modal failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил изменение названия."))


class LimitRoomModal(discord.ui.Modal, title="Лимит участников"):
    limit = discord.ui.TextInput(
        label="0 — без лимита, 1–99 — лимит",
        placeholder="10",
        min_length=1,
        max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await send_interaction_success(
                interaction,
                await set_user_limit(interaction.client, interaction.user, int(str(self.limit).strip())),
            )
        except ValueError:
            await send_interaction_error(interaction, "Введите число от 0 до 99.")
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Limit modal failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил изменение лимита."))


class BitrateRoomModal(discord.ui.Modal, title="Bitrate комнаты"):
    bitrate = discord.ui.TextInput(
        label="Bitrate в kbps",
        placeholder="64",
        min_length=1,
        max_length=4,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await send_interaction_success(
                interaction,
                await set_bitrate(interaction.client, interaction.user, int(str(self.bitrate).strip())),
            )
        except ValueError:
            await send_interaction_error(interaction, "Введите bitrate числом в kbps.")
        except (VoiceControlError, discord.Forbidden, discord.HTTPException) as exc:
            LOGGER.exception("Bitrate modal failed")
            await send_interaction_error(interaction, getattr(exc, "message", "Discord отклонил изменение bitrate."))
