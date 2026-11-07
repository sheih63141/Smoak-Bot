#!/usr/bin/env bash
# Супервизор: держит бота запущенным, перезапускает при падении.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
export PORT="${PORT:-8000}"

fails=0
while true; do
  started=$(date +%s)
  python3 -u automod_bot.py
  code=$?
  lived=$(( $(date +%s) - started ))
  echo "[supervisor $(date +%H:%M:%S)] бот остановился: код $code, проработал ${lived}s"

  if [ "$code" = "2" ]; then
    echo "[supervisor] ошибка доступа (intents/токен) — перезапуск не поможет, стоп"
    exit 2
  fi
  if [ "$lived" -lt 30 ]; then fails=$((fails+1)); else fails=0; fi
  if [ "$fails" -ge 6 ]; then
    echo "[supervisor] 6 падений подряд за минуту — вероятно токен или сеть, стоп"
    exit 3
  fi
  echo "[supervisor] перезапускаю через 5 секунд (подряд падений: $fails)"
  sleep 5
done
