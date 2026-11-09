"""Summarise the bot's decision log (bot_trades.jsonl).

  python -m memebot.bot.review [--log bot_trades.jsonl] [--since-hours 24]
Also used by the Telegram /review command and the daily summary.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter


def _norm(reason):
    """Group reasons that differ only by numbers: 'pool only 5.2 SOL' -> 'pool only # SOL'."""
    return re.sub(r"(?<![\w.])[-+]?\d+(\.\d+)?%?", "#", reason).strip()


def load(path, since_ts=0):
    if not os.path.exists(path):
        return []
    out = []
    for l in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("ts", 0) >= since_ts:
            out.append(e)
    return out


def summary(events, title="all time"):
    buys = [e for e in events if e.get("action") == "buy" and e.get("reason") != "chase"]
    sells = [e for e in events if e.get("action") == "sell"]
    closed = [e for e in sells if e.get("closed") and e.get("pnl") is not None]
    skips = [e for e in events if e.get("action") == "skip"]
    lines = [f"📊 Review ({title}, PAPER)",
             f"entries {len(buys)}, closed trades {len(closed)}, skipped tokens {len(skips)}"]
    if closed:
        pnl = [e["pnl"] for e in closed]
        wins = [p for p in pnl if p > 0]
        lines.append(f"PnL {sum(pnl):+.4f} SOL | win rate {len(wins)/len(pnl):.0%} | "
                     f"avg {sum(pnl)/len(pnl):+.4f} | best {max(pnl):+.4f} | worst {min(pnl):+.4f}")
        by = Counter()
        pnl_by = Counter()
        for e in sells:
            k = _norm(e.get("reason", "?").split("(")[0])
            by[k] += 1
            if e.get("pnl") is not None:
                pnl_by[k] += e["pnl"]
        lines.append("exits: " + ", ".join(f"{k} x{v} ({pnl_by[k]:+.3f})" for k, v in by.most_common(6)))
    if skips:
        reasons = Counter()
        for e in skips:
            for r in e.get("reason", "?").split("; "):
                reasons[_norm(r)] += 1
        lines.append("top skip reasons: " + ", ".join(f"{k} x{v}" for k, v in reasons.most_common(5)))
    return "\n".join(lines)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="bot_trades.jsonl")
    ap.add_argument("--since-hours", type=float, default=0)
    a = ap.parse_args()
    since = time.time() - a.since_hours * 3600 if a.since_hours else 0
    print(summary(load(a.log, since), f"last {a.since_hours:g}h" if a.since_hours else "all time"))


if __name__ == "__main__":
    main()
