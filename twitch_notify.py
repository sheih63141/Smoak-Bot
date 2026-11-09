#!/usr/bin/env python3
"""
Автоуведомления о начале стрима Twitch → #📺│стримы.

Источник истины — САМО СООБЩЕНИЕ в канале: в footer embed лежит метка
«smoak-stream:<id эфира>». Поэтому:
  • перезапуск бота / новый раннер Actions НЕ создаёт дубль анонса;
  • если эфир начался, пока бот был выключен, анонс всё равно появится;
  • новый эфир (другой stream.id) анонсируется всегда.

Два режима:
  1) python twitch_notify.py          — один проход и выход (для GitHub Actions);
  2) automod_bot.py подхватывает watcher() — опрос каждые POLL_SECONDS секунд.

Twitch-ключи не нужны: публичный GraphQL-эндпоинт веб-плеера.
Настройки: TWITCH_LOGIN, STREAM_CHANNEL, POLL_SECONDS, PING_ROLE, TWITCH_FAKE_LIVE.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from pathlib import Path

import aiohttp
import discord

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "1568607492991353053"))
TWITCH_LOGIN = os.getenv("TWITCH_LOGIN", "smoak52")
STREAM_CHANNEL = os.getenv("STREAM_CHANNEL", "📺│стримы")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
PING_ROLE = os.getenv("PING_ROLE", "").strip()
FAKE_LIVE = os.getenv("TWITCH_FAKE_LIVE", "0") == "1"

GQL_URL = "https://gql.twitch.tv/gql"
GQL_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
API = "https://discord.com/api/v10"
STATE_FILE = Path(__file__).with_name("twitch_state.json")
COLOR = 0x9146FF
TAG = "smoak-stream:"

QUERY = ('query{user(login:"%s"){displayName stream{id title viewersCount createdAt game{name}}}}'
         % TWITCH_LOGIN)


class TwitchError(Exception):
    """Сеть/API подвёл — НЕ считать это «эфир закончился»."""


def fresh_state() -> dict:
    return {"live": False, "message_id": None, "stream_id": None,
            "started_at": None, "updates": 0}


def load_state() -> dict:
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {**fresh_state(), **s}
    except Exception:
        return fresh_state()


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def tag(stream: dict) -> str:
    return TAG + str(stream.get("id") or "live")


# --------------------------------------------------------------------------- REST
async def dapi(session: aiohttp.ClientSession, method: str, path: str, payload=None):
    headers = {"Authorization": f"Bot {TOKEN}", "User-Agent": "DiscordBot (smoak,1.0)"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        async with session.request(method, API + path, json=payload, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=20)) as resp:
            raw = await resp.text()
            try:
                body = json.loads(raw) if raw else {}
            except ValueError:
                body = {}
            return resp.status, body
    except Exception as e:
        raise TwitchError(f"Discord REST {method} {path}: {e!r}")


async def stream_channel_id(session) -> str | None:
    st, chans = await dapi(session, "GET", f"/guilds/{GUILD_ID}/channels")
    if st != 200 or not isinstance(chans, list):
        print(f"[twitch] не прочитал каналы: HTTP {st}")
        return None
    for c in chans:
        if c["type"] == 0 and c["name"] == STREAM_CHANNEL:
            return c["id"]
    print(f"[twitch] нет канала #{STREAM_CHANNEL}")
    return None


async def find_announcement(session, ch_id: str, stream: dict) -> str | None:
    """Ищем уже опубликованный анонс ЭТОГО эфира по метке в footer."""
    st, msgs = await dapi(session, "GET", f"/channels/{ch_id}/messages?limit=25")
    if st != 200 or not isinstance(msgs, list):
        return None
    t = tag(stream)
    for m in msgs:
        for e in m.get("embeds", []):
            if t in ((e.get("footer") or {}).get("text") or ""):
                return m["id"]
    return None


async def ping_content(session) -> str | None:
    if not PING_ROLE:
        return None
    st, roles = await dapi(session, "GET", f"/guilds/{GUILD_ID}/roles")
    if st == 200 and isinstance(roles, list):
        for r in roles:
            if r["name"] == PING_ROLE:
                return f"<@&{r['id']}>"
    return None


# --------------------------------------------------------------------------- Twitch
async def fetch_stream(session: aiohttp.ClientSession) -> dict | None:
    """dict = идёт эфир, None = офлайн. При ошибке сети — TwitchError."""
    if FAKE_LIVE:
        now = dt.datetime.now(dt.timezone.utc)
        return {"displayName": TWITCH_LOGIN, "id": "test",
                "title": "ТЕСТ уведомления — так будет выглядеть анонс эфира",
                "viewersCount": 12, "createdAt": now.isoformat().replace("+00:00", "Z"),
                "game": {"name": "Just Chatting"}}
    try:
        async with session.post(
            GQL_URL, json=[{"query": QUERY}],
            headers={"Client-ID": GQL_CLIENT_ID, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise TwitchError(f"Twitch HTTP {resp.status}: {(await resp.text())[:120]}")
            data = await resp.json()
    except TwitchError:
        raise
    except Exception as e:
        raise TwitchError(f"Twitch недоступен: {e!r}")
    try:
        user = data[0]["data"]["user"]
    except (KeyError, IndexError, TypeError):
        raise TwitchError(f"неожиданный ответ: {str(data)[:160]}")
    if not user:
        raise TwitchError(f"канал {TWITCH_LOGIN} не найден")
    return user.get("stream")          # None = офлайн


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
            pass
    e = discord.Embed(
        title=title, url=f"https://www.twitch.tv/{TWITCH_LOGIN}", colour=COLOR,
        description="**🔴 В эфире!** Заходи смотреть.")
    e.set_author(name=f"{stream.get('displayName') or TWITCH_LOGIN} · Twitch",
                 url=f"https://www.twitch.tv/{TWITCH_LOGIN}")
    e.add_field(name="🎮 Игра", value=game, inline=True)
    e.add_field(name="👀 Зрители", value=str(viewers), inline=True)
    if start_ts:
        e.add_field(name="⏱ Начало", value=f"<t:{start_ts}:t> (<t:{start_ts}:R>)", inline=True)
    e.set_image(url=f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{TWITCH_LOGIN.lower()}-1280x720.jpg")
    e.add_field(name="Ссылка", value=f"https://www.twitch.tv/{TWITCH_LOGIN}", inline=False)
    e.set_footer(text=("обновлено" if update else "стрим начался") + " · " + tag(stream))
    e.timestamp = dt.datetime.now(dt.timezone.utc)
    return e


def ended_embed(stream_tag: str, started_at: str | None) -> discord.Embed:
    e = discord.Embed(
        title="Эфир закончился",
        description=f"Спасибо, кто смотрел! Запись: https://www.twitch.tv/{TWITCH_LOGIN}/videos",
        colour=0x4B367C)
    if started_at:
        try:
            start = dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            mins = int((dt.datetime.now(dt.timezone.utc) - start).total_seconds() // 60)
            e.add_field(name="⏱ Длительность", value=f"{mins // 60} ч {mins % 60} мин")
        except ValueError:
            pass
    e.set_footer(text=stream_tag)
    e.timestamp = dt.datetime.now(dt.timezone.utc)
    return e


# --------------------------------------------------------------------------- один проход
async def run_once(session: aiohttp.ClientSession, state: dict) -> dict:
    ch_id = await stream_channel_id(session)
    if ch_id is None:
        return state
    stream = await fetch_stream(session)      # None = офлайн, TwitchError = сбой

    if stream is None:
        if state.get("live"):
            mid = state.get("message_id")
            if mid:
                await dapi(session, "PATCH", f"/channels/{ch_id}/messages/{mid}",
                           {"embeds": [ended_embed(tag({"id": state.get("stream_id")}),
                                                   state.get("started_at")).to_dict()]})
            print("[twitch] ⚫ эфир закончился")
            return fresh_state()
        return state

    mid = await find_announcement(session, ch_id, stream)
    updates = int(state.get("updates") or 0) + 1
    if mid is None:
        content = await ping_content(session)
        payload = {"embeds": [make_embed(stream).to_dict()]}
        if content:
            payload["content"] = content
        st, res = await dapi(session, "POST", f"/channels/{ch_id}/messages", payload)
        if st not in (200, 201):
            raise TwitchError(f"не опубликовал анонс: HTTP {st} {str(res)[:160]}")
        mid = res.get("id")
        if not content:
            await dapi(session, "PUT", f"/channels/{ch_id}/pins/{mid}")
        print(f"[twitch] 🔴 эфир начался — анонс {mid} (stream {stream.get('id')})")
        updates = 0
    elif updates % 5 == 0:
        await dapi(session, "PATCH", f"/channels/{ch_id}/messages/{mid}",
                   {"embeds": [make_embed(stream, update=True).to_dict()]})
        print(f"[twitch] 👀 обновил зрителей: {stream.get('viewersCount')}")
    else:
        print(f"[twitch] анонс уже есть (stream {stream.get('id')}) — дубль не публикуем")

    return {"live": True, "message_id": mid, "stream_id": stream.get("id"),
            "started_at": stream.get("createdAt"), "updates": updates}


# --------------------------------------------------------------------------- цикл для бота
async def watcher(client: discord.Client) -> None:
    await client.wait_until_ready()
    state = load_state()
    n = 0
    print(f"[twitch] следим за {TWITCH_LOGIN} → #{STREAM_CHANNEL} (опрос {POLL_SECONDS} с)")
    async with aiohttp.ClientSession() as session:
        while not client.is_closed():
            try:
                state = await run_once(session, state)
                save_state(state)
            except TwitchError as e:
                print("[twitch] API:", e)       # состояние НЕ трогаем
            except Exception as e:
                print("[twitch] ошибка:", repr(e))
            n += 1
            if n % 20 == 0:
                print(f"[twitch] цикл жив | {'в эфире ' + str(state.get('stream_id')) if state.get('live') else 'офлайн'}")
            await asyncio.sleep(POLL_SECONDS)


_task: asyncio.Task | None = None


def setup(client: discord.Client) -> None:
    """Совместимость с automod_bot."""
    return


async def on_ready(client: discord.Client) -> None:
    """Запустить watcher один раз; перезапустить, если задача умерла."""
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(watcher(client))


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ Нужен DISCORD_TOKEN")

    async def once():
        async with aiohttp.ClientSession() as session:
            state = await run_once(session, load_state())
            save_state(state)

    try:
        asyncio.run(once())
    except TwitchError as e:
        print("[twitch] API:", e)
        raise SystemExit(1)
