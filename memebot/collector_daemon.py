"""Run the unbiased cohort collector forever (stdlib only, Python 3.9+).

  python3 -m memebot.collector_daemon --out cohort.jsonl

Every --register-every minutes (default 2): record newly migrated (PumpSwap) pools, whatever their later fate.
The newest-200-pools window only spans 4-8 minutes, so registration must never wait long: the clock runs from the
START of each pass, and each fill pass in between is small (--max-fill 8, ~40 s). Until 11/2026 a fill pass took
20 pools (~2.5 min) every 5 minutes and delayed registration past the window: pools were missed.
Fill: candles + RugCheck + reserve snapshot for pools older than 3 h (GeckoTerminal keeps only ~16.6 h of 1-min
candles, so the backlog must not grow; 8 pools per 2 minutes is ~5,700 a day against ~2,300 new pools).
Dead pools are kept with empty candles: dropping them would reintroduce survivorship bias.
Safe to stop/restart; both files are append-only (see store.py). Ctrl+C to stop.
"""
import argparse
import os
import subprocess
import sys
import time


def run(*args):
    r = subprocess.run([sys.executable, "-m", "memebot.collect", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    print(time.strftime("%F %T"), "|", " ".join(args[:4]), "->", last, flush=True)
    if r.returncode:
        print(r.stderr[-300:], flush=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--register-every", type=float, default=2)
    ap.add_argument("--fill-every", type=float, default=2)
    ap.add_argument("--max-fill", type=int, default=8)
    a = ap.parse_args()
    nxt_reg = nxt_fill = 0.0
    while True:
        now = time.time()
        if now >= nxt_reg:
            nxt_reg = now + a.register_every * 60          # from the start of the pass: a slow pass does not shift the clock
            run("--out", a.out, "--max-pools", "100", "--min-age-h", "0", "--max-age-h", "3")
        elif now >= nxt_fill:
            nxt_fill = now + a.fill_every * 60
            run("--out", a.out, "--fill", "--min-age-h", "3", "--max-fill", str(a.max_fill))
        else:
            time.sleep(5)


if __name__ == "__main__":
    main()
