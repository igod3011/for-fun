"""When to enter, and which filters help? Backtest on the collector's REAL data (cohort.jsonl).

For each canonical pump.fun graduation pool and each entry delay (minutes after the pool was created):
  * entry price from GeckoTerminal 1-min candles, converted to SOL with the registration snapshot;
    pool reserves at entry from the constant product k = SOL*tokens (registration snapshot);
  * exit A "hold": sell everything into the REAL pool reserves at fill time (Helius snapshot) -> what you
    would actually get back, however absurd the last trade price looks;
  * exit B "bot rules": the bot's stop loss / take profit / trailing / max hold on candle closes, then exit A
    for whatever is still held. A candle implying an impossible pool (>5x the entry pool) ends the walk.
Filters compared: F0 any alive pool, F1 + bot guard (>=40 SOL, <=20% SOL drop since registration),
F2 + momentum (price not lower than 10 min earlier, >=5 active minutes in the last 10).
Results are split into the earlier and later half of the data to see whether they are stable.

  python -m memebot.ml.entry_timing --data cohort.jsonl
"""
import argparse
import json
import math
import statistics as st
import sys

from ..bot import amm

STAKE, FEE = 0.05, 0.005
TP = [(0.5, 0.5), (1.0, 0.5)]
SL, TRAIL_ON, TRAIL, MAX_HOLD = 0.25, 0.3, 0.2, 120


def close_at(candles, t, tol=120):
    """Close of the last candle at or before t, if it is at most tol seconds old (pool still trading)."""
    best = None
    for c in candles:
        if c[0] > t:
            break
        best = c
    return best[4] if best and t - best[0] <= tol else None


def setup(p):
    r, f = p.get("helius_reg") or {}, p.get("helius_fill") or {}
    s0, t0, s1, t1 = r.get("pool_sol"), r.get("pool_tokens"), f.get("pool_sol"), f.get("pool_tokens")
    if not (s0 and t0) or s1 is None or t1 is None or not p.get("mint", "").endswith("pump"):
        return None
    if not 1.0e10 <= s0 * t0 <= 2.6e10:
        return None
    c = sorted(p.get("candles") or [])
    t_reg = r.get("fetched_at") or p.get("registered_at")
    usd_reg = close_at(c, t_reg, tol=300)
    if not c or not usd_reg:
        return None
    return {"c": c, "k": s0 * t0, "s0": s0, "s1": s1, "t1": t1, "t_reg": t_reg,
            "conv": usd_reg / (s0 / t0), "t_fill": f.get("fetched_at") or p.get("fetched_at")}


def entry(S, created, delay_min, guard, momentum):
    te = created + delay_min * 60
    if not S["t_fill"] or te >= S["t_fill"]:
        return None
    usd = close_at(S["c"], te)
    if not usd:
        return None                                       # nothing traded around te: dead, cannot enter
    p_sol = usd / S["conv"]
    s_e, t_e = math.sqrt(S["k"] * p_sol), math.sqrt(S["k"] / p_sol)
    if s_e > 5 * S["s0"]:
        return None                                       # implausible price (data glitch)
    if guard:
        if s_e < 40 or (te >= S["t_reg"] and s_e < 0.8 * S["s0"]):
            return None
    if momentum:
        prev = close_at(S["c"], te - 600, tol=300)
        active = sum(1 for c in S["c"] if te - 600 < c[0] <= te and c[5] > 0)
        if not prev or usd < prev or active < 5:
            return None
    return te, usd, s_e, t_e


def exit_hold(S, q):
    return amm.sell(q, S["s1"], S["t1"], FEE)


def exit_bot(S, te, usd_e, s_e, q):
    held, got, peak, done = q, 0.0, 1.0, set()
    for c in S["c"]:
        if c[0] <= te:
            continue
        if c[0] > te + MAX_HOLD * 60 or c[0] >= S["t_fill"]:
            break
        if math.sqrt(S["k"] * (c[4] / S["conv"])) > 5 * s_e:
            break                                         # implausible candle: stop trusting prices
        low, close = c[3] / usd_e, c[4] / usd_e
        mult = lambda m: (got + held * (STAKE / q) * m * (1 - FEE)) / STAKE
        if mult(low) <= 1 - SL:
            return got + held * (STAKE / q) * (1 - SL) * (1 - FEE)
        cur = mult(close)
        peak = max(peak, cur)
        if peak >= 1 + TRAIL_ON and cur <= peak * (1 - TRAIL):
            return got + held * (STAKE / q) * close * (1 - FEE)
        for i, (g, frac) in enumerate(TP):
            if i not in done and cur >= 1 + g:
                done.add(i)
                got += held * frac * (STAKE / q) * close * (1 - FEE)
                held *= 1 - frac
    return got + exit_hold(S, held)


def describe(rets):
    if len(rets) < 5:
        return f"n={len(rets):4}  (too few)"
    q = st.quantiles(rets, n=4)
    avg = sum(min(r, 10) for r in rets) / len(rets)
    return (f"n={len(rets):4}  win {sum(r > 0 for r in rets)/len(rets):4.0%}  "
            f"q {q[0]:+5.0%}/{q[1]:+5.0%}/{q[2]:+5.0%}  avg {avg:+6.1%}")


def run(rows, delays=(5, 15, 30, 60), out=print):
    pools = sorted(((p, S) for p in rows for S in [setup(p)] if S), key=lambda x: x[0]["created"])
    out(f"canonical pump.fun pools with candles + both reserve snapshots: {len(pools)}")
    if len(pools) < 40:
        out("too few pools for a meaningful test")
        return {}
    half = len(pools) // 2
    results = {}
    for name, guard, mom in (("F0 alive", False, False), ("F1 +guard", True, False), ("F2 +guard+momentum", True, True)):
        for d in delays:
            for mode in ("hold", "bot"):
                parts = {"early": [], "late": []}
                for i, (p, S) in enumerate(pools):
                    e = entry(S, p["created"], d, guard, mom)
                    if not e:
                        continue
                    te, usd, s_e, t_e = e
                    q = amm.buy(STAKE, s_e, t_e, FEE)
                    val = exit_hold(S, q) if mode == "hold" else exit_bot(S, te, usd, s_e, q)
                    parts["early" if i < half else "late"].append(val / STAKE - 1)
                results[(name, d, mode)] = parts
                allr = parts["early"] + parts["late"]
                avg = lambda x: f"{sum(min(r, 10) for r in x) / len(x):+.0%}" if x else "n/a"
                out(f"{name:20} +{d:2}min {mode:4} | all {describe(allr)} | early avg {avg(parts['early'])}"
                    f" late avg {avg(parts['late'])}")
    return results


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.data, encoding="utf-8", errors="replace")]
    run(rows)
    print("\nRead 'avg' (gains capped at +1000%) and whether early/late halves agree. A filter only helps if it\n"
          "beats F0 at the same delay in BOTH halves. All numbers are after ~0.5% fee per swap, 0.05 SOL stake.\n"
          "F2 needs 10 minutes of price history, so it can only enter from about +15 min.")


if __name__ == "__main__":
    main()
