#!/usr/bin/env bash
# Супервизор: держит бота запущенным + сторож, который ловит зависание.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
export PORT="${PORT:-8000}"

# --- сторож: если /health не отвечает дважды подряд, убиваем бота,
#     и супервизор поднимает его заново ---
watchdog() {
  local fails=0
  sleep 60
  while true; do
    if curl -s -m 10 "http://127.0.0.1:${PORT}/health" | grep -q ok; then
      fails=0
    else
      fails=$((fails+1))
      echo "[watchdog $(date +%H:%M:%S)] health не отвечает (промах $fails/2)"
      if [ "$fails" -ge 2 ]; then
        echo "[watchdog] бот завис — перезапускаю"
        pkill -f "python3 -u automod_bot.py"
        fails=0
      fi
    fi
    sleep 45
  done
}
watchdog &

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
