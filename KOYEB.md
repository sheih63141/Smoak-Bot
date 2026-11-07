# 🚀 Деплой бота на Koyeb (24/7, бесплатно)

Бот должен работать круглосуточно, иначе реакции на панели тикетов ничего не делают.
Koyeb даёт бесплатный веб-сервис (0.1 vCPU / 512 МБ, Франкфурт) — для бота этого хватает с запасом.

Проект уже полностью подготовлен: `Dockerfile`, health-check на `/health`, `.dockerignore` (токен в образ не попадёт), git-репозиторий с первым коммитом.

---

## Шаг 0. Перевыпустите токен (обязательно)

Старый токен лежал в файлах на моей стороне, а в интернет ему нельзя. Developer Portal → ваше приложение → **Bot** → **Reset Token** → скопируйте новый. Старый сразу перестанет работать.

---

## Шаг 1. Залейте проект на GitHub

Репозиторий в папке уже инициализирован (`.env` в него не попал — проверено).

**Вариант А — через сайт (без консоли):**
1. github.com → **New repository** → имя `smoak-bot` → **Private** → Create
2. На странице пустого репозитория — **uploading an existing file**
3. Перетащите **всё содержимое папки `discord-server`** (кроме `.env`!)
4. Commit changes

**Вариант Б — через консоль:**
```bash
cd discord-server
git remote add origin https://github.com/ВАШ_НИК/smoak-bot.git
git branch -M main
git push -u origin main
```

---

## Шаг 2. Создайте сервис на Koyeb

1. Зайдите на **app.koyeb.com** → войдите через GitHub
2. **Create Service** → **Web service**
3. **GitHub** → разрешите Koyeb доступ к репозиториям (Install GitHub App) → выберите `smoak-bot`, ветку `main`
4. **Builder: Dockerfile** (путь оставьте пустым — он в корне)
5. **Instance: Free** · **Region: Frankfurt (fra)**
6. **Ports / Exposing:** добавьте порт **8000**, protocol **HTTP**, route **`/`**
7. **Health check:** protocol HTTP, port **8000**, path **`/health`**
8. **Scaling:** min **1**, max **1** ← важно, два экземпляра выкинут друг друга (`session has been invalidated`)
9. **Environment variables:**

| Переменная | Значение | Секрет? |
|---|---|---|
| `DISCORD_TOKEN` | новый токен после Reset | 🔒 да |
| `GUILD_ID` | `1568607492991353053` | нет |
| `MEMBERS_INTENT` | `0` | нет |
| `IDLE_MINUTES` | `15` | нет |
| `PORT` | `8000` | нет |

10. **Deploy**

---

## Шаг 3. Проверка

В логах сервиса (Dashboard → ваш сервис → Logs) должно появиться:

```
[health] слушаю порт 8000
Бот на связи: Bot  Smoak#6527
[ticket] панель готова: 🎫 📋 📝
```

Откройте `https://ВАШ-СЕРВИС-ВАША-ОРГ.koyeb.app/health` — должен вернуться `ok`.
Теперь нажмите 🎫 на панели в Discord: появится приватный канал `вопрос-вашник`.

---

## Шаг 4. Не давайте боту засыпать

Бесплатный инстанс Koyeb **засыпает после часа без HTTP-трафика**. Тикеты при этом перестанут создаваться.

Лечение — бесплатный пинг раз в 5 минут:
1. **uptimerobot.com** → регистрация → **Add New Monitor**
2. Monitor Type: **HTTP(s)** · Friendly Name: `smoak-bot` · URL: `https://ВАШ-СЕРВИС.koyeb.app/health`
3. Interval: **5 minutes** → Create

Готово: монитор дёргает бота, инстанс не засыпает, тикеты работают круглосуточно.

---

## Что уже настроено в проекте под Koyeb

- `Dockerfile` — python:3.12-slim, `PORT=8000`, `EXPOSE 8000`, запуск `automod_bot.py`
- `automod_bot.py` — health-сервер на `0.0.0.0:$PORT` (`/` и `/health`), без него Koyeb не пропустит деплой
- `MEMBERS_INTENT=0` по умолчанию — бот стартует **без** галки Server Members Intent (участников получает точечным запросом). Если включите галку в портале — поставьте `MEMBERS_INTENT=1`, тогда заработает массовая выдача роли
- `.dockerignore` и `.gitignore` — токен, `__pycache__`, архив не уходят ни в образ, ни в GitHub
- `twitch_state.json` на Koyeb не сохраняется (эфемерный диск) — после рестарта бот может один раз повторить анонс. Не критично

---

## Частые проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `PrivilegedIntentsRequired` | `MEMBERS_INTENT=1`, а галка в портале не стоит | поставить `MEMBERS_INTENT=0` или включить галку |
| `session has been invalidated` | бот запущен в двух местах (ПК + Koyeb) | оставить только один экземпляр |
| Сервис «unhealthy» | health-check не на том порту/пути | порт 8000, path `/health` |
| Реакции не создают тикет | инстанс спит | UptimeRobot, шаг 4 |
| Тикет создался, но автор его не видит | категория скрыта от `@everyone` | это норма — автору доступ выдаётся персонально на канал |
