#!/usr/bin/env bash
# Быстрая проверка: жив ли бот, и перезапуск, если умер.
cd "$(dirname "$0")" || exit 1
pid=$(ps -eo pid,args | grep "[a]utomod_bot.py" | awk '{print $1}' | head -1)
if [ -n "$pid" ]; then
  echo "✅ бот работает (pid $pid)"
  curl -s -m 5 http://127.0.0.1:8000/health && echo " ← health ok"
else
  echo "⚠️ бот не запущен — поднимаю"
  nohup ./run_forever.sh > bot.log 2>&1 &
  sleep 8
  pid=$(ps -eo pid,args | grep "[a]utomod_bot.py" | awk '{print $1}' | head -1)
  [ -n "$pid" ] && echo "✅ поднят (pid $pid)" || echo "❌ не поднялся, смотри bot.log"
fi
