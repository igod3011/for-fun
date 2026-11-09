import json
import os
from dataclasses import asdict, dataclass, field


@dataclass
class BotConfig:
    mode: str = "paper"                 # only "paper" exists; real execution is not implemented on purpose
    paper_balance_sol: float = 1.0
    stake_sol: float = 0.05             # SOL per entry
    max_positions: int = 3
    max_daily_loss_sol: float = 0.2     # no new entries once today's realized loss reaches this
    fee: float = 0.005                  # per swap (pool fee + priority fee approx)

    # entry filter (placeholder until the 2-week analysis decides better rules)
    min_pool_sol: float = 40.0          # graduation pools start ~60-85 SOL; half the SOL = price down ~75%
    max_drop_since_reg: float = 0.2     # skip if pool SOL fell >20% between registration and our buy ("falling knife")
    k_min: float = 1.0e10               # canonical pump.fun graduation pool: SOL*tokens ~ 1-2.6e10
    k_max: float = 2.6e10
    max_age_min: float = 15.0           # only pools registered within this many minutes of creation
    max_top10: float = 0.5              # top-10 holders (pool excluded) share of supply

    # exits
    stop_loss: float = 0.25             # sell all at -25% (value measured by what the pool would really pay)
    take_profit: list = field(default_factory=lambda: [[0.5, 0.5], [1.0, 0.5]])  # [gain, fraction of remaining]
    trail_activate: float = 0.3
    trail: float = 0.2
    drain_exit: float = 0.25            # sell all if pool SOL drops 25% below its peak while we hold
    max_hold_min: float = 120.0

    # "mua đuổi": add once to a winner while the pool keeps getting deeper
    chase_enabled: bool = False
    chase_gain: float = 0.3
    chase_window_min: float = 10.0
    chase_stake_sol: float = 0.025

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
    cohort_path: str = "cohort.jsonl"
    log_path: str = "bot_trades.jsonl"
    state_path: str = "bot_state.json"
    series_path: str = "bot_series.jsonl"

    @classmethod
    def load(cls, path="bot_config.json"):
        cfg = cls()
        if os.path.exists(path):
            for k, v in json.load(open(path)).items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        return cfg

    def dump(self):
        return asdict(self)
