#!/usr/bin/env python3
"""
Автоматика модерации для сервера SmoakTeam.

Что делает:
  1. МУТ. Выдали тайм-аут (timeout) → бот автоматически выдаёт роль «🔇 Заглушённый».
     Сняли тайм-аут → роль снимается. И наоборот: выдали роль вручную → включается тайм-аут.
  2. ПЕРЕКИДЫВАЕТ. Заглушённого участника, зашедшего в любой войс, бот переносит
     в канал «🤐 Мут-зона» (или отключает от голоса, если канала нет).
  3. НЕАКТИВНОСТЬ. Если человек сидит в войсе и N минут ничего не делает
     (не говорит, не стримит, не переключался, не писал в чат) — бот переносит его в AFK.

Запуск:
    pip install discord.py
    export DISCORD_TOKEN=...   (или .env)
    export GUILD_ID=...
    python automod_bot.py

ВАЖНО (одноразовая настройка в Developer Portal):
    Bot → Privileged Gateway Intents → включить **SERVER MEMBERS INTENT**
    Без него бот не увидит тайм-ауты и участников.

Бот должен работать постоянно (ПК, VPS, хостинг ботов). Пока процесс жив — работает автоматика.

Настройки через переменные окружения:
    IDLE_MINUTES=15        через сколько минут неактивности кидать в AFK (0 = выключить)
    MUTE_TIMEOUT_MINUTES=60  какой тайм-аут ставить, если роль выдали вручную
    AUTO_TIMEOUT_ON_ROLE=1 1 = роль вручную включает тайм-аут, 0 = не включать
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys

import discord

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)
IDLE_MINUTES = int(os.getenv("IDLE_MINUTES", "15"))
MUTE_TIMEOUT_MINUTES = int(os.getenv("MUTE_TIMEOUT_MINUTES", "60"))
AUTO_TIMEOUT_ON_ROLE = os.getenv("AUTO_TIMEOUT_ON_ROLE", "1") == "1"

MUTED_ROLE = "🔇 Заглушённый"
MUTE_ZONE = "🤐 Мут-зона"
AFK_NAME = "AFK"
LOG_CHANNEL = "логи"

# кого не трогаем при авто-AFK
SKIP_ROLES = {
    "👑 Владелец", "🛡 Администратор", "🔨 Модератор", "🧰 Хелпер",
    "🎥 Стример", "💎 ВИП", "🤖 Бот",
}

MEMBERS_INTENT = os.getenv("MEMBERS_INTENT", "0") == "1"

intents = discord.Intents.default()
intents.members = MEMBERS_INTENT   # привилегированный — включить Server Members Intent
intents.voice_states = True
intents.guilds = True

client = discord.Client(intents=intents)
last_activity: dict[tuple[int, int], datetime.datetime] = {}
_loop: asyncio.Task | None = None


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def log(guild: discord.Guild, text: str) -> None:
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch is None:
        return
    try:
        await ch.send(f"🤖 {text}")
    except discord.HTTPException:
        pass


def muted_until(member):
    """Время окончания тайм-аута (в разных сборках discord.py поле зовётся по-разному)."""
    return getattr(member, "timed_out_until", None) or getattr(member, "communication_disabled_until", None)


def is_protected(member: discord.Member) -> bool:
    if member.bot:
        return True
    return any(r.name in SKIP_ROLES for r in member.roles)


def muted_role(guild: discord.Guild) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=MUTED_ROLE)


@client.event
async def on_ready() -> None:
    global _loop
    print(f"Бот на связи: {client.user}")
    for g in client.guilds:
        print(f"  сервер: {g.name} ({g.id}) | участников {g.member_count} | "
              f"роль мута: {'есть' if muted_role(g) else 'НЕТ'} | "
              f"мут-зона: {'есть' if discord.utils.get(g.voice_channels, name=MUTE_ZONE) else 'НЕТ'} | "
              f"AFK: {'есть' if discord.utils.get(g.voice_channels, name=AFK_NAME) else 'НЕТ'}")
    print(f"  тикеты (кнопка): {'вкл' if TICKETS else 'выкл'}")
    print(f"  автовыдача роли участника: {'вкл' if GATE else 'выкл'}")
    print(f"  стрим-уведомления: {'вкл → #анонсы-стримов' if TWITCH else 'выкл'}")
    print(f"  режим: AFK через {IDLE_MINUTES} мин неактивности, "
          f"тайм-аут по роли {MUTE_TIMEOUT_MINUTES} мин ({'вкл' if AUTO_TIMEOUT_ON_ROLE else 'выкл'})")
    if _loop is None or _loop.done():
        _loop = asyncio.create_task(idle_watcher())

    global _health_started
    if not _health_started:
        _health_started = True
        try:
            await _start_health()
        except Exception as e:      # порт занят — боту это не должно мешать
            print("[health] не поднялся:", repr(e))

    # хуки модулей (кнопки и уведомления) — один on_ready на весь процесс
    for name, mod, hook in (
        ("role_gate", globals().get("role_gate"), "on_ready"),
        ("ticket_gate", globals().get("ticket_gate"), "on_ready"),
        ("twitch_notify", globals().get("twitch_notify"), "on_ready"),
    ):
        if mod is None:
            continue
        try:
            await getattr(mod, hook)(client)
        except Exception as e:
            print(f"{name} hook:", repr(e))


# --------------------------------------------------------------------------- 1. муть ↔ тайм-аут
@client.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    guild = after.guild
    role = muted_role(guild)
    if role is None:
        return

    was_muted = muted_until(before) is not None
    now_muted = muted_until(after) is not None
    has_role = role in after.roles
    had_role = role in before.roles

    # дали тайм-аут -> выдаём роль
    if now_muted and not has_role:
        try:
            await after.add_roles(role, reason="авто: выдан тайм-аут")
            await log(guild, f"🔇 {after.mention} получил тайм-аут → выдана роль «{MUTED_ROLE}»")
        except discord.HTTPException as e:
            print("не смог выдать роль:", e)

    # сняли тайм-аут -> снимаем роль
    elif not now_muted and was_muted and has_role:
        try:
            await after.remove_roles(role, reason="авто: тайм-аут снят")
            await log(guild, f"🔊 {after.mention} — тайм-аут снят, роль «{MUTED_ROLE}» убрана")
        except discord.HTTPException as e:
            print("не смог снять роль:", e)

    # роль выдали вручную -> ставим тайм-аут (чтобы мут работал и в голосе)
    elif AUTO_TIMEOUT_ON_ROLE and has_role and not had_role and not now_muted:
        try:
            await after.timeout(
                datetime.timedelta(minutes=MUTE_TIMEOUT_MINUTES),
                reason="авто: выдана роль мута",
            )
            await log(guild, f"⏳ {after.mention} получил роль «{MUTED_ROLE}» вручную → тайм-аут {MUTE_TIMEOUT_MINUTES} мин")
        except discord.HTTPException as e:
            print("не смог поставить тайм-аут:", e)

    # роль сняли вручную -> снимаем тайм-аут
    elif had_role and not has_role and now_muted:
        try:
            await after.timeout(None, reason="авто: снята роль мута")
            await log(guild, f"✅ {after.mention} — роль «{MUTED_ROLE}» снята, тайм-аут тоже")
        except discord.HTTPException as e:
            print("не смог снять тайм-аут:", e)

    # хуки других модулей (например, выдача роли после принятия правил)
    mod = globals().get("join_gate")
    if mod:
        try:
            await mod.handle_member_update(before, after)
        except Exception as e:
            print("join_gate:", repr(e))


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    print(f"[reaction] {payload.emoji} в канале {payload.channel_id} от {payload.user_id}")
    for name in ("ticket_gate", "role_gate"):
        mod = globals().get(name)
        if mod is None:
            continue
        try:
            handled = await mod.handle_raw_reaction_add(client, payload)
            if handled:
                return
        except Exception as e:
            print(f"{name}:", repr(e))


@client.event
async def on_member_join(member: discord.Member) -> None:
    mod = globals().get("join_gate")
    if mod:
        try:
            await mod.handle_member_join(member)
        except Exception as e:
            print("join_gate:", repr(e))


# ------------------------------------------------------- 2. перекидывание в мут-зону + трекинг
@client.event
async def on_voice_state_update(member: discord.Member,
                                before: discord.VoiceState,
                                after: discord.VoiceState) -> None:
    if member.bot:
        return
    guild = member.guild

    # заглушённых изолируем
    role = muted_role(guild)
    silenced = (role in member.roles) or (muted_until(member) is not None)
    if silenced and after.channel is not None:
        zone = discord.utils.get(guild.voice_channels, name=MUTE_ZONE)
        if zone and after.channel != zone:
            try:
                await member.move_to(zone, reason="авто: участник заглушён")
                await log(guild, f"🤐 {member.mention} заглушён → перенесён в «{MUTE_ZONE}»")
            except discord.HTTPException:
                pass
        elif zone is None:
            try:
                await member.move_to(None, reason="авто: участник заглушён")
            except discord.HTTPException:
                pass
        return

    # активность
    key = (guild.id, member.id)
    if after.channel is None:
        last_activity.pop(key, None)
        return
    fired = (
        before.channel != after.channel
        or after.self_stream != before.self_stream
        or after.self_video != before.self_video
        or after.self_mute != before.self_mute
        or after.self_deaf != before.self_deaf
    )
    if fired or key not in last_activity:
        last_activity[key] = utcnow()


@client.event
async def on_message(message: discord.Message) -> None:
    """Написал в чат, сидя в войсе — значит живой."""
    if message.guild is None or message.author.bot:
        return
    member = message.author
    if getattr(member, "voice", None) and member.voice and member.voice.channel:
        last_activity[(message.guild.id, member.id)] = utcnow()


# --------------------------------------------------------------- 3. AFK-сторож
async def idle_watcher() -> None:
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            if IDLE_MINUTES > 0:
                for guild in client.guilds:
                    afk = discord.utils.get(guild.voice_channels, name=AFK_NAME) or guild.afk_channel
                    if afk is None:
                        continue
                    for vc in guild.voice_channels:
                        if vc == afk:
                            continue
                        for member in list(vc.members):
                            if is_protected(member):
                                continue
                            if member.voice and (member.voice.self_stream or member.voice.self_video):
                                last_activity[(guild.id, member.id)] = utcnow()
                                continue
                            key = (guild.id, member.id)
                            last = last_activity.get(key)
                            if last is None:
                                last_activity[key] = utcnow()
                                continue
                            idle_min = (utcnow() - last).total_seconds() / 60
                            if idle_min >= IDLE_MINUTES:
                                try:
                                    await member.move_to(afk, reason=f"авто-AFK: {int(idle_min)} мин без активности")
                                    last_activity.pop(key, None)
                                    await log(guild, f"💤 {member.mention} — {int(idle_min)} мин без активности → AFK")
                                except discord.HTTPException:
                                    pass
            if IDLE_MINUTES > 0 or True:
                print(f"[heartbeat] {utcnow().strftime('%H:%M:%S')} — бот жив, "
                      f"соединение: {'закрыто' if client.is_closed() else 'ок'}")
        except Exception as e:  # сторож не должен падать
            print("idle_watcher:", repr(e))
        await asyncio.sleep(60)


# --- тикеты: кнопка в #создать-тикет (ticket_gate.py) ---
try:
    import ticket_gate
    ticket_gate.setup(client)
    TICKETS = True
except Exception as e:
    print("ticket_gate не подключён:", repr(e))
    TICKETS = False

# --- кнопка «получить роль» в #получить-роль (role_gate.py) ---
try:
    import role_gate
    role_gate.setup(client)
    GATE_BTN = True
except Exception as e:
    print("role_gate не подключён:", repr(e))
    GATE_BTN = False

# --- автовыдача роли участника при входe (join_gate.py) ---
try:
    import join_gate
    join_gate.setup(client)
    GATE = True
except Exception as e:
    print("join_gate не подключён:", repr(e))
    GATE = False

# --- уведомления о стриме Twitch в том же процессе (если модуль рядом) ---
try:
    import twitch_notify
    twitch_notify.setup(client)
    TWITCH = True
except Exception as e:  # модуль не обязателен
    print("twitch_notify не подключён:", repr(e))
    TWITCH = False


_health_started = False


async def _start_health() -> None:
    """Мини-HTTP для бесплатных хостингов (Render/Koyeb/Railway требуют открытый порт)."""
    port = os.getenv("PORT")
    if not port:
        print("[health] PORT не задан — HTTP-сервер не нужен (локальный запуск)")
        return
    try:
        from aiohttp import web
    except ImportError:
        print("aiohttp не установлен — health-check пропущен")
        return

    async def ping(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ping)
    app.router.add_get("/health", ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port))
    try:
        await site.start()
        print(f"[health] слушаю порт {port}")
    except OSError as e:
        print(f"[health] порт {port} занят: {e}")
        return

    # самопинг: бесплатный инстанс Koyeb засыпает без HTTP-трафика —
    # дёргаем свой публичный адрес каждые 4 минуты
    domain = os.getenv("PUBLIC_URL") or os.getenv("KOYEB_PUBLIC_DOMAIN")
    if domain:
        if not domain.startswith("http"):
            domain = "https://" + domain
        asyncio.create_task(_keep_awake(domain.rstrip("/")))
        print(f"[health] самопинг включён → {domain}")


async def _keep_awake(url: str) -> None:
    """Каждые 4 минуты пингует собственный /health, чтобы инстанс не засыпал."""
    import aiohttp
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.get(f"{url}/health") as r:
                    print(f"[keep-awake] {r.status}")
        except Exception as e:
            print("[keep-awake]", repr(e))
        await asyncio.sleep(240)


if __name__ == "__main__":
    if not TOKEN:
        print("❌ Нужен DISCORD_TOKEN")
        sys.exit(1)
    try:
        client.run(TOKEN)
    except discord.PrivilegedIntentsRequired:
        print("\n" + "=" * 68)
        print("❌ ВКЛЮЧИТЕ ОДНУ ГАЛКУ В DEVELOPER PORTAL — без неё автоматика не работает")
        print("=" * 68)
        print("https://discord.com/developers/applications → ваше приложение → Bot →")
        print("Privileged Gateway Intents → включить **SERVER MEMBERS INTENT** → Save Changes")
        print("\nЗатем запустите снова. Галку может поставить только владелец приложения.")
        print("Диагностический запуск без неё (часть функций не будет работать):")
        print("  MEMBERS_INTENT=0 python automod_bot.py")
        sys.exit(2)
