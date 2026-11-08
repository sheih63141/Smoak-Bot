@echo off
chcp 65001 >nul
title Автозапуск бота SmoakTeam
cd /d %~dp0

echo Добавляю бота в автозагрузку Windows...
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SmoakBot.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%LNK%'); ^
   $s.TargetPath = '%~dp0start.bat'; ^
   $s.WorkingDirectory = '%~dp0'; ^
   $s.WindowStyle = 1; ^
   $s.Description = 'SmoakTeam Discord bot'; ^
   $s.Save()"

if exist "%LNK%" (
  echo.
  echo ✅ Готово. Бот будет стартовать сам при входе в Windows.
  echo    Файл: %LNK%
  echo.
  echo Чтобы убрать автозапуск — удалите этот файл из папки Startup.
) else (
  echo ❌ Не получилось. Добавьте вручную: Win+R → shell:startup → положите ярлык на start.bat
)
echo.
pause
