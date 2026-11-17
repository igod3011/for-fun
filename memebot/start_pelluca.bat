@echo off
rem Pelluca public bot (read-only). Needs PELLUCA_BOT_TOKEN set in this window:  set PELLUCA_BOT_TOKEN=...
cd /d "%~dp0\.."
if "%PELLUCA_BOT_TOKEN%"=="" (
  echo Chua dat PELLUCA_BOT_TOKEN. Go: set PELLUCA_BOT_TOKEN=token_cua_bot_pelluca
  exit /b 1
)
python -m memebot.pelluca.bot
