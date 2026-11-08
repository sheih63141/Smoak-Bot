#!/usr/bin/env bash
# Деплой бота 24/7 на Koyeb одной командой.
# Нужен только API-токен Koyeb: app.koyeb.com → Account → API → Create API token
#
# Запуск:  ./deploy-koyeb.sh
# Или:     KOYEB_TOKEN=xxx ./deploy-koyeb.sh
set -euo pipefail
cd "$(dirname "$0")"

APP="${KOYEB_APP:-smoakteam}"
SVC="${KOYEB_SERVICE:-bot}"
REGION="${KOYEB_REGION:-fra}"

echo "══════════════════════════════════════════════"
echo " Деплой SmoakTeam-бота на Koyeb"
echo " приложение: $APP / сервис: $SVC / регион: $REGION"
echo "══════════════════════════════════════════════"

# ---------- 1. Koyeb CLI ----------
export PATH="$HOME/.koyeb/bin:$PATH"
if ! command -v koyeb >/dev/null 2>&1; then
  echo "→ ставлю Koyeb CLI..."
  curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/master/install.sh | sh
  export PATH="$HOME/.koyeb/bin:$PATH"
fi
echo "✅ Koyeb CLI: $(koyeb version 2>/dev/null | head -1)"

# ---------- 2. токен Koyeb ----------
if [ -z "${KOYEB_TOKEN:-}" ]; then
  echo
  echo "Нужен API-токен Koyeb (создаётся один раз):"
  echo "  app.koyeb.com → Account → API → Create API token"
  printf "Вставьте токен: "
  read -rs KOYEB_TOKEN
  echo
fi
TOK=(--token "$KOYEB_TOKEN")

# ---------- 3. токен Discord ----------
DTOKEN="${DISCORD_TOKEN:-}"
if [ -z "$DTOKEN" ] && [ -f .env ]; then
  DTOKEN="$(grep -E '^DISCORD_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')"
fi
if [ -z "$DTOKEN" ]; then
  printf "Токен бота Discord (Developer Portal → Bot → Reset Token): "
  read -rs DTOKEN
  echo
fi

# ---------- 4. проверка доступа ----------
if ! koyeb apps list "${TOK[@]}" >/dev/null 2>&1; then
  echo "❌ Koyeb не принял токен. Проверьте, что он скопирован целиком и не отозван."
  exit 1
fi
echo "✅ доступ к Koyeb подтверждён"

# ---------- 5. секрет с токеном Discord ----------
if koyeb secrets get discord-token "${TOK[@]}" >/dev/null 2>&1; then
  echo "→ обновляю секрет discord-token"
  koyeb secrets update discord-token --value "$DTOKEN" "${TOK[@]}" >/dev/null 2>&1 || true
else
  echo "→ создаю секрет discord-token"
  koyeb secrets create discord-token --value "$DTOKEN" "${TOK[@]}" >/dev/null
fi

# ---------- 6. деплой ----------
echo "→ собираю и выкатываю (2–4 минуты)..."
koyeb deploy . "$APP/$SVC" \
  "${TOK[@]}" \
  --archive-builder docker \
  --archive-docker-dockerfile Dockerfile \
  --instance-type free \
  --regions "$REGION" \
  --ports 8000:http \
  --routes /:8000 \
  --checks 8000:http:/health \
  --min-scale 1 --max-scale 1 \
  --light-sleep-delay 0 \
  --deep-sleep-delay 0 \
  --env PORT=8000 \
  --env GUILD_ID=1568607492991353053 \
  --env MEMBERS_INTENT=0 \
  --env IDLE_MINUTES=15 \
  --env 'DISCORD_TOKEN={{secret.discord-token}}'

# ---------- 7. итог ----------
echo
echo "══════════════════════════════════════════════"
koyeb services get "$APP/$SVC" "${TOK[@]}" 2>/dev/null || true
URL="$(koyeb services get "$APP/$SVC" -o json "${TOK[@]}" 2>/dev/null \
        | grep -oE 'https://[a-z0-9-]+\.koyeb\.app' | head -1 || true)"
echo
if [ -n "$URL" ]; then
  echo "🌍 Адрес сервиса: $URL"
  echo "   health:  $URL/health"
else
  echo "🌍 Адрес сервиса: Dashboard → Services → $SVC → Public URL"
fi
echo
echo "Готово. Бот теперь живёт на Koyeb и не зависит от вашего ПК."
echo "После проверки отзовите API-токен: Account → API → удалить токен."
