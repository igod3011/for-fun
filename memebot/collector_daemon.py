"""Run the unbiased cohort collector forever (stdlib only, Python 3.9+).

  python3 -m memebot.collector_daemon --out cohort.jsonl

Every --register-every minutes (default 2; the newest-200-pools window only spans ~4 min): record newly migrated (PumpSwap) pools, whatever their later fate.
Every --fill-every minutes (default 10, <=10 pools per pass so registration is never starved): fetch candles + RugCheck for registered pools older than 3h
(dead pools are kept with empty candles: dropping them would reintroduce survivorship bias).
Safe to stop/restart; data is appended/rewritten in --out. Ctrl+C to stop.
"""
import argparse
import subprocess
import sys
import time


def run(*args):
    r = subprocess.run([sys.executable, "-m", "memebot.collect", *args], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    print(time.strftime("%F %T"), "|", " ".join(args[:4]), "->", last, flush=True)
    if r.returncode:
        print(r.stderr[-300:], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--register-every", type=int, default=2)
    ap.add_argument("--fill-every", type=int, default=10)
    a = ap.parse_args()
    nxt_reg = nxt_fill = 0.0
    while True:
        now = time.time()
        if now >= nxt_reg:
            run("--out", a.out, "--source", "new", "--register-only", "--min-age-h", "0", "--max-age-h", "3", "--max-pools", "100")
            nxt_reg = time.time() + a.register_every * 60
        if now >= nxt_fill:
            run("--out", a.out, "--fill", "--min-age-h", "3", "--max-fill", "10")
            nxt_fill = time.time() + a.fill_every * 60
        time.sleep(30)


if __name__ == "__main__":
    main()
