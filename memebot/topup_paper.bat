@echo off
REM Adds paper SOL to the bot's balance:  memebot\topup_paper.bat 5
REM Stops the bot, adds the amount (P&L figures do not change), then starts the bot again.
REM Run it from the project folder, in a Command Prompt where HELIUS_API_KEY, TELEGRAM_BOT_TOKEN and
REM TELEGRAM_CHAT_ID are set. Once the bot runs this version you can also send it  /topup 5  in Telegram.
if "%~1"=="" (echo usage: memebot\topup_paper.bat 5 & exit /b 1)
if not defined TELEGRAM_BOT_TOKEN (echo TELEGRAM_BOT_TOKEN is not set: nothing was changed & exit /b 1)
if not defined TELEGRAM_CHAT_ID (echo TELEGRAM_CHAT_ID is not set: nothing was changed & exit /b 1)
if not defined HELIUS_API_KEY (echo HELIUS_API_KEY is not set: nothing was changed & exit /b 1)
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*memebot.bot.runner*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 2 /nobreak >nul
python -m memebot.bot.topup %1 --bot-stopped
if errorlevel 1 (echo TOP-UP FAILED: balance not changed. Starting the bot again. )
call memebot\start_bot.bat
