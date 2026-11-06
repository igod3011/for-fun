@echo off
REM Stops every python.exe, then starts ONE background collector in this folder.
REM Run it from a Command Prompt where you already did:  set HELIUS_API_KEY=...
taskkill /IM python.exe /F >nul 2>&1
powershell -Command "Start-Process python -ArgumentList '-m','memebot.collector_daemon','--out','cohort.jsonl' -WindowStyle Hidden -RedirectStandardOutput daemon.log -RedirectStandardError daemon.err"
echo collector restarted. Check in ~5 minutes:  type daemon.log
