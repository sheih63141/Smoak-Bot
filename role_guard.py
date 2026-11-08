#!/usr/bin/env python3
"""
Сторож роли «👑 Владелец».

Раз в GUARD_SECONDS секунд бот проверяет участника через REST (не нужен
Server Members Intent) и, если роли нет, сразу возвращает её. Дополнительно
ловится событие on_member_update — мгновенно, когда Members Intent включён.

Кого сторожим и какую роль — через переменные окружения:
    GUARD_USER_ID=970550805277081601   .dimas.gg
    GUARD_ROLE_ID=1568626336606593185  👑 Владелец
    GUARD_SECONDS=5                    интервал проверки
"""
from __future__ import annotations

import asyncio
import os
import time

import discord

GUILD_ID = int(os.getenv("GUILD_ID", "1568607492991353053"))
GUARD_USER_ID = int(os.getenv("GUARD_USER_ID", "970550805277081601"))
GUARD_ROLE_ID = int(os.getenv("GUARD_ROLE_ID", "1568626336606593185"))
GUARD_SECONDS = max(2, int(os.getenv("GUARD_SECONDS", "5")))
LOG_CHANNEL = "📋│логи"

_last: dict[int, float] = {}


def _role(guild: discord.Guild):
    return (guild.get_role(GUARD_ROLE_ID)
            or discord.utils.get(guild.roles, name="👑 Владелец"))


async def restore(client, guild: discord.Guild, member=None, why: str = "пропала") -> bool:
    """Вернуть роль, если её нет. Возвращает True, если действительно вернули."""
    role = _role(guild)
    if role is None:
        return False
    if member is None:
        try:
            member = await guild.fetch_member(GUARD_USER_ID)
        except (discord.NotFound, discord.HTTPException):
            return False
    if role in member.roles:
        return False
    # не шлём два восстановления подряд (watch + on_member_update)
    now = time.monotonic()
    if now - _last.get(guild.id, 0) < 3:
        return False
    try:
        await member.add_roles(role, reason="сторож: роль Владельца возвращена")
    except discord.HTTPException as e:
        print("[guard] не смог вернуть роль:", e)
        return False
    _last[guild.id] = now
    print(f"[guard] 👑 Владелец возвращён: {member} ({why})")
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch:
        try:
            await ch.send(f"👑 Роль «Владелец» возвращена {member.mention} ({why}).")
        except discord.HTTPException:
            pass
    return True


async def watch(client: discord.Client) -> None:
    """Фоновая проверка — работает даже с выключенным Members Intent."""
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            guild = client.get_guild(GUILD_ID) or (client.guilds[0] if client.guilds else None)
            if guild is not None:
                await restore(client, guild, why="снята или пропала")
        except Exception as e:
            print("[guard] watch:", repr(e))
        await asyncio.sleep(GUARD_SECONDS)


async def handle_member_update(client: discord.Client, before, after) -> None:
    """Мгновенная реакция на снятие роли (нужен Server Members Intent)."""
    if after.id != GUARD_USER_ID:
        return
    role = _role(after.guild)
    if role is None or role in after.roles:
        return
    await restore(client, after.guild, after, why="снята вручную")
