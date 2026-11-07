@echo off
chcp 65001 >nul
cd /d %~dp0
echo === SmoakTeam bot ===
python -m pip install -q -r requirements.txt
if exist .env (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
) else (
  echo Нет файла .env — скопируйте .env.example в .env и вставьте токен
  pause
  exit /b
)
set MEMBERS_INTENT=0
set IDLE_MINUTES=15
python -u automod_bot.py
echo.
echo Бот остановлен. Не закрывайте это окно, пока бот нужен.
pause
