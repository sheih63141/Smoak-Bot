#!/usr/bin/env python3
"""
Слэш-команды модерации: /мут /анмут /кик /бан.

В этой сборке discord.py дерево команд (client.tree) недоступно, поэтому:
  1) команды публикуем напрямую через REST (PUT /applications/{id}/commands);
  2) сами события приходят сырым пакетом INTERACTION_CREATE — ловим их в
     automod_bot.on_socket_raw_receive и отвечаем через REST-колбэк (3 секунды).

Ответ видит только вызвавший (ephemeral).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import urllib.error
import urllib.request

import discord

import commands as textcmd

API = "https://discord.com/api/v10"

COMMANDS = [
    {
        "name": "мут",
        "description": "Дать мут участнику",
        "options": [
            {"type": 6, "name": "ник", "description": "Кого наказываем", "required": True},
            {"type": 3, "name": "время", "description": "10м, 2ч, 7д (по умолчанию 1ч)", "required": False},
            {"type": 3, "name": "причина", "description": "За что", "required": False},
        ],
    },
    {
        "name": "анмут",
        "description": "Снять мут",
        "options": [{"type": 6, "name": "ник", "description": "С кого снимаем", "required": True}],
    },
    {
        "name": "кик",
        "description": "Выгнать участника",
        "options": [
            {"type": 6, "name": "ник", "description": "Кого выгоняем", "required": True},
            {"type": 3, "name": "причина", "description": "За что", "required": False},
        ],
    },
    {
        "name": "бан",
        "description": "Забанить участника",
        "options": [
            {"type": 6, "name": "ник", "description": "Кого баним", "required": True},
            {"type": 3, "name": "причина", "description": "За что", "required": False},
        ],
    },
]


def _rest(method: str, path: str, token: str, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("User-Agent", "DiscordBot (smoak, 1.0)")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _parse_time(text: str | None) -> datetime.timedelta | None:
    if not text:
        return None
    text = text.strip().lower().replace(" ", "")
    units = {"с": 1, "сек": 1, "м": 60, "мин": 60, "ч": 3600, "час": 3600,
             "д": 86400, "дн": 86400, "день": 86400, "дней": 86400}
    digits = ""
    unit = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            unit += ch
    if not digits:
        return None
    value = int(digits)
    if not unit:
        unit = "м"
    mult = units.get(unit)
    if mult is None:
        return None
    return datetime.timedelta(seconds=min(value * mult, 28 * 24 * 3600))


async def register(client: discord.Client, token: str) -> None:
    app_id = getattr(client, "application_id", None) or (client.user.id if client.user else None)
    if not app_id:
        return
    loop = asyncio.get_running_loop()
    code, res = await loop.run_in_executor(
        None, lambda: _rest("PUT", f"/applications/{app_id}/commands", token, COMMANDS))
    if code in (200, 201):
        print("[slash] зарегистрированы: " + ", ".join("/" + c["name"] for c in COMMANDS))
    else:
        print("[slash] регистрация не удалась:", code, res.get("message"))


async def handle(client: discord.Client, token: str, data: dict) -> None:
    """Пришло INTERACTION_CREATE — выполняем команду и отвечаем колбэком."""
    if data.get("type") != 2:
        return
    name = ((data.get("data") or {}).get("name") or "").lower()
    guild = client.get_guild(int(data["guild_id"])) if data.get("guild_id") else None
    if guild is None or not data.get("member"):
        return
    author = guild.get_member(int(data["member"]["user"]["id"]))
    if author is None:
        return

    async def respond(text: str, error: bool = False) -> None:
        def post():
            return _rest("POST", f"/interactions/{data['id']}/{data['token']}/callback", token,
                         {"type": 4, "data": {"content": text, "flags": 64}})
        await asyncio.get_running_loop().run_in_executor(None, post)

    if not textcmd._staff(author):
        await respond("⛔ Команды доступны только команде сервера.", True)
        return

    opts = {o["name"]: o.get("value") for o in ((data.get("data") or {}).get("options") or [])}
    target_id = opts.get("ник")
    target = None
    if target_id:
        target = guild.get_member(int(target_id))
        if target is None:
            try:
                target = await guild.fetch_member(int(target_id))
            except discord.HTTPException:
                target = None
    if target is None:
        await respond("❓ Не нашёл участника.", True)
        return

    err = textcmd._can_punish(author, target)
    if err:
        await respond(f"⛔ {err}", True)
        return

    reason = (opts.get("причина") or "без причины").strip()
    reason_full = f"{reason} | модератор: {author}"

    try:
        if name == "мут":
            dur = _parse_time(opts.get("время")) or datetime.timedelta(hours=1)
            await target.timeout(dur, reason=reason_full)
            await respond(f"🔇 **{target.display_name}** в муте на **{textcmd._human(dur)}**\nПричина: {reason}")
            await textcmd._log(guild, f"🔇 {author.mention} → мут {target.mention} на "
                                      f"{textcmd._human(dur)}. Причина: {reason}")
        elif name == "анмут":
            await target.timeout(None, reason=f"анмут: {author}")
            await respond(f"🔊 **{target.display_name}** размучен.")
            await textcmd._log(guild, f"🔊 {author.mention} снял мут с {target.mention}")
        elif name == "кик":
            await target.kick(reason=reason_full)
            await respond(f"👢 **{target.display_name}** кикнут\nПричина: {reason}")
            await textcmd._log(guild, f"👢 {author.mention} кикнул {target} ({target.id}). Причина: {reason}")
        elif name == "бан":
            await target.ban(reason=reason_full, delete_message_days=0)
            await respond(f"🔨 **{target.display_name}** забанен\nПричина: {reason}")
            await textcmd._log(guild, f"🔨 {author.mention} забанил {target} ({target.id}). Причина: {reason}")
        else:
            await respond("❓ Неизвестная команда.", True)
    except discord.HTTPException as e:
        await respond(f"❌ Discord не дал выполнить: {e}", True)
