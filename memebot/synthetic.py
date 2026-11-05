"""Synthetic memecoin universe: organic runners, duds, wash-traded and rugged tokens.

Metadata red flags are only *correlated* with bad outcomes (some rugs look clean,
some organic tokens look risky), so the anomaly filter is never a perfect oracle.
NOTE: the data-generating process is hand-made, so results show the plumbing works,
not that the strategy has an edge on real markets."""
import random

from .models import Candle, Token, TokenMeta

DUR = 240  # minutes of history per token


def _candles(rng, kind, t0):
    price = rng.uniform(5e-6, 5e-5)
    liq = rng.uniform(20_000, 150_000)
    base_vol = liq * rng.uniform(0.01, 0.04)
    surge_at = rng.randint(30, 120)
    rug_at = surge_at + rng.randint(15, 60)
    out = []
    for i in range(DUR):
        o = price
        vol_mult, buy_p, drift, makers_f = 1.0, 0.5, 0.0, 0.5
        if kind == "organic":
            if surge_at <= i < surge_at + 25:
                vol_mult, buy_p, drift = rng.uniform(3, 6), 0.68, 0.025
            elif i >= surge_at + 25:
                drift = -0.004
        elif kind == "dud":
            drift, buy_p, vol_mult = -0.003, 0.45, 0.6
        elif kind == "wash":
            vol_mult, makers_f = rng.uniform(3, 6), 0.06
            drift = rng.gauss(0, 0.004)
        elif kind == "rug":
            if surge_at <= i < rug_at:
                vol_mult, buy_p, drift = rng.uniform(3, 6), 0.7, 0.03
            elif i == rug_at:
                drift, buy_p, vol_mult = -0.9, 0.1, 8
                liq *= 0.05
            elif i > rug_at:
                drift, buy_p, vol_mult = -0.01, 0.2, 0.2
        c = o * (1 + drift + rng.gauss(0, 0.012))
        c = max(c, o * 0.02, 1e-9)
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.006)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.006)))
        if kind == "organic" and surge_at <= i < surge_at + 25:
            liq *= 1.01
        vol = base_vol * vol_mult * rng.uniform(0.6, 1.4)
        txns = max(4, int(vol / rng.uniform(40, 90)))
        buys = min(txns, max(0, int(rng.gauss(txns * buy_p, txns * 0.08))))
        out.append(Candle(t0 + i, o, hi, lo, c, vol, buys, txns - buys,
                          max(1, int(txns * makers_f * rng.uniform(0.8, 1.2))), liq))
        price = c
    return out


def _meta(rng, kind, idx, t0):
    risky_p = {"organic": 0.15, "dud": 0.3, "wash": 0.5, "rug": 0.65}[kind]
    risky = rng.random() < risky_p
    return TokenMeta(
        id=f"{kind[:2].upper()}{idx:04d}", symbol=f"MEME{idx}", created_ts=t0,
        mint_revoked=not (risky and rng.random() < 0.4),
        freeze_revoked=not (risky and rng.random() < 0.25),
        top10_pct=rng.uniform(0.5, 0.9) if risky else rng.uniform(0.1, 0.4),
        lp_locked_pct=rng.uniform(0.0, 0.3) if risky and rng.random() < 0.6 else rng.uniform(0.8, 1.0),
    )


def generate_universe(n=300, seed=7, mix=None):
    rng = random.Random(seed)
    mix = mix or {"organic": 0.2, "dud": 0.45, "wash": 0.15, "rug": 0.2}
    kinds = list(mix)
    tokens = []
    for i in range(n):
        kind = rng.choices(kinds, weights=[mix[k] for k in kinds])[0]
        t0 = rng.randint(0, 2000)
        meta = _meta(rng, kind, i, t0)
        tokens.append((kind, Token(meta, _candles(rng, kind, t0))))
    return tokens
