@echo off
REM Stops the bot (not the collector), archives the old paper ledger to archive\<date>\ and opens a new one.
REM Afterwards start the bot again with memebot\start_bot.bat (needs the three environment variables).
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*memebot.bot.runner*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 2 /nobreak >nul
python -m memebot.bot.reset_paper --bot-stopped
if errorlevel 1 (echo RESET FAILED: nothing was changed. & exit /b 1)
echo done. Now run:  memebot\start_bot.bat
