#!/usr/bin/env python3
"""
«Смотрим фильм»: пишешь боту — он сам поднимает совместный просмотр.

Как это работает в Discord:
  бот создаёт приглашение в голосовой канал с активностью «Смотрим вместе»
  (Watch Together) и сразу постит кнопку-ссылку. По клику Discord сам
  закидывает человека в войс и открывает плеер — фильм выбирают вместе.

Способы запуска:
  • кнопка «🎬 Включить фильм» в #🎬│смотрим-фильм;
  • /фильм [ссылка] — надёжно, не требует Message Content Intent;
  • !фильм [ссылка] в том же канале — заработает после включения
    Message Content Intent в Developer Portal.

Боты в Discord не умеют транслировать видео в голосовой канал (это «Прямой эфир»
пользователя), поэтому запуск идёт через встроенную активность Discord.
"""
from __future__ import annotations

import discord
from discord import app_commands

MOVIE_TEXT = "🎬│смотрим-фильм"
MOVIE_VOICE = "🎬 Смотрим - фильм"
WATCH_TOGETHER = 880218394199220334      # встроенная активность «Смотрим вместе»
PANEL_MARK = "СМОТРИМ ФИЛЬМ"
BUTTON_ID = "smoak:movie"


def _link_from(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip()
    return t if t.startswith(("http://", "https://")) else None


async def start_movie(ctx, link: str | None = None) -> None:
    """ctx = Interaction (кнопка/слэш-команда) или Message (!фильм)."""
    if isinstance(ctx, discord.Interaction):
        if ctx.response.is_done():
            return
        await ctx.response.defer()          # укладываемся в 3 секунды Discord
        guild = ctx.guild
    else:
        guild = ctx.guild
        if guild is None:
            return

    voice = discord.utils.get(guild.voice_channels, name=MOVIE_VOICE)
    if voice is None:
        return await _send(ctx, "❌ Нет голосового канала «🎬 Смотрим - фильм».")

    try:
        invite = await voice.create_invite(
            max_age=3600, max_uses=0, unique=True,
            target_type=discord.InviteTarget.embedded_application,
            target_application_id=WATCH_TOGETHER,
            reason="запуск совместного просмотра",
        )
    except discord.HTTPException as e:
        return await _send(ctx, f"❌ Не удалось запустить просмотр: {e}")

    embed = discord.Embed(
        title="🎬 Смотрим фильм",
        description=(f"Просмотр запущен в **{voice.name}**.\n"
                     "Жми кнопку ниже — Discord сам закинет тебя в войс и откроет "
                     "плеер «Смотрим вместе». Фильм выбираете вместе.\n\n"
                     "Ссылка живёт 1 час, зайти могут все."),
        color=0xE50914)
    if link:
        embed.add_field(name="Фильм", value=link, inline=False)
    embed.set_footer(text=PANEL_MARK)

    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="▶️ Запустить просмотр", emoji="🍿",
                                    style=discord.ButtonStyle.link, url=invite.url))
    if link:
        view.add_item(discord.ui.Button(label="🎞 Открыть фильм",
                                        style=discord.ButtonStyle.link, url=link))
    await _send(ctx, embed=embed, view=view)


async def _send(ctx, content=None, *, embed=None, view=None) -> None:
    if isinstance(ctx, discord.Interaction):
        await ctx.followup.send(content=content, embed=embed, view=view)
    else:
        await ctx.reply(content=content, embed=embed, view=view, mention_author=False)


class MovieButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)      # постоянная кнопка, живёт после рестарта

    @discord.ui.button(label="Включить фильм", emoji="🎬", style=discord.ButtonStyle.primary,
                       custom_id=BUTTON_ID)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.response.is_done():
            return
        try:
            await start_movie(interaction)
        except Exception as e:
            print("[movie] кнопка:", repr(e))


def panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="🎬 Смотрим фильм",
        description=("Нажми **Включить фильм** — бот сам создаст сеанс «Смотрим вместе» "
                     "в голосовом канале и даст ссылку.\n\n"
                     "Можно написать `!фильм` или `/фильм`, либо сразу `/фильм ссылка:...` — "
                     "тогда бот прикрепит и ссылку на фильм."),
        color=0xE50914)
    e.set_footer(text=PANEL_MARK)
    return e


async def ensure_panel(guild: discord.Guild) -> None:
    ch = discord.utils.get(guild.text_channels, name=MOVIE_TEXT)
    if ch is None:
        return
    try:
        async for m in ch.history(limit=30):
            if m.author.id == guild.me.id and m.embeds and \
                    (m.embeds[0].footer and m.embeds[0].footer.text == PANEL_MARK):
                return
        msg = await ch.send(embed=panel_embed(), view=MovieButton())
        try:
            await msg.pin(reason="панель «Смотрим фильм»")
        except discord.HTTPException:
            pass
        print("[movie] панель готова в #", MOVIE_TEXT)
    except discord.HTTPException as e:
        print("[movie] панель:", repr(e))


async def handle_message(client: discord.Client, message: discord.Message) -> bool:
    """!фильм [ссылка] в #🎬│смотрим-фильм. Нужен Message Content Intent."""
    if message.guild is None or message.author.bot:
        return False
    if getattr(message.channel, "name", "") != MOVIE_TEXT:
        return False
    text = (message.content or "").strip()
    low = text.lower()
    if not low.startswith(("!фильм", "!кино")):
        return False
    rest = text.split(" ", 1)[1] if " " in text else ""
    await start_movie(message, _link_from(rest))
    return True


def slash_command():
    @app_commands.command(name="фильм", description="Запустить совместный просмотр фильма")
    @app_commands.describe(ссылка="Ссылка на фильм — необязательно")
    async def film(interaction: discord.Interaction, ссылка: str | None = None):
        await start_movie(interaction, _link_from(ссылка))
    return film
