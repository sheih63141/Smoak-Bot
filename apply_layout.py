#!/usr/bin/env python3
"""
Применяет актуальную структуру SmoakTeam (дизайн CS-сообщества).

Идемпотентно: работает через REST и список каналов гильдии (без кэша discord.py),
поэтому при повторном запуске НЕ создаёт дубли. История сообщений сохраняется,
так как каналы переименовываются на месте по ID.

    DISCORD_TOKEN=... python3 apply_layout.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

GUILD_ID = int(os.getenv("GUILD_ID", "1568607492991353053"))
TOKEN = os.getenv("DISCORD_TOKEN", "")

# категория -> [(тип, имя, лимит)]   тип: 0 = текст, 2 = войс
LAYOUT = {
    "📢 ИНФОРМАЦИЯ": [
        (0, "📕│правила", 0), (0, "🎁│розыгрыш", 0),
        (0, "📺│стримы", 0), (0, "📢│объявления", 0),
    ],
    "💬 CHAT": [
        (0, "💬│флудилка", 0), (0, "🖼│мемы-и-клипы", 0),
        (0, "🎬│смотрим-фильм", 0),
    ],
    "🎫 ПОДДЕРЖКА": [(0, "🎫│подать-тикет", 0)],
    "🔊 ОБЩЕСТВЕННОЕ МЕСТО": [
        (2, "🚀 France - Paris", 0), (2, "🗽 Нью-Йорк - Walk street", 0),
        (2, "🏜 Дубай - Downtown", 0),
    ],
    "🔫 COUNTER-STRIKE": [
        (2, "🔫 Пати - 1", 5), (2, "🔫 Пати - 2", 5), (2, "🔫 Пати - 3", 5),
    ],
    "🎧 ЧИЛЛ": [
        (2, "🎧 Стрим - комната", 0), (2, "🎧 Чилл - 1", 0), (2, "🎧 Чилл - 2", 0),
        (2, "🎬 Смотрим - фильм", 0),
    ],
    "🔒 ПРИВАТНОЕ": [
        (2, "🎬 Стримерская", 0), (2, "👥 Тим - 1", 0),
        (2, "👥 Тим - 2", 0), (2, "💎 ВИП - комната", 0), (0, "💬│приват-чат", 0),
    ],
    "🛠 КОМАНДА (скрыто)": [
        (0, "🛡│мод-чат", 0), (0, "📋│логи", 0), (0, "📝│заявки", 0),
    ],
    "😴 AFK": [(2, "😴 AFK", 0)],
    "🔇 МУТ": [(2, "В муте", 0)],
}

# если канал называется по-старому — переименовать, а не создавать второй
ALIASES = {
    "🚀 France - Paris": ["🔊 Общий"],
    "🔫 Пати - 1": ["🔫 Пати 1", "🟢 Major players CS2"],
    "🔫 Пати - 2": ["🔫 Пати 2", "🟠 Premier 5x5", "🟠 Premier"],
    "🔫 Пати - 3": ["🔫 Пати 3", "🔴 Faceit"],
    "🎧 Стрим - комната": ["🎧 Стрим-комната", "🎬 Стрим-комната"],
    "🎧 Чилл - 1": ["🎧 Чилл", "🎧 Чилл 1"],
    "🎧 Чилл - 2": ["🎧 Чилл 2"],
    "🎬 Стримерская": ["🎬 Стример - ская"],
    "👥 Тим - 1": ["👥 Тим-1", "Тим-1"],
    "👥 Тим - 2": ["👥 Тим-2", "Тим-2"],
    "💎 ВИП - комната": ["💎 ВИП-комната", "ВИП-комната"],
    "😴 AFK": ["AFK", "😴 AFK - зона"],
    "📕│правила": ["правила"],
    "📺│стримы": ["анонсы-стримов"], "📢│объявления": ["объявления"],
    "💬│флудилка": ["общий-чат"], "🖼│мемы-и-клипы": ["мемы-и-клипы"],
    "🎫│подать-тикет": ["🎫-подать-тикет"],
    "🛡│мод-чат": ["мод-чат"], "📋│логи": ["логи"], "📝│заявки": ["заявки"],
    "💬│приват-чат": ["приват-чат"],
}


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


def main() -> None:
    status, channels = api("GET", f"/guilds/{GUILD_ID}/channels")
    if status != 200:
        raise SystemExit(f"не удалось прочитать каналы: {status} {channels}")
    # ВАЖНО: имя категории может совпадать с именем канала («😴 AFK»),
    # поэтому ищем отдельно по типам — иначе появляются дубли.
    by_cat = {c["name"]: c for c in channels if c["type"] == 4}
    by_ch = {(c["name"], c["type"]): c for c in channels if c["type"] in (0, 2)}
    cat_ids = {}

    for pos, (cat_name, items) in enumerate(LAYOUT.items()):
        cat = by_cat.get(cat_name)
        if cat is None:
            code, cat = api("POST", f"/guilds/{GUILD_ID}/channels",
                            {"name": cat_name, "type": 4, "position": pos})
            print(f"категория + {cat_name}: {code}")
        else:
            api("PATCH", f"/channels/{cat['id']}", {"position": pos})
        cat_ids[cat_name] = cat["id"]

    for cat_name, items in LAYOUT.items():
        for ch_pos, (kind, name, limit) in enumerate(items):
            ch = by_ch.get((name, kind))
            if ch is None:
                for alias in ALIASES.get(name, []):
                    ch = by_ch.get((alias, kind))
                    if ch:
                        code, _ = api("PATCH", f"/channels/{ch['id']}",
                                      {"name": name, "parent_id": cat_ids[cat_name],
                                       **({"user_limit": limit} if kind == 2 else {})})
                        print(f"  {alias} → {name}: {code}")
                        break
            if ch is None:
                code, ch = api("POST", f"/guilds/{GUILD_ID}/channels",
                               {"name": name, "type": kind,
                                "parent_id": cat_ids[cat_name],
                                **({"user_limit": limit} if kind == 2 else {})})
                print(f"  + {name}: {code}")
                if code not in (200, 201):
                    continue
            payload = {}
            if ch.get("parent_id") != cat_ids[cat_name]:
                payload["parent_id"] = cat_ids[cat_name]
            if kind == 2 and ch.get("user_limit") != limit:
                payload["user_limit"] = limit
            if payload:
                api("PATCH", f"/channels/{ch['id']}", payload)
    print("готово: структура применена, дублей нет")


if __name__ == "__main__":
    main()
