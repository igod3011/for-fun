@echo off
REM One-off (11/2026): stop the collector, move the candles out of cohort.jsonl into cohort.fills.jsonl,
REM then start the collector again with the new schedule.
REM Run it from the project folder, in a Command Prompt where you already did:  set HELIUS_API_KEY=...
if not defined HELIUS_API_KEY (echo HELIUS_API_KEY is not set in this window & exit /b 1)
if not exist cohort.jsonl (echo cohort.jsonl not found: run this from the project folder & exit /b 1)
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*memebot.collect*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 3 /nobreak >nul
python -m memebot.store --migrate cohort.jsonl --collector-stopped
if errorlevel 1 (echo MIGRATION FAILED: nothing was changed. The collector is stopped; run memebot\restart_collector.bat to start it again. & exit /b 1)
powershell -Command "Start-Process python -ArgumentList '-m','memebot.collector_daemon','--out','cohort.jsonl' -WindowStyle Hidden -RedirectStandardOutput daemon.log -RedirectStandardError daemon.err"
echo done. Check in ~5 minutes:  python -m memebot.healthcheck
