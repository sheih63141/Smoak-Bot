#!/usr/bin/env python3
"""
Автоуведомления о начале стрима на Twitch → канал #анонсы-стримов.

Как работает:
  раз в 60 секунд спрашивает у Twitch, идёт ли эфир у канала.
  Начался эфир  → публикует анонс (название, игра, зрители, превью, ссылка).
  Эфир идёт     → раз в 5 минут обновляет счётчик зрителей в том же сообщении.
  Эфир кончился → правит сообщение: «эфир закончился» + длительность.

Twitch-ключи НЕ нужны: используется публичный GraphQL-эндпоинт, который отдаёт
название стрима, игру, зрителей и время начала.

Запуск отдельно:
    export DISCORD_TOKEN=...
    export GUILD_ID=...
    export TWITCH_LOGIN=smoak52
    python twitch_notify.py

Либо в одном процессе с автоматикой модерации — automod_bot.py сам подхватит
этот модуль (см. функцию setup()).

Настройки:
    TWITCH_LOGIN=smoak52            канал Twitch
    STREAM_CHANNEL=анонсы-стримов   куда постить
    POLL_SECONDS=60                 период опроса
    PING_ROLE=                      имя роли для пинга (по умолчанию без пинга)
    TWITCH_FAKE_LIVE=1              тест: сыграть «эфир начался» без реального стрима
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from pathlib import Path

import aiohttp
import discord

TWITCH_LOGIN = os.getenv("TWITCH_LOGIN", "smoak52")
STREAM_CHANNEL = os.getenv("STREAM_CHANNEL", "📺│стримы")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
PING_ROLE = os.getenv("PING_ROLE", "").strip()
FAKE_LIVE = os.getenv("TWITCH_FAKE_LIVE", "0") == "1"

GQL_URL = "https://gql.twitch.tv/gql"
GQL_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # публичный client-id веб-плеера Twitch
STATE_FILE = Path(__file__).with_name("twitch_state.json")
COLOR = 0x9146FF

QUERY = (
    'query{user(login:"%s"){displayName stream{id title viewersCount createdAt game{name}}}}'
    % TWITCH_LOGIN
)


# --------------------------------------------------------------------------- состояние
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"live": False, "message_id": None, "started_at": None}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- Twitch
async def fetch_stream(session: aiohttp.ClientSession) -> dict | None:
    """Возвращает данные эфира или None, если канал офлайн."""
    if FAKE_LIVE:
        now = dt.datetime.now(dt.timezone.utc)
        return {
            "displayName": TWITCH_LOGIN,
            "id": "test",
            "title": "ТЕСТ уведомления — так будет выглядеть анонс эфира",
            "viewersCount": 12,
            "createdAt": now.isoformat().replace("+00:00", "Z"),
            "game": {"name": "Just Chatting"},
        }
    payload = [{"query": QUERY}]
    async with session.post(
        GQL_URL,
        json=payload,
        headers={"Client-ID": GQL_CLIENT_ID, "Content-Type": "application/json"},
        timeout=aiohttp.ClientTimeout(total=20),
    ) as resp:
        if resp.status != 200:
            print(f"[twitch] HTTP {resp.status}")
            return None
        data = await resp.json()
    try:
        user = data[0]["data"]["user"]
    except (KeyError, IndexError, TypeError):
        print("[twitch] неожиданный ответ:", str(data)[:200])
        return None
    if not user:
        print(f"[twitch] канал {TWITCH_LOGIN} не найден")
        return None
    return user.get("stream")


# --------------------------------------------------------------------------- embed
def make_embed(stream: dict, update: bool = False) -> discord.Embed:
    title = stream.get("title") or "Эфир"
    game = (stream.get("game") or {}).get("name") or "без категории"
    viewers = stream.get("viewersCount") or 0
    created = stream.get("createdAt")
    start_ts = None
    if created:
        try:
            start_ts = int(dt.datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp())
        except ValueError:
            start_ts = None

    e = discord.Embed(
        title=title,
        url=f"https://www.twitch.tv/{TWITCH_LOGIN}",
        colour=COLOR,
        description="**🔴 В эфире!** Заходи смотреть и обсудим в 🎧 Стрим-комната.",
    )
    e.set_author(name=f"{stream.get('displayName') or TWITCH_LOGIN} · Twitch",
                 url=f"https://www.twitch.tv/{TWITCH_LOGIN}")
    e.add_field(name="🎮 Игра", value=game, inline=True)
    e.add_field(name="👀 Зрители", value=str(viewers), inline=True)
    if start_ts:
        e.add_field(name="⏱ Начало", value=f"<t:{start_ts}:t> (<t:{start_ts}:R>)", inline=True)
    e.set_image(url=f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{TWITCH_LOGIN.lower()}-1280x720.jpg")
    e.add_field(name="Ссылка", value=f"https://www.twitch.tv/{TWITCH_LOGIN}", inline=False)
    e.set_footer(text="обновлено" if update else "стрим начался")
    e.timestamp = dt.datetime.now(dt.timezone.utc)
    return e


def ended_embed(stream: dict | None, started_at: str | None) -> discord.Embed:
    e = discord.Embed(
        title="Эфир закончился",
        description=f"Спасибо, кто смотрел! Запись: https://www.twitch.tv/{TWITCH_LOGIN}/videos",
        colour=0x4B367C,
    )
    if started_at:
        try:
            start = dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            mins = int((dt.datetime.now(dt.timezone.utc) - start).total_seconds() // 60)
            e.add_field(name="⏱ Длительность", value=f"{mins // 60} ч {mins % 60} мин")
        except ValueError:
            pass
    e.timestamp = dt.datetime.now(dt.timezone.utc)
    return e


# --------------------------------------------------------------------------- цикл
async def watcher(client: discord.Client) -> None:
    await client.wait_until_ready()
    state = load_state()
    poll = 0
    print(f"[twitch] следим за {TWITCH_LOGIN} → #{STREAM_CHANNEL} (опрос {POLL_SECONDS} с)")
    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            try:
                guild = (client.get_guild(int(os.getenv("GUILD_ID", "0") or 0))
                         if os.getenv("GUILD_ID") else None) or (client.guilds[0] if client.guilds else None)
                if guild:
                    channel = discord.utils.get(guild.text_channels, name=STREAM_CHANNEL)
                    stream = await fetch_stream(session)
                    is_live = stream is not None

                    # --- эфир начался
                    if is_live and not state.get("live"):
                        if channel:
                            content = None
                            if PING_ROLE:
                                role = discord.utils.get(guild.roles, name=PING_ROLE)
                                content = role.mention if role else None
                            msg = await channel.send(content=content, embed=make_embed(stream))
                            if not content:
                                await msg.pin(reason="анонс эфира")
                            state = {"live": True, "message_id": msg.id,
                                     "started_at": stream.get("createdAt")}
                            save_state(state)
                            print(f"[twitch] 🔴 эфир начался — анонс опубликован (id {msg.id})")
                        else:
                            print(f"[twitch] нет канала #{STREAM_CHANNEL}")

                    # --- эфир идёт: обновляем зрителей
                    elif is_live and state.get("live"):
                        poll += 1
                        if poll % 5 == 0 and channel and state.get("message_id"):
                            try:
                                msg = await channel.fetch_message(state["message_id"])
                                await msg.edit(embed=make_embed(stream, update=True))
                            except discord.NotFound:
                                # сообщение удалили — перезапостим
                                state["message_id"] = None
                                state["live"] = False
                            except discord.HTTPException:
                                pass

                    # --- эфир кончился
                    elif not is_live and state.get("live"):
                        if channel and state.get("message_id"):
                            try:
                                msg = await channel.fetch_message(state["message_id"])
                                await msg.edit(embed=ended_embed(None, state.get("started_at")))
                            except (discord.NotFound, discord.HTTPException):
                                pass
                        print("[twitch] ⚫ эфир закончился")
                        state = {"live": False, "message_id": None, "started_at": None}
                        save_state(state)
            except Exception as e:  # цикл не должен падать
                print("[twitch] ошибка:", repr(e))
            await asyncio.sleep(POLL_SECONDS)


_started = False


def setup(client: discord.Client) -> None:
    """Ничего не регистрирует: совместимость с automod_bot."""
    return


async def on_ready(client: discord.Client) -> None:
    """Хук: запустить цикл опроса Twitch один раз."""
    global _started
    if _started:
        return
    _started = True
    asyncio.create_task(watcher(client))


if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.guilds = True
    own_client = discord.Client(intents=intents)

    @own_client.event
    async def on_ready() -> None:
        await globals()["on_ready"](own_client)

    token = os.getenv("DISCORD_TOKEN", "")
    if not token:
        raise SystemExit("❌ Нужен DISCORD_TOKEN")
    own_client.run(token)
