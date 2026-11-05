import argparse
import statistics
from dataclasses import replace

from .config import Config
from .engine import Engine
from .strategy import STRATEGIES
from .synthetic import generate_universe


def run(tokens, cfg, strategy_name, use_filter=True):
    eng = Engine(cfg, STRATEGIES[strategy_name], use_filter)
    events = sorted(
        ((c.ts, t.meta.id, i) for _, t in tokens for i, c in enumerate(t.candles)),
    )
    by_id = {t.meta.id: t for _, t in tokens}
    for _, tid, i in events:
        tok = by_id[tid]
        eng.on_candle(tok.meta, tok.candles[: i + 1])
    # close leftovers at last mark
    for tid in list(eng.broker.positions):
        c = by_id[tid].candles[-1]
        eng.broker.sell(tid, c.close, c.liquidity, c.ts, "end")
    return eng


def summarize(eng, cfg):
    tr = eng.broker.trades
    eq = [e for _, e in eng.curve] or [cfg.capital]
    peak, mdd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak)
    wins = [t for t in tr if t["pnl"] > 0]
    reasons = {}
    for t in tr:
        for r in t["reason"].split("+"):
            reasons[r] = reasons.get(r, 0) + 1
    return {
        "trades": len(tr),
        "win_rate": len(wins) / len(tr) if tr else 0,
        "avg_ret": statistics.mean(t["ret"] for t in tr) if tr else 0,
        "worst": min((t["ret"] for t in tr), default=0),
        "final_equity": eng.broker.cash,
        "total_ret": eng.broker.cash / cfg.capital - 1,
        "max_dd": mdd,
        "exit_reasons": reasons,
        "entries_blocked": eng.skipped,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="breakout_volume")
    a = ap.parse_args()
    cfg = Config()
    tokens = generate_universe(a.n, a.seed)
    for label, flt in (("WITH anomaly filter", True), ("WITHOUT anomaly filter", False)):
        s = summarize(run(tokens, cfg, a.strategy, flt), cfg)
        print(f"\n== {a.strategy} | {label}")
        for k, v in s.items():
            print(f"  {k:15s} {v:.3f}" if isinstance(v, float) else f"  {k:15s} {v}")


if __name__ == "__main__":
    main()
