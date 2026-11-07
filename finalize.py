#!/usr/bin/env python3
"""
Дочистка сервера после setup_bot.py:
  1) удаляет старую (дублирующую) структуру каналов;
  2) включает защиту: AutoMod-правила, уровень верификации, фильтр контента;
  3) настраивает AFK-канал, уведомления, системный канал;
  4) печатает итоговую структуру и чек-лист того, что осталось руками.

Запуск: python finalize.py
"""
from __future__ import annotations

import os
import sys

import discord

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# Что считаем «старой структурой» и удаляем
LEGACY_CATEGORIES = ["~~~FLUD~~~", "~~~Counter Strike~~~"]
LEGACY_CHANNELS = ["чатикс", "клипы-со-стрима", "модерка", "КС"]

client = discord.Client(intents=discord.Intents.default())


@client.event
async def on_ready() -> None:
    g = client.get_guild(GUILD_ID)
    if not g:
        print("❌ Сервер не найден")
        await client.close()
        return
    print(f"Сервер: {g.name}\n")

    # ---------------------------------------------------------------- 1. Чистка
    print("--- удаление старой структуры ---")
    for name in LEGACY_CHANNELS:
        for ch in [c for c in g.channels if c.name == name and not isinstance(c, discord.CategoryChannel)]:
            try:
                await ch.delete(reason="finalize: чистка дублей структуры")
                print(f"  🗑 удалён канал #{name}")
            except discord.HTTPException as e:
                print(f"  ⚠️ #{name}: {e}")
    for name in LEGACY_CATEGORIES:
        for cat in [c for c in g.categories if c.name == name]:
            try:
                await cat.delete(reason="finalize: чистка дублей структуры")
                print(f"  🗑 удалена категория {name}")
            except discord.HTTPException as e:
                print(f"  ⚠️ {name}: {e}")

    # ------------------------------------------------- 2. Защита от спама/рейдов
    print("\n--- защита сервера ---")
    try:
        await g.edit(
            verification_level=discord.VerificationLevel.medium,
            explicit_content_filter=discord.ContentFilter.all_members,
            default_notifications=discord.NotificationLevel.only_mentions,
            afk_timeout=300,
            reason="finalize: базовая защита",
        )
        print("  ✅ уровень верификации: средний | фильтр контента: все участники | уведомления: только упоминания")
    except discord.HTTPException as e:
        print(f"  ⚠️ настройки сервера: {e}")

    afk = discord.utils.get(g.voice_channels, name="AFK")
    if afk:
        try:
            await g.edit(afk_channel=afk, reason="finalize: AFK")
            print("  ✅ AFK-канал: AFK (тайм-аут 5 мин)")
        except discord.HTTPException as e:
            print(f"  ⚠️ AFK: {e}")

    logs = discord.utils.get(g.text_channels, name="логи")
    alerts = [discord.AutoModRuleAction(channel_id=logs.id)] if logs else []

    async def make_rule(name, trigger, actions, enabled=True):
        existing = discord.utils.get(await g.fetch_automod_rules(), name=name)
        if existing:
            print(f"  ↻ правило «{name}» уже есть")
            return
        try:
            await g.create_automod_rule(name=name, trigger=trigger, actions=actions, enabled=enabled,
                                        event_type=discord.AutoModRuleEventType.message_send,
                                        reason="finalize: автомод")
            print(f"  ✅ правило «{name}»")
        except discord.HTTPException as e:
            print(f"  ⚠️ правило «{name}»: {e}")

    # спам одинаковыми сообщениями
    await make_rule(
        "Анти-спам",
        discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
        [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)] + alerts,
    )
    # запрещённые слова: мат, оскорбления, 18+
    presets = discord.AutoModPresets.all()
    await make_rule(
        "Запрещённые слова",
        discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.keyword_preset, presets=presets),
        [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)] + alerts,
    )
    # массовые пинги
    await make_rule(
        "Массовые пинги",
        discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.mention_spam, mention_limit=6),
        [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)] + alerts,
    )
    # приглашения на чужие серверы (кроме своих — см. allow_list)
    await make_rule(
        "Чужие инвайты",
        discord.AutoModTrigger(
            type=discord.AutoModRuleTriggerType.keyword,
            keyword_filter=[r"discord\.gg/\w+", r"discord\.com/invite/\w+", r"discordapp\.com/invite/\w+"],
            allow_list=[r"discord\.gg/" + s for s in []],
        ),
        [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)] + alerts,
    )

    # ----------------------------------------------------------- 3. Итог
    print("\n--- ИТОГОВАЯ СТРУКТУРА ---")
    for cat in sorted(g.categories, key=lambda c: c.position):
        hidden = not cat.permissions_for(g.default_role).view_channel
        print(f"{'🔒' if hidden else '📂'} {cat.name}")
        for ch in cat.channels:
            print(f"     {'🔈' if isinstance(ch, discord.VoiceChannel) else '#'} {ch.name}")
    loose = [c for c in g.channels if c.category is None and not isinstance(c, discord.CategoryChannel)]
    if loose:
        print("Вне категорий: " + ", ".join(f"#{c.name}" for c in loose))

    print("\nРоли по позициям (сверху вниз):")
    for r in sorted([r for r in g.roles if r.name != "@everyone"], key=lambda r: r.position, reverse=True):
        print(f"  {r.position:>2}. {r.name}")

    rules = await g.fetch_automod_rules()
    print("\nAutoMod: " + (", ".join(f"{r.name}{'' if r.enabled else ' (выкл)'}" for r in rules) or "нет правил"))
    print("\nНастройки: верификация=" + str(g.verification_level).split('.')[-1]
          + f" | фильтр={str(g.explicit_content_filter).split('.')[-1]}"
          + f" | уведомления={str(g.default_notifications).split('.')[-1]}"
          + f" | AFK={g.afk_channel.name if g.afk_channel else '—'} ({g.afk_timeout//60} мин)")
    await client.close()


if __name__ == "__main__":
    if not TOKEN or not GUILD_ID:
        print("❌ Нужны DISCORD_TOKEN и GUILD_ID")
        sys.exit(1)
    client.run(TOKEN)
