#!/usr/bin/env python3
"""
Русские слэш-команды модерации.
/мут /замутить /анмут /снятьмут /размут /кик /выгнать /бан /забанить /пред

Мут = выдача роли 🔇 Мут: человек перестаёт видеть все каналы,
кроме «💤 AFK» и «🔇 В муте». Срок снимается ботом автоматически.

Дерево команд в этой сборке discord.py недоступно, поэтому:
  1) команды публикуем через REST (PUT /applications/{id}/commands);
  2) события ловим сырым пакетом в automod_bot.on_socket_raw_receive;
  3) отвечаем через REST-колбэк (успеть за 3 секунды), ответ виден только модератору.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

import discord

import commands as textcmd
import moderation as mod

API = "https://discord.com/api/v10"

TARGET = {"type": 6, "name": "ник", "description": "Кого наказываем", "required": True}
TIME = {"type": 3, "name": "время", "description": "10м, 2ч, 7д (если пусто — 1 час)", "required": False}
REASON = {"type": 3, "name": "причина", "description": "За что наказание", "required": False}

# имя команды -> действие
ALIASES = {
    "мут": "мут", "замут": "мут", "замутить": "мут",
    "анмут": "анмут", "снятьмут": "анмут", "размут": "анмут",
    "кик": "кик", "выгнать": "кик",
    "бан": "бан", "забанить": "бан",
    "варн": "варн", "пред": "варн",
    "помощь": "помощь",
}

COMMANDS = [
    {"name": "мут", "description": "Замутить участника (роль 🔇 Мут, только AFK и «В муте»)",
     "options": [TARGET, TIME, REASON]},
    {"name": "замутить", "description": "То же, что /мут", "options": [TARGET, TIME, REASON]},
    {"name": "снятьмут", "description": "Снять мут с участника", "options": [TARGET]},
    {"name": "анмут", "description": "То же, что /снятьмут", "options": [TARGET]},
    {"name": "кик", "description": "Выгнать участника с сервера", "options": [TARGET, REASON]},
    {"name": "бан", "description": "Забанить участника", "options": [TARGET, REASON]},
    {"name": "пред", "description": "Выдать предупреждение", "options": [TARGET, REASON]},
    {"name": "помощь", "description": "Все команды модерации"},
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


async def register(client: discord.Client, token: str) -> None:
    app_id = getattr(client, "application_id", None) or (client.user.id if client.user else None)
    if not app_id:
        return
    loop = asyncio.get_running_loop()
    code, res = await loop.run_in_executor(
        None, lambda: _rest("PUT", f"/applications/{app_id}/commands", token, COMMANDS))
    if code in (200, 201):
        print("[slash] русские команды: " + ", ".join("/" + c["name"] for c in COMMANDS))
    else:
        print("[slash] регистрация не удалась:", code, res.get("message"))


def _opt(name: str, value):
    return {"name": name, "value": value, "type": 3}


async def handle(client: discord.Client, token: str, data: dict) -> None:
    if data.get("type") != 2:
        return
    name = ((data.get("data") or {}).get("name") or "").lower()
    action = ALIASES.get(name)
    if action is None:
        return
    guild = client.get_guild(int(data["guild_id"])) if data.get("guild_id") else None
    if guild is None or not data.get("member"):
        return
    author = guild.get_member(int(data["member"]["user"]["id"]))
    if author is None:
        return

    loop = asyncio.get_running_loop()

    async def respond(text: str) -> None:
        payload = {"type": 4, "data": {"content": text, "flags": 64,
                                       "allowed_mentions": {"parse": []}}}
        await loop.run_in_executor(
            None, lambda: _rest("POST", f"/interactions/{data['id']}/{data['token']}/callback",
                                token, payload))

    if not textcmd._staff(author):
        await respond("⛔ Эти команды доступны только команде сервера.")
        return

    if action == "помощь":
        await respond(textcmd.HELP)
        return

    opts = {o["name"]: o.get("value") for o in ((data.get("data") or {}).get("options") or [])}
    target = None
    if opts.get("ник"):
        target = guild.get_member(int(opts["ник"]))
        if target is None:
            try:
                target = await guild.fetch_member(int(opts["ник"]))
            except discord.HTTPException:
                target = None
    if target is None:
        await respond("❓ Не нашёл такого участника.")
        return

    err = textcmd._can_punish(author, target)
    if err:
        await respond(f"⛔ {err}")
        return

    reason = (opts.get("причина") or "без причины").strip()
    reason_full = f"{reason} | модератор: {author}"

    try:
        if action == "мут":
            dur = mod.parse_duration(opts.get("время"))
            if dur is None:
                dur = mod.parse_duration("1ч")
            res = await mod.apply_mute(guild, target, dur, reason, author)
            if res.startswith("Discord") or res.startswith("роль"):
                await respond(f"❌ {res}")
                return
            await respond(
                f"🔇 **{target.display_name}** замучен на **{res}**\n"
                f"Причина: {reason}\n"
                f"Видит только «💤 AFK» и «🔇 В муте». Мут снимется сам.")
            await textcmd._log(guild, f"🔇 {author.mention} замутил {target.mention} на {res}. "
                                      f"Причина: {reason}")
        elif action == "анмут":
            ok = await mod.remove_mute(guild, target, str(author))
            await respond(f"🔊 **{target.display_name}** размучен." if ok
                          else f"ℹ️ У **{target.display_name}** не было мута.")
            await textcmd._log(guild, f"🔊 {author.mention} снял мут с {target.mention}")
        elif action == "кик":
            await target.kick(reason=reason_full)
            await respond(f"👢 **{target.display_name}** выгнан\nПричина: {reason}")
            await textcmd._log(guild, f"👢 {author.mention} выгнал {target} ({target.id}). Причина: {reason}")
        elif action == "бан":
            await target.ban(reason=reason_full, delete_message_days=0)
            await respond(f"🔨 **{target.display_name}** забанен\nПричина: {reason}")
            await textcmd._log(guild, f"🔨 {author.mention} забанил {target} ({target.id}). Причина: {reason}")
        elif action == "варн":
            await respond(f"⚠️ **{target.display_name}** получил предупреждение\nПричина: {reason}")
            await textcmd._log(guild, f"⚠️ {author.mention} выдал предупреждение {target.mention}. "
                                      f"Причина: {reason}")
    except discord.HTTPException as e:
        await respond(f"❌ Discord не дал выполнить: {e}")
