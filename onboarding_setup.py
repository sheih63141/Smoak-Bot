#!/usr/bin/env python3
"""
Настройка входа на сервер: экран правил (галочки) + онбординг с выбором роли.

Что делает:
  1. Включает режим «Сообщество» (Community) — без него нет экрана правил.
     #правила становится каналом правил, #игровые-новости — каналом обновлений.
  2. Включает экран проверки: новичок видит правила и ставит галочки
     («ознакомлен», «13+»), без этого каналы сервера недоступны.
  3. Настраивает онбординг: обязательный выбор «👋 Я участник — с правилами ознакомлен»
     (выдаёт роль 👋 Участник) + необязательный выбор интересов (какие каналы открыть).
  4. Проверяет, что всё включилось, и печатает итог.

Запуск:  DISCORD_TOKEN=... GUILD_ID=... python onboarding_setup.py
Повторный запуск безопасен — настройки перезаписываются теми же значениями.
"""
from __future__ import annotations

import os
import sys

import discord
from discord.http import Route
from discord.onboarding import (
    OnboardingMode,
    OnboardingPrompt,
    OnboardingPromptOption,
    OnboardingPromptType,
)

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

RULES_CHANNEL = "правила"
UPDATES_CHANNEL = "игровые-новости"
MEMBER_ROLE = "👋 Участник"
DEFAULT_CHANNELS = ["правила", "общий-чат", "поиск-игроков"]

VERIFY_DESCRIPTION = "Чтобы попасть на сервер, подтверди, что ознакомился с правилами."
VERIFY_FIELDS = [
    {
        "field_type": "TERMS",
        "label": "Я прочитал(а) правила и согласен(на) с ними",
        "required": True,
        "values": ["https://discord.com/guidelines"],
    },
    {
        "field_type": "TERMS",
        "label": "Мне 13 лет или больше (требование Discord)",
        "required": True,
        "values": ["https://discord.com/terms"],
    },
]

INTERESTS = [
    ("🎮 Игры и сборы", "Поиск тиммейтов и игровые новости", ["поиск-игроков", "игровые-новости"]),
    ("🎥 Стримы", "Анонсы эфиров и обсуждение", ["анонсы-стримов", "стрим-обсуждение"]),
    ("💬 Общение и мемы", "Общий чат, мемы, клипы", ["общий-чат", "мемы-и-арты"]),
]

client = discord.Client(intents=discord.Intents.default())


@client.event
async def on_ready() -> None:
    g = client.get_guild(GUILD_ID)
    if not g:
        print("❌ сервер не найден")
        await client.close()
        return

    def text_ch(name: str) -> discord.TextChannel | None:
        return discord.utils.get(g.text_channels, name=name)

    # ---------------------------------------------------------- 1. Community
    print("--- режим сообщества ---")
    try:
        await g.edit(
            community=True,
            rules_channel=text_ch(RULES_CHANNEL),
            public_updates_channel=text_ch(UPDATES_CHANNEL),
            verification_level=discord.VerificationLevel.medium,
            explicit_content_filter=discord.ContentFilter.all_members,
            reason="включение экрана правил",
        )
        print(f"  ✅ Community | правила → #{RULES_CHANNEL} | обновления → #{UPDATES_CHANNEL}")
    except discord.HTTPException as e:
        print(f"  ⚠️ Community: {e.status} {e.code} {str(e.text)[:150]}")

    # ------------------------------------------------- 2. Экран проверки правил
    print("\n--- экран правил (галочки при входе) ---")
    try:
        payload = {"enabled": True, "description": VERIFY_DESCRIPTION, "form_fields": VERIFY_FIELDS}
        r = await client.http.request(
            Route("PATCH", "/guilds/{guild_id}/member-verification", guild_id=g.id), json=payload
        )
        for f in r.get("form_fields", []):
            print(f"  [ ] {f['label']}")
        print("  ✅ сохранено")
    except discord.HTTPException as e:
        print(f"  ⚠️ экран правил: {e.status} {e.code} {str(e.text)[:150]}")

    # -------------------------------------------------------------- 3. Онбординг
    print("\n--- онбординг при входе ---")
    member_role = discord.utils.get(g.roles, name=MEMBER_ROLE)
    if member_role is None:
        print(f"  ⚠️ нет роли «{MEMBER_ROLE}» — онбординг без выдачи роли")
        first_prompt = None
    else:
        first_prompt = OnboardingPrompt(
            type=OnboardingPromptType.multiple_choice,
            title="Подтверди участие",
            single_select=True,
            required=True,
            in_onboarding=True,
            options=[
                OnboardingPromptOption(
                    title="👋 Я участник — с правилами ознакомлен",
                    description="Выдаст роль «Участник» и откроет каналы",
                    roles=[member_role],
                )
            ],
        )

    options = []
    for title, desc, channels in INTERESTS:
        chs = [text_ch(c) for c in channels]
        chs = [c for c in chs if c]
        if chs:
            options.append(OnboardingPromptOption(title=title, description=desc, channels=chs))
    interests_prompt = OnboardingPrompt(
        type=OnboardingPromptType.multiple_choice,
        title="Что тебе интересно?",
        single_select=False,
        required=False,
        in_onboarding=True,
        options=options or [
            OnboardingPromptOption(title="💬 Общение", channels=[text_ch("общий-чат")])
        ],
    )

    prompts = ([first_prompt] if first_prompt else []) + [interests_prompt]
    defaults = [text_ch(n) for n in DEFAULT_CHANNELS]
    defaults = [c for c in defaults if c]
    try:
        ob = await g.edit_onboarding(
            prompts=prompts,
            default_channels=defaults,
            enabled=True,
            mode=OnboardingMode.advanced,
            reason="онбординг новичков",
        )
        print(f"  ✅ включён | режим: {ob.mode} | каналы по умолчанию: "
              f"{', '.join('#' + c.name for c in ob.default_channels)}")
        for p in ob.prompts:
            mark = "обязательный" if p.required else "по желанию"
            print(f"   • {p.title} ({mark})")
            for o in p.options:
                extra = []
                if o.roles:
                    extra.append("роли: " + ", ".join(r.name for r in o.roles))
                if o.channels:
                    extra.append("каналы: " + ", ".join("#" + c.name for c in o.channels))
                print(f"       - {o.title} [{'; '.join(extra) or '—'}]")
    except discord.HTTPException as e:
        print(f"  ⚠️ онбординг: {e.status} {e.code} {str(e.text)[:200]}")

    # ------------------------------------------------------------ 4. Проверка
    print("\n--- проверка ---")
    features = await client.http.request(Route("GET", "/guilds/{guild_id}", guild_id=g.id))
    feats = features.get("features", [])
    print("  экран правил:", "ВКЛ" if "MEMBER_VERIFICATION_GATE_ENABLED" in feats else "ВЫКЛ")
    print("  онбординг:   ", "ВКЛ" if "GUILD_ONBOARDING" in feats else "ВЫКЛ")
    print("  роль для новичков выдаёт бот (join_gate.py) — нужен Server Members Intent")
    await client.close()


if __name__ == "__main__":
    if not TOKEN or not GUILD_ID:
        print("❌ Нужны DISCORD_TOKEN и GUILD_ID")
        sys.exit(1)
    client.run(TOKEN)
