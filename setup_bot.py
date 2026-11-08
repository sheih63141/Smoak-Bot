#!/usr/bin/env python3
"""
Автосборка Discord-сервера: роли, категории, текстовые и голосовые каналы, права.

Запуск:
    pip install -r requirements.txt
    python setup_bot.py               # боевой прогон
    python setup_bot.py --dry-run     # только показать план, ничего не менять
    python setup_bot.py --wipe        # сначала удалить всё, что создал скрипт (см. --dry-run!)

Переменные окружения (или файл .env):
    DISCORD_TOKEN  — токен бота (Developer Portal -> Bot -> Reset Token)
    GUILD_ID       — ID вашего сервера (ПКМ по иконке сервера -> Копировать ID сервера)

Скрипт идемпотентный: повторный запуск не создаёт дубликаты, а досоздаёт недостающее.
"""
from __future__ import annotations

import os
import sys
import asyncio

import discord
from discord import Permissions

# ----------------------------------------------------------------------------
# 0. Конфигурация запуска
# ----------------------------------------------------------------------------
DRY_RUN = "--dry-run" in sys.argv
WIPE = "--wipe" in sys.argv


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# ----------------------------------------------------------------------------
# 1. Базовая настройка @everyone: всё опасное выключено
# ----------------------------------------------------------------------------
EVERYONE_BASE = Permissions(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    add_reactions=True,
    embed_links=True,
    attach_files=True,
    use_external_emojis=True,
    use_external_stickers=True,
    use_application_commands=True,
    connect=True,
    speak=True,
    stream=True,
    use_voice_activation=True,
    change_nickname=True,
    # выключено:
    administrator=False,
    manage_guild=False,
    manage_roles=False,
    manage_channels=False,
    manage_messages=False,
    manage_webhooks=False,
    kick_members=False,
    ban_members=False,
    moderate_members=False,
    mention_everyone=False,
    move_members=False,
    deafen_members=False,
    priority_speaker=False,
    view_audit_log=False,
    create_public_threads=False,
    create_private_threads=False,
    manage_threads=False,
)

# Порядок в списке = порядок в иерархии (первый — самый высокий).
# key нужен только для привязки прав к каналам.
ROLES: list[dict] = [
    {
        "key": "owner",
        "name": "👑 Владелец",
        "color": 0xF1C40F,
        "hoist": True,
        "mentionable": False,
        "perms": {"administrator": True},
    },
    {
        "key": "admin",
        "name": "🛡 Администратор",
        "color": 0xE74C3C,
        "hoist": True,
        "mentionable": True,
        "perms": {"administrator": True},
    },
    {
        "key": "mod",
        "name": "🔨 Модератор",
        "color": 0xE67E22,
        "hoist": True,
        "mentionable": True,
        "perms": {
            "view_audit_log": True,
            "manage_messages": True,
            "moderate_members": True,
            "kick_members": True,
            "ban_members": False,  # баны — только у администрации
            "move_members": True,
            "deafen_members": True,
            "mute_members": True,
            "manage_threads": True,
            "create_private_threads": True,
            "manage_nicknames": True,
            "view_channel": True,
            "send_messages": True,
        },
    },
    {
        "key": "helper",
        "name": "🧰 Хелпер",
        "color": 0x3498DB,
        "hoist": True,
        "mentionable": True,
        "perms": {
            "manage_messages": True,
            "moderate_members": True,
            "move_members": True,
            "create_private_threads": True,
            "view_channel": True,
            "send_messages": True,
        },
    },
    {
        "key": "streamer",
        "name": "🎥 Стример",
        "color": 0xEB459E,
        "hoist": True,
        "mentionable": True,
        "perms": {
            "priority_speaker": True,
            "stream": True,
            "embed_links": True,
            "attach_files": True,
            "view_channel": True,
            "send_messages": True,
        },
    },
    {
        "key": "bot",
        "name": "🤖 Бот",
        "color": 0x95A5A6,
        "hoist": True,
        "mentionable": False,
        "perms": {"view_channel": True, "send_messages": True, "embed_links": True, "read_message_history": True},
    },
    {
        "key": "active",
        "name": "⭐ Активный",
        "color": 0x2ECC71,
        "hoist": False,
        "mentionable": True,
        "perms": {"external_emojis": True, "attach_files": True},
    },
    {
        "key": "vip",
        "name": "💎 ВИП",
        "color": 0xF4D03F,
        "hoist": True,
        "mentionable": True,
        "perms": {
            "view_channel": True,
            "send_messages": True,
            "read_message_history": True,
            "add_reactions": True,
            "external_emojis": True,
            "external_stickers": True,
            "attach_files": True,
            "embed_links": True,
            "priority_speaker": True,
            "stream": True,
            "mention_everyone": False,
        },
    },
    {
        "key": "member",
        "name": "👋 Участник",
        "color": 0x9B59B6,
        "hoist": False,
        "mentionable": False,
        "perms": {},
    },
    {
        "key": "muted",
        "name": "🔇 Заглушённый",
        "color": 0x2F3136,
        "hoist": False,
        "mentionable": False,
        # deny на уровне роли: снимается вручную модератором
        "perms": {},
        "deny": {"send_messages": True, "speak": True, "add_reactions": True, "connect": True},
    },
]

# Роли самоассайна (без прав, только для пингов и «кто во что играет»)
# Роли платформ (PC / PlayStation / Xbox) убраны полностью — платформа на сервере не делится.
# Роли по интересам удалены с сервера по решению владельца (07.11.2026).
# Пустые списки = скрипт их больше не создаёт. Вернуть — вписать имена обратно.
SELF_ROLES_GAMES: list[str] = []
SELF_ROLES_OTHER: list[str] = []
SELF_ROLES: list[str] = SELF_ROLES_GAMES + SELF_ROLES_OTHER

# ----------------------------------------------------------------------------
# 2. Структура каналов
#    overwrites: {"role_key" или "everyone": {"allow": {...}, "deny": {...}}}
#    Ключи — имена прав discord.Permissions (snake_case).
# ----------------------------------------------------------------------------
def deny_everyone_but_staff(*staff: str) -> dict:
    o = {"everyone": {"deny": {"view_channel": True}}}
    for s in staff:
        o[s] = {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}}
    return o


CATEGORIES: list[dict] = [
    {
        "name": "📌 СТАРТ",
        "channels": [
            {
                "type": "text",
                "name": "правила",
                "topic": "Правила сервера. Прочитал — поставь ✅ внизу. Обязательно к прочтению.",
                "overwrites": {
                    "everyone": {"deny": {"send_messages": True, "create_public_threads": True}},
                    "mod": {"allow": {"send_messages": True}},
                    "admin": {"allow": {"send_messages": True}},
                },
            },
            {
                "type": "text",
                "name": "получить-роль",
                "topic": "Нажми кнопку — получишь роль Участник и доступ ко всем каналам.",
                "overwrites": {
                    "everyone": {"deny": {"send_messages": True}},
                    "member": {"deny": {"view_channel": True}},
                    "mod": {"allow": {"view_channel": True, "send_messages": True}},
                    "admin": {"allow": {"view_channel": True, "send_messages": True}},
                },
            },
        ],
    },
    {
        "name": "💬 ОБЩЕНИЕ",
        "members_only": True,
        "channels": [
            {"type": "text", "name": "общий-чат", "topic": "Главный чат CS2-клуба. Знакомимся, общаемся, собираем пати."},
            {"type": "text", "name": "мемы-и-клипы", "topic": "Мемы, скриншоты, клипы и хайлайты. Без спама и NSFW."},
            {"type": "text", "name": "стрим-обсуждение", "topic": "Обсуждаем эфиры. Ссылки на чужие стримы — только с разрешения админов."},
        ],
    },
    {
        "name": "📢 НОВОСТИ",
        "members_only": True,
        "channels": [
            {"type": "text", "name": "объявления", "topic": "Турниры, ивенты и важные изменения. Пишут только админы.", "read_only": True},
            {"type": "text", "name": "обновления-cs2", "topic": "Патчи Valve, изменения карт и оружия. Коротко и по делу.", "read_only": True},
            {"type": "text", "name": "анонсы-стримов", "topic": "Ссылка + что играем + когда. Пишут стримеры и модерация.", "read_only": True},
        ],
    },
    {
        "name": "🔫 CS2",
        "members_only": True,
        "channels": [
            {"type": "text", "name": "сбор-на-катку", "topic": "Режим, ранг, сколько людей, голос. Формат — в закрепе."},
            {"type": "text", "name": "раскидки-и-тактики", "topic": "Сетапы смоков, флешек и разбор карт CS2."},
        ],
    },
    {
        "name": "🔊 ГОЛОС",
        "members_only": True,
        "channels": [
            {"type": "voice", "name": "🔊 Общий"},
            {"type": "voice", "name": "🔫 Пати 1", "user_limit": 5},
            {"type": "voice", "name": "🔫 Пати 2", "user_limit": 5},
            {"type": "voice", "name": "🎯 Практика", "user_limit": 5},
            {"type": "voice", "name": "🎧 Стрим-комната", "user_limit": 10},
            {"type": "voice", "name": "🎧 Чилл", "user_limit": 20},
        ],
    },
    {
        "name": "🎫 ПОДДЕРЖКА",
        "members_only": True,
        "channels": [
            {
                "type": "text",
                "name": "🎫-подать-тикет",
                "topic": "Поставь реакцию: 🎫 вопрос хелперу · 📋 обращение к админам · 📝 заявка в команду.",
                "overwrites": {
                    "everyone": {"deny": {"send_messages": True, "create_private_threads": True,
                                          "create_public_threads": True},
                                 "allow": {"view_channel": True, "read_message_history": True,
                                           "add_reactions": True}},
                    "member": {"allow": {"view_channel": True, "read_message_history": True,
                                         "add_reactions": True}},
                    "helper": {"allow": {"send_messages": True, "read_message_history": True,
                                         "manage_messages": True}},
                    "mod": {"allow": {"send_messages": True, "read_message_history": True,
                                      "manage_messages": True}},
                    "admin": {"allow": {"send_messages": True, "read_message_history": True,
                                        "manage_messages": True}},
                },
            }
        ],
    },
    {
        "name": "🎫 ТИКЕТЫ",
        "overwrites": {
            "everyone": {"deny": {"view_channel": True}},
            "helper": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
            "mod": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
            "admin": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
        },
        "channels": [],
    },
    {
        "name": "📋 ОБРАЩЕНИЯ",
        "overwrites": {
            "everyone": {"deny": {"view_channel": True}},
            "helper": {"deny": {"view_channel": True}},
            "mod": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
            "admin": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
        },
        "channels": [],
    },
    {
        "name": "📝 ЗАЯВКИ",
        "overwrites": {
            "everyone": {"deny": {"view_channel": True}},
            "helper": {"deny": {"view_channel": True}},
            "mod": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
            "admin": {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}},
        },
        "channels": [],
    },
    {
        "name": "🛠 КОМАНДА (скрыто)",
        "staff_only": True,
        "channels": [
            {"type": "text", "name": "мод-чат", "topic": "Внутренние обсуждения команды.", "staff": ["mod", "admin"]},
            {"type": "text", "name": "логи", "topic": "Автоматические логи бана/кика/удалённых сообщений (сюда пишет Carl-bot).", "staff": ["mod", "admin"]},
            {"type": "text", "name": "заявки", "topic": "Заявки в модераторы / хелперы / стримеры.", "staff": ["helper", "mod", "admin"]},
        ],
    },
    {
        "name": "🔒 ПРИВАТНОЕ",
        # категория скрыта от @everyone, доступ — только по ролям ниже
        "overwrites": {
            "everyone": {"deny": {"view_channel": True}},
            "owner": {"allow": {"view_channel": True, "connect": True, "speak": True}},
            "admin": {"allow": {"view_channel": True, "connect": True, "speak": True}},
            "mod": {"allow": {"view_channel": True, "connect": True, "speak": True}},
            "helper": {"allow": {"view_channel": True}},
            "streamer": {"allow": {"view_channel": True, "connect": True, "speak": True, "stream": True}},
            "vip": {"allow": {"view_channel": True}},
        },
        "channels": [
            {
                "type": "voice",
                "name": "🎬 Стримерская",
                "user_limit": 10,
                "overwrites": {
                    "everyone": {"deny": {"view_channel": True}},
                    "streamer": {"allow": {"view_channel": True, "connect": True, "speak": True, "stream": True}},
                    "mod": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "admin": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "vip": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                },
            },
            {
                "type": "voice",
                "name": "👥 Тим-1",
                "user_limit": 6,
                "overwrites": {
                    "everyone": {"deny": {"view_channel": True}},
                    "mod": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "helper": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "admin": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "streamer": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                },
            },
            {
                "type": "voice",
                "name": "👥 Тим-2",
                "user_limit": 6,
                "overwrites": {
                    "everyone": {"deny": {"view_channel": True}},
                    "mod": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "helper": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "admin": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "streamer": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                },
            },
            {
                "type": "voice",
                "name": "💎 ВИП-комната",
                "user_limit": 5,
                "overwrites": {
                    "everyone": {"deny": {"view_channel": True}},
                    "vip": {"allow": {"view_channel": True, "connect": True, "speak": True, "priority_speaker": True}},
                    "admin": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                    "mod": {"allow": {"view_channel": True, "connect": True, "speak": True}},
                },
            },
            {
                "type": "text",
                "name": "приват-чат",
                "topic": "Только команда и ВИП: сборы, договорённости, приватные комнаты.",
                "overwrites": {
                    "everyone": {"deny": {"view_channel": True}},
                    "vip": {"allow": {"view_channel": True, "send_messages": True}},
                    "streamer": {"allow": {"view_channel": True, "send_messages": True}},
                    "helper": {"allow": {"view_channel": True, "send_messages": True}},
                    "mod": {"allow": {"view_channel": True, "send_messages": True}},
                    "admin": {"allow": {"view_channel": True, "send_messages": True}},
                },
            },
        ],
    },
    {
        "name": "💤 AFK",
        "members_only": True,
        "channels": [{"type": "voice", "name": "AFK", "user_limit": 99}],
    },
]

# ----------------------------------------------------------------------------
# 3. Логика применения
# ----------------------------------------------------------------------------
def build_overwrite(spec: dict) -> discord.PermissionOverwrite:
    kwargs: dict[str, bool | None] = {}
    for name, value in (spec.get("allow") or {}).items():
        kwargs[name] = True
    for name, value in (spec.get("deny") or {}).items():
        kwargs[name] = False
    return discord.PermissionOverwrite(**kwargs)


class Builder:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.roles: dict[str, discord.Role] = {}
        self.log: list[str] = []

    def say(self, msg: str) -> None:
        print(msg)
        self.log.append(msg)

    async def wipe(self) -> None:
        """Удаляет категории и каналы, совпадающие с планом, и роли из плана."""
        names = {c["name"] for c in CATEGORIES}
        for ch in list(self.guild.channels):
            if ch.name in names or any(ch.name == c["name"] for cat in CATEGORIES for c in cat["channels"]):
                if DRY_RUN:
                    self.say(f"[dry] удалил бы канал {ch.name}")
                else:
                    await ch.delete(reason="setup_bot --wipe")
        role_names = {r["name"] for r in ROLES} | set(SELF_ROLES)
        for role in list(self.guild.roles):
            if role.name in role_names:
                if DRY_RUN:
                    self.say(f"[dry] удалил бы роль {role.name}")
                else:
                    await role.delete(reason="setup_bot --wipe")

    async def setup_everyone(self) -> None:
        everyone = self.guild.default_role
        if DRY_RUN:
            self.say("[dry] настроил бы права @everyone")
            return
        await everyone.edit(permissions=EVERYONE_BASE, reason="setup_bot: базовая защита")
        self.say("✅ @everyone: опасные права сняты")

    async def setup_roles(self) -> None:
        # создаём снизу вверх, чтобы порядок встал правильно
        for spec in reversed(ROLES):
            role = discord.utils.get(self.guild.roles, name=spec["name"])
            perms = Permissions.none()
            for name, value in spec["perms"].items():
                setattr(perms, name, value)
            for name, value in (spec.get("deny") or {}).items():
                setattr(perms, name, False)
            if DRY_RUN:
                self.say(f"[dry] роль {spec['name']}")
                continue
            if role is None:
                role = await self.guild.create_role(
                    name=spec["name"],
                    permissions=perms,
                    colour=discord.Colour(spec["color"]),
                    hoist=spec["hoist"],
                    mentionable=spec["mentionable"],
                    reason="setup_bot: роли",
                )
                self.say(f"✅ создана роль {spec['name']}")
            else:
                await role.edit(
                    permissions=perms,
                    colour=discord.Colour(spec["color"]),
                    hoist=spec["hoist"],
                    mentionable=spec["mentionable"],
                )
                self.say(f"↻ обновлена роль {spec['name']}")
            self.roles[spec["key"]] = role

        for name in SELF_ROLES:
            role = discord.utils.get(self.guild.roles, name=name)
            if DRY_RUN:
                self.say(f"[dry] роль {name}")
                continue
            if role is None:
                role = await self.guild.create_role(name=name, permissions=Permissions.none(), mentionable=True)
                self.say(f"✅ создана роль {name}")

        if not DRY_RUN and os.getenv("SKIP_POSITIONS", "0") != "1":
            # выравниваем позиции строго по плану (SKIP_POSITIONS=1 — не трогать порядок)
            order = [self.roles[s["key"]] for s in ROLES if s["key"] in self.roles]
            positions = {}
            top = max((r.position for r in order), default=1)
            for i, role in enumerate(order):
                positions[role] = top - i
            try:
                await self.guild.edit_role_positions(positions=positions)
                self.say("✅ иерархия ролей выстроена")
            except discord.HTTPException as e:
                self.say(f"⚠️ не удалось переставить роли ({e}); порядок можно поправить руками в настройках сервера")

    def resolve_role(self, key: str) -> discord.Role | None:
        """Роль по ключу из ROLES или по имени (для ролей, созданных не скриптом)."""
        if key == "everyone":
            return self.guild.default_role
        if key in self.roles:
            return self.roles[key]
        spec = next((r for r in ROLES if r["key"] == key), None)
        if spec:
            return discord.utils.get(self.guild.roles, name=spec["name"])
        return discord.utils.get(self.guild.roles, name=key)

    def build_overwrites(self, spec_map: dict) -> dict:
        overwrites: dict = {}
        for key, ov in (spec_map or {}).items():
            role = self.resolve_role(key)
            if role:
                overwrites[role] = build_overwrite(ov)
            else:
                print(f"  ⚠️ роль '{key}' не найдена — пропускаю в правах")
        return overwrites

    async def setup_categories(self) -> None:
        for cat_spec in CATEGORIES:
            cat = discord.utils.get(self.guild.categories, name=cat_spec["name"])
            cat_overwrites: dict = {}
            if cat_spec.get("staff_only"):
                cat_overwrites[self.guild.default_role] = build_overwrite({"deny": {"view_channel": True}})
                for key in ("mod", "admin"):
                    role = self.roles.get(key)
                    if role:
                        cat_overwrites[role] = build_overwrite({"allow": {"view_channel": True}})
            cat_overwrites.update(self.build_overwrites(cat_spec.get("overwrites")))
            if cat_spec.get("members_only"):
                # новичок без роли не видит категорию вообще
                cat_overwrites[self.guild.default_role] = build_overwrite({"deny": {"view_channel": True}})
                allow = {"view_channel": True, "read_message_history": True,
                         "send_messages": True, "connect": True, "speak": True}
                for key in ("member", "active", "vip"):
                    role = self.resolve_role(key)
                    if role:
                        cat_overwrites[role] = build_overwrite({"allow": allow})

            if DRY_RUN:
                self.say(f"[dry] категория {cat_spec['name']}")
            elif cat is None:
                cat = await self.guild.create_category(
                    cat_spec["name"], overwrites=cat_overwrites, reason="setup_bot: категории"
                )
                self.say(f"✅ создана категория {cat_spec['name']}")
            else:
                self.say(f"↻ категория {cat_spec['name']} уже есть — обновляю права")
                for target, ov in cat_overwrites.items():
                    try:
                        await cat.set_permissions(target, overwrite=ov)
                    except discord.HTTPException as e:
                        print(f"  ⚠️ права категории {cat_spec['name']}: {e}")

            if not DRY_RUN and cat_spec.get("staff_only"):
                helper = self.roles.get("helper")
                if helper:
                    await cat.set_permissions(
                        helper, overwrite=discord.PermissionOverwrite(view_channel=False)
                    )

            for ch_spec in cat_spec["channels"]:
                await self.setup_channel(cat, ch_spec)

    async def setup_channel(self, cat: discord.CategoryChannel | None, spec: dict) -> None:
        name = spec["name"]
        exists = discord.utils.get(self.guild.channels, name=name)
        if exists:
            self.say(f"↻ канал #{name} уже есть — пропускаю")
            return
        if DRY_RUN:
            self.say(f"[dry] {'голосовой' if spec['type'] == 'voice' else 'текстовый'} канал {name} (в «{cat.name if cat else '—'}»)")
            return

        overwrites: dict = self.build_overwrites(spec.get("overwrites"))
        staff = spec.get("staff")
        if staff:
            overwrites[self.guild.default_role] = build_overwrite({"deny": {"view_channel": True}})
            for key in staff:
                role = self.roles.get(key)
                if role:
                    overwrites[role] = build_overwrite(
                        {"allow": {"view_channel": True, "send_messages": True, "read_message_history": True}}
                    )

        if spec["type"] == "voice":
            ch = await self.guild.create_voice_channel(
                name, category=cat, overwrites=overwrites, user_limit=spec.get("user_limit", 0),
                reason="setup_bot: каналы",
            )
            self.say(f"✅ 🔈 {name}")
        else:
            ch = await self.guild.create_text_channel(
                name, category=cat, overwrites=overwrites, topic=spec.get("topic"),
                slowmode_delay=spec.get("slowmode", 0), reason="setup_bot: каналы",
            )
            self.say(f"✅ # {name}")

        # приветственное сообщение в ключевых каналах
        texts = {
            "правила": texts_rules(),
            "🎫-подать-тикет": texts_ticket(),
            "анонсы-стримов": texts_stream_announce(),
        }
        if name in texts and texts[name] and isinstance(ch, discord.TextChannel):
            await ch.send(texts[name])


# ----------------------------------------------------------------------------
# 4. Тексты сообщений (правятся свободно)
# ----------------------------------------------------------------------------
def texts_rules() -> str:
    return (
        "**📜 ПРАВИЛА СЕРВЕРА**\n"
        "Прочитал — поставь ✅ внизу. Незнание правил не освобождает от санкций.\n\n"
        "**1. Уважение.** Без оскорблений, травли, дискриминации и переходов на личности. "
        "Спор — это нормально, хамство — нет.\n"
        "**2. Контент.** Никакого NSFW, шок-контента, жестокости и политики.\n"
        "**3. Спам и реклама.** Без флуда, капса, массовых пингов и рекламы чужих серверов без разрешения.\n"
        "**4. Голос.** Не перебивать, не включать «музыку из колонок» в общий чат, не мешать стримам.\n"
        "**5. Ники и аватары.** Читаемые, без оскорблений и рекламы.\n"
        "**6. Каналы по назначению.** Ищешь тиму — в #сбор-на-катку, мемы — в #мемы-и-клипы.\n"
        "**7. Discord ToS.** Правила Discord действуют всегда: без читов, софта для накрутки и обхода банов.\n\n"
        "**Санкции:** предупреждение → мут (1 ч / 24 ч / 7 дней) → кик → бан. "
        "Нарушения п.1 и п.2 — сразу мут или бан без предупреждения.\n"
        "**Апелляции и жалобы** — через #📋-обращения (видят только администрация).\n"
    )


def texts_nav() -> str:
    return (
        "**🧭 НАВИГАЦИЯ**\n\n"
        "💬 **#общий-чат** — знакомства и болтовня\n"
        "🎮 **#поиск-игроков** — собрать пати: *игра / сколько нужно / какой войс*\n"
        "🎥 **#анонсы-стримов** — кто и что стримит\n"
        "☎ **🔊 ГОЛОС** — заходи в «Общий» или «Пати 1–2»\n"
        "🎟 **#🎫-подать-тикет** — поставь реакцию: 🎫 вопрос хелперу, "
        "📋 обращение к админам, 📝 заявка в команду\n\n"
        "**Как включить уведомления:** зайди в #выбери-роли и поставь реакции — пинги только по теме.\n"
        "**Хочешь стримить у нас?** Открой тикет: выдадим роль 🎥 Стример и доступ к анонсам.\n"
    )


def texts_roles() -> str:
    if not SELF_ROLES:
        return ("**Роли по интересам убраны.**\n"
                "Следи за #анонсы — стримы и ивенты анонсируются там, "
                "а собрать пати можно в #поиск-игроков.")
    lines = ["**🎭 ВЫБЕРИ РОЛИ**\n", "*Игры:*"]
    for r in SELF_ROLES_GAMES:
        lines.append(f"• {r}")
    lines.append("\n*Уведомления:*")
    for r in SELF_ROLES_OTHER:
        lines.append(f"• {r}")
    lines.append(
        "\nПоставь реакцию под сообщением — роль появится. Снять повторным нажатием."
        "\n\nЕсли реакции не работают, попроси администратора настроить Reaction Roles в Carl-bot."
    )
    return "\n".join(lines)


def texts_ticket() -> str:
    return (
        "**🎫 ПОДДЕРЖКА**\n"
        "Нажми **Создать тикет** ниже. Откроется приватный канал, где ответит команда сервера.\n\n"
        "Для чего тикет: жалоба на участника, разбан/апелляция, заявка в модераторы или хелперы, "
        "заявка на стрим, идея ивента, любой приватный вопрос.\n\n"
        "Полезно сразу приложить: ники, ссылки на сообщения, время, скриншоты."
    )


def texts_stream_announce() -> str:
    return (
        "**Шаблон анонса стрима** — скопируй и заполни:\n"
        "```\n"
        "🎥 @Стример в эфире\n"
        "Что: \n"
        "Когда: сегодня в 20:00 МСК\n"
        "Тут: https://twitch.tv/... или https://youtube.com/live/...\n"
        "Заходите в 🎧 Стрим-комната — обсудим в голосе\n"
        "```"
    )


# ----------------------------------------------------------------------------
# 5. Клиент
# ----------------------------------------------------------------------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"Бот вошёл как {client.user}")
    guild = client.get_guild(GUILD_ID) if GUILD_ID else None
    if guild is None:
        owned = [g for g in client.guilds if g.owner_id == client.user.id]
        guild = owned[0] if owned else None
    if guild is None:
        print("❌ Сервер не найден. Проверь GUILD_ID или пригласи бота на сервер ссылкой:")
        print("   Developer Portal -> OAuth2 -> URL Generator -> scopes: bot + applications.commands,")
        print("   permissions: Administrator (для первичной сборки удобнее всего)")
        if DRY_RUN:
            print("\n--- ПЛАН СБОРКИ ---")
            for cat in CATEGORIES:
                print(f"\n{cat['name']}")
                for ch in cat["channels"]:
                    print(f"   {'🔈' if ch['type'] == 'voice' else '#'} {ch['name']}")
        await client.close()
        return

    print(f"Сервер: {guild.name} ({guild.id})")
    b = Builder(guild)
    if WIPE:
        await b.wipe()
        if DRY_RUN:
            await client.close()
            return
    await b.setup_everyone()
    await b.setup_roles()
    await b.setup_categories()

    print("\n" + ("=== DRY RUN: ничего не изменено ===" if DRY_RUN else "=== ГОТОВО ==="))
    print("Дальше руками (5 минут):")
    print("  1) Настройки сервера -> Модерация: включи AutoMod + Verification Level = Средний")
    print("  2) #выбери-роли: посты под роли + реакции (или Reaction Roles в Carl-bot)")
    print("  3) Пригласи Carl-bot (логи, автомод), Ticket Tool (тикеты), Statbot (статистика)")
    print("  4) Настройки сервера -> Приветствие: канал #правила, текст онбординга в texts/welcome.md")
    await client.close()


def print_plan() -> None:
    print("--- ПЛАН СБОРКИ (без подключения к Discord) ---")
    print("@everyone: опасные права сняты; писать и слушать можно только в разрешённых каналах\n")
    print("Роли (сверху вниз):")
    for r in ROLES:
        print(f"  • {r['name']}")
    print("  • " + ", ".join(SELF_ROLES[:6]) + ", ... (роли самоассайна)\n")
    for cat in CATEGORIES:
        print(cat["name"])
        for ch in cat["channels"]:
            mark = "🔈" if ch["type"] == "voice" else "#"
            print(f"   {mark} {ch['name']}")
    print(f"\nИтого: {sum(len(c['channels']) for c in CATEGORIES)} каналов в {len(CATEGORIES)} категориях, "
          f"{len(ROLES) + len(SELF_ROLES)} ролей.")


if __name__ == "__main__":
    if not TOKEN:
        if DRY_RUN:
            print_plan()
            sys.exit(0)
        print("❌ Нет DISCORD_TOKEN. Скопируй .env.example в .env и вставь токен (или запусти с --dry-run для предпросмотра).")
        sys.exit(1)
    try:
        client.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Токен не принят. Перевыпусти его в Developer Portal -> Bot -> Reset Token.")
        sys.exit(1)
