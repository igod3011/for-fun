"""How good is the /watch drain alert? Measured on the collector's 10-day cohort (graduated pump.fun pools).

For every canonical pool with candles, the pool's REAL SOL is rebuilt minute by minute from the candle closes and
the pool invariant (same method as ml/entry_timing.py: s = sqrt(k * price_in_SOL) - virtual). A user is assumed to
start watching at registration (~5 min after graduation). The alert rule (watch.drain_alert) is replayed on that
series up to the fill snapshot (>=3 h later), which also gives the outcome:
  dead      fill SOL < 10% of registration SOL   (the "total loss" cases the alert should catch)
  survived  fill SOL >= 50% of registration SOL  (an alert here is a FALSE alarm)
Metrics per rule (drop, window):
  caught    share of dead pools alerted while the pool still held >= 50% of its registration SOL (time to sell)
  false     share of alerts that went to pools that survived
Thresholds are chosen on the earlier 60% of pools (time order) and reported on the later 40% with a bootstrap CI,
next to the trivial baseline "alert on every pool". KPI (Notion): caught >= 60%, false <= 20%.

  python -m memebot.pelluca.drain_eval --data cohort.jsonl
"""
import argparse
import math

from .. import store
from ..ml.entry_timing import bootstrap_ci, setup
from .watch import drain_alert

GRID = [(d, w) for d in (0.2, 0.3, 0.4, 0.5) for w in (2, 5, 10, 30)]


def series(S):
    """[(t, real pool SOL)] from registration to fill, from candle closes (implausible prices dropped)."""
    out = []
    for c in S["c"]:
        t, close = c[0], c[4]
        if t < S["t_reg"] or (S["t_fill"] and t > S["t_fill"]) or not close:
            continue
        s_eff = math.sqrt(S["k"] * close / S["conv"])
        if s_eff > 5 * (S["s0"] + S["v"]):
            continue
        out.append((t, max(0.0, s_eff - S["v"])))
    return out


def first_alert(ser, drop, window):
    """(t, sol) of the first reading on which the rule fires, or None."""
    for i in range(len(ser)):
        t = ser[i][0]
        h = [x for x in ser[max(0, i - 200):i + 1] if t - x[0] <= 3600]
        if drain_alert(h, t, drop=drop, window_min=window)[0]:
            return ser[i]
    return None


def outcome(S):
    r = S["s1"] / S["s0"] if S["s0"] else 0
    return "dead" if r < 0.1 else "survived" if r >= 0.5 else "middle"


def evaluate(items, drop, window):
    """items: [(S, series, outcome)] -> dict of counts and rates (pure, unit-tested)."""
    dead = caught = alerts = false = 0
    hits = []
    for S, ser, out in items:
        a = first_alert(ser, drop, window)
        if out == "dead":
            dead += 1
            ok = bool(a and a[1] >= 0.5 * S["s0"])
            caught += ok
            hits.append(1.0 if ok else 0.0)
        if a:
            alerts += 1
            false += out == "survived"
    return {"drop": drop, "window": window, "dead": dead, "caught": caught / dead if dead else None,
            "alerts": alerts, "false": false / alerts if alerts else None, "hits": hits}


def baseline(items):
    n = len(items)
    surv = sum(1 for _, _, o in items if o == "survived")
    return {"false": surv / n if n else None, "caught": 1.0}


def pick(results, max_false=0.2):
    ok = [r for r in results if r["false"] is not None and r["false"] <= max_false and r["caught"] is not None]
    if ok:
        return max(ok, key=lambda r: (r["caught"], -r["false"]))
    scored = [r for r in results if r["false"] is not None]
    return min(scored, key=lambda r: r["false"]) if scored else None


def load_items(path):
    items = []
    for p in store.load(path, filled_only=True):
        S = setup(p)
        if not S:
            continue
        ser = series(S)
        if len(ser) >= 3:
            items.append((p.get("registered_at") or S["t_reg"], (S, ser, outcome(S))))
    items.sort(key=lambda x: x[0])
    return [x[1] for x in items]


def fmt(r):
    c = "n/a" if r["caught"] is None else f"{r['caught']:.0%}"
    f = "n/a" if r["false"] is None else f"{r['false']:.0%}"
    return f"drop {r['drop']:.0%} / {r['window']:>2} min: caught {c} of {r['dead']} dead, {r['alerts']} alerts, false {f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--max-false", type=float, default=0.2)
    a = ap.parse_args()
    items = load_items(a.data)
    if len(items) < 20:
        raise SystemExit(f"only {len(items)} usable pools in {a.data}: need the filled cohort (cohort.jsonl + fills)")
    cut = int(len(items) * 0.6)
    train, test = items[:cut], items[cut:]
    print(f"{len(items)} pools with candles: train {len(train)}, test {len(test)}")
    b = baseline(test)
    print(f"Baseline 'alert every pool' on TEST: false {b['false']:.0%}")
    res = [evaluate(train, d, w) for d, w in GRID]
    print("\nTRAIN (choose thresholds):")
    for r in res:
        print("  " + fmt(r))
    best = pick(res, a.max_false)
    if not best:
        raise SystemExit("no rule produced alerts")
    t = evaluate(test, best["drop"], best["window"])
    ci = bootstrap_ci(t["hits"])
    print(f"\nCHOSEN on train: drop {best['drop']:.0%} within {best['window']} min")
    print("TEST: " + fmt(t))
    if ci:
        print(f"TEST caught 90% CI: {ci[0]:.0%}..{ci[1]:.0%}")
    kpi = t["caught"] is not None and t["caught"] >= 0.6 and t["false"] is not None and t["false"] <= 0.2
    print("KPI (caught >= 60%, false <= 20%):", "MET" if kpi else "NOT MET")


if __name__ == "__main__":
    main()
