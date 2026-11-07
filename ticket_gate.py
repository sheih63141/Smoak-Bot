#!/usr/bin/env python3
"""
Тикеты на реакциях — три направления с одной панели, БЕЗ веток.

В канале «🎫-подать-тикет» висит панель с тремя реакциями:

  🎫 → вопрос хелперу       → приватный канал в «🎫 ТИКЕТЫ»
                              видят: автор + 🧰 Хелпер / 🔨 Модератор / 🛡 Администратор
  📋 → обращение к админам  → приватный канал в «📋 ОБРАЩЕНИЯ»
                              видят: автор + 🔨 Модератор / 🛡 Администратор (хелпер НЕ видит)
  📝 → заявка в команду     → приватный канал в «📝 ЗАЯВКИ»
                              видят: автор + 🔨 Модератор / 🛡 Администратор (хелпер НЕ видит)

Закрытие: реакция 🔒 в тикете (доступна автору и команде) — переписка
уходит в #логи файлом .txt, канал удаляется. Либо просто удалить канал.
"""
from __future__ import annotations

import asyncio
import io

import discord

PANEL_CHANNEL = "🎫-подать-тикет"
LOG_CHANNEL = "логи"

QUESTION_EMOJI = "🎫"
ADMIN_EMOJI = "📋"
APPLY_EMOJI = "📝"
CLOSE_EMOJI = "🔒"

QUESTION_STAFF = ["🧰 Хелпер", "🔨 Модератор", "🛡 Администратор"]
ADMIN_STAFF = ["🔨 Модератор", "🛡 Администратор"]

# emoji -> направление
ROUTES = {
    QUESTION_EMOJI: {
        "kind": "вопрос",
        "category": "🎫 ТИКЕТЫ",
        "prefix": "вопрос",
        "staff": QUESTION_STAFF,
    },
    ADMIN_EMOJI: {
        "kind": "обращение",
        "category": "📋 ОБРАЩЕНИЯ",
        "prefix": "обращение",
        "staff": ADMIN_STAFF,
    },
    APPLY_EMOJI: {
        "kind": "заявка",
        "category": "📝 ЗАЯВКИ",
        "prefix": "заявка",
        "staff": ADMIN_STAFF,
    },
}

PANEL_TEXT = (
    "**🎟 Тикеты и заявки**\n"
    "Поставь реакцию — откроется личный канал, его увидишь только ты и команда.\n\n"
    f"{QUESTION_EMOJI} — **вопрос хелперу**: что-то не работает, как получить роль, помощь по серверу\n"
    f"{ADMIN_EMOJI} — **обращение к администрации**: жалоба на участника или модератора, апелляция мута/бана\n"
    f"{APPLY_EMOJI} — **заявка в команду**: хочу стать модератором или хелпером\n\n"
    "-# Один тикет на одну тему. Закрыть свой тикет — реакция 🔒 внутри него."
)

INTROS = {
    "вопрос": (
        "**Тикет хелперу.**\n"
        "Опиши вопрос подробно: что случилось, где, приложи скриншоты и ники.\n"
        "Хелпер ответит здесь.\n\n"
        f"Когда вопрос решён — поставь {CLOSE_EMOJI} на это сообщение."
    ),
    "обращение": (
        "**Обращение к администрации.**\n"
        "Напиши: кто, когда, что произошло, ссылки на сообщения или скриншоты.\n"
        "Если это апелляция — объясни, почему считаешь наказание несправедливым.\n\n"
        f"Когда вопрос решён — поставь {CLOSE_EMOJI} на это сообщение."
    ),
    "заявка": (
        "**Заявка в команду.** Ответь одним сообщением:\n"
        "• кем хочешь быть: модератор или хелпер\n"
        "• возраст и часовой пояс\n"
        "• сколько времени бываешь на сервере\n"
        "• опыт модерации, если был\n"
        "• почему хочешь в команду\n\n"
        f"Когда закончишь — поставь {CLOSE_EMOJI} на это сообщение."
    ),
}


def _safe(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum() or ch in "-_")[:18] or "user"


async def _log(guild: discord.Guild, text: str) -> None:
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch:
        try:
            await ch.send(text)
        except discord.HTTPException:
            pass


async def _category(guild: discord.Guild, name: str) -> discord.CategoryChannel:
    cat = discord.utils.get(guild.categories, name=name)
    if cat is not None:
        return cat
    return await guild.create_category(
        name,
        overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
        reason="категория для тикетов",
    )


async def create_ticket(guild: discord.Guild, member: discord.Member, emoji: str):
    """Создаёт приватный канал-тикет (или возвращает уже открытый)."""
    route = ROUTES.get(emoji)
    if route is None:
        return None

    category = await _category(guild, route["category"])
    base = f"{route['prefix']}-{_safe(member.name)}"

    for ch in category.text_channels:
        if ch.name.startswith(base):
            try:
                await ch.send(f"{member.mention}, твой тикет уже открыт — пиши здесь.")
            except discord.HTTPException:
                pass
            return ch

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                            read_message_history=True, attach_files=True,
                                            embed_links=True, add_reactions=True),
    }
    for role_name in route["staff"]:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_messages=True, attach_files=True, add_reactions=True)
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_channels=True, manage_messages=True, add_reactions=True)

    channel = await guild.create_text_channel(
        base, category=category,
        topic=f"{route['kind']} | {member} ({member.id})",
        overwrites=overwrites,
        reason=f"тикет по реакции {emoji}",
    )

    ping = " ".join(r.mention for r in
                    (discord.utils.get(guild.roles, name=n) for n in route["staff"]) if r)
    msg = await channel.send(f"{member.mention} {ping}\n\n{INTROS[route['kind']]}")
    try:
        await msg.add_reaction(CLOSE_EMOJI)
        await msg.pin()
    except discord.HTTPException:
        pass

    await _log(guild, f"{emoji} Открыт тикет {channel.mention} ({route['kind']}) от {member.mention}")
    return channel


async def close_ticket(channel: discord.TextChannel, by: discord.Member) -> None:
    lines = []
    try:
        async for m in channel.history(limit=500, oldest_first=True):
            stamp = m.created_at.strftime("%d.%m.%Y %H:%M")
            lines.append(f"[{stamp}] {m.author.display_name}: {m.content}")
            for a in m.attachments:
                lines.append(f"    вложение: {a.url}")
    except discord.HTTPException:
        pass

    logs = discord.utils.get(channel.guild.text_channels, name=LOG_CHANNEL)
    if logs and lines:
        data = io.BytesIO("\n".join(lines).encode("utf-8"))
        try:
            await logs.send(f"🔒 Тикет `{channel.name}` закрыт ({by.mention})",
                            file=discord.File(data, filename=f"{channel.name}.txt"))
        except discord.HTTPException as e:
            print("[ticket]", e)

    try:
        await channel.send(f"🔒 Тикет закрыт ({by.mention}). Канал удалится через 5 секунд.")
    except discord.HTTPException:
        pass
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"закрыто: {by}")
    except discord.HTTPException as e:
        print("[ticket]", e)


def _staff_names(channel: discord.TextChannel) -> list[str]:
    cat_name = getattr(channel.category, "name", "")
    for route in ROUTES.values():
        if route["category"] == cat_name:
            return route["staff"]
    return []


async def handle_raw_reaction_add(client: discord.Client, payload) -> bool:
    """True — реакция обработана этим модулем."""
    if payload.guild_id is None:
        return False
    guild = client.get_guild(payload.guild_id)
    if guild is None:
        return False
    emoji = str(payload.emoji)
    if emoji not in (*ROUTES, CLOSE_EMOJI):
        return False

    channel = guild.get_channel(payload.channel_id)
    if channel is None:
        return False
    try:
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
    except discord.HTTPException:
        return True
    if member is None or member.bot:
        return True

    # --- панель: открыть тикет ---
    panel = discord.utils.get(guild.text_channels, name=PANEL_CHANNEL)
    if panel is not None and channel.id == panel.id:
        created = await create_ticket(guild, member, emoji)
        if created:
            print(f"[ticket] {emoji} → {created.name} ({member})")
        return True

    # --- 🔒 внутри тикета: закрыть ---
    if emoji == CLOSE_EMOJI and isinstance(channel, discord.TextChannel):
        staff = _staff_names(channel)
        if not staff:
            return False
        role_names = {r.name for r in member.roles}
        author_ok = channel.topic and f"({member.id})" in channel.topic
        if not (role_names & set(staff)) and not author_ok:
            return True
        await close_ticket(channel, member)
        return True

    return False


async def ensure_panel(client: discord.Client) -> None:
    for guild in client.guilds:
        ch = discord.utils.get(guild.text_channels, name=PANEL_CHANNEL)
        if ch is None:
            print(f"[ticket] нет канала «{PANEL_CHANNEL}»")
            continue
        msgs = [m async for m in ch.history(limit=20) if m.author.id == client.user.id]
        if msgs:
            msg = msgs[-1]
            if (msg.content or "") != PANEL_TEXT:
                try:
                    await msg.edit(content=PANEL_TEXT)
                except discord.HTTPException:
                    pass
        else:
            msg = await ch.send(PANEL_TEXT)
            try:
                await msg.pin(reason="панель тикетов")
            except discord.HTTPException:
                pass
        have = {str(r.emoji) for r in msg.reactions}
        for emoji in ROUTES:
            if emoji not in have:
                try:
                    await msg.add_reaction(emoji)
                except discord.HTTPException:
                    pass
        print(f"[ticket] панель готова: {' '.join(ROUTES)}")


def setup(client: discord.Client) -> None:
    """Кнопок нет — совместимость с automod_bot."""
    return


async def on_ready(client: discord.Client) -> None:
    try:
        await ensure_panel(client)
    except Exception as e:
        print("[ticket]", repr(e))
