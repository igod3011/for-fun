"""Step 2: do "smart" wallets exist, and do they STAY smart?

Uses the collector's Helius snapshots: top-10 holders (pool excluded) at registration, and the REALIZABLE
outcome of each pool (what the pool would really pay at fill, see report.realizable_return).
  1. Sort tradable canonical pump.fun pools by creation time; first --train-frac = discovery, rest = test.
  2. Discovery: score every wallet that was an early top-10 holder: smoothed win rate over the pools it was in.
  3. Test (out of sample, later in time): do pools where a selected wallet was an early holder do better
     than pools without one? PASS needs >= 20 such pools, a higher MEAN return AND a higher win rate, and the
     90% bootstrap CI of the mean difference above 0 (until 11/2026 a +5-point win rate on 20 pools was enough).
  4. Writes smart_wallets.json (selected on ALL data) for the bot's follow mode, with the test verdict inside;
     the bot refuses a FAIL list.
Wallet-farm pools (the bot's own filter, strategy.farm_reasons) are left out: they lose anyway, so any wallet seen
only in normal pools would look "smart" for that reason alone. Pass --with-farms to see the difference.
Limit: "was a top-10 holder ~5 min after creation" is not "bought early and sold well". A PASS here is a reason
to paper-trade follow mode, not proof that copying those wallets pays.

  python -m memebot.ml.wallet_scores --data cohort.jsonl
"""
import argparse
import json
import statistics as st
import sys
from collections import defaultdict

from .. import store
from ..bot.amm import row_virt
from ..bot.config import BotConfig
from ..bot.strategy import farm_reasons
from ..report import realizable_return
from .rc_rules import diff_ci, mean


def tradable(p, min_sol=20.0, k_min=1.0e10, k_max=2.6e10):
    h = p.get("helius_reg") or {}
    sol, tok = h.get("pool_sol"), h.get("pool_tokens")
    return (p.get("mint", "").endswith("pump") and sol and tok and sol >= min_sol
            and k_min <= sol * tok <= k_max and h.get("top_holders") and p.get("helius_fill"))


def verdict(hit, miss, min_hit=20):
    """(passed, text). hit/miss: test-pool returns with / without a selected wallet among the early holders."""
    if len(hit) < min_hit or len(miss) < min_hit:
        return False, f"FAIL: too few test pools with a selected wallet ({len(hit)}; need {min_hit})"
    win = lambda x: sum(v > 0 for v in x) / len(x)
    lo, hi = diff_ci(hit, miss)
    if mean(hit) > mean(miss) and win(hit) > win(miss) and lo > 0:
        return True, f"PASS: selected wallets kept an edge out of sample (mean diff 90% CI {lo:+.0%}..{hi:+.0%})"
    return False, f"FAIL: no reliable out-of-sample edge (mean diff 90% CI {lo:+.0%}..{hi:+.0%})"


def score_wallets(pools, min_pools=3, prior=5, max_share=0.10):
    """pools: list of (holders, ret). Wallets holding > max_share of supply are skipped (dev/bundle wallets)."""
    base = sum(r > 0 for _, r in pools) / len(pools) if pools else 0
    stats = defaultdict(lambda: [0, 0, []])
    for holders, r in pools:
        for owner, share in holders:
            if share > max_share:
                continue
            s = stats[owner]
            s[0] += 1
            s[1] += r > 0
            s[2].append(r)
    scored = []
    for w, (n, wins, rets) in stats.items():
        if n >= min_pools:
            smoothed = (wins + prior * base) / (n + prior)
            scored.append((smoothed, n, wins, st.median(rets), w))
    scored.sort(reverse=True)
    return base, scored


def evaluate(test, selected):
    hit = [r for h, r in test if any(o in selected for o, _ in h)]
    miss = [r for h, r in test if not any(o in selected for o, _ in h)]

    def desc(x):
        if not x:
            return "n=0"
        avg = sum(min(v, 10) for v in x) / len(x)
        return f"n={len(x)} win {sum(v > 0 for v in x)/len(x):.0%}, avg {avg:+.0%}"
    return hit, miss, desc(hit), desc(miss)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--train-frac", type=float, default=0.6)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", default="smart_wallets.json")
    ap.add_argument("--with-farms", action="store_true", help="keep wallet-farm pools (not what the bot trades)")
    a = ap.parse_args()
    rows = store.load(a.data, candles=False, filled_only=True)
    pools = sorted((p for p in rows if tradable(p)), key=lambda p: p["created"])
    if not a.with_farms:
        cfg, n = BotConfig(), len(pools)
        pools = [p for p in pools if not farm_reasons(p["helius_reg"], cfg)]
        print(f"wallet-farm pools left out: {n - len(pools)} of {n}")
    data = [(p["helius_reg"]["top_holders"], r) for p in pools
            for r in [realizable_return(p, virt=row_virt(p))] if r is not None]
    print(f"tradable canonical pools with holder addresses + outcome: {len(data)}")
    if len(data) < 100:
        print("too few pools yet (need a few days of data collected AFTER the address update)")
        return
    cut = int(len(data) * a.train_frac)
    train, test = data[:cut], data[cut:]
    base, scored = score_wallets(train)
    sel = {w for *_, w in scored[:a.top]}
    print(f"discovery: {len(train)} pools, base win rate {base:.0%}, wallets in >=3 pools: {len(scored)}")
    for sm, n, wins, med, w in scored[:10]:
        print(f"   {w[:8]}..  pools {n:3}  wins {wins:3}  smoothed {sm:.0%}  median {med:+.0%}")
    hit, miss, dh, dm = evaluate(test, sel)
    print(f"TEST (later pools): with a selected wallet early: {dh} | without: {dm}")
    _, text = verdict(hit, miss)
    print(text)
    _, scored_all = score_wallets(data)
    json.dump({"verdict": text, "test_with": dh, "test_without": dm,
               "wallets": [w for *_, w in scored_all[:a.top]]}, open(a.out, "w"), indent=1)
    print(f"wrote {a.out} ({min(a.top, len(scored_all))} wallets, selected on all data)")


if __name__ == "__main__":
    main()
