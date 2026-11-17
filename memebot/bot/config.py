import json
import os
from dataclasses import asdict, dataclass, field

from .amm import PUMP_FEE, PUMP_VIRTUAL_SOL


@dataclass
class BotConfig:
    mode: str = "paper"                 # only "paper" exists; real execution is not implemented on purpose
    paper_balance_sol: float = 1.0
    stake_sol: float = 0.2              # SOL per entry; grid: 0.2 beat 0.05 (fixed tx fee 0.3% vs 1.2% per round trip)
    max_positions: int = 3
    max_daily_loss_sol: float = 0.6     # PAPER: loose so measurement is not cut short; set tight before real money
    fee: float = PUMP_FEE               # per swap: 1.2% measured from real quotes 11/2026 (was assumed 0.5%)
    tx_fee_sol: float = 0.0003          # per transaction, fixed (priority + base fee)
    virtual_quote_sol: float = PUMP_VIRTUAL_SOL   # FALLBACK virtual reserve; the bot reads each pool's own value on-chain

    # entry filter (placeholder until the 2-week analysis decides better rules)
    min_pool_sol: float = 40.0          # graduation pools start ~60-85 SOL; half the SOL = price down ~75%
    max_drop_since_reg: float = 0.2     # skip if pool SOL fell >20% between registration and our buy ("falling knife")
    k_min: float = 1.0e10               # canonical pump.fun graduation pool: SOL*tokens ~ 1-2.6e10
    k_max: float = 2.6e10
    max_age_min: float = 15.0           # only pools registered within this many minutes of creation
    entry_delay_min: float = 90.0       # walk-forward grid (839 pools): +90 min was best on train AND positive on test
    entry_window_min: float = 30.0      # ... and no later than delay + window (otherwise "missed window")
    # wallet-farm filter on the holder snapshot at registration (11/2026, ml/rc_rules.py: kept beat flagged in both
    # time halves; bot-style trades -25% flagged vs -4% kept). The old rule `top10 > 50% -> skip` was REMOVED: it
    # rejected the better group (-4% vs -22% kept, wrong way round in both halves).
    max_holders_reg: int = 1000         # this many holders ~5 min after creation is a farm, not a crowd (None disables)
    min_top10: float = 0.15             # top-10 (pool excluded) below this share = supply spread over a farm (None disables)
    # one wallet holding half the supply: either a scripted fake pool (LP pulled at ~30 min, -100%) or a whale-run
    # token with no upside (98 bot-style trades: mean -14.8%, best +16%). Among non-farm pools this is the group to
    # drop; the remaining "organic" pools are the only group not clearly negative (11/2026).
    max_top1: float = 0.5               # largest single holder (pool excluded) at registration (None disables)

    # pre-buy intelligence (RugCheck + DexScreener), checked right before buying
    use_intel: bool = True
    max_dev_pct: float = 0.03           # dev (creator) still holding > 3% of supply -> skip (never fired on 348 pools)
    block_creator_rugs: bool = True     # creator has rugged tokens before -> skip
    max_change_h1: float = 0.8          # already +80% in the last hour -> skip (None disables)

    # exits
    stop_loss: float = 0.10             # grid: tight 10-15% stops won; value = what the pool would really pay
    take_profit: list = field(default_factory=list)  # [[gain, fraction of remaining], ...]; grid: none was best
    trail_activate: float = 0.2
    trail: float = 0.1
    drain_exit: float = 0.25            # sell all if pool SOL drops 25% below its peak while we hold
    max_hold_min: float = 60.0

    # follow "smart" wallets (step 3). OFF until memebot.ml.wallet_scores says PASS on real data
    follow_enabled: bool = False
    wallets_path: str = "smart_wallets.json"
    follow_poll_s: float = 60.0
    follow_min_wallets: int = 1         # how many watched wallets must buy the same mint ...
    follow_window_min: float = 10.0     # ... within this many minutes
    follow_max_wallets: int = 20

    # loop timing / files
    poll_positions_s: float = 15.0
    discover_every_s: float = 60.0
    collector_stale_min: float = 15.0   # no new pool registered for this long -> the collector is down: say so on Telegram
    cohort_path: str = "cohort.jsonl"
    log_path: str = "bot_trades.jsonl"
    state_path: str = "bot_state.json"
    series_path: str = "bot_series.jsonl"

    @classmethod
    def load(cls, path="bot_config.json"):
        cfg = cls()
        if os.path.exists(path):
            with open(path) as f:
                for k, v in json.load(f).items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
        return cfg

    def dump(self):
        return asdict(self)
