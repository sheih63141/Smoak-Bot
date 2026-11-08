#!/usr/bin/env python3
"""
Автоматика модерации для сервера SmoakTeam.

Что делает:
  1. МУТ. Выдали тайм-аут (timeout) → бот автоматически выдаёт роль «🔇 Заглушённый».
     Сняли тайм-аут → роль снимается. И наоборот: выдали роль вручную → включается тайм-аут.
  2. ПЕРЕКИДЫВАЕТ. Заглушённого участника, зашедшего в любой войс, бот переносит
     в канал «🤐 Мут-зона» (или отключает от голоса, если канала нет).
  3. АВТО-AFK ОТКЛЮЧЁН. Discord не присылает боту событие «участник говорит»,
     поэтому любой таймер «неактивности» переносил разговаривающих людей.
     Канал «😴 AFK» остаётся обычным войсом: заходят туда сами.

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
    MUTE_TIMEOUT_MINUTES=60  какой тайм-аут ставить, если роль выдали вручную
    AUTO_TIMEOUT_ON_ROLE=1 1 = роль вручную включает тайм-аут, 0 = не включать
"""
from __future__ import annotations

import asyncio
import json
import datetime
import os
import sys

import discord

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)
MUTE_TIMEOUT_MINUTES = int(os.getenv("MUTE_TIMEOUT_MINUTES", "60"))
AUTO_TIMEOUT_ON_ROLE = os.getenv("AUTO_TIMEOUT_ON_ROLE", "1") == "1"

MUTED_ROLE = os.getenv("MUTED_ROLE", "🔇 Мут")
MUTE_ZONE = "В муте"
AFK_NAME = "😴 AFK"
LOG_CHANNEL = "📋│логи"

# служебные роли: бот не трогает их в автоматике
SKIP_ROLES = {
    "👑 Владелец", "🛡 Администратор", "🔨 Модератор", "🧰 Хелпер",
    "🎥 Стример", "💎 ВИП", "🤖 Бот",
}

MEMBERS_INTENT = os.getenv("MEMBERS_INTENT", "0") == "1"

intents = discord.Intents.default()
intents.members = MEMBERS_INTENT   # привилегированный — включить Server Members Intent
intents.voice_states = True
intents.guilds = True

from discord.ext import commands as _dp_commands

client = _dp_commands.Bot(command_prefix="!", intents=intents, help_command=None)


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
    print(f"Бот на связи: {client.user}")
    for g in client.guilds:
        print(f"  сервер: {g.name} ({g.id}) | участников {g.member_count} | "
              f"роль мута: {'есть' if muted_role(g) else 'НЕТ'} | "
              f"мут-зона: {'есть' if discord.utils.get(g.voice_channels, name=MUTE_ZONE) else 'НЕТ'} | "
              f"AFK: {'есть' if discord.utils.get(g.voice_channels, name=AFK_NAME) else 'НЕТ'}")
    print(f"  тикеты (кнопка): {'вкл' if TICKETS else 'выкл'}")
    print("  выдача роли участника: после ника в задании 3")
    print(f"  стрим-уведомления: {'вкл → #анонсы-стримов' if TWITCH else 'выкл'}")
    print(f"  режим: авто-AFK выключен | "
          f"тайм-аут по роли {MUTE_TIMEOUT_MINUTES} мин ({'вкл' if AUTO_TIMEOUT_ON_ROLE else 'выкл'})")

    global _health_started
    if not _health_started:
        _health_started = True
        try:
            await _start_health()
        except Exception as e:      # порт занят — боту это не должно мешать
            print("[health] не поднялся:", repr(e))

    if MUTE_CORE:
        try:
            guild = client.guilds[0] if client.guilds else None
            if guild is not None:
                await mod_core.ensure_mute_setup(guild)
                await mod_core.apply_channel_rules(guild)
            logch = discord.utils.get(guild.text_channels, name="логи") if guild else None
            asyncio.create_task(mod_core.expire_loop(client, logch))
        except Exception as e:
            print("mute setup:", repr(e))

    try:
        import slash_commands
        slash_commands.build(client)
        client.add_view(slash_commands.NickButton())
        synced = await client.tree.sync()
        print("[slash] команды синхронизированы: " + ", ".join("/" + c.name for c in synced))
        for g in client.guilds:
            await slash_commands.ensure_nick_panel(g)
    except Exception as e:
        print("slash_commands:", repr(e))

    # хуки модулей (кнопки и уведомления) — один on_ready на весь процесс
    for name, mod, hook in (
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



@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    print(f"[reaction] {payload.emoji} в канале {payload.channel_id} от {payload.user_id}")
    for name in ("ticket_gate",):
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
    try:
        import slash_commands
        await slash_commands.prompt_newcomer(member)
    except Exception as e:
        print("nick prompt:", repr(e))


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



@client.event
async def on_message(message: discord.Message) -> None:
    """Команды модерации."""
    if message.guild is None or message.author.bot:
        return

    # /мут, /кик, /бан, /анмут, /помощь
    if mod_commands is not None:
        try:
            if await mod_commands.handle_message(client, message):
                return
        except Exception as e:
            print("commands:", repr(e))



# --------------------------------------------------------------- 3. AFK
# Автоперенос убран намеренно: шлюз Discord не сообщает о факте речи в войсе,
# поэтому бот не может отличить разговаривающего участника от молчащего.
# «😴 AFK» — обычный голосовой канал, туда заходят по желанию.


# --- тикеты: кнопка в #создать-тикет (ticket_gate.py) ---
try:
    import commands as mod_commands
except Exception as e:
    print("commands не подключён:", repr(e))
    mod_commands = None

try:
    import ticket_gate
    ticket_gate.setup(client)
    TICKETS = True
except Exception as e:
    print("ticket_gate не подключён:", repr(e))
    TICKETS = False

# «получить-роль» удалён: роль выдаётся только после ника в задании 3.
# role_gate.py и join_gate.py больше не подключаются, чтобы не было обхода.
GATE_BTN = False

GATE = False   # автовыдача роли при входе выключена: роль только после ника

# --- мут: автоснятие по истечении срока (moderation.py) ---
try:
    import moderation as mod_core
    MUTE_CORE = True
except Exception as e:
    print("moderation не подключён:", repr(e))
    MUTE_CORE = False

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
    domain = (os.getenv("PUBLIC_URL")
              or os.getenv("KOYEB_PUBLIC_DOMAIN")
              or os.getenv("RENDER_EXTERNAL_URL")
              or os.getenv("RAILWAY_PUBLIC_DOMAIN"))
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
