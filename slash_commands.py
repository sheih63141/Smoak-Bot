#!/usr/bin/env python3
"""
Русские слэш-команды SmoakTeam.

    /мут        — роль 🔇 Мут: видит только «😴 AFK» и «В муте»
    /снятьмут   — снять мут
    /кик        — выгнать
    /бан        — забанить
    /пред       — предупреждение
    /помощь     — шпаргалка
    /фильм      — запустить «Смотрим фильм»

Ник с Твича более НЕ обязателен: новичок проходит онбординг и сразу получает
роль «👋 Участник». Панель «Указать ник» и модалка удалены по просьбе владельца.
"""
from __future__ import annotations

import discord
from discord import app_commands

import commands as textcmd
import moderation as mod
import movie_night


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

    registered = {c.name for c in role_mute.tree.get_commands()}
    for cmd in (mute, unmute, kick, ban, warn, help_cmd, movie_night.slash_command()):
        if cmd.name not in registered:      # on_ready может вызваться повторно
            role_mute.tree.add_command(cmd)
    return role_mute
