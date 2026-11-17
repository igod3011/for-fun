"""Pure decision functions (no I/O) so they can be unit-tested and replayed on recorded data."""
from dataclasses import dataclass, field, fields

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
    realized_sol: float = 0.0
    entry_pool_tok: float = 0.0
    entry_price_usd: float = 0.0
    entry_mcap: float = 0.0
    virt_sol: float = None             # the pool's virtual reserve (read on-chain); None = cfg.virtual_quote_sol

    @classmethod
    def from_state(cls, d):
        """Tolerates fields written by older versions (e.g. `chased`)."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def farm_reasons(h, cfg):
    """Wallet-farm signs in a holder snapshot (Helius): thousands of holders minutes after creation, or a top-10
    share too flat to be organic. 11/2026: such pools ended with one transaction selling the whole supply 9 times
    out of 10 (ml/rc_rules.py: kept beat flagged in both time halves)."""
    bad = []
    holders, t10 = h.get("holders"), h.get("top10_pct")
    if holders is not None and cfg.max_holders_reg is not None and holders >= cfg.max_holders_reg:
        bad.append(f"wallet farm: {holders} holders")
    if t10 is not None and cfg.min_top10 is not None and t10 < cfg.min_top10:
        bad.append(f"wallet farm: top10 only {t10:.0%}")
    return bad


def control_reasons(h, cfg):
    """Pools nobody outside can win in: not created by a pump.fun migration (no virtual reserve on-chain: the
    creator holds the LP and pulls it; a scripted family did so at ~30 min in 126 of 127 pools), or one wallet holding
    most of the supply."""
    bad = []
    if h.get("virt_sol") == 0:
        bad.append("not a pump.fun migration (no virtual reserve: LP can be pulled)")
    t1 = h.get("top1_pct")
    if t1 is not None and cfg.max_top1 is not None and t1 >= cfg.max_top1:
        bad.append(f"one holder controls {t1:.0%} of supply")
    return bad


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
    if h.get("top10_pct") is None:
        bad.append("no holder data")
    bad += farm_reasons(h, cfg)
    bad += control_reasons(h, cfg)
    age = (c.get("registered_at", 0) - c.get("created", 0)) / 60
    if age > cfg.max_age_min:
        bad.append(f"too old at registration ({age:.0f} min)")
    return (not bad), bad


def pos_virt(pos, cfg):
    return cfg.virtual_quote_sol if pos.virt_sol is None else pos.virt_sol


def exit_decision(pos, pool_sol, pool_tok, now, cfg):
    """Returns (fraction_to_sell, reason) or (0, None). Value = SOL the pool would REALLY pay now."""
    if pool_tok <= 0 or pos.tokens <= 0:
        return 1.0, "pool empty"
    value = amm.sell(pos.tokens, pool_sol, pool_tok, cfg.fee, pos_virt(pos, cfg))
    mult = (value + pos.realized_sol) / pos.cost_sol
    pos.peak_mult = max(pos.peak_mult, mult)
    pos.peak_pool_sol = max(pos.peak_pool_sol, pool_sol)
    # price-based stops first; in an AMM a dump also lowers pool SOL, so the drain rule below only matters for
    # liquidity pulled at a flat price. LP of pump.fun-migrated pools is burnt (cannot be pulled): what looked
    # like "liquidity removed" in our data were whole-supply dumps (see amm.py), which the stop loss sees first.
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
