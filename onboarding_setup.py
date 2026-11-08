#!/usr/bin/env python3
"""
Онбординг SmoakTeam: 2 задания, ник НЕ требуется.

1) «Кто ты?»            — обязательное, сразу выдаёт роль «👋 Участник»;
2) «Что тебе интересно?» — по желанию, открывает тематические каналы.

Раньше было третье задание «Ник с Твича» — убрано по просьбе владельца:
новичок попадает на сервер без всяких форм и смены ника.

Идемпотентно: повторный запуск переиспользует ID существующих вопросов.
    DISCORD_TOKEN=... GUILD_ID=... python3 onboarding_setup.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

GUILD_ID = os.getenv("GUILD_ID", "1568607492991353053")
TOKEN = os.getenv("DISCORD_TOKEN", "")

RULES = "1568626357791887501"          # 📕│правила
CH_STREAMS = "1568626387017797803"     # 📺│стримы
CH_CHAT = "1568626371335557238"        # 💬│флудилка
CH_MEMES = "1568626373591826443"       # 🖼│мемы-и-клипы
CH_PARTY1 = "1568626398300602511"      # 🔫 Пати - 1
CH_PARTY2 = "1568626399793651904"      # 🔫 Пати - 2
MEMBER_ROLE = "1568626326792048693"    # 👋 Участник


def emoji(name: str) -> dict:
    return {"id": None, "name": name, "animated": False}


def api(method: str, path: str, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request("https://discord.com/api/v10" + path,
                                 data=body, method=method)
    req.add_header("Authorization", f"Bot {TOKEN}")
    req.add_header("User-Agent", "DiscordBot (smoak,1.0)")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


_seq = 0


def snowflake() -> str:
    """Уникальный ID для нового вопроса/варианта (Discord требует id даже у новых)."""
    global _seq
    _seq += 1
    return str(((int(time.time() * 1000) - 1420070400000) << 22) | (_seq & 0x3FFFFF))


def opt(title: str, description: str, channels=(), roles=(),
        emoji_name="✅", old=None) -> dict:
    o = {
        "title": title,
        "description": description,
        "emoji": emoji(emoji_name),
        "channel_ids": list(channels),
        "role_ids": list(roles),
    }
    o["id"] = old["id"] if old else snowflake()
    return o


def prompt(title: str, options, *, single: bool, required: bool, old=None) -> dict:
    p = {
        "title": title,
        "options": options,
        "single_select": single,
        "required": required,
        "in_onboarding": True,
        "type": 0,
    }
    p["id"] = old["id"] if old else snowflake()
    return p


def main() -> None:
    status, current = api("GET", f"/guilds/{GUILD_ID}/onboarding")
    if status != 200:
        raise SystemExit(f"не прочитал онбординг: {status} {current}")
    old_prompts = {p["title"]: p for p in current.get("prompts", [])}

    def old(t: str):
        return old_prompts.get(t)

    def old_option(p: dict | None, title: str):
        if not p:
            return None
        return next((o for o in p.get("options", []) if o["title"] == title), None)

    p1 = old("Кто ты?")
    p2 = old("Что тебе интересно?")

    prompts = [
        prompt("Кто ты?", [
            opt("👋 Я участник — с правилами ознакомлен",
                "Сразу выдаст роль «Участник» и откроет все каналы",
                [RULES], [MEMBER_ROLE], "👋",
                old_option(p1, "👋 Я участник — с правилами ознакомлен")),
        ], single=True, required=True, old=p1),
        prompt("Что тебе интересно?", [
            opt("🔫 CS2 и пати", "Пати-каналы Counter-Strike",
                [CH_PARTY1, CH_PARTY2], (), "🔫", old_option(p2, "🔫 CS2 и пати")),
            opt("📺 Стримы", "Анонсы эфиров", [CH_STREAMS], (), "📺",
                old_option(p2, "📺 Стримы")),
            opt("💬 Общение и мемы", "Флудилка, мемы и клипы",
                [CH_CHAT, CH_MEMES], (), "💬", old_option(p2, "💬 Общение и мемы")),
        ], single=False, required=False, old=p2),
    ]

    payload = {
        "prompts": prompts,
        "default_channel_ids": [RULES],
        "enabled": True,
        "mode": 1,
    }
    status, res = api("PUT", f"/guilds/{GUILD_ID}/onboarding", payload)
    print("PUT /onboarding:", status)
    if status != 200:
        print(json.dumps(res, ensure_ascii=False, indent=2)[:1500])
        raise SystemExit(1)
    for i, p in enumerate(res.get("prompts", []), 1):
        print(f"  задание {i}: {p['title']} "
              f"({'обязательное' if p['required'] else 'по желанию'})")
        for o in p["options"]:
            print(f"     {o['title']} → роли {o['role_ids']}")
    print("  ник не требуется")


if __name__ == "__main__":
    main()
