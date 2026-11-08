#!/usr/bin/env python3
"""
Ядро модерации SmoakTeam: мут через роль 🔇 Мут.

Логика мута:
  • выдаём роль 🔇 Мут — она запрещает видеть все каналы;
  • оставляем доступ только в 💤 AFK и 🔇 В муте;
  • срок хранится в mute_state.json, бот сам снимает мут по истечении;
  • после перезапуска бота мут не теряется.
"""
from __future__ import annotations

import datetime
import json
import os

import discord

MUTE_ROLE_NAME = "🔇 Мут"
MUTE_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mute_state.json")
AFK_CHANNEL_ID = 1568626419024531466
TALK_ROOM_NAME = "В муте"
MUTE_CATEGORY_NAME = "🔇 МУТ"

VIEW = 1024
SEND = 2048
CONNECT = 1 << 20
SPEAK = 1 << 21


# ---------------- время ----------------

_UNITS = {"с": 1, "сек": 1, "м": 60, "мин": 60, "ч": 3600, "час": 3600, "чс": 3600,
          "д": 86400, "дн": 86400, "день": 86400, "дней": 86400}


def parse_duration(text: str | None) -> datetime.timedelta | None:
    """«10м», «2ч», «7д», «30с», «10» (=минуты). Максимум 28 дней."""
    if not text:
        return None
    t = str(text).strip().lower().replace(" ", "")
    digits, unit = "", ""
    for ch in t:
        if ch.isdigit():
            digits += ch
        else:
            unit += ch
    if not digits:
        return None
    mult = _UNITS.get(unit or "м")
    if mult is None:
        return None
    return datetime.timedelta(seconds=min(int(digits) * mult, 28 * 86400))


def human(d: datetime.timedelta) -> str:
    s = int(d.total_seconds())
    for size, name in ((86400, "д"), (3600, "ч"), (60, "м")):
        if s >= size and s % size == 0:
            return f"{s // size}{name}"
    if s >= 86400:
        return f"{s // 86400}д {s % 86400 // 3600}ч"
    if s >= 3600:
        return f"{s // 3600}ч {s % 3600 // 60}м"
    if s >= 60:
        return f"{s // 60}м"
    return f"{s}с"


# ---------------- состояние ----------------

def _load() -> dict:
    try:
        with open(MUTE_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    with open(MUTE_STATE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------- роль и каналы ----------------

def mute_role(guild: discord.Guild):
    return discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)


async def ensure_mute_setup(guild: discord.Guild) -> tuple:
    """Создаёт/чинит роль 🔇 Мут и комнату «В муте». Возвращает (роль, комната)."""
    role = mute_role(guild)
    if role is None:
        role = await guild.create_role(name=MUTE_ROLE_NAME, colour=discord.Colour(0x546E7A),
                                       permissions=discord.Permissions.none(),
                                       reason="роль для мута")
        print("[mute] роль создана:", role.name)
    else:
        # роль должна стоять ниже модераторов и ничего не разрешать
        try:
            await role.edit(permissions=discord.Permissions.none(),
                            colour=discord.Colour(0x546E7A), mentionable=False)
        except discord.HTTPException:
            pass

    cat = discord.utils.get(guild.categories, name=MUTE_CATEGORY_NAME)
    if cat is None:
        cat = await guild.create_category(MUTE_CATEGORY_NAME, reason="категория для замученных")
        print("[mute] категория создана:", cat.name)

    room = discord.utils.get(guild.voice_channels, name=TALK_ROOM_NAME)
    if room is None:
        room = await guild.create_voice_channel(
            TALK_ROOM_NAME, category=cat, user_limit=2, reason="комната для замученных")
        print("[mute] комната создана:", room.name)
    elif getattr(room, "category_id", None) != cat.id:
        try:
            await room.edit(category=cat)
        except discord.HTTPException:
            pass
    return role, room


async def apply_channel_rules(guild: discord.Guild) -> int:
    """Замученный не видит ничего, кроме 💤 AFK и 🔇 В муте. Возвращает число правок."""
    role = mute_role(guild)
    if role is None:
        return 0
    changed = 0

    def is_allowed(ch, parent_name: str) -> bool:
        return (ch.id == AFK_CHANNEL_ID or ch.name == TALK_ROOM_NAME
                or parent_name in ("💤 AFK", MUTE_CATEGORY_NAME))

    parents = {c.id: c.name for c in guild.categories}
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            pname = ch.name
        else:
            pname = parents.get(getattr(ch, "category_id", None), "")
        try:
            if is_allowed(ch, pname):
                await ch.set_permissions(role, view_channel=True,
                                         connect=isinstance(ch, discord.VoiceChannel),
                                         speak=False, send_messages=False)
            else:
                await ch.set_permissions(role, view_channel=False)
            changed += 1
        except discord.HTTPException as e:
            print("[mute] не смог права на", ch.name, e)
    print(f"[mute] правила каналов обновлены: {changed}")
    return changed


# ---------------- выдача / снятие ----------------

async def apply_mute(guild: discord.Guild, member: discord.Member,
                     duration: datetime.timedelta, reason: str, by: discord.Member) -> str:
    role = mute_role(guild) or (await ensure_mute_setup(guild))[0]
    if role.position >= guild.me.top_role.position:
        return "роль 🔇 Мут выше роли бота — поднимите роль бота в настройках ролей"
    try:
        await member.add_roles(role, reason=f"мут: {by} — {reason}")
    except discord.HTTPException as e:
        return f"Discord не дал выдать роль мута: {e}"

    until = datetime.datetime.now(datetime.timezone.utc) + duration
    data = _load()
    data[str(member.id)] = {"until": until.isoformat(), "reason": reason,
                            "by": str(by), "guild": str(guild.id)}
    _save(data)
    return human(duration)


async def remove_mute(guild: discord.Guild, member: discord.Member, by: str = "бот") -> bool:
    role = mute_role(guild)
    data = _load()
    data.pop(str(member.id), None)
    _save(data)
    if role is None or role not in member.roles:
        return False
    try:
        await member.remove_roles(role, reason=f"анмут: {by}")
        return True
    except discord.HTTPException:
        return False


def muted_until(member_id: int):
    info = _load().get(str(member_id))
    if not info:
        return None
    try:
        return datetime.datetime.fromisoformat(info["until"])
    except Exception:
        return None


async def expire_loop(client: discord.Client, log_channel=None) -> None:
    """Раз в 30 секунд снимает истёкшие муты. Переживает перезапуск бота."""
    import asyncio
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            data = _load()
            now = datetime.datetime.now(datetime.timezone.utc)
            for uid, info in list(data.items()):
                try:
                    until = datetime.datetime.fromisoformat(info["until"])
                except Exception:
                    data.pop(uid, None)
                    continue
                if until > now:
                    continue
                guild = client.get_guild(int(info.get("guild", 0))) or (client.guilds[0] if client.guilds else None)
                if guild is None:
                    continue
                member = guild.get_member(int(uid))
                if member is None:
                    try:
                        member = await guild.fetch_member(int(uid))
                    except discord.HTTPException:
                        member = None
                if member is not None:
                    if await remove_mute(guild, member, "истёк срок"):
                        print("[mute] срок вышел:", member)
                        if log_channel is not None:
                            try:
                                await log_channel.send(
                                    f"🔊 Срок мута истёк — **{member.display_name}** снова может общаться.")
                            except discord.HTTPException:
                                pass
                data.pop(uid, None)
            _save(data)
        except Exception as e:
            print("[mute] expire_loop:", repr(e))
        await asyncio.sleep(30)
