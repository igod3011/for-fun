"""Which pools survive? A small model on what is known AT REGISTRATION (~5 min after the pool was created).

64% of canonical pools end with one holder cluster selling the whole supply; the few that do not are where all the
return is. This asks whether the holder snapshot can tell them apart better than the bot's two-threshold farm rule.

  * features: holder count, top-1/5/10/20 shares, pool share of supply, pool SOL, virtual-reserve-adjusted price
    level, minutes between creation and registration (all from helius_reg: no look-ahead);
  * label: survived = buying at registration and holding to fill lost less than half (most others lose ~98%);
  * split by TIME: fit on the earlier --train-frac of pools, judge on the later ones only;
  * judged twice on the test pools: ranking quality (AUC) and money: bot-rule trades (+90 min, real fee, stop filled
    at the candle close) of the model's top --keep share versus the rest, with a bootstrap CI, next to the same
    comparison for the bot's farm rule.
Logistic regression in plain Python (stdlib only). A positive result here is a reason to paper-trade the model,
not proof of an edge: the kept trades must still be above 0, and their CI is reported.

  python -m memebot.ml.select_model --data cohort.jsonl --stake 0.2 --max-h1 0.8
"""
import argparse
import json
import math
import sys

from .. import store
from ..bot import amm
from ..bot.config import BotConfig
from ..bot.strategy import farm_reasons
from . import entry_timing as et
from .rc_rules import diff_ci, mean, outcomes

FEATURES = ("log_holders", "top1", "top5", "top10", "top20", "pool_pct", "log_pool_sol", "price_level", "reg_age_min",
            "page_limit")


def features(p):
    """Feature vector from the registration snapshot, or None when holder data is missing."""
    h = p.get("helius_reg") or {}
    if h.get("holders") is None or h.get("top10_pct") is None or not h.get("pool_sol") or not h.get("pool_tokens"):
        return None
    v = amm.row_virt(p)
    return [math.log1p(h["holders"]), h.get("top1_pct") or 0.0, h.get("top5_pct") or 0.0, h["top10_pct"],
            h.get("top20_pct") or 0.0, h.get("pool_pct") or 0.0, math.log(h["pool_sol"]),
            math.log(amm.price(h["pool_sol"], h["pool_tokens"], v) * 1e9),       # market cap in SOL, log
            (p.get("registered_at", 0) - p.get("created", 0)) / 60.0,
            1.0 if (h.get("accounts_fetched") or 0) >= 2000 else 0.0]


def fit(X, y, epochs=400, lr=0.3, l2=1e-3):
    """Standardise, then batch gradient descent on the logistic loss. Returns a predict(x) -> probability."""
    n, d = len(X), len(X[0])
    mu = [sum(r[j] for r in X) / n for j in range(d)]
    sd = [math.sqrt(sum((r[j] - mu[j]) ** 2 for r in X) / n) or 1.0 for j in range(d)]
    Z = [[(r[j] - mu[j]) / sd[j] for j in range(d)] for r in X]
    w, b = [0.0] * d, 0.0
    for _ in range(epochs):
        gw, gb = [0.0] * d, 0.0
        for z, t in zip(Z, y):
            e = 1 / (1 + math.exp(-max(-30, min(30, b + sum(wi * zi for wi, zi in zip(w, z)))))) - t
            gb += e
            for j in range(d):
                gw[j] += e * z[j]
        b -= lr * gb / n
        w = [wi - lr * (g / n + l2 * wi) for wi, g in zip(w, gw)]

    def predict(x):
        s = b + sum(wi * (xi - m) / s_ for wi, xi, m, s_ in zip(w, x, mu, sd))
        return 1 / (1 + math.exp(-max(-30, min(30, s))))
    predict.weights = dict(zip(FEATURES, w))
    return predict


def auc(scores, labels):
    """Probability that a random positive is ranked above a random negative (ties count half)."""
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return None
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        rank_sum += sum(l for _, l in pairs[i:j]) * (i + j + 1) / 2          # average rank of the tie group
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def compare(name, kept, dropped, out):
    """kept / dropped: bot-trade returns. Prints the comparison and returns (mean kept, CI of kept, CI of diff)."""
    if len(kept) < 10 or len(dropped) < 10:
        out(f"  {name:28} kept n={len(kept)} / dropped n={len(dropped)}: too few trades")
        return None
    ci_k, ci_d = et.bootstrap_ci(kept), diff_ci(kept, dropped)
    out(f"  {name:28} kept n={len(kept):3} avg {mean(kept):+6.1%} (90% CI {ci_k[0]:+.1%}..{ci_k[1]:+.1%}) | "
        f"dropped n={len(dropped):3} avg {mean(dropped):+6.1%} | kept-dropped 90% CI {ci_d[0]:+.0%}..{ci_d[1]:+.0%}")
    return mean(kept), ci_k, ci_d


def run(rows, train_frac=0.6, keep=0.33, max_h1=None, out=print):
    pools = sorted(((p, S, x) for p in rows for S in [et.setup(p)] if S for x in [features(p)] if x),
                   key=lambda t: t[0]["created"])
    out(f"canonical pools with holder data and an outcome: {len(pools)}")
    if len(pools) < 200:
        out("too few pools to fit and test a model")
        return None
    data = [(x, p) + outcomes(p, S, max_h1) for p, S, x in pools]           # (features, row, hold, bot)
    cut = int(len(data) * train_frac)
    train, test = data[:cut], data[cut:]
    label = lambda d: 1 if d[2] > -0.5 else 0
    model = fit([d[0] for d in train], [label(d) for d in train])
    out(f"train {len(train)} pools ({sum(label(d) for d in train) / len(train):.0%} survived), "
        f"test {len(test)} pools ({sum(label(d) for d in test) / len(test):.0%} survived)")
    out("weights (standardised): " + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(model.weights.items(), key=lambda kv: -abs(kv[1]))))
    s_test = [model(d[0]) for d in test]
    a = auc(s_test, [label(d) for d in test])
    cfg = BotConfig()
    farm = [0.0 if farm_reasons(d[1]["helius_reg"], cfg) else 1.0 for d in test]
    out(f"TEST ranking: model AUC {a:.3f} | farm rule AUC {auc(farm, [label(d) for d in test]):.3f}   (0.5 = no information)")
    thr = sorted(model(d[0]) for d in train)[int(len(train) * (1 - keep))]   # threshold chosen on TRAIN only
    out(f"TEST money: bot-rule trades at +{90} min; model keeps scores >= {thr:.3f} (top {keep:.0%} of train)")
    bots = [(s, f, d[3]) for s, f, d in zip(s_test, farm, test) if d[3] is not None]
    res = {"auc": a, "n_test": len(test),
           "all": mean([b for _, _, b in bots]) if bots else None,
           "model": compare("model top scores", [b for s, _, b in bots if s >= thr], [b for s, _, b in bots if s < thr], out),
           "farm": compare("farm rule (bot today)", [b for _, f, b in bots if f], [b for _, f, b in bots if not f], out),
           "both": compare("farm rule AND model", [b for s, f, b in bots if f and s >= thr],
                           [b for s, f, b in bots if not (f and s >= thr)], out)}
    if bots:
        out(f"  {'no selection':28} all  n={len(bots):3} avg {res['all']:+6.1%}")
    return res


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="cohort.jsonl")
    ap.add_argument("--train-frac", type=float, default=0.6)
    ap.add_argument("--keep", type=float, default=0.33, help="share of pools the model keeps (threshold set on train)")
    ap.add_argument("--tx-fee", type=float, default=0.0003)
    ap.add_argument("--stake", type=float, default=0.2)
    ap.add_argument("--max-h1", type=float, default=0.8)
    ap.add_argument("--json", help="also write the result here")
    a = ap.parse_args()
    et.TX_FEE, et.STAKE = a.tx_fee, a.stake
    res = run(store.load(a.data, filled_only=True), a.train_frac, a.keep, a.max_h1)
    if res and a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1)
    print("\nRead the 'kept' average and ITS interval: selection only matters if the kept trades are above 0.\n"
          "'kept-dropped' above 0 means the selection separates good from bad, not that it makes money.")


if __name__ == "__main__":
    main()
