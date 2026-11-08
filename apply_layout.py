#!/usr/bin/env python3
"""
Дизайн сервера SmoakTeam в стиле CS2-сообщества (как на референсе, без GTA).

Один прогон приводит сервер к нужному виду: переименовывает каналы на месте
(история сообщений сохраняется), создаёт недостающие, раскладывает по категориям.
Повторный запуск ничего не ломает.
"""
from __future__ import annotations

import asyncio
import os

import discord

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = 1568607492991353053

# (старое имя или None, новое имя, категория, тип: text/voice/category)
CATEGORIES = [
    ("📌 СТАРТ", "📢 ИНФОРМАЦИЯ"),
    ("💬 ОБЩЕНИЕ", "💬 CHAT"),
    ("🎫 ПОДДЕРЖКА", "🎫 ПОДДЕРЖКА"),
    (None, "🔊 ОБЩЕСТВЕННОЕ МЕСТО"),
    (None, "🔫 COUNTER-STRIKE"),
    (None, "🎧 ЧИЛЛ"),
    ("🔒 ПРИВАТНОЕ", "🔒 ПРИВАТНОЕ"),
    ("🛠 КОМАНДА (скрыто)", "🛠 КОМАНДА (скрыто)"),
    ("💤 AFK", "😴 AFK"),
    ("🔇 МУТ", "🔇 МУТ"),
    ("📢 НОВОСТИ", None),          # категорию убираем, каналы переезжают в ИНФОРМАЦИЮ
    ("🔊 ГОЛОС", None),            # переименовываем в ОБЩЕСТВЕННОЕ МЕСТО отдельно
]

TEXT = [
    ("правила", "📕│правила", "📢 ИНФОРМАЦИЯ", True),
    ("получить-роль", "🔑│получить-роль", "📢 ИНФОРМАЦИЯ", False),
    (None, "👋│новенькие", "📢 ИНФОРМАЦИЯ", True),
    (None, "🎁│розыгрыш", "📢 ИНФОРМАЦИЯ", False),
    ("анонсы-стримов", "📺│стримы", "📢 ИНФОРМАЦИЯ", True),
    (None, "▶️│ютуб", "📢 ИНФОРМАЦИЯ", False),
    ("объявления", "📢│объявления", "📢 ИНФОРМАЦИЯ", True),
    ("общий-чат", "💬│флудилка", "💬 CHAT", False),
    ("мемы-и-клипы", "🖼│мемы-и-клипы", "💬 CHAT", False),
    ("стрим-обсуждение", "🎬│стрим-обсуждение", "💬 CHAT", False),
    ("🎫-подать-тикет", "🎫│подать-тикет", "🎫 ПОДДЕРЖКА", False),
    ("мод-чат", "🛡│мод-чат", "🛠 КОМАНДА (скрыто)", False),
    ("логи", "📋│логи", "🛠 КОМАНДА (скрыто)", False),
    ("заявки", "📝│заявки", "🛠 КОМАНДА (скрыто)", False),
    ("приват-чат", "💬│приват-чат", "🔒 ПРИВАТНОЕ", False),
]

VOICE = [
    ("🔊 Общий", "🚀 France - Paris", "🔊 ОБЩЕСТВЕННОЕ МЕСТО", 0),
    (None, "🗽 Нью-Йорк - Walk street", "🔊 ОБЩЕСТВЕННОЕ МЕСТО", 0),
    (None, "🏜 Дубай - Downtown", "🔊 ОБЩЕСТВЕННОЕ МЕСТО", 0),
    ("🔫 Пати 1", "🟢 Major players CS2", "🔫 COUNTER-STRIKE", 5),
    ("🔫 Пати 2", "🟠 Premier 5x5", "🔫 COUNTER-STRIKE", 5),
    ("🔫 Пати 3", "🔴 Faceit", "🔫 COUNTER-STRIKE", 5),
    ("🎧 Чилл", "🎧 Чилл 1", "🎧 ЧИЛЛ", 0),
    (None, "🎧 Чилл 2", "🎧 ЧИЛЛ", 0),
    ("🎧 Стрим-комната", "🎬 Стрим-комната", "🎧 ЧИЛЛ", 0),
    ("🎬 Стримерская", "🎬 Стримерская", "🔒 ПРИВАТНОЕ", 0),
    ("👥 Тим-1", "👥 Тим-1", "🔒 ПРИВАТНОЕ", 0),
    ("👥 Тим-2", "👥 Тим-2", "🔒 ПРИВАТНОЕ", 0),
    ("💎 ВИП-комната", "💎 ВИП-комната", "🔒 ПРИВАТНОЕ", 0),
    ("AFK", "😴 AFK", "😴 AFK", 0),
    ("В муте", "В муте", "🔇 МУТ", 2),
]


async def main() -> None:
    client = discord.Client(intents=discord.Intents.none())
    await client.login(TOKEN)
    guild = await client.fetch_guild(GUILD_ID)

    # 1. категории
    cats = {}
    for old, new in CATEGORIES:
        if new is None:
            continue
        cat = discord.utils.get(guild.categories, name=new)
        if cat is None and old:
            cat = discord.utils.get(guild.categories, name=old)
            if cat is not None:
                await cat.edit(name=new, reason="редизайн")
                print(f"  категория {old} → {new}")
        if cat is None:
            cat = await guild.create_category(new, reason="редизайн")
            print(f"  категория создана: {new}")
        cats[new] = cat
    # старое имя 🔊 ГОЛОС → ОБЩЕСТВЕННОЕ МЕСТО
    old_voice = discord.utils.get(guild.categories, name="🔊 ГОЛОС")
    if old_voice is not None:
        await old_voice.edit(name="🔊 ОБЩЕСТВЕННОЕ МЕСТО", reason="редизайн")
        cats["🔊 ОБЩЕСТВЕННОЕ МЕСТО"] = old_voice
        print("  категория 🔊 ГОЛОС → 🔊 ОБЩЕСТВЕННОЕ МЕСТО")

    # 2. текстовые
    for old, new, cat, readonly in TEXT:
        ch = discord.utils.get(guild.text_channels, name=new)
        if ch is None and old:
            ch = discord.utils.get(guild.text_channels, name=old)
            if ch is not None:
                await ch.edit(name=new, category=cats[cat], reason="редизайн")
                print(f"  текст {old} → {new}")
        if ch is None:
            ch = await guild.create_text_channel(new, category=cats[cat], reason="редизайн")
            print(f"  текст создан: {new}")
        elif ch.category_id != cats[cat].id:
            await ch.edit(category=cats[cat], reason="редизайн")
        if readonly:
            ow = ch.overwrites_for(guild.default_role)
            if ow.send_messages is not False:
                await ch.set_permissions(guild.default_role, send_messages=False, reason="только чтение")

    # 3. голосовые
    for old, new, cat, limit in VOICE:
        ch = discord.utils.get(guild.voice_channels, name=new)
        if ch is None and old:
            ch = discord.utils.get(guild.voice_channels, name=old)
            if ch is not None:
                await ch.edit(name=new, category=cats[cat], user_limit=limit, reason="редизайн")
                print(f"  войс {old} → {new}")
        if ch is None:
            ch = await guild.create_voice_channel(new, category=cats[cat], user_limit=limit, reason="редизайн")
            print(f"  войс создан: {new}")
        elif ch.category_id != cats[cat].id:
            await ch.edit(category=cats[cat], reason="редизайн")

    # 4. пустые категории — прочь
    for cat in list(guild.categories):
        if not cat.channels:
            old = discord.utils.get(guild.categories, name="📢 НОВОСТИ")
            if cat.name in ("📢 НОВОСТИ",) or old:
                pass
    for name in ("📢 НОВОСТИ",):
        cat = discord.utils.get(guild.categories, name=name)
        if cat is not None:
            for ch in cat.channels:
                target = discord.utils.get(guild.categories, name="📢 ИНФОРМАЦИЯ")
                if target:
                    await ch.edit(category=target, reason="редизайн")
            await cat.delete(reason="редизайн: пустая категория")
            print("  категория 📢 НОВОСТИ удалена")

    print("\nитог:")
    guild = await client.fetch_guild(GUILD_ID)
    chans = await guild.fetch_channels()
    for c in sorted(chans, key=lambda x: (x.category.position if x.category else 99, x.position)):
        if isinstance(c, discord.CategoryChannel):
            print(f"  {c.name}")
        else:
            print(f"    └ {c.name}")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
