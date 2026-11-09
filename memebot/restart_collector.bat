@echo off
REM Stops ONLY the collector (not the bot), then starts ONE background collector in this folder.
REM Run it from a Command Prompt where you already did:  set HELIUS_API_KEY=...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*memebot.collect*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
powershell -Command "Start-Process python -ArgumentList '-m','memebot.collector_daemon','--out','cohort.jsonl' -WindowStyle Hidden -RedirectStandardOutput daemon.log -RedirectStandardError daemon.err"
echo collector restarted. Check in ~5 minutes:  python -m memebot.healthcheck
