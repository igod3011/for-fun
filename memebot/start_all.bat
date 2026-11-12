@echo off
REM After a reboot: starts BOTH the collector and the bot. The bot can only trade pools the collector registers,
REM so starting the bot alone does nothing.
REM Run it from the project folder, in a Command Prompt where you already set HELIUS_API_KEY, TELEGRAM_BOT_TOKEN
REM and TELEGRAM_CHAT_ID.
if not defined HELIUS_API_KEY (echo HELIUS_API_KEY is not set & exit /b 1)
if not defined TELEGRAM_BOT_TOKEN (echo TELEGRAM_BOT_TOKEN is not set & exit /b 1)
if not defined TELEGRAM_CHAT_ID (echo TELEGRAM_CHAT_ID is not set & exit /b 1)
call memebot\restart_collector.bat
call memebot\start_bot.bat
echo both started. Check in ~5 minutes:  python -m memebot.healthcheck
