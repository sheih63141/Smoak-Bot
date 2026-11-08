#!/usr/bin/env python3
"""
УСТАРЕЛО: канал «получить-роль» удалён. Модуль не подключается к боту.
Роль «👋 Участник» выдаёт NickModal (slash_commands.py) после ввода ника с Твича.

Что делает:
  • держит в канале #получить-роль сообщение с кнопкой
    «✅ Я прочитал правила — выдать роль»;
  • по нажатию выдаёт роль 👋 Участник, пишет в #логи, приветствует;
  • повторное нажатие / уже выданная роль — вежливый ответ без дублей;
  • бот, у которого роль выше 👋 Участник, работает даже если человек
    зашёл давно и роль потерял.

Требует, чтобы бот был запущен (иначе кнопка не работает — выдавайте роль вручную).
Подключается к automod_bot.py автоматически: automod_bot.py → import role_gate.
"""
from __future__ import annotations

import os

import discord
from discord import ui

MEMBER_ROLE = os.getenv("MEMBER_ROLE", "👋 Участник")
RULES_CHANNEL = os.getenv("RULES_CHANNEL", "📕│правила")
CHECK = "✅"
GATE_EMOJI = CHECK
GATE_CHANNEL = os.getenv("GATE_CHANNEL", "🔑│получить-роль")
LOG_CHANNEL = os.getenv("LOG_CHANNEL", "📋│логи")

TEXT = (
    "**Получение роли**\n"
    "Поставь **✅** на это сообщение (или под правилами) — сразу получишь роль "
    "**👋 Участник** и откроется сервер."
)


def channel_rules(guild: discord.Guild) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name=RULES_CHANNEL)


async def rules_message(guild: discord.Guild) -> discord.Message | None:
    ch = channel_rules(guild)
    if ch is None:
        return None
    async for m in ch.history(limit=20):
        if m.author.id == guild.me.id and m.pinned:
            return m
    return None


async def has_check(guild: discord.Guild, member: discord.Member) -> bool:
    """Поставил ли человек ✅ под правилами."""
    msg = await rules_message(guild)
    if msg is None:
        return True  # правил нет — не блокируем
    for r in msg.reactions:
        if str(r.emoji) == CHECK:
            async for u in r.users():
                if u.id == member.id:
                    return True
    return False


async def handle_raw_reaction_add(client: discord.Client, payload) -> bool:
    """✅ в #правила или #получить-роль = роль участника. Возвращает True, если обработали."""
    if str(payload.emoji) != CHECK or payload.guild_id is None:
        return False
    guild = client.get_guild(payload.guild_id)
    if guild is None:
        return False

    gate_ch = discord.utils.get(guild.text_channels, name=GATE_CHANNEL)
    rules_ch = channel_rules(guild)
    allowed = {c.id for c in (gate_ch, rules_ch) if c}
    if payload.channel_id not in allowed:
        return False

    member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
    if member is None or member.bot:
        return True
    await grant(member, "поставил ✅")
    return True


async def grant(member: discord.Member, why: str) -> None:
    role = discord.utils.get(member.guild.roles, name=MEMBER_ROLE)
    if role is None or role in member.roles:
        return
    try:
        await member.add_roles(role, reason=f"гейт: {why}")
    except discord.HTTPException as e:
        print("[role_gate]", e)
        return
    logs = discord.utils.get(member.guild.text_channels, name=LOG_CHANNEL)
    if logs:
        try:
            await logs.send(f"🔓 {member.mention} — роль «{MEMBER_ROLE}» ({why})")
        except discord.HTTPException:
            pass


async def ensure_message(client: discord.Client) -> None:
    """Обновляет сообщение «Получение роли»: новый текст, без кнопок, с реакцией ✅."""
    for guild in client.guilds:
        ch = discord.utils.get(guild.text_channels, name=GATE_CHANNEL)
        if ch is None:
            continue
        msgs = [m async for m in ch.history(limit=20) if m.author.id == client.user.id]
        if msgs:
            msg = next((m for m in msgs if m.pinned), msgs[0])
            try:
                await msg.edit(content=TEXT, view=None)
                if not msg.pinned:
                    await msg.pin(reason="получение роли")
            except discord.HTTPException as e:
                print("[role_gate]", e)
        else:
            msg = await ch.send(TEXT)
            try:
                await msg.pin(reason="получение роли")
            except discord.HTTPException:
                pass
            print(f"[role_gate] сообщение опубликовано в #{GATE_CHANNEL}")

        if not any(str(r.emoji) == CHECK for r in msg.reactions):
            try:
                await msg.add_reaction(CHECK)
                print("[role_gate] ✅ добавлена в #получить-роль")
            except discord.HTTPException:
                pass

        rm = await rules_message(guild)
        if rm is not None and not any(str(r.emoji) == CHECK for r in rm.reactions):
            try:
                await rm.add_reaction(CHECK)
                print("[role_gate] ✅ добавлена в #правила")
            except discord.HTTPException:
                pass


async def _gate_message(client: discord.Client, guild: discord.Guild) -> discord.Message | None:
    ch = discord.utils.get(guild.text_channels, name=GATE_CHANNEL)
    if ch is None:
        return None
    async for m in ch.history(limit=10):
        if m.author.id == client.user.id and m.pinned:
            return m
    return None


def setup(client: discord.Client) -> None:
    """Совместимость: кнопок больше нет, всё на реакциях."""
    return


async def on_ready(client: discord.Client) -> None:
    """Хук: поставить кнопку, если её нет. Вызывает automod_bot из своего on_ready."""
    try:
        await ensure_message(client)
    except Exception as e:
        print("[role_gate]", repr(e))
