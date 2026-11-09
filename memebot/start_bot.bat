@echo off
REM Stops a running bot (if any), then starts ONE background PAPER bot in this folder.
REM Run it from a Command Prompt where you already set HELIUS_API_KEY, TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
if not defined TELEGRAM_BOT_TOKEN (echo TELEGRAM_BOT_TOKEN is not set & exit /b 1)
if not defined TELEGRAM_CHAT_ID (echo TELEGRAM_CHAT_ID is not set & exit /b 1)
if not defined HELIUS_API_KEY (echo HELIUS_API_KEY is not set & exit /b 1)
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*memebot.bot.runner*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
powershell -Command "Start-Process python -ArgumentList '-m','memebot.bot.runner' -WindowStyle Hidden -RedirectStandardOutput bot.log -RedirectStandardError bot.err"
echo bot started. You should get a "bot started" message in Telegram within a few seconds.
