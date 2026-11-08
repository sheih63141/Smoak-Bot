#!/usr/bin/env python3
"""
Русские слэш-команды + выдача ника с Твича.

Команды модерации (коротко, без дублей):
    /мут        — роль 🔇 Мут: видит только «💤 AFK» и «🔇 В муте», микрофон запрещён
    /снятьмут   — снять мут
    /кик        — выгнать
    /бан        — забанить
    /пред       — предупреждение
    /помощь     — шпаргалка

Ник с Твича:
    в «#получить-роль» висит кнопка «Указать ник» → модалка «Ник: (Твича)» →
    жмёшь «Готово» → бот ставит ник. Новенького бот сам зовёт в канал.
"""
from __future__ import annotations

import discord
from discord import app_commands

import commands as textcmd
import moderation as mod

NICK_CHANNEL = "🔑│получить-роль"
PANEL_MARK = "УКАЗАТЬ НИК TWITCH"


# ---------------------------------------------------------------- модалка ника

class NickModal(discord.ui.Modal, title="Твой ник с Твича"):
    def __init__(self):
        super().__init__(timeout=600)
        self.nick = discord.ui.TextInput(
            label="Ник: (Твича)",
            placeholder="например: smoak52",
            min_length=2, max_length=32, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        value = str(self.nick.value).strip()
        try:
            await interaction.user.edit(nick=value)
        except discord.Forbidden:
            await interaction.response.send_message(
                "⛔ Не могу сменить ник: владелец сервера или роль выше моей.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Discord не дал сменить ник: {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Готово, теперь ты **{value}**", ephemeral=True)


class NickButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # постоянная кнопка — работает и после перезапуска

    @discord.ui.button(label="Указать ник", emoji="🎮", style=discord.ButtonStyle.success,
                       custom_id="smoak:setnick")
    async def set_nick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NickModal())


def nick_panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="Ник: (Твича)",
        description=("Нажми **Указать ник** и впиши свой ник с Twitch — бот сразу поставит его "
                     "тебе на сервере.\n\n"
                     "Пример: `smoak52` → ник на сервере станет **smoak52**.\n"
                     "Поменять можно в любой момент."),
        color=0x9146FF)
    e.set_footer(text=PANEL_MARK)
    return e


async def ensure_nick_panel(guild: discord.Guild) -> None:
    ch = discord.utils.get(guild.text_channels, name=NICK_CHANNEL)
    if ch is None:
        return
    try:
        async for m in ch.history(limit=40):
            if m.author.id == guild.me.id and m.embeds and \
                    (m.embeds[0].footer and m.embeds[0].footer.text == PANEL_MARK):
                return
        await ch.send(embed=nick_panel_embed(), view=NickButton())
        print("[nick] панель ника готова")
    except discord.HTTPException as e:
        print("[nick] панель:", repr(e))


async def prompt_newcomer(member: discord.Member) -> None:
    """Зовём новичка указать ник — в канал, без личных сообщений."""
    ch = discord.utils.get(member.guild.text_channels, name=NICK_CHANNEL)
    if ch is None:
        return
    try:
        await ch.send(
            f"{member.mention} добро пожаловать! Поставь ник с Твича: нажми кнопку ниже → "
            f"**Ник: (Твича)** → **Готово**.",
            view=NickButton(), delete_after=900)
    except discord.HTTPException:
        pass


# ---------------------------------------------------------------- команды

def build(role_mute):
    """Регистрирует команды на дереве бота."""
    group = app_commands.Group

    async def _target(interaction: discord.Interaction, member: discord.Member):
        err = textcmd._can_punish(interaction.user, member)
        if err:
            await interaction.response.send_message(f"⛔ {err}", ephemeral=True)
            return False
        if not textcmd._staff(interaction.user):
            await interaction.response.send_message(
                "⛔ Эти команды доступны только команде сервера.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="мут", description="Мут: роль 🔇 Мут, видит только AFK и «В муте»")
    @app_commands.describe(ник="Кого наказываем", время="10м, 2ч, 7д (пусто — 1 час)",
                           причина="За что наказание")
    async def mute(interaction: discord.Interaction, ник: discord.Member,
                   время: str | None = None, причина: str | None = None):
        if not await _target(interaction, ник):
            return
        dur = mod.parse_duration(время) or mod.parse_duration("1ч")
        reason = (причина or "без причины").strip()
        res = await mod.apply_mute(interaction.guild, ник, dur, reason, interaction.user)
        if res.startswith(("Discord", "роль")):
            await interaction.response.send_message(f"❌ {res}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🔇 **{ник.display_name}** замучен на **{res}**\nПричина: {reason}\n"
            f"Доступны только «💤 AFK» и «🔇 В муте», микрофон закрыт. Мут снимется сам.",
            ephemeral=True)
        await textcmd._log(interaction.guild,
                           f"🔇 {interaction.user.mention} замутил {ник.mention} на {res}. Причина: {reason}")

    @app_commands.command(name="снятьмут", description="Снять мут с участника")
    @app_commands.describe(ник="С кого снимаем")
    async def unmute(interaction: discord.Interaction, ник: discord.Member):
        err = textcmd._can_punish(interaction.user, ник)
        if err:
            await interaction.response.send_message(f"⛔ {err}", ephemeral=True)
            return
        ok = await mod.remove_mute(interaction.guild, ник, str(interaction.user))
        await interaction.response.send_message(
            f"🔊 **{ник.display_name}** размучен." if ok else f"ℹ️ У **{ник.display_name}** не было мута.",
            ephemeral=True)
        await textcmd._log(interaction.guild, f"🔊 {interaction.user.mention} снял мут с {ник.mention}")

    @app_commands.command(name="кик", description="Выгнать участника с сервера")
    @app_commands.describe(ник="Кого выгоняем", причина="За что")
    async def kick(interaction: discord.Interaction, ник: discord.Member, причина: str | None = None):
        if not await _target(interaction, ник):
            return
        reason = (причина or "без причины").strip()
        try:
            await ник.kick(reason=f"{reason} | модератор: {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Не смог выгнать: {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"👢 **{ник.display_name}** выгнан. Причина: {reason}",
                                                ephemeral=True)
        await textcmd._log(interaction.guild,
                           f"👢 {interaction.user.mention} выгнал {ник} ({ник.id}). Причина: {reason}")

    @app_commands.command(name="бан", description="Забанить участника")
    @app_commands.describe(ник="Кого баним", причина="За что")
    async def ban(interaction: discord.Interaction, ник: discord.Member, причина: str | None = None):
        if not await _target(interaction, ник):
            return
        reason = (причина or "без причины").strip()
        try:
            await ник.ban(reason=f"{reason} | модератор: {interaction.user}", delete_message_days=0)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Не смог забанить: {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"🔨 **{ник.display_name}** забанен. Причина: {reason}",
                                                ephemeral=True)
        await textcmd._log(interaction.guild,
                           f"🔨 {interaction.user.mention} забанил {ник} ({ник.id}). Причина: {reason}")

    @app_commands.command(name="пред", description="Выдать предупреждение")
    @app_commands.describe(ник="Кому", причина="За что")
    async def warn(interaction: discord.Interaction, ник: discord.Member, причина: str | None = None):
        if not await _target(interaction, ник):
            return
        reason = (причина or "без причины").strip()
        await interaction.response.send_message(
            f"⚠️ **{ник.display_name}** получил предупреждение. Причина: {reason}", ephemeral=True)
        await textcmd._log(interaction.guild,
                           f"⚠️ {interaction.user.mention} выдал предупреждение {ник.mention}. Причина: {reason}")

    @app_commands.command(name="помощь", description="Все команды модерации")
    async def help_cmd(interaction: discord.Interaction):
        await interaction.response.send_message(textcmd.HELP, ephemeral=True)

    for cmd in (mute, unmute, kick, ban, warn, help_cmd):
        role_mute.tree.add_command(cmd)
    return role_mute
