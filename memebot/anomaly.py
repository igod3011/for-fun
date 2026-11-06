"""Rule-based rug-pull / manipulation detection.

Hard flags block entry outright and force an exit when seen on an open position.
Soft flags add to a score; entry is blocked once the score reaches cfg.max_score.
"""
from dataclasses import dataclass, field

HARD = {"mint_authority_active", "freeze_authority_active", "liquidity_drain", "dump", "rugged"}
WEIGHTS = {
    "top10_concentrated": 40,
    "lp_not_locked": 40,
    "wash_trading": 40,
    "sell_pressure": 30,
    "parabolic": 25,
    "low_liquidity": 100,
}


@dataclass
class Assessment:
    score: int = 0
    flags: list = field(default_factory=list)

    @property
    def hard(self):
        return any(f in HARD for f in self.flags)

    def blocked(self, cfg):
        return self.hard or self.score >= cfg.max_score


def assess(meta, candles, cfg):
    a = Assessment()
    if not candles:
        return a
    c = candles[-1]

    def add(flag):
        a.flags.append(flag)
        a.score += 100 if flag in HARD else WEIGHTS.get(flag, 0)

    if meta.rugged:
        add("rugged")
    if not meta.mint_revoked:
        add("mint_authority_active")
    if not meta.freeze_revoked:
        add("freeze_authority_active")
    if meta.top10_pct > cfg.max_top10:
        add("top10_concentrated")
    if meta.lp_locked_pct < cfg.min_lp_locked:
        add("lp_not_locked")
    if c.liquidity < cfg.min_liquidity:
        add("low_liquidity")

    recent = candles[-5:]
    if len(candles) >= 2 and c.liquidity < (1 - cfg.drain_pct) * max(x.liquidity for x in recent):
        add("liquidity_drain")

    if len(candles) >= 2:
        prev = candles[-2]
        if prev.close > 0 and c.close < (1 - cfg.dump_pct) * prev.close and c.sells > c.buys:
            add("dump")

    last3 = candles[-3:]
    txns = sum(x.buys + x.sells for x in last3)
    if txns >= 30:
        if sum(x.makers for x in last3) / txns < cfg.wash_makers_ratio:
            add("wash_trading")
        if sum(x.sells for x in last3) / txns > 0.65:
            add("sell_pressure")

    if len(candles) > 10 and candles[-10].close > 0 and c.close / candles[-10].close > cfg.max_run:
        add("parabolic")
    return a
