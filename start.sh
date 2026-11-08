#!/usr/bin/env bash
# Запуск бота в один клик (Linux / macOS): ./start.sh
cd "$(dirname "$0")" || exit 1
python3 -m pip install -q -r requirements.txt
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export MEMBERS_INTENT="${MEMBERS_INTENT:-1}"
export IDLE_MINUTES="${IDLE_MINUTES:-15}"
exec python3 -u automod_bot.py
