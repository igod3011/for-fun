"""Backtest the engine on REAL collected PumpSwap candles (see collect.py).

Real-data limitations (be honest when reading results):
  * GeckoTerminal OHLCV has no buy/sell split or maker counts: buys=sells=1 (neutral),
    so buy-ratio, wash-trading and sell-pressure checks are inert here.
  * Liquidity is a FIXED assumption (--liq, default $25k). Never use the collection-time
    reserve: it is known only in hindsight and filtering on it leaks the outcome (this
    produced a bogus +250% result once). The liquidity-drain flag therefore cannot fire.
  * Survivorship bias: pools are listed some hours after creation, so rugs that already
    went to zero and got delisted may be missing. Results are optimistic.
"""
import argparse
import json
import statistics
from dataclasses import replace

from .backtest import run, summarize
from .config import Config
from .models import Candle, Token, TokenMeta
from .strategy import STRATEGIES


def buy_at_migration(candles, cfg):
    """Naive baseline: enter 5 minutes after the pool opens, no signal."""
    return len(candles) == 6


STRATEGIES_REAL = dict(STRATEGIES, buy_at_migration=buy_at_migration)


def load(path, require_rugcheck=True, assumed_liq=25_000.0):
    toks = []
    for line in open(path):
        p = json.loads(line)
        rc = p.get("rugcheck")
        if require_rugcheck and not rc:
            continue
        rc = rc or {}
        raw = {int(c[0] // 60): c for c in p["candles"]}
        lo, hi = min(raw), max(raw)
        out, last = [], None
        for m in range(lo, hi + 1):
            if m in raw:
                _, o, h, l, c, v = raw[m]
                last = c
                out.append(Candle(m, o, h, l, c, v, 1, 1, 2, assumed_liq))
            elif last is not None:
                out.append(Candle(m, last, last, last, last, 0.0, 0, 0, 0, assumed_liq))
        meta = TokenMeta(
            p["mint"], p["name"], p["created"] // 60,
            mint_revoked=rc.get("mint_revoked", False), freeze_revoked=rc.get("freeze_revoked", False),
            top10_pct=rc["top10_pct"] if rc.get("top10_pct") is not None else 1.0,
            lp_locked_pct=rc["lp_locked_pct"] if rc.get("lp_locked_pct") is not None else 0.0,
            rugged=bool(rc.get("rugged")))
        toks.append(("real", Token(meta, out)))
    return toks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--liq", type=float, default=25_000.0)
    a = ap.parse_args()
    toks = load(a.data, assumed_liq=a.liq)
    print(f"tokens loaded: {len(toks)}")
    cfg = replace(Config(), max_age_min=900, min_buy_ratio=0.0, max_hold_min=240)
    print(f"{'strategy':18} {'filter':6} {'trades':>6} {'win%':>6} {'avg_ret':>8} {'worst':>7} {'total':>7} {'maxDD':>6}")
    for name in STRATEGIES_REAL:
        for flt in (True, False):
            eng = run(toks, cfg, name, flt) if name in STRATEGIES else None
            if eng is None:
                from .engine import Engine
                eng = Engine(cfg, STRATEGIES_REAL[name], flt)
                ev = sorted((c.ts, t.meta.id, i) for _, t in toks for i, c in enumerate(t.candles))
                byid = {t.meta.id: t for _, t in toks}
                for _, tid, i in ev:
                    eng.on_candle(byid[tid].meta, byid[tid].candles[: i + 1])
                for tid in list(eng.broker.positions):
                    c = byid[tid].candles[-1]
                    eng.broker.sell(tid, c.close, c.liquidity, c.ts, "end")
            s = summarize(eng, cfg)
            print(f"{name:18} {'on' if flt else 'off':6} {s['trades']:6d} {s['win_rate']*100:6.1f} "
                  f"{s['avg_ret']*100:7.1f}% {s['worst']*100:6.0f}% {s['total_ret']*100:6.1f}% {s['max_dd']*100:5.0f}%")


if __name__ == "__main__":
    main()
