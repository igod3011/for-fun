"""One scorer and one set of gates for every hypothesis (stdlib only).

A hypothesis hands in trades as (timestamp, net return as a fraction of the stake), costs already deducted.
Gates (agreed 13/11/2026, memebot/research/PHASE1_AUDIT.md section 4), backtest -> paper:
  * at least MIN_TRADES trades,
  * net expectancy > 0 in BOTH time halves,
  * lower bound of the confidence interval > 0 on the whole sample,
  * still > 0 without its TOP_DROP best trades (not carried by a handful of winners).
The interval is 90% for a single pre-registered rule and widens with the number of variants that were tried
(Bonferroni: level = 1 - 0.10 / variants), because the best of many tries always looks good.
"""
import random
import statistics as st

MIN_TRADES, TOP_DROP, CAP = 100, 4, 10.0      # a single trade counts for at most +1000% (same cap as entry_timing)
PASS, UNPROVEN, REJECTED, NO_DATA = "PASS", "UNPROVEN", "REJECTED", "NO_DATA"


def bootstrap_ci(x, level=0.90, n=2000, seed=0):
    """Percentile bootstrap interval of the mean. None when there are too few values."""
    if len(x) < 8:
        return None
    rng = random.Random(seed)
    k = len(x)
    means = sorted(sum(rng.choice(x) for _ in range(k)) / k for _ in range(n))
    lo = int((1 - level) / 2 * n)
    return means[lo], means[n - 1 - lo]


def max_drawdown(rets):
    eq = peak = dd = 0.0
    for r in rets:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def metrics(trades, variants=1):
    """trades: [(ts, ret)]. Returns a dict; an empty list gives {"n": 0}."""
    trades = sorted(trades)
    x = [min(r, CAP) for _, r in trades]
    n = len(x)
    if not n:
        return {"n": 0}
    wins, losses = [r for r in x if r > 0], [r for r in x if r <= 0]
    half = n // 2
    mean = lambda v: sum(v) / len(v) if v else 0.0
    level = 1 - 0.10 / max(1, variants)
    days = max((trades[-1][0] - trades[0][0]) / 86400, 1.0)
    return {"n": n, "mean": mean(x), "median": st.median(x), "win": len(wins) / n,
            "profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else float("inf"),
            "half1": mean(x[:half]), "half2": mean(x[half:]), "ci": bootstrap_ci(x, level), "ci_level": level,
            "ex_top": mean(sorted(x)[:-TOP_DROP]) if n > TOP_DROP else None,
            "recent": mean(x[-max(1, n // 5):]),                 # newest 20% of the trades: is the edge fading?
            "max_dd": max_drawdown(x), "worst": min(x), "days": days, "per_year": n / days * 365}


def verdict(m):
    """(status, reason) from the gates above."""
    if not m.get("n"):
        return NO_DATA, "no trades"
    ci = m["ci"]
    if ci is None or m["n"] < 30:
        return NO_DATA, f"only {m['n']} trades"
    if ci[1] < 0:
        return REJECTED, "the whole confidence interval is below 0"
    fails = []
    if m["n"] < MIN_TRADES:
        fails.append(f"{m['n']} trades < {MIN_TRADES}")
    if ci[0] <= 0:
        fails.append("interval contains 0")
    if m["half1"] <= 0 or m["half2"] <= 0:
        fails.append("not positive in both halves")
    if m["ex_top"] is not None and m["ex_top"] <= 0:
        fails.append(f"negative without its {TOP_DROP} best trades")
    return (PASS, "all gates passed") if not fails else (UNPROVEN, "; ".join(fails))


def monte_carlo(rets, stake_usd, per_year, capital=100.0, max_loss=50.0, runs=2000, seed=0):
    """Resample one year of trades (with replacement, fixed stake). Returns the chance that the account is ever
    down max_loss from its start, and the 5% / 50% / 95% year-end P&L in USD. Assumes trades are independent,
    which understates the risk of strategies whose losses cluster (say so in the report)."""
    if len(rets) < 8:
        return None
    rng = random.Random(seed)
    k = max(1, min(int(round(per_year)), 5000))
    ruined, finals = 0, []
    for _ in range(runs):
        eq, low = 0.0, 0.0
        for _ in range(k):
            eq += stake_usd * min(rng.choice(rets), CAP)
            low = min(low, eq)
        ruined += low <= -max_loss
        finals.append(eq)
    finals.sort()
    return {"p_ruin": ruined / runs, "p5": finals[int(0.05 * runs)], "p50": finals[runs // 2],
            "p95": finals[int(0.95 * runs) - 1], "trades": k, "capital": capital, "max_loss": max_loss}


def rank_key(m, status, stake_usd):
    """Order of the ranking: passed first, then by the LOWER bound of the yearly net P&L in USD (not by the mean:
    a wide interval is not a good strategy)."""
    order = {PASS: 0, UNPROVEN: 1, NO_DATA: 2, REJECTED: 3}[status]
    lo = m["ci"][0] * stake_usd * m["per_year"] if m.get("ci") else float("-inf")
    return order, -lo
