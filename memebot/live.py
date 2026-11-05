"""LIVE PAPER runner (no real orders, no wallet, no keys).

!! UNTESTED against the real APIs: the sandbox this was written in blocks
!! dexscreener.com / rugcheck.xyz. Field names follow the public docs as I know them;
!! expect to fix small things on first run (run with --once and read the output).

Data: DexScreener has no OHLC endpoint, so we poll snapshots and build 1-minute
candles ourselves. Volume/txn counts are approximated from the 5-minute rolling
window (divided by 5), so volume-surge signals are noisier than in the backtest.
"""
import argparse
import json
import time
import urllib.request

from .config import Config
from .engine import Engine
from .models import Candle, TokenMeta
from .strategy import STRATEGIES

UA = {"User-Agent": "memebot-paper/0.1"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return json.load(r)


def new_solana_tokens():
    prof = get("https://api.dexscreener.com/token-profiles/latest/v1")
    return [p["tokenAddress"] for p in prof if p.get("chainId") == "solana"]


def best_pair(addr):
    pairs = get(f"https://api.dexscreener.com/latest/dex/tokens/{addr}").get("pairs") or []
    pairs = [p for p in pairs if p.get("chainId") == "solana"]
    return max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd", 0), default=None)


def rugcheck_meta(addr, created_min):
    """Map RugCheck's risk list onto TokenMeta. Unknown => assume the worst."""
    meta = TokenMeta(addr, addr[:6], created_min, mint_revoked=False, freeze_revoked=False,
                     top10_pct=1.0, lp_locked_pct=0.0)
    try:
        rep = get(f"https://api.rugcheck.xyz/v1/tokens/{addr}/report")
    except Exception:
        return meta
    risks = " | ".join(r.get("name", "").lower() for r in rep.get("risks", []))
    meta.mint_revoked = "mint authority" not in risks
    meta.freeze_revoked = "freeze authority" not in risks
    top = rep.get("topHolders") or []
    meta.top10_pct = sum(h.get("pct", 0) for h in top[:10]) / 100 if top else 1.0
    lps = rep.get("markets") or []
    if lps:
        meta.lp_locked_pct = max((m.get("lp", {}).get("lpLockedPct", 0) for m in lps), default=0) / 100
    return meta


class Feed:
    def __init__(self):
        self.meta, self.hist, self.last = {}, {}, {}

    def poll(self, addr, now_min):
        p = best_pair(addr)
        if not p or not p.get("priceUsd"):
            return None
        price = float(p["priceUsd"])
        tx = (p.get("txns") or {}).get("m5", {})
        buys, sells = int(tx.get("buys", 0) / 5), int(tx.get("sells", 0) / 5)
        if addr not in self.meta:
            created = int((p.get("pairCreatedAt") or now_min * 60000) / 60000)
            self.meta[addr] = rugcheck_meta(addr, created)
        prev = self.last.get(addr, price)
        c = Candle(now_min, prev, max(prev, price), min(prev, price), price,
                   ((p.get("volume") or {}).get("m5", 0)) / 5, buys, sells,
                   max(1, int((buys + sells) * 0.5)),   # makers unknown: assume 50%
                   (p.get("liquidity") or {}).get("usd", 0))
        self.last[addr] = price
        self.hist.setdefault(addr, []).append(c)
        return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="breakout_volume")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    cfg, feed = Config(), Feed()
    eng = Engine(cfg, STRATEGIES[a.strategy])
    watch = set()
    while True:
        now = int(time.time() // 60)
        try:
            watch |= set(new_solana_tokens())
        except Exception as e:
            print("profile fetch failed:", e)
        for addr in list(watch) + list(eng.broker.positions):
            try:
                if feed.poll(addr, now):
                    eng.on_candle(feed.meta[addr], feed.hist[addr])
            except Exception as e:
                print(addr[:8], "error:", e)
        print(f"[{time.strftime('%H:%M:%S')}] watch={len(watch)} open={list(eng.broker.positions)} "
              f"cash={eng.broker.cash:.2f} closed={len(eng.broker.trades)} blocked={eng.skipped}")
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
