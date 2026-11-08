#!/usr/bin/env python3
"""
Автовыдача роли «👋 Участник» новичкам.

Логика:
  • зашёл на сервер и правила уже приняты  → роль выдаётся сразу;
  • зашёл и висит на экране правил (pending) → роль выдаётся в момент,
    когда он поставил галочки и нажал «Принять правила»;
  • каждый вход пишется в #логи.

Роль выдаётся один раз и не трогает другие роли. Ботов пропускает.

Требует SERVER MEMBERS INTENT (Developer Portal → Bot → Privileged Gateway Intents).

Как отдельный процесс:
    DISCORD_TOKEN=... GUILD_ID=... python join_gate.py

Или вместе с остальным — automod_bot.py подхватывает модуль сам.
"""
from __future__ import annotations

import os

import discord

MEMBER_ROLE = os.getenv("MEMBER_ROLE", "👋 Участник")
WELCOME_CHANNEL = os.getenv("WELCOME_CHANNEL", "💬│флудилка")
LOG_CHANNEL = os.getenv("LOG_CHANNEL", "📋│логи")


async def _log(guild: discord.Guild, text: str) -> None:
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch:
        try:
            await ch.send(f"🤖 {text}")
        except discord.HTTPException:
            pass


async def grant(member: discord.Member, why: str) -> None:
    role = discord.utils.get(member.guild.roles, name=MEMBER_ROLE)
    if role is None:
        print(f"[join_gate] нет роли «{MEMBER_ROLE}»")
        return
    if role in member.roles:
        return
    try:
        await member.add_roles(role, reason=f"авто: {why}")
        await _log(member.guild, f"✅ {member.mention} — выдана роль «{MEMBER_ROLE}» ({why})")
        print(f"[join_gate] роль выдана: {member} ({why})")
        ch = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL)
        if ch:
            await ch.send(
                f"👋 {member.mention} теперь **{MEMBER_ROLE}**. "
                f"Ищи пати в #поиск-игроков, анонсы эфиров — в #анонсы-стримов."
            )
    except discord.HTTPException as e:
        print("[join_gate] не смог выдать роль:", e)


def setup(client: discord.Client) -> None:
    """Совместимость: хуки вызывает automod_bot из своих обработчиков."""
    return


async def handle_member_join(member: discord.Member) -> None:
    if member.bot:
        return
    await _log(member.guild, f"📥 {member.mention} зашёл на сервер")
    if not member.pending:
        await grant(member, "вошёл на сервер")


async def handle_member_update(before: discord.Member, after: discord.Member) -> None:
    # момент, когда человек принял правила на экране верификации
    if before.pending and not after.pending:
        await grant(after, "принял правила")


if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.members = True
    own = discord.Client(intents=intents)
    setup(own)

    @own.event
    async def on_ready() -> None:
        print(f"[join_gate] на связи: {own.user} | серверов: {len(own.guilds)}")

    token = os.getenv("DISCORD_TOKEN", "")
    if not token:
        raise SystemExit("❌ Нужен DISCORD_TOKEN")
    try:
        own.run(token)
    except discord.PrivilegedIntentsRequired:
        print("❌ Включите SERVER MEMBERS INTENT в Developer Portal → Bot → Privileged Gateway Intents")
