"""Do the RugCheck rules (dev %, creator rug history, insiders, risk flags) and the holder rules (holder count,
top-10 share) separate good pools from bad ones?

Uses only what was known AT REGISTRATION (no look-ahead): rc_reg (RugCheck) and helius_reg (holders), on canonical
pump.fun graduation pools.
For every rule, pools are split into FLAGGED (the rule would skip them) and KEPT, and compared on two outcomes:
  * hold: buy at the registration reserves, sell into the REAL pool at fill time (every pool -> most data);
  * bot:  the bot's entry (+90 min, guard, --max-h1) and exit rules, stop filled per entry_timing.STOP_FILL
          (few trades -> wide intervals).
A rule is worth keeping only if KEPT beats FLAGGED in BOTH time halves and the 90% CI of the difference is above 0.
Many rules are tested at once: one "KEEP" among a dozen exploratory rules can still be luck.

  python -m memebot.ml.rc_rules --data cohort.jsonl --stake 0.2 --max-h1 0.8
"""
import argparse
import random
import sys

from .. import store
from . import entry_timing as et

BOT_RULES = {"sl": 0.10, "tp": [], "trail_on": 0.2, "trail": 0.1, "max_hold": 60}
BOT_DELAY = 90
MIN_GROUP = 10                 # per half and per group; below this a verdict is "too few"

# name -> predicate on rc_reg: True = the rule would SKIP the pool. The first three are what the bot enforces.
RULES = {
    "bot: dev holds >3%": lambda rc: (rc.get("dev_pct") or 0) > 0.03,
    "bot: creator rugged before": lambda rc: bool(rc.get("creator_rugs")),
    "bot: insiders >10% (top holders)": lambda rc: (rc.get("insider_pct") or 0) > 0.10,
    "bot: any of the three": lambda rc: any(RULES[k](rc) for k in list(RULES)[:3]),
    "x: insider graph detected >0": lambda rc: (rc.get("insiders_detected") or 0) > 0,
    "x: creator launched before": lambda rc: (rc.get("creator_launches") or 0) > 0,
    "x: creator unknown": lambda rc: not rc.get("creator"),
}
RISK_FLAGS = ("High holder correlation", "Single holder ownership", "Large Amount of LP Unlocked",
              "Top 10 holders high ownership", "High ownership", "High market cap per holder", "Low Liquidity",
              "High holder concentration", "Copycat token")
for _f in RISK_FLAGS:
    RULES[f"x: risk '{_f}'"] = lambda rc, f=_f: f in (rc.get("risks") or [])
RULES["x: any risk flag"] = lambda rc: bool(rc.get("risks"))

# Rules on the Helius holder snapshot at registration (helius_reg), ~5 min after the pool was created. A real
# graduation has a few hundred holders by then; thousands of holders with a flat distribution is a wallet farm
# that later sells the whole supply in one transaction (11/2026: 64% of canonical pools ended that way).
HOLDER_RULES = {
    "bot: top10 >50%": lambda h: (h.get("top10_pct") or 0) > 0.5,
    "x: holders >=500": lambda h: (h.get("holders") or 0) >= 500,
    "x: holders >=1000": lambda h: (h.get("holders") or 0) >= 1000,
    "x: holders >=1500": lambda h: (h.get("holders") or 0) >= 1500,
    "x: top10 <15%": lambda h: (h.get("top10_pct") or 0) < 0.15,
    "x: holders >=1000 or top10 <15%": lambda h: (h.get("holders") or 0) >= 1000 or (h.get("top10_pct") or 0) < 0.15,
}


def outcomes(p, S, max_h1=None):
    """(hold return from registration, bot-rule return or None)."""
    q = et.buy_at(S["s0"], S["t0"], S["v"])
    hold = (et.exit_hold(S, q) - et.TX_FEE) / et.STAKE - 1
    bot = None
    e = et.entry(S, p["created"], BOT_DELAY, guard=True, momentum=False, max_h1=max_h1)
    if e:
        te, usd, s_e, t_e = e
        q = et.buy_at(s_e, t_e, S["v"])
        bot = (et.exit_bot(S, te, usd, s_e, q, BOT_RULES) - et.TX_FEE) / et.STAKE - 1
    return hold, bot


def mean(x):
    return sum(min(v, 10) for v in x) / len(x)


def diff_ci(kept, flagged, n=2000, level=0.9, seed=0):
    """Percentile bootstrap CI of mean(kept) - mean(flagged), gains capped at +1000%."""
    rng = random.Random(seed)
    a, b = [min(v, 10) for v in kept], [min(v, 10) for v in flagged]
    d = sorted(sum(rng.choice(a) for _ in a) / len(a) - sum(rng.choice(b) for _ in b) / len(b) for _ in range(n))
    return d[int((1 - level) / 2 * n)], d[int((1 + level) / 2 * n) - 1]


def judge(items):
    """items: [(is_early, flagged, ret)]. -> dict with group stats and a verdict."""
    g = {(h, f): [r for e, fl, r in items if e == h and fl == f] for h in (True, False) for f in (True, False)}
    kept, flagged = g[(True, False)] + g[(False, False)], g[(True, True)] + g[(False, True)]
    res = {"n_kept": len(kept), "n_flagged": len(flagged), "kept": mean(kept) if kept else None,
           "flagged": mean(flagged) if flagged else None, "ci": None, "halves": []}
    if min(len(x) for x in g.values()) < MIN_GROUP:
        res["verdict"] = "too few"
        return res
    res["halves"] = [mean(g[(h, False)]) - mean(g[(h, True)]) for h in (True, False)]
    res["ci"] = diff_ci(kept, flagged)
    if all(d > 0 for d in res["halves"]) and res["ci"][0] > 0:
        res["verdict"] = "KEEP"
    elif all(d > 0 for d in res["halves"]):
        res["verdict"] = "unproven"
    else:
        res["verdict"] = "no"
    return res


def section(title, pools, feature, rules, max_h1, out, results):
    """pools: [(row, setup)] sorted by creation time; feature(row) -> what the rules' predicates look at."""
    out(f"{title}: {len(pools)}")
    if len(pools) < 4 * MIN_GROUP:
        out("too few pools for any comparison")
        return
    half = len(pools) // 2
    data = [(i < half, feature(p)) + outcomes(p, S, max_h1) for i, (p, S) in enumerate(pools)]
    holds, bots = [d[2] for d in data], [d[3] for d in data if d[3] is not None]
    out(f"baseline hold from registration: n={len(holds)} avg {mean(holds):+.1%}, lost >90%: {sum(r < -0.9 for r in holds) / len(holds):.0%}")
    out(f"baseline bot rules @+{BOT_DELAY}min:      n={len(bots)}" + (f" avg {mean(bots):+.1%}" if bots else ""))
    pct = lambda v: "   n/a" if v is None else f"{v:+6.0%}"
    for mode, idx in (("hold", 2), ("bot", 3)):
        out(f"\n[{mode}]  rule                                   flagged        kept     kept-flagged: early/late, 90% CI   verdict")
        for name, pred in rules.items():
            r = judge([(d[0], bool(pred(d[1])), d[idx]) for d in data if d[idx] is not None])
            results[(mode, name)] = r
            extra = ""
            if r["halves"]:
                extra = f"{r['halves'][0]:+5.0%}/{r['halves'][1]:+5.0%}, {r['ci'][0]:+.0%}..{r['ci'][1]:+.0%}"
            out(f"  {name:38} n={r['n_flagged']:4} {pct(r['flagged'])} | n={r['n_kept']:4} {pct(r['kept'])} | {extra:28} {r['verdict']}")


def run(rows, max_h1=None, out=print):
    pools = sorted(((p, S) for p in rows for S in [et.setup(p)] if S), key=lambda x: x[0]["created"])
    results = {}
    section("canonical pools with RugCheck-at-registration, candles and both reserve snapshots",
            [(p, S) for p, S in pools if (p.get("rc_reg") or {}).get("risks") is not None],
            lambda p: p["rc_reg"], RULES, max_h1, out, results)
    out("")
    section("canonical pools with holder data at registration (Helius), candles and both reserve snapshots",
            [(p, S) for p, S in pools if p["helius_reg"].get("holders") is not None],
            lambda p: p["helius_reg"], HOLDER_RULES, max_h1, out, results)
    return results


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--tx-fee", type=float, default=0.0003)
    ap.add_argument("--stake", type=float, default=0.2)
    ap.add_argument("--max-h1", type=float, default=0.8)
    ap.add_argument("--stop-fill", choices=("close", "low", "stop"), default="close")
    a = ap.parse_args()
    et.TX_FEE, et.STAKE, et.STOP_FILL = a.tx_fee, a.stake, a.stop_fill
    run(store.load(a.data, filled_only=True), a.max_h1)       # only filled pools have an outcome
    print(f"\nKEEP = kept pools beat flagged ones in both time halves AND the 90% CI of the difference is above 0.\n"
          f"unproven = right direction in both halves, CI contains 0. too few = a group has <{MIN_GROUP} pools in a half.\n"
          f"'x:' rules are exploratory: with this many rules, expect about one false KEEP by luck.")


if __name__ == "__main__":
    main()
