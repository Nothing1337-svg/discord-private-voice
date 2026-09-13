from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

import discord

from database.models import VoiceChannelRecord
from utils.permissions import VoiceControlError, require_bot_can_manage_member, require_bot_permissions


if TYPE_CHECKING:
    from bot import PrivateVoiceBot


LOGGER = logging.getLogger(__name__)
DEFAULT_ROOM_BITRATE = 64000
MIN_BITRATE = 8000
RENAME_COOLDOWN_SECONDS = 60.0
ACTION_COOLDOWN_SECONDS = 1.5


def room_name_for(member: discord.Member) -> str:
    base = f"Комната • {member.display_name}".strip()
    return base[:100] or f"Комната • {member.display_name}"[:100]


def get_verified_role(guild: discord.Guild, verified_role_id: int) -> discord.Role:
    role = guild.get_role(verified_role_id)
    if role is None:
        LOGGER.error(
            "Configured VERIFIED_ROLE_ID=%s was not found in guild %s (%s)",
            verified_role_id,
            guild.id,
            guild.name,
        )
        raise VoiceControlError(
            f"Роль Verified с ID `{verified_role_id}` не найдена на сервере. "
            "Проверьте VERIFIED_ROLE_ID в .env и перезапустите бота."
        )
    return role


def make_private_everyone_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=False, connect=False)


def make_public_room_overwrite(*, locked: bool, hidden: bool) -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=not hidden,
        connect=not locked,
        speak=True,
        use_voice_activation=True,
        stream=True,
    )


def make_privileged_room_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        connect=True,
        speak=True,
        use_voice_activation=True,
        stream=True,
    )


def make_blocked_room_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(connect=False)


def make_bot_room_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        connect=True,
        speak=True,
        use_voice_activation=True,
        stream=True,
        manage_channels=True,
        move_members=True,
        mute_members=True,
        deafen_members=True,
    )


def build_private_room_overwrites(
    guild: discord.Guild,
    verified_role: discord.Role,
    owner: discord.Member,
    *,
    locked: bool,
    hidden: bool,
    allowed_members: list[discord.Member] | None = None,
    blocked_members: list[discord.Member] | None = None,
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: make_private_everyone_overwrite(),
        verified_role: make_public_room_overwrite(locked=locked, hidden=hidden),
        owner: make_privileged_room_overwrite(),
    }

    if guild.me is not None:
        overwrites[guild.me] = make_bot_room_overwrite()

    for allowed in allowed_members or []:
        if not allowed.bot:
            overwrites[allowed] = make_privileged_room_overwrite()

    for blocked in blocked_members or []:
        if not blocked.bot and blocked.id != owner.id:
            overwrites[blocked] = make_blocked_room_overwrite()

    return overwrites


async def apply_room_permission_state(
    bot: "PrivateVoiceBot",
    channel: discord.VoiceChannel,
    room: VoiceChannelRecord,
    *,
    reason: str,
) -> None:
    owner = channel.guild.get_member(room.owner_id)
    if owner is None:
        LOGGER.warning("Cannot apply room permissions for %s: owner %s is missing", channel.id, room.owner_id)
        return
    verified_role = get_verified_role(channel.guild, bot.config.verified_role_id)

    allowed_members = [
        member
        for user_id in await bot.db.get_channel_permissions(channel.id, "allow")
        if (member := channel.guild.get_member(user_id)) is not None
    ]
    blocked_members = [
        member
        for user_id in await bot.db.get_channel_permissions(channel.id, "block")
        if (member := channel.guild.get_member(user_id)) is not None
    ]

    await channel.edit(
        overwrites=build_private_room_overwrites(
            channel.guild,
            verified_role,
            owner,
            locked=room.locked,
            hidden=room.hidden,
            allowed_members=allowed_members,
            blocked_members=blocked_members,
        ),
        reason=reason,
    )


async def ensure_create_room_permissions(
    guild: discord.Guild,
    verified_role_id: int,
    category: discord.CategoryChannel,
    creator: discord.VoiceChannel,
) -> None:
    verified_role = get_verified_role(guild, verified_role_id)
    base_overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: make_private_everyone_overwrite(),
        verified_role: make_privileged_room_overwrite(),
    }
    if guild.me is not None:
        base_overwrites[guild.me] = make_bot_room_overwrite()

    await category.edit(overwrites=base_overwrites, reason="Private voice setup permissions")
    await creator.edit(
        category=category,
        overwrites=base_overwrites,
        reason="Private voice create room permissions",
    )


def get_room_lock(bot: "PrivateVoiceBot", channel_id: int) -> asyncio.Lock:
    lock = bot.room_locks.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        bot.room_locks[channel_id] = lock
    return lock


def get_member_create_lock(bot: "PrivateVoiceBot", guild_id: int, member_id: int) -> asyncio.Lock:
    key = (guild_id, member_id)
    lock = bot.member_create_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        bot.member_create_locks[key] = lock
    return lock


def check_action_cooldown(bot: "PrivateVoiceBot", user_id: int, action: str, seconds: float = ACTION_COOLDOWN_SECONDS) -> None:
    now = time.monotonic()
    key = (user_id, action)
    ready_at = bot.action_cooldowns.get(key, 0.0)
    if ready_at > now:
        remaining = max(1, round(ready_at - now))
        raise VoiceControlError(f"Подождите {remaining} сек. перед повторным действием.")
    bot.action_cooldowns[key] = now + seconds


def clamp_user_limit(value: int) -> int:
    if value < 0 or value > 99:
        raise VoiceControlError("Лимит должен быть числом от 0 до 99.")
    return value


def normalize_bitrate(guild: discord.Guild, kbps: int) -> int:
    if kbps < 8:
        raise VoiceControlError("Bitrate не может быть ниже 8 kbps.")
    requested = kbps * 1000
    maximum = int(guild.bitrate_limit)
    if requested > maximum:
        raise VoiceControlError(f"На этом сервере максимум {maximum // 1000} kbps.")
    return requested


def privacy_mode(locked: bool, hidden: bool) -> str:
    if locked and hidden:
        return "locked_hidden"
    if locked:
        return "locked"
    if hidden:
        return "hidden"
    return "open"


async def send_interaction_error(interaction: discord.Interaction, message: str) -> None:
    content = f"⚠️ {message}"
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


async def send_interaction_success(interaction: discord.Interaction, message: str) -> None:
    content = f"✅ {message}"
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔊 Управление приватной комнатой",
        description=(
            "Создайте комнату через `➕ Создать приват`, затем используйте кнопки ниже. "
            "Панель работает только с временными комнатами, созданными ботом."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Доступ", value="Закрыть, открыть, скрыть, показать", inline=False)
    embed.add_field(name="Настройки", value="Название, лимит, bitrate, передача владельца", inline=False)
    embed.add_field(name="Пользователи", value="Разрешить, запретить, выгнать, mute, deafen", inline=False)
    embed.set_footer(text="Ответы панели видны только пользователю, который нажал кнопку.")
    return embed


def build_room_info_embed(guild: discord.Guild, room: VoiceChannelRecord, channel: discord.VoiceChannel) -> discord.Embed:
    owner = guild.get_member(room.owner_id)
    limit = room.user_limit if room.user_limit else "без лимита"
    created_at = _format_created_at(room.created_at)
    embed = discord.Embed(title="ℹ️ Информация о приватной комнате", color=discord.Color.green())
    embed.add_field(name="Название", value=channel.name, inline=False)
    embed.add_field(name="Владелец", value=owner.mention if owner else f"`{room.owner_id}`", inline=True)
    embed.add_field(name="Участников", value=f"{len(channel.members)}/{limit}", inline=True)
    embed.add_field(name="Лимит", value=str(limit), inline=True)
    embed.add_field(name="Доступ", value="Locked" if room.locked else "Open", inline=True)
    embed.add_field(name="Видимость", value="Hidden" if room.hidden else "Visible", inline=True)
    embed.add_field(name="Bitrate", value=f"{room.bitrate // 1000} kbps", inline=True)
    embed.add_field(name="Создана", value=created_at, inline=False)
    return embed


def _format_created_at(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return discord.utils.format_dt(dt, "F")


async def get_member_room(bot: "PrivateVoiceBot", member: discord.Member) -> tuple[VoiceChannelRecord, discord.VoiceChannel]:
    if member.voice is None or member.voice.channel is None:
        raise VoiceControlError("Сначала зайдите в свою приватную голосовую комнату.")
    if not isinstance(member.voice.channel, discord.VoiceChannel):
        raise VoiceControlError("Текущий канал не является голосовой комнатой.")

    room = await bot.db.get_voice_channel(member.voice.channel.id)
    if room is None:
        raise VoiceControlError("Этот канал не управляется ботом как временная приватная комната.")
    return room, member.voice.channel


async def get_owned_room(bot: "PrivateVoiceBot", member: discord.Member) -> tuple[VoiceChannelRecord, discord.VoiceChannel]:
    room, channel = await get_member_room(bot, member)
    if room.owner_id != member.id:
        raise VoiceControlError("Управлять этой комнатой может только её владелец.")
    return room, channel


async def set_locked(bot: "PrivateVoiceBot", member: discord.Member, locked: bool) -> str:
    room, channel = await get_owned_room(bot, member)
    require_bot_permissions(member.guild, manage_channels=True)
    async with get_room_lock(bot, channel.id):
        await bot.db.update_room_state(channel.id, locked=locked)
        latest = await bot.db.get_voice_channel(channel.id)
        if latest is not None:
            await apply_room_permission_state(
                bot,
                channel,
                latest,
                reason=f"Private voice {'lock' if locked else 'unlock'} by {member}",
            )
        await bot.db.upsert_user_preferences(
            member.guild.id,
            member.id,
            privacy_mode=privacy_mode(locked, latest.hidden if latest else room.hidden),
        )
    LOGGER.info("%s %s room %s", member, "locked" if locked else "unlocked", channel.id)
    return "Комната закрыта." if locked else "Комната открыта."


async def set_hidden(bot: "PrivateVoiceBot", member: discord.Member, hidden: bool) -> str:
    room, channel = await get_owned_room(bot, member)
    require_bot_permissions(member.guild, manage_channels=True)
    async with get_room_lock(bot, channel.id):
        await bot.db.update_room_state(channel.id, hidden=hidden)
        latest = await bot.db.get_voice_channel(channel.id)
        if latest is not None:
            await apply_room_permission_state(
                bot,
                channel,
                latest,
                reason=f"Private voice {'hide' if hidden else 'show'} by {member}",
            )
        await bot.db.upsert_user_preferences(
            member.guild.id,
            member.id,
            privacy_mode=privacy_mode(room.locked, hidden),
        )
    LOGGER.info("%s %s room %s", member, "hid" if hidden else "showed", channel.id)
    return "Комната скрыта." if hidden else "Комната снова видна."


async def rename_room(bot: "PrivateVoiceBot", member: discord.Member, name: str, *, from_button: bool = False) -> str:
    room, channel = await get_owned_room(bot, member)
    require_bot_permissions(member.guild, manage_channels=True)
    if from_button:
        check_action_cooldown(bot, member.id, "rename", RENAME_COOLDOWN_SECONDS)
    clean_name = name.strip()[:100]
    if not clean_name:
        raise VoiceControlError("Название не может быть пустым.")
    async with get_room_lock(bot, channel.id):
        await channel.edit(name=clean_name, reason=f"Private voice rename by {member}")
    LOGGER.info("%s renamed room %s to %r", member, channel.id, clean_name)
    return f"Комната переименована в `{clean_name}`."


async def set_user_limit(bot: "PrivateVoiceBot", member: discord.Member, limit: int) -> str:
    room, channel = await get_owned_room(bot, member)
    require_bot_permissions(member.guild, manage_channels=True)
    next_limit = clamp_user_limit(limit)
    async with get_room_lock(bot, channel.id):
        await channel.edit(user_limit=next_limit, reason=f"Private voice limit by {member}")
        await bot.db.update_room_state(channel.id, user_limit=next_limit)
        await bot.db.upsert_user_preferences(member.guild.id, member.id, user_limit=next_limit)
    LOGGER.info("%s set room %s limit to %s", member, channel.id, next_limit)
    return "Лимит убран." if next_limit == 0 else f"Лимит установлен: {next_limit}."


async def set_bitrate(bot: "PrivateVoiceBot", member: discord.Member, kbps: int) -> str:
    room, channel = await get_owned_room(bot, member)
    require_bot_permissions(member.guild, manage_channels=True)
    bitrate = normalize_bitrate(member.guild, kbps)
    async with get_room_lock(bot, channel.id):
        await channel.edit(bitrate=bitrate, reason=f"Private voice bitrate by {member}")
        await bot.db.update_room_state(channel.id, bitrate=bitrate)
        await bot.db.upsert_user_preferences(member.guild.id, member.id, bitrate=bitrate)
    LOGGER.info("%s set room %s bitrate to %s", member, channel.id, bitrate)
    return f"Bitrate установлен: {bitrate // 1000} kbps."


async def permit_user(bot: "PrivateVoiceBot", owner: discord.Member, target: discord.Member) -> str:
    room, channel = await get_owned_room(bot, owner)
    require_bot_permissions(owner.guild, manage_channels=True)
    if target.bot:
        raise VoiceControlError("Боту не нужно выдавать персональный доступ.")
    async with get_room_lock(bot, channel.id):
        await bot.db.set_channel_permission(channel.id, target.id, "allow")
        await bot.db.set_preference_permission(owner.guild.id, owner.id, target.id, "allow")
        latest = await bot.db.get_voice_channel(channel.id)
        if latest is not None:
            await apply_room_permission_state(bot, channel, latest, reason=f"Private voice permit by {owner}")
    LOGGER.info("%s permitted %s in room %s", owner, target, channel.id)
    return f"{target.mention} теперь может зайти даже в закрытую комнату."


async def reject_user(bot: "PrivateVoiceBot", owner: discord.Member, target: discord.Member) -> str:
    room, channel = await get_owned_room(bot, owner)
    require_bot_permissions(owner.guild, manage_channels=True, move_members=True)
    if target.bot:
        raise VoiceControlError("Нельзя добавить бота в blacklist.")
    if target.id == owner.id:
        raise VoiceControlError("Нельзя запретить вход владельцу комнаты.")
    async with get_room_lock(bot, channel.id):
        await bot.db.set_channel_permission(channel.id, target.id, "block")
        await bot.db.set_preference_permission(owner.guild.id, owner.id, target.id, "block")
        latest = await bot.db.get_voice_channel(channel.id)
        if latest is not None:
            await apply_room_permission_state(bot, channel, latest, reason=f"Private voice reject by {owner}")
        if target.voice and target.voice.channel and target.voice.channel.id == channel.id:
            require_bot_can_manage_member(target)
            await target.move_to(None, reason=f"Rejected from private voice by {owner}")
    LOGGER.info("%s rejected %s from room %s", owner, target, channel.id)
    return f"{target.mention} больше не может подключаться к комнате."


async def transfer_ownership(bot: "PrivateVoiceBot", owner: discord.Member, target: discord.Member) -> str:
    room, channel = await get_owned_room(bot, owner)
    if target.bot:
        raise VoiceControlError("Нельзя передать комнату боту.")
    if target.id == owner.id:
        raise VoiceControlError("Вы уже владелец этой комнаты.")
    if target not in channel.members:
        raise VoiceControlError("Передать комнату можно только участнику этой комнаты.")
    async with get_room_lock(bot, channel.id):
        await bot.db.update_room_state(channel.id, owner_id=target.id)
        latest = await bot.db.get_voice_channel(channel.id)
        if latest is not None:
            await apply_room_permission_state(bot, channel, latest, reason=f"Private voice ownership transfer by {owner}")
    LOGGER.info("%s transferred room %s to %s", owner, channel.id, target)
    return f"Владелец комнаты теперь {target.mention}."


async def claim_room(bot: "PrivateVoiceBot", member: discord.Member) -> str:
    room, channel = await get_member_room(bot, member)
    if member not in channel.members:
        raise VoiceControlError("Забрать можно только комнату, в которой вы сейчас находитесь.")
    current_owner = member.guild.get_member(room.owner_id)
    if current_owner is not None and current_owner in channel.members:
        raise VoiceControlError("Текущий владелец находится в комнате, Claim запрещён.")
    async with get_room_lock(bot, channel.id):
        latest = await bot.db.get_voice_channel(channel.id)
        if latest is None:
            raise VoiceControlError("Комната уже не активна.")
        latest_owner = member.guild.get_member(latest.owner_id)
        if latest_owner is not None and latest_owner in channel.members:
            raise VoiceControlError("Текущий владелец вернулся в комнату, Claim запрещён.")
        await bot.db.update_room_state(channel.id, owner_id=member.id)
        claimed = await bot.db.get_voice_channel(channel.id)
        if claimed is not None:
            await apply_room_permission_state(bot, channel, claimed, reason=f"Private voice claimed by {member}")
    LOGGER.info("%s claimed room %s", member, channel.id)
    return f"{member.mention} теперь владелец комнаты."


async def kick_user(bot: "PrivateVoiceBot", owner: discord.Member, target: discord.Member) -> str:
    room, channel = await get_owned_room(bot, owner)
    require_bot_permissions(owner.guild, move_members=True)
    if target.id == owner.id:
        raise VoiceControlError("Нельзя выгнать владельца через его собственную панель.")
    if target not in channel.members:
        raise VoiceControlError("Этот пользователь не находится в вашей комнате.")
    require_bot_can_manage_member(target)
    await target.move_to(None, reason=f"Kicked from private voice by {owner}")
    LOGGER.info("%s kicked %s from room %s", owner, target, channel.id)
    return f"{target.mention} отключён от комнаты."


async def set_member_mute(bot: "PrivateVoiceBot", owner: discord.Member, target: discord.Member, muted: bool) -> str:
    room, channel = await get_owned_room(bot, owner)
    require_bot_permissions(owner.guild, mute_members=True)
    if target.id == owner.id:
        raise VoiceControlError("Нельзя заглушить владельца через его собственную панель.")
    if target not in channel.members:
        raise VoiceControlError("Этот пользователь не находится в вашей комнате.")
    require_bot_can_manage_member(target)
    await target.edit(mute=muted, reason=f"Private voice {'mute' if muted else 'unmute'} by {owner}")
    LOGGER.info("%s %s %s in room %s", owner, "muted" if muted else "unmuted", target, channel.id)
    return f"{target.mention} заглушён." if muted else f"С {target.mention} снят mute."


async def set_member_deafen(bot: "PrivateVoiceBot", owner: discord.Member, target: discord.Member, deafened: bool) -> str:
    room, channel = await get_owned_room(bot, owner)
    require_bot_permissions(owner.guild, deafen_members=True)
    if target.id == owner.id:
        raise VoiceControlError("Нельзя deafen владельца через его собственную панель.")
    if target not in channel.members:
        raise VoiceControlError("Этот пользователь не находится в вашей комнате.")
    require_bot_can_manage_member(target)
    await target.edit(deafen=deafened, reason=f"Private voice {'deafen' if deafened else 'undeafen'} by {owner}")
    LOGGER.info("%s %s %s in room %s", owner, "deafened" if deafened else "undeafened", target, channel.id)
    return f"{target.mention} теперь не слышит комнату." if deafened else f"{target.mention} снова слышит комнату."


async def delete_room(bot: "PrivateVoiceBot", owner: discord.Member) -> str:
    room, channel = await get_owned_room(bot, owner)
    require_bot_permissions(owner.guild, manage_channels=True)
    async with get_room_lock(bot, channel.id):
        await channel.delete(reason=f"Private voice deleted by owner {owner}")
        await bot.db.delete_voice_channel(channel.id)
        await bot.db.clear_user_preferred_name(room.guild_id, room.owner_id)
    LOGGER.info("%s deleted room %s", owner, channel.id)
    return "Комната удалена."


async def delete_room_by_channel(bot: "PrivateVoiceBot", channel: discord.VoiceChannel, reason: str) -> None:
    async with get_room_lock(bot, channel.id):
        room = await bot.db.get_voice_channel(channel.id)
        if room is None:
            return
        await channel.delete(reason=reason)
        await bot.db.delete_voice_channel(channel.id)
        await bot.db.clear_user_preferred_name(room.guild_id, room.owner_id)
    LOGGER.info("Deleted temporary room %s: %s", channel.id, reason)


async def create_private_room(bot: "PrivateVoiceBot", member: discord.Member) -> None:
    settings = await bot.db.get_guild_settings(member.guild.id)
    if settings is None:
        return
    if member.voice is None or member.voice.channel is None or member.voice.channel.id != settings.creator_channel_id:
        return

    require_bot_permissions(
        member.guild,
        manage_channels=True,
        view_channel=True,
        connect=True,
        speak=True,
        use_voice_activation=True,
        stream=True,
        move_members=True,
    )
    lock = get_member_create_lock(bot, member.guild.id, member.id)
    async with lock:
        if member.voice is None or member.voice.channel is None or member.voice.channel.id != settings.creator_channel_id:
            return

        existing = await bot.db.get_owner_room(member.guild.id, member.id)
        if existing:
            existing_channel = member.guild.get_channel(existing.channel_id)
            if isinstance(existing_channel, discord.VoiceChannel):
                await member.move_to(existing_channel, reason="Moved to existing private room")
                return
            await bot.db.delete_voice_channel(existing.channel_id)

        category = member.guild.get_channel(settings.category_id)
        if not isinstance(category, discord.CategoryChannel):
            LOGGER.warning("Configured category %s is missing in guild %s", settings.category_id, member.guild.id)
            return

        prefs = await bot.db.get_user_preferences(member.guild.id, member.id)
        locked = prefs.privacy_mode in {"locked", "locked_hidden"}
        hidden = prefs.privacy_mode in {"hidden", "locked_hidden"}
        bitrate = min(prefs.bitrate or DEFAULT_ROOM_BITRATE, int(member.guild.bitrate_limit))
        user_limit = clamp_user_limit(prefs.user_limit)

        allowed_members = [
            saved_member
            for user_id in await bot.db.get_preference_permissions(member.guild.id, member.id, "allow")
            if (saved_member := member.guild.get_member(user_id)) is not None
        ]
        blocked_members = [
            saved_member
            for user_id in await bot.db.get_preference_permissions(member.guild.id, member.id, "block")
            if (saved_member := member.guild.get_member(user_id)) is not None
        ]
        verified_role = get_verified_role(member.guild, bot.config.verified_role_id)

        channel = await category.create_voice_channel(
            name=room_name_for(member),
            overwrites=build_private_room_overwrites(
                member.guild,
                verified_role,
                member,
                locked=locked,
                hidden=hidden,
                allowed_members=allowed_members,
                blocked_members=blocked_members,
            ),
            user_limit=user_limit,
            bitrate=bitrate,
            reason=f"Private voice room created for {member}",
        )
        await bot.db.create_voice_channel(
            member.guild.id,
            channel.id,
            member.id,
            locked=locked,
            hidden=hidden,
            user_limit=user_limit,
            bitrate=bitrate,
        )
        await _apply_saved_user_permissions(bot, member, channel)

        try:
            await member.move_to(channel, reason="Join to Create private voice room")
        except (discord.Forbidden, discord.HTTPException):
            await bot.db.delete_voice_channel(channel.id)
            await channel.delete(reason="Owner could not be moved into private room")
            raise

        LOGGER.info("Created private room %s for %s in guild %s", channel.id, member, member.guild.id)


async def _apply_saved_user_permissions(bot: "PrivateVoiceBot", owner: discord.Member, channel: discord.VoiceChannel) -> None:
    allowed_ids = await bot.db.get_preference_permissions(owner.guild.id, owner.id, "allow")
    blocked_ids = await bot.db.get_preference_permissions(owner.guild.id, owner.id, "block")

    for user_id in allowed_ids:
        member = owner.guild.get_member(user_id)
        if member and not member.bot:
            await bot.db.set_channel_permission(channel.id, member.id, "allow")

    for user_id in blocked_ids:
        member = owner.guild.get_member(user_id)
        if member and not member.bot and member.id != owner.id:
            await bot.db.set_channel_permission(channel.id, member.id, "block")


async def cleanup_guild_rooms(bot: "PrivateVoiceBot", guild: discord.Guild, *, delete_non_empty: bool = False) -> tuple[int, int]:
    removed_channels = 0
    removed_records = 0
    rooms = await bot.db.list_voice_channels(guild.id)
    for room in rooms:
        channel = guild.get_channel(room.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await bot.db.delete_voice_channel(room.channel_id)
            removed_records += 1
            continue
        if not channel.members or delete_non_empty:
            await delete_room_by_channel(bot, channel, "Private voice cleanup")
            removed_channels += 1
    return removed_channels, removed_records


async def enforce_blocked_member(bot: "PrivateVoiceBot", member: discord.Member, channel: discord.VoiceChannel) -> None:
    room = await bot.db.get_voice_channel(channel.id)
    if room is None:
        return
    blocked = await bot.db.get_channel_permissions(channel.id, "block")
    if member.id in blocked and member.id != room.owner_id:
        require_bot_permissions(member.guild, move_members=True)
        await member.move_to(None, reason="Blocked from private voice room")
