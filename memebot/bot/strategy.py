"""Pure decision functions (no I/O) so they can be unit-tested and replayed on recorded data."""
from dataclasses import dataclass, field

from . import amm


@dataclass
class Position:
    mint: str
    pool: str
    name: str
    tokens: float
    cost_sol: float
    opened_at: float
    entry_pool_sol: float
    peak_mult: float = 1.0
    peak_pool_sol: float = 0.0
    tp_done: list = field(default_factory=list)
    chased: bool = False
    realized_sol: float = 0.0


def entry_check(c, cfg):
    """c: a cohort row (from the collector) with a Helius registration snapshot. Returns (ok, reasons)."""
    h = c.get("helius_reg") or {}
    sol, tok = h.get("pool_sol"), h.get("pool_tokens")
    bad = []
    if not c.get("mint", "").endswith("pump"):
        bad.append("not a pump.fun mint")
    if not sol or not tok:
        bad.append("no reserve snapshot")
    else:
        if sol < cfg.min_pool_sol:
            bad.append(f"pool only {sol:.1f} SOL")
        if not (cfg.k_min <= sol * tok <= cfg.k_max):
            bad.append("non-canonical pool (k)")
    if h.get("mint_authority"):
        bad.append("mint authority active")
    if h.get("freeze_authority"):
        bad.append("freeze authority active")
    t10 = h.get("top10_pct")
    if t10 is None:
        bad.append("no holder data")
    elif t10 > cfg.max_top10:
        bad.append(f"top10 {t10:.0%}")
    age = (c.get("registered_at", 0) - c.get("created", 0)) / 60
    if age > cfg.max_age_min:
        bad.append(f"too old at registration ({age:.0f} min)")
    return (not bad), bad


def exit_decision(pos, pool_sol, pool_tok, now, cfg):
    """Returns (fraction_to_sell, reason) or (0, None). Value = SOL the pool would REALLY pay now."""
    if pool_tok <= 0 or pos.tokens <= 0:
        return 1.0, "pool empty"
    value = amm.sell(pos.tokens, pool_sol, pool_tok, cfg.fee)
    mult = (value + pos.realized_sol) / pos.cost_sol
    pos.peak_mult = max(pos.peak_mult, mult)
    pos.peak_pool_sol = max(pos.peak_pool_sol, pool_sol)
    # price-based stops first; in an AMM a dump also lowers pool SOL, so the drain rule below is meant
    # for liquidity being pulled while the price has not (yet) moved much
    if mult <= 1 - cfg.stop_loss:
        return 1.0, f"stop loss ({mult - 1:+.0%})"
    if pos.peak_mult >= 1 + cfg.trail_activate and mult <= pos.peak_mult * (1 - cfg.trail):
        return 1.0, f"trailing stop (peak {pos.peak_mult - 1:+.0%}, now {mult - 1:+.0%})"
    if pool_sol < (1 - cfg.drain_exit) * pos.peak_pool_sol:
        return 1.0, f"pool SOL drained {pool_sol:.1f}/{pos.peak_pool_sol:.1f}"
    for i, (gain, frac) in enumerate(cfg.take_profit):
        if i not in pos.tp_done and mult >= 1 + gain:
            pos.tp_done.append(i)
            return frac, f"take profit {gain:+.0%}"
    if (now - pos.opened_at) / 60 >= cfg.max_hold_min:
        return 1.0, "max hold time"
    return 0.0, None


def chase_check(pos, pool_sol, pool_tok, now, cfg):
    if not cfg.chase_enabled or pos.chased or pos.tp_done:
        return False
    mult = (amm.sell(pos.tokens, pool_sol, pool_tok, cfg.fee) + pos.realized_sol) / pos.cost_sol
    young = (now - pos.opened_at) / 60 <= cfg.chase_window_min
    deeper = pool_sol >= pos.entry_pool_sol * 1.1
    return young and deeper and mult >= 1 + cfg.chase_gain
