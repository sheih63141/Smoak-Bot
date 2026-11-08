#!/usr/bin/env python3
"""
Команды модерации обычным текстом — работают без слэш-интеракций.

  /мут @ник 1ч спам в чате      — мут: роль 🔇 Мут (только AFK и «В муте»)
  /снятьмут @ник                — снять мут раньше срока
  /кик @ник причина             — выгнать с сервера
  /бан @ник причина             — забанить
  /помощь                       — список команд

Работает и с «!» вместо «/». Вместо @ника можно написать ник или ID.
Время: 30м, 1ч, 2ч30м, 1д, 7д. Без времени мут по умолчанию 1 час.
"""
from __future__ import annotations

import datetime
import io
import re

import discord

import moderation as mod

PREFIXES = ("/", "!")
# только русские и без дублей — одна команда на действие
COMMANDS = ("мут", "снятьмут", "кик", "бан", "пред", "помощь")
LOG_CHANNEL = "логи"

STAFF_ROLES = ["🧰 Хелпер", "🔨 Модератор", "🛡 Администратор", "👑 Владелец"]
MUTED_ROLE_NAMES = ["🔇 Мут", "🔇 Заглушённый"]

TIME_RE = re.compile(r"(\d+)\s*(м|мин|минут\w*|ч|час\w*|д|дн\w*|s|m|h|d)", re.IGNORECASE)
CALL_RE = re.compile(r"^[/!]\s*([а-яa-z]+)\s*(.*)$", re.IGNORECASE | re.DOTALL)

HELP = """**🛠 Команды модерации**

```
/мут @ник 10м причина     — мут
/снятьмут @ник            — снять мут
/кик @ник причина         — выгнать с сервера
/бан @ник причина         — забанить
/пред @ник причина        — предупреждение
/помощь                   — эта шпаргалка
```

**Время:** `30с` · `10м` · `2ч` · `7д` (без времени — 1 час, максимум 28 дней)
**Кого:** @упоминание, ник или ID
**Работает** и текстом с `!`, например `!мут @ник 10м спам`.

-# Замученный видит только «💤 AFK» и «🔇 В муте». Мут снимается сам, когда выйдет время."""


def _staff(member: discord.Member) -> bool:
    names = {r.name for r in member.roles}
    return bool(names & set(STAFF_ROLES)) or member.guild_permissions.administrator


def _parse_time(text: str) -> tuple[datetime.timedelta | None, str]:
    """Возвращает (длительность, остаток строки без времени)."""
    total = datetime.timedelta()
    found = False
    rest = text
    for m in TIME_RE.finditer(text):
        found = True
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith(("м", "m")) and not unit.startswith("мин"):
            total += datetime.timedelta(minutes=n)
        elif unit.startswith(("ч", "h")) or unit.startswith("час"):
            total += datetime.timedelta(hours=n)
        elif unit.startswith(("д", "d", "дн")):
            total += datetime.timedelta(days=n)
        else:
            total += datetime.timedelta(minutes=n)
        rest = rest.replace(m.group(0), " ", 1)
    return (total if found else None), " ".join(rest.split())


async def _resolve_target(message: discord.Message, arg: str):
    if message.mentions:
        return message.mentions[0]
    arg = arg.strip().strip("<>@!")
    if not arg:
        return None
    if arg.isdigit():
        try:
            return await message.guild.fetch_member(int(arg))
        except discord.HTTPException:
            return None
    needle = arg.lower()
    for m in message.guild.members:
        if m.name.lower() == needle or m.display_name.lower() == needle:
            return m
    return None


def _can_punish(author: discord.Member, target: discord.Member) -> str | None:
    """Возвращает текст ошибки или None, если наказывать можно."""
    if target.id == author.id:
        return "себя наказывать не надо"
    if target.id == author.guild.owner_id:
        return "владельца сервера трогать нельзя"
    if target.bot and target.id != (author.guild.me.id if author.guild.me else 0):
        return "ботов не наказываем"
    if author.id != author.guild.owner_id and target.top_role >= author.top_role:
        return f"у {target.display_name} роль не ниже твоей — не могу"
    return None


async def _log(guild: discord.Guild, text: str, file=None) -> None:
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch is None:
        return
    try:
        await ch.send(text, file=file)
    except discord.HTTPException:
        pass


async def _reply(message: discord.Message, text: str, color: int = 0x2ECC71) -> None:
    try:
        await message.channel.send(embed=discord.Embed(description=text, color=color))
    except discord.HTTPException:
        pass


async def handle_message(client: discord.Client, message: discord.Message) -> bool:
    """True — сообщение было командой и обработано."""
    if message.author.bot or message.guild is None:
        return False
    content = (message.content or "").strip()
    m = CALL_RE.match(content)
    if not m:
        return False
    cmd = m.group(1).lower()
    if cmd not in COMMANDS:
        return False

    is_staff = _staff(message.author)
    if not is_staff:
        await _reply(message, "⛔ Команды модерации доступны только команде сервера.", 0xE74C3C)
        return True

    # команда — не для чужих глаз
    try:
        await message.delete()
    except discord.HTTPException:
        pass

    args = m.group(2).strip()
    guild = message.guild
    author = message.author

    if cmd in ("помощь",):
        await _reply(message, HELP, 0x3498DB)
        return True

    target = await _resolve_target(message, args)
    if target is None:
        await _reply(message, "❓ Не нашёл такого участника. Укажи @упоминание, ник или ID.", 0xE74C3C)
        return True

    err = _can_punish(author, target)
    if err:
        await _reply(message, f"⛔ {err}", 0xE74C3C)
        return True

    # ---- АНМУТ ----
    if cmd in ("снятьмут", "анмут", "размут", "unmute"):
        try:
            await target.timeout(None, reason=f"анмут: {author}")
        except discord.HTTPException:
            pass
        ok = await mod.remove_mute(guild, target, str(author))
        await _reply(message, f"🔊 **{target.display_name}** размучен." if ok
                     else f"ℹ️ У **{target.display_name}** не было мута.")
        await _log(guild, f"🔊 {author.mention} снял мут с {target.mention}")
        return True

    # ---- МУТ / КИК / БАН ----
    duration, reason = _parse_time(args)
    # выкидываем из причины сам ник/@упоминание
    for junk in (target.mention, f"<@!{target.id}>", target.name, target.display_name, str(target.id)):
        reason = reason.replace(junk, " ")
    reason = " ".join(reason.split()) or "без причины"
    reason_full = f"{reason} | модератор: {author}"

    if cmd in ("пред",):
        await _reply(message, f"⚠️ **{target.display_name}** получил предупреждение\n"
                              f"Причина: {reason}", 0xE67E22)
        await _log(guild, f"⚠️ {author.mention} выдал предупреждение {target.mention}. Причина: {reason}")
        return True

    if cmd in ("мут",):
        dur = duration or datetime.timedelta(hours=1)
        if dur > datetime.timedelta(days=28):
            dur = datetime.timedelta(days=28)
        res = await mod.apply_mute(guild, target, dur, reason, author)
        if res.startswith("Discord") or res.startswith("роль"):
            await _reply(message, f"❌ {res}", 0xE74C3C)
            return True
        await _reply(message, f"🔇 **{target.display_name}** замучен на **{res}**\n"
                              f"Причина: {reason}\n"
                              f"Видит только «💤 AFK» и «🔇 В муте», мут снимется сам.")
        await _log(guild, f"🔇 {author.mention} → мут {target.mention} на {res}. Причина: {reason}")
        return True

    if cmd in ("кик",):
        try:
            await target.kick(reason=reason_full)
        except discord.HTTPException as e:
            await _reply(message, f"❌ Не смог кикнуть: {e}", 0xE74C3C)
            return True
        await _reply(message, f"👢 **{target.display_name}** кикнут\nПричина: {reason}")
        await _log(guild, f"👢 {author.mention} кикнул {target} ({target.id}). Причина: {reason}")
        return True

    if cmd in ("бан",):
        try:
            await target.ban(reason=reason_full, delete_message_days=0)
        except discord.HTTPException as e:
            await _reply(message, f"❌ Не смог забанить: {e}", 0xE74C3C)
            return True
        await _reply(message, f"🔨 **{target.display_name}** забанен\nПричина: {reason}")
        await _log(guild, f"🔨 {author.mention} забанил {target} ({target.id}). Причина: {reason}")
        return True

    return False


def _human(d: datetime.timedelta) -> str:
    parts = []
    days, rem = divmod(int(d.total_seconds()), 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if mins:
        parts.append(f"{mins} мин")
    return " ".join(parts) or "меньше минуты"
