from __future__ import annotations

import discord


class VoiceControlError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def format_missing_permissions(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def require_bot_permissions(guild: discord.Guild, **permissions: bool) -> None:
    me = guild.me
    if me is None:
        raise VoiceControlError("Не удалось определить участника бота на сервере.")

    current = me.guild_permissions
    missing = [name for name, required in permissions.items() if required and not getattr(current, name, False)]
    if missing:
        raise VoiceControlError(
            "У бота не хватает прав: "
            f"{format_missing_permissions(missing)}. Проверьте роль бота и позицию роли."
        )


def ensure_manage_guild(interaction: discord.Interaction) -> bool:
    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    return user.guild_permissions.manage_guild or user.guild_permissions.administrator
